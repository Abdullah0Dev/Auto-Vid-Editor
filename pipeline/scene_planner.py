"""Step 2 — Scene segmentation with global context."""
import json
import re

from config import MODEL_ORCHESTRATOR, PLAN_DIR
from models.types import Scene, ImportantMoment
from pipeline.context_extractor import format_context_for_prompt
from utils.llm_client import chat
from utils.logger import log


CHUNK_SECONDS = 60
MIN_SCENE_DURATION = 8.0
MAX_SCENE_DURATION = 15.0

PLACEHOLDER_STRINGS = [
    "وصف بحث بالعربية",
    "English translation of the search query",
    "النص الأصلي هنا",
    "العبارة المهمة",
]

SYSTEM_PROMPT = """You are a scene planner for an Arabic historical documentary.
You receive GLOBAL CONTEXT and a transcript CHUNK with timestamps.
You split the chunk into visually-coherent scenes and return JSON only.

OUTPUT SCHEMA (one object, no markdown fences):
{
  "scenes": [
    {
      "id": <int, starting at 1 within this chunk>,
      "start": <float seconds>,
      "end": <float seconds>,
      "text": "<verbatim transcript text for this scene>",
      "visual_type": "image|graphic",
      "arabic_query": "<3-8 Arabic words describing a VISIBLE thing>",
      "english_query": "<3-8 English words, Wikimedia-Commons-friendly>",
      "audio_note": "<e.g. 'low ambient music', 'silence', 'oud underscore'>",
      "is_important": <true|false>,
      "ken_burns": "zoom_in|zoom_out|pan_left|pan_right",
      "content_type": "quran|hadith|poetry|dua|narration"
    }
  ]
}

SCENE RULES
1. Group 2-4 consecutive transcript lines into ONE scene that makes sense to be with each other.
2. Each scene must be 5-15 seconds long.
3. `text` MUST be copied verbatim from the transcript — never paraphrase.
4. `start`/`end` MUST fall inside the chunk window given by the user.
   Do NOT restart numbering at 0. Keep ids continuous.
5. `is_important` = true ONLY for: دعاء، رثاء، تعجب، أو نقطة تحول درامية.
6. QURAN/HADITH/POETRY/DUA or someone talking important stuff MAKE SURE IT'S IN ONE SCENE

CONTENT_TYPE — choose exactly ONE per scene. Used to trigger audio FX downstream:
  • "quran"     → triggers Quran recitation layer.
                  Detect: "قال الله", "قال تعالى", "بسم الله", or Quranic cadence.
  • "hadith"    → triggers hadith narration layer.
                  Detect: "قال النبي", "قال رسول الله", "عن <صحابي>", "روى البخاري/مسلم".
  • "poetry"    → triggers poetic recitation.
                  Detect: two hemistichs, matching rhyme (بيت شعر), "قال الشاعر".
  • "dua"       → triggers soft supplication bed.
                  Detect: starts with "اللهم", "ربنا", "سبحان", "لا حول ولا قوة".
  • "narration" → everything else (author's voice, explanation, story). DEFAULT.
VISUAL TYPE

Use "graphic" when the scene benefits from a self-contained Remotion graphic.

Use "graphic" for:
- Quranic passages
- Hadith
- Classical poetry
- Direct scholarly quotes
- Historical figure introductions
- Named battles / conquests
- Geography / journeys / routes
- Clear numerical statistics
- Dua / short Arabic emphasis
- Strong informational beats where typography or structured graphics
  communicate better than a photograph

Use "image" for:
- Generic narration
- Landscape / atmosphere
- Architecture / artifact shots
- Descriptive scenes
- Mood
- Generic historical context
- Scenes where the visual subject is primarily a photograph/painting

IMPORTANT:
Do not make every Arabic sentence a graphic.
Graphics should be intentional visual beats.

CONTENT_TYPE:

quran:
  Quran quotation / ayah content

hadith:
  Hadith / Prophet ﷺ narration

poetry:
  Classical poetry / بيت شعر

dua:
  Supplication / devotional phrase

narration:
  Everything else

The transcript text MUST remain verbatim.
KEN_BURNS — vary across consecutive scenes. Never repeat the same value 3× in a row.

OUTPUT: JSON only. No explanations. No ``` fences.
"""

USER_PROMPT = """GLOBAL CONTEXT:
{context}

CHUNK TIMING: this chunk covers {chunk_start:.1f}s to {chunk_end:.1f}s.

TRANSCRIPT:
{transcript}

Use start/end timestamps between {chunk_start:.1f} and {chunk_end:.1f}. Do not restart at 0.

Return JSON only."""


def plan(transcript_text: str, context: dict | None = None,          video_duration: float | None = None
) -> tuple[list[Scene], list[ImportantMoment]]:
    PLAN_DIR.mkdir(parents=True, exist_ok=True)

    context_str = format_context_for_prompt(context or {})

    chunks = _chunk_transcript(transcript_text, CHUNK_SECONDS)
    log.info(f"Planning {len(chunks)} chunk(s) with {MODEL_ORCHESTRATOR}...")

    all_scenes: list[Scene] = []
    all_moments: list[ImportantMoment] = []

    for i, (chunk_text, c_start, c_end) in enumerate(chunks, start=1):
        log.info(f"Chunk {i}/{len(chunks)}: {len(chunk_text)} chars "
                 f"[{c_start:.1f}s – {c_end:.1f}s]")

        result = chat(
            MODEL_ORCHESTRATOR,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT.format(
                    context=context_str,
                    chunk_start=c_start,
                    chunk_end=c_end,
                    transcript=chunk_text,
                )},
            ],
            label=f"Scene Planner [{i}/{len(chunks)}]",
        )

        raw = result.get("message", {}).get("content", "")
        (PLAN_DIR / f"raw_chunk_{i:02d}.txt").write_text(raw or "<EMPTY>", encoding="utf-8")

        if not raw.strip():
            log.warn(f"Chunk {i}: empty response — skipping")
            continue

        parsed = _try_parse_json(raw)
        if parsed is None:
            log.warn(f"Chunk {i}: invalid JSON — skipping")
            continue

        scenes = _build_scenes(parsed)
        moments = _build_moments(parsed, scenes)
        all_scenes.extend(scenes)
        all_moments.extend(moments)
        log.ok(f"Chunk {i}: {len(scenes)} scenes, {len(moments)} moments")

    all_scenes.sort(key=lambda s: s.start)
    all_scenes = _sanitize_scenes(all_scenes)
    all_scenes = _merge_short_scenes(all_scenes)
    # ── NEW: enforce full coverage ────────────────
    if video_duration:
        all_scenes = _ensure_full_coverage(all_scenes, video_duration)

    for idx, s in enumerate(all_scenes, start=1):
        s.id = idx

    all_moments = [
        m for m in all_moments
        if m.start < m.end and m.text and not _is_placeholder(m.text)
    ]

    if not all_scenes:
        raise RuntimeError("Scene planning produced no scenes")

    (PLAN_DIR / "scene_plan.json").write_text(
        json.dumps(
            {"scenes": [vars(s) for s in all_scenes],
             "important_moments": [vars(m) for m in all_moments]},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    log.ok(f"Final: {len(all_scenes)} scenes, {len(all_moments)} moments")
    return all_scenes, all_moments

 

def _is_placeholder(text: str) -> bool:
    """Return True if a string is one of the schema examples."""
    if not text:
        return True
    # The literal placeholder example strings
    hard_placeholders = [
        "وصف بحث بالعربية",
        "English translation of the search query",
        "النص الأصلي هنا",
        "العبارة المهمة",
    ]
    return any(p in text for p in hard_placeholders)


def _chunk_transcript(transcript_text: str, chunk_seconds: int
                      ) -> list[tuple[str, float, float]]:
    lines = [l for l in transcript_text.split("\n") if l.strip()]
    if not lines:
        return [(transcript_text, 0.0, 0.0)]

    chunks: list[tuple[str, float, float]] = []
    current: list[str] = []
    chunk_start = None
    chunk_end = 0.0

    for line in lines:
        m = re.match(r"\[(\d+\.?\d*)–(\d+\.?\d*)\]", line)
        if not m:
            current.append(line)
            continue

        line_start = float(m.group(1))
        line_end = float(m.group(2))

        if chunk_start is None:
            chunk_start = line_start

        if line_end - chunk_start > chunk_seconds and current:
            chunks.append(("\n".join(current), chunk_start, chunk_end))
            current = []
            chunk_start = line_start

        current.append(line)
        chunk_end = line_end

    if current:
        chunks.append(("\n".join(current), chunk_start, chunk_end))

    return chunks


def _try_parse_json(text: str) -> dict | None:
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        candidate = text[first:last + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        repaired = (
            candidate
            .replace("\u060C", ",")
            .replace("\u061B", ";")
            .replace("\u201C", '"')
            .replace("\u201D", '"')
            .replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace(",}", "}")
            .replace(",]", "]")
        )
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    return None

VALID_CONTENT_TYPES = {"narration", "quran", "hadith", "poetry", "dua"}
VALID_VISUAL_TYPES = {"image", "graphic"}
VALID_CONTENT_TYPES = {
    "narration",
    "quran",
    "hadith",
    "poetry",
    "dua",
}
def _build_scenes(plan: dict) -> list[Scene]:
    scenes = []
    for i, s in enumerate(plan.get("scenes", []), start=1):
        try:
            text = str(s.get("text", "")).strip()
            if not text or _is_placeholder(text):
                continue

            arabic_q = str(s.get("arabic_query", "")).strip()
            english_q = str(s.get("english_query", "")).strip()

            if _is_placeholder(arabic_q):
                arabic_q = text
            if _is_placeholder(english_q):
                english_q = ""

            start = float(s["start"])
            end = float(s["end"])
            if end <= start:
                continue
            visual_type = (
                str(s.get("visual_type", "image"))
                .strip()
                .lower()
            )

            if visual_type not in VALID_VISUAL_TYPES:
                visual_type = "image"
            # Parse content_type safely
            content_type = str(s.get("content_type", "narration")).lower().strip()
            if content_type not in VALID_CONTENT_TYPES:
                content_type = "narration"

            scenes.append(Scene(
                id=i,
                start=start,
                end=end,
                text=text,
                visual_type=visual_type,
                arabic_query=arabic_q,
                english_query=english_q,
                audio_note=(s.get("audio_note") or "low ambient music"),
                is_important=bool(s.get("is_important", False)),
                ken_burns=s.get("ken_burns", "zoom_in"),
                content_type=content_type,
            ))
        except (KeyError, TypeError, ValueError) as e:
            log.warn(f"Skipping malformed scene: {e}")
    return scenes

def _build_moments(plan: dict, scenes: list[Scene]) -> list[ImportantMoment]:
    """
    Build important moments. Handles two model behaviors:
      1. Proper objects: [{start, end, text, effect}, ...]
      2. Plain strings: ["some phrase", ...]  (model's lazy format)
    For plain strings, we fall back to scenes marked is_important=True.
    """
    moments: list[ImportantMoment] = []

    for m in plan.get("important_moments", []):
        # Case 1: proper object
        if isinstance(m, dict):
            try:
                text = str(m.get("text", "")).strip()
                if _is_placeholder(text):
                    continue
                start = float(m["start"])
                end = float(m["end"])
                if end <= start:
                    continue
                moments.append(ImportantMoment(
                    start=start, end=end, text=text,
                    effect=m.get("effect", "echo"),
                ))
            except (KeyError, TypeError, ValueError):
                continue

        # Case 2: plain string — we ignore it here and pick up the
        # important scenes later (see below).
        elif isinstance(m, str):
            log.debug(f"Ignoring string moment: {m[:60]!r}")

    # Always augment with scenes that the model marked is_important.
    # This is more reliable than trusting important_moments output.
    for s in scenes:
        if not s.is_important:
            continue
        # Avoid duplicates (same time window)
        if any(abs(mm.start - s.start) < 0.5 for mm in moments):
            continue
        moments.append(ImportantMoment(
            start=s.start,
            end=s.end,
            text=s.text[:80],
            effect="echo",
        ))

    return moments

def _sanitize_scenes(scenes: list[Scene]) -> list[Scene]:
    out = []
    for s in scenes:
        if not s.text or _is_placeholder(s.text):
            continue
        if s.end <= s.start:
            continue
        if not s.english_query:
            # Fall back: use the first clause of Arabic query as-is.
            # Cross-lingual search is better than no query at all.
            s.english_query = s.arabic_query or s.text
            log.warn(f"Scene {s.id}: no English query — using Arabic")
        out.append(s)
    if len(out) != len(scenes):
        log.info(f"Sanitized: dropped {len(scenes) - len(out)} invalid scenes")
    return out


def _merge_short_scenes(
    scenes: list[Scene],
) -> list[Scene]:

    if not scenes:
        return scenes

    merged: list[Scene] = []

    buffer: list[Scene] = []
    buffer_duration = 0.0

    def flush() -> None:
        nonlocal buffer
        nonlocal buffer_duration

        if not buffer:
            return

        first = buffer[0]

        arabic_q = max(
            (
                s.arabic_query
                for s in buffer
                if s.arabic_query
            ),
            key=len,
            default="",
        )

        english_q = max(
            (
                s.english_query
                for s in buffer
                if s.english_query
            ),
            key=len,
            default="",
        )

        special_types = [
            s.content_type
            for s in buffer
            if s.content_type != "narration"
        ]

        content_type = (
            special_types[0]
            if special_types
            else first.content_type
        )

        merged.append(
            Scene(
                id=first.id,
                start=first.start,
                end=buffer[-1].end,
                text=" ".join(
                    s.text for s in buffer
                ),
                visual_type=first.visual_type,
                arabic_query=arabic_q,
                english_query=english_q,
                audio_note=first.audio_note,
                is_important=any(
                    s.is_important
                    for s in buffer
                ),
                ken_burns=first.ken_burns,
                content_type=content_type,
            )
        )

        buffer = []
        buffer_duration = 0.0

    for scene in scenes:

        # Never merge different visual modes.
        if (
            buffer
            and scene.visual_type
            != buffer[-1].visual_type
        ):
            flush()

        # Never merge different semantic content types
        # when either side is a special type.
        if (
            buffer
            and scene.content_type
            != buffer[-1].content_type
            and (
                scene.content_type != "narration"
                or buffer[-1].content_type != "narration"
            )
        ):
            flush()

        duration = (
            scene.end - scene.start
        )

        # Don't create scenes bigger than MAX_SCENE_DURATION.
        if (
            buffer
            and buffer_duration + duration
            > MAX_SCENE_DURATION
        ):
            flush()

        buffer.append(scene)
        buffer_duration += duration

        if buffer_duration >= MIN_SCENE_DURATION:
            flush()

    flush()

    log.info(
        f"Merged short scenes: "
        f"{len(scenes)} → {len(merged)}"
    )

    return merged
def _ensure_full_coverage(scenes: list[Scene],
                          video_duration: float) -> list[Scene]:
    """
    Snap scenes to span [0, video_duration] with no internal gaps.
    Prevents `-shortest` from truncating the final render.
    """
    if not scenes or video_duration <= 0:
        return scenes

    # Snap first scene to time 0
    if scenes[0].start > 0.1:
        log.info(f"Extending scene 1 start from {scenes[0].start:.2f}s → 0.00s")
        scenes[0].start = 0.0

    # Fill internal gaps by extending previous scene
    for i in range(len(scenes) - 1):
        gap = scenes[i + 1].start - scenes[i].end
        if gap > 0.1:
            log.warn(f"Filling {gap:.2f}s gap between scene {scenes[i].id} "
                     f"and scene {scenes[i+1].id}")
            scenes[i].end = scenes[i + 1].start

    # Extend last scene to video duration
    last = scenes[-1]
    if last.end < video_duration - 0.1:
        log.warn(f"Extending last scene end from {last.end:.2f}s → "
                 f"{video_duration:.2f}s (video duration)")
        last.end = video_duration

    total = sum(s.end - s.start for s in scenes)
    log.ok(f"Scene coverage: 0.00s → {video_duration:.2f}s "
           f"(total {total:.2f}s across {len(scenes)} scenes)")
    return scenes
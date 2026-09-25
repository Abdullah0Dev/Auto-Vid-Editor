"""Step 2 — Scene segmentation with global context."""
import json
import re

from config import MODEL_ORCHESTRATOR, PLAN_DIR
from models.types import Scene, ImportantMoment
from pipeline.context_extractor import format_context_for_prompt
from utils.ollama_client import chat
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


SYSTEM_PROMPT = """You are a film editor planning scenes for an Arabic historical documentary.

You will receive GLOBAL CONTEXT about the whole video and a CHUNK of transcript.
Segment the chunk into scenes and return valid JSON only.

JSON schema:
{
  "scenes": [
    {
      "id": 1,
      "start": 0.0,
      "end": 8.0,
      "text": "original transcript text",
      "visual_type": "image",
      "arabic_query": "بحث بالعربية (املأها بقيم حقيقية)",
      "english_query": "English image search query",
      "audio_note": "low ambient music",
      "is_important": false,
      "ken_burns": "zoom_in"
    }
  ],
  "important_moments": []
}

Strict rules:
- Return JSON only. No commentary, no markdown fences.
- ⚠️ The schema strings above are EXAMPLES. Replace them with real content.
- Group 2-4 consecutive short transcript lines into ONE scene.
- Each scene: 5-15 seconds.
- is_important = true for دعاء، رثاء، تعجب، or dramatic turning points.
- ken_burns: one of zoom_in, zoom_out, pan_left, pan_right.

For queries — remember these are IMAGE search terms:
- ❌ BAD: "Allah is the best disposer of affairs" (a prayer, not an image)
- ✅ GOOD: "Islamic prayer manuscript page"
- ❌ BAD: "Author biography, born 673"
- ✅ GOOD: "medieval Islamic scholar portrait"
- ❌ BAD: "Imam Muhammad ibn Ahmad"
- ✅ GOOD: "13th century Damascus mosque architecture"

If the scene is emotional/abstract, use MOOD queries: "candlelit mosque interior", "old Arabic manuscript on wooden table", "desert caravan at sunset".
Use the GLOBAL CONTEXT to anchor queries in the correct era, region, and entities."""


USER_PROMPT = """GLOBAL CONTEXT:
{context}

CHUNK TIMING: this chunk covers {chunk_start:.1f}s to {chunk_end:.1f}s.

TRANSCRIPT:
{transcript}

Use start/end timestamps between {chunk_start:.1f} and {chunk_end:.1f}. Do not restart at 0.

Return JSON only."""


def plan(transcript_text: str, context: dict | None = None) -> tuple[list[Scene], list[ImportantMoment]]:
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


def _build_scenes(plan: dict) -> list[Scene]:
    scenes = []
    for i, s in enumerate(plan.get("scenes", []), start=1):
        try:
            text = str(s.get("text", "")).strip()
            if not text or _is_placeholder(text):
                continue

            arabic_q = str(s.get("arabic_query", "")).strip()
            english_q = str(s.get("english_query", "")).strip()

            # Repair: if arabic_query is a placeholder, use the scene text
            if _is_placeholder(arabic_q):
                arabic_q = text

            # Repair: if english_query is a placeholder, try to salvage
            # by stripping the Arabic prefix and using just the text
            if _is_placeholder(english_q):
                english_q = ""

            # Skip scenes where the timestamps are obviously wrong
            start = float(s["start"])
            end = float(s["end"])
            if end <= start:
                continue

            scenes.append(Scene(
                id=i,
                start=start,
                end=end,
                text=text,
                visual_type=s.get("visual_type", "image"),
                arabic_query=arabic_q,
                english_query=english_q,
                audio_note=(s.get("audio_note") or "low ambient music"),
                is_important=bool(s.get("is_important", False)),
                ken_burns=s.get("ken_burns", "zoom_in"),
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


def _merge_short_scenes(scenes: list[Scene]) -> list[Scene]:
    if not scenes:
        return scenes

    merged: list[Scene] = []
    buffer: list[Scene] = []
    buffer_duration = 0.0

    def flush():
        nonlocal buffer, buffer_duration
        if not buffer:
            return
        first = buffer[0]
        # For queries, take the longest (most specific) one rather than joining
        arabic_q = max((s.arabic_query for s in buffer if s.arabic_query),
                       key=len, default="")
        english_q = max((s.english_query for s in buffer if s.english_query),
                        key=len, default="")
        merged.append(Scene(
            id=first.id,
            start=first.start,
            end=buffer[-1].end,
            text=" ".join(s.text for s in buffer),
            visual_type=first.visual_type,
            arabic_query=arabic_q,
            english_query=english_q,
            audio_note=first.audio_note,
            is_important=any(s.is_important for s in buffer),
            ken_burns=first.ken_burns,
        ))
        buffer = []
        buffer_duration = 0.0

    for s in scenes:
        buffer.append(s)
        buffer_duration += s.end - s.start
        if buffer_duration >= MIN_SCENE_DURATION:
            flush()

    flush()
    log.info(f"Merged short scenes: {len(scenes)} → {len(merged)}")
    return merged
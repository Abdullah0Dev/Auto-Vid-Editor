"""Step 2 — Scene planning, query generation, and translation."""
import json
import re

from config import MODEL_ORCHESTRATOR, PLAN_DIR
from models.types import Scene, ImportantMoment
from utils.ollama_client import chat
from utils.logger import log


# --- Tuning ---
CHUNK_SECONDS = 60          # plan in 60s windows to avoid model degradation
MIN_SCENE_DURATION = 5.0    # merge scenes shorter than this
MAX_SCENE_DURATION = 15.0   # split scenes longer than this


SYSTEM_PROMPT = """أنت مدير تصوير ومونتاج لفيديوهات تاريخية عربية.

مهمتك: قسّم النص المفرّغ إلى مشاهد، وأعد النتيجة على شكل JSON صالح فقط.

شكل JSON المطلوب:
{
  "scenes": [
    {
      "id": 1,
      "start": 0.0,
      "end": 8.5,
      "text": "النص الأصلي هنا",
      "visual_type": "image",
      "arabic_query": "وصف بحث بالعربية",
      "english_query": "English translation of the search query",
      "audio_note": "low ambient music",
      "is_important": false,
      "ken_burns": "zoom_in"
    }
  ],
  "important_moments": [
    {
      "start": 0.0,
      "end": 0.0,
      "text": "العبارة المهمة",
      "effect": "echo"
    }
  ]
}

قواعد صارمة:
- أعد JSON فقط. لا تكتب أي شرح أو مقدمة أو خاتمة.
- لا تستخدم ``` أو أي تنسيق markdown.
- ابدأ الرد مباشرة بـ { وانتهِ بـ }.
- **جمّع 2-4 مقاطع متتالية في مشهد واحد** إذا كانت أقل من 5 ثوانٍ لكل منها.
- اجعل كل مشهد بين 5 و 15 ثانية.
- كل مشهد يجب أن يحتوي على text و arabic_query و english_query.
- لا تُصدر مشاهد فارغة أبداً. إذا لم تجد مشهداً كاملاً، تجاهله.
- is_important = true للعبارات الحماسية أو المؤثرة.
- ken_burns: واحدة من zoom_in, zoom_out, pan_left, pan_right.
- effect: واحدة من echo, reverb, pause.

مهم جداً: كل مشهد في المخرجات يجب أن يكون كاملاً بجميع الحقول. لا تكتب مشاهد تحتوي على start و end فقط."""


USER_PROMPT = """النص المفرّغ:
{transcript}

قسّم هذا النص إلى مشاهد وأعد JSON فقط."""


def plan(transcript_text: str) -> tuple[list[Scene], list[ImportantMoment]]:
    PLAN_DIR.mkdir(parents=True, exist_ok=True)

    # --- Split transcript into 60-second chunks ---
    chunks = _chunk_transcript(transcript_text, CHUNK_SECONDS)
    log.info(f"Planning {len(chunks)} chunk(s) with {MODEL_ORCHESTRATOR}...")

    all_scenes: list[Scene] = []
    all_moments: list[ImportantMoment] = []

    for i, chunk in enumerate(chunks, start=1):
        log.info(f"Chunk {i}/{len(chunks)}: {len(chunk)} chars")

        result = chat(
            MODEL_ORCHESTRATOR,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT.format(transcript=chunk)},
            ],
            label=f"Scene Planner [{i}/{len(chunks)}]",
        )

        raw_content = result.get("message", {}).get("content", "")

        # Save each chunk's raw response
        raw_file = PLAN_DIR / f"raw_chunk_{i:02d}.txt"
        raw_file.write_text(raw_content or "<EMPTY>", encoding="utf-8")

        if not raw_content.strip():
            log.warn(f"Chunk {i}: empty response — skipping")
            continue

        parsed = _try_parse_json(raw_content)
        if parsed is None:
            log.warn(f"Chunk {i}: invalid JSON — skipping")
            continue

        scenes = _build_scenes(parsed, offset=i * 1000)
        moments = _build_moments(parsed)
        all_scenes.extend(scenes)
        all_moments.extend(moments)
        log.ok(f"Chunk {i}: {len(scenes)} scenes, {len(moments)} moments")

    # --- Post-process: sort, merge, sanitize ---
    all_scenes.sort(key=lambda s: s.start)
    all_scenes = _sanitize_scenes(all_scenes)
    all_scenes = _merge_short_scenes(all_scenes)

    # Re-number scene IDs
    for idx, s in enumerate(all_scenes, start=1):
        s.id = idx

    if not all_scenes:
        log.error("No valid scenes after post-processing.")
        raise RuntimeError("Scene planning produced no scenes")

    # Save the parsed plan
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


# ---------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------

def _chunk_transcript(transcript_text: str, chunk_seconds: int) -> list[str]:
    """
    Split a timestamped transcript like '[0.0–4.0] text' into chunks
    by looking at the end time of each line.
    """
    lines = [l for l in transcript_text.split("\n") if l.strip()]
    if not lines:
        return [transcript_text]

    chunks: list[str] = []
    current: list[str] = []
    chunk_start = 0.0

    for line in lines:
        m = re.match(r"\[(\d+\.?\d*)–(\d+\.?\d*)\]", line)
        if not m:
            current.append(line)
            continue
        end_t = float(m.group(2))

        if end_t - chunk_start > chunk_seconds and current:
            chunks.append("\n".join(current))
            current = []
            chunk_start = end_t

        current.append(line)

    if current:
        chunks.append("\n".join(current))

    return chunks


# ---------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------

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


# ---------------------------------------------------------------
# Building
# ---------------------------------------------------------------

def _build_scenes(plan: dict, offset: int = 0) -> list[Scene]:
    scenes = []
    for i, s in enumerate(plan.get("scenes", []), start=1):
        try:
            text = str(s.get("text", "")).strip()
            if not text:
                continue  # skip empty scenes
            scenes.append(Scene(
                id=offset + int(s.get("id", i)),
                start=float(s["start"]),
                end=float(s["end"]),
                text=text,
                visual_type=s.get("visual_type", "image"),
                arabic_query=s.get("arabic_query", ""),
                english_query=s.get("english_query", ""),
                audio_note=s.get("audio_note", ""),
                is_important=bool(s.get("is_important", False)),
                ken_burns=s.get("ken_burns", "zoom_in"),
            ))
        except (KeyError, TypeError, ValueError) as e:
            log.warn(f"Skipping malformed scene: {e}")
    return scenes


def _build_moments(plan: dict) -> list[ImportantMoment]:
    moments = []
    for m in plan.get("important_moments", []):
        try:
            moments.append(ImportantMoment(
                start=float(m["start"]),
                end=float(m["end"]),
                text=str(m.get("text", "")),
                effect=m.get("effect", "echo"),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return moments


# ---------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------

def _sanitize_scenes(scenes: list[Scene]) -> list[Scene]:
    """Drop scenes without text or queries, and drop obviously broken ranges."""
    out = []
    for s in scenes:
        if not s.text or not s.english_query:
            continue
        if s.end <= s.start:
            continue
        out.append(s)
    if len(out) != len(scenes):
        log.info(f"Sanitized: dropped {len(scenes) - len(out)} invalid scenes")
    return out


def _merge_short_scenes(scenes: list[Scene]) -> list[Scene]:
    """
    Merge consecutive scenes shorter than MIN_SCENE_DURATION into
    the next one, until the combined duration is >= MIN_SCENE_DURATION.
    """
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
        merged.append(Scene(
            id=first.id,
            start=first.start,
            end=buffer[-1].end,
            text=" ".join(s.text for s in buffer),
            visual_type=first.visual_type,
            arabic_query=" | ".join(s.arabic_query for s in buffer if s.arabic_query),
            english_query=" | ".join(s.english_query for s in buffer if s.english_query),
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

    flush()  # any remaining

    log.info(f"Merged short scenes: {len(scenes)} → {len(merged)}")
    return merged
"""Step 2 — Scene planning, query generation, and translation."""
import json
import re

from config import MODEL_ORCHESTRATOR, PLAN_DIR
from models.types import Scene, ImportantMoment
from utils.ollama_client import chat
from utils.logger import log


CHUNK_SECONDS = 60
MIN_SCENE_DURATION = 8.0
MAX_SCENE_DURATION = 15.0


# Strings the model copies verbatim from the prompt schema.
PLACEHOLDER_STRINGS = [
    "وصف بحث بالعربية",
    "English translation of the search query",
    "النص الأصلي هنا",
    "العبارة المهمة",
    "low ambient music",       # This one is OK to keep — it's a valid default
    "English translation",
    "search query",
    "...",
]


SYSTEM_PROMPT = """أنت مدير تصوير ومونتاج لفيديوهات تاريخية عربية.

مهمتك: قسّم النص المفرّغ إلى مشاهد، وأعد النتيجة على شكل JSON صالح فقط.

⚠️ الأهم: english_query و arabic_query هما أوامر بحث عن صور، وليسا وصفاً للتعليق الصوتي.

أمثلة على أوامر بحث سيئة (لا تفعل هذا):
- "Voiceover in Arabic" — هذا وصف لما يفعله الراوي، ليس بحثاً عن صورة
- "Author's biography" — عام جداً، لن يجلب نتيجة
- "تعريف المؤلف" — وصف للنص، ليس بحثاً عن صورة

أمثلة على أوامر بحث جيدة (افعل هذا):
- "Al-Dhahabi historian manuscript" — يذكر اسم الشخصية
- "medieval Damascus mosque architecture" — يذكر المكان المحدد
- "Islamic golden age scholar portrait" — يذكر الحقبة والموضوع
- "old Arabic manuscript pages" — يذكر نوع الصورة المطلوبة

قواعد صارمة:
- أعد JSON فقط. لا تكتب أي شرح.
- لا تستخدم ``` أو markdown.
- استخرج الأسماء والأماكن والتواريخ من النص واذكرها في queries.
- إذا ذكر النص "الذهبي" أو "سير أعلام النبلاء" أو "تاريخ الإسلام"، فليكن البحث عن "Al-Dhahabi" و "Tarikh al-Islam manuscript" وليس "Author biography".
- **جمّع 2-4 أسطر متتالية في مشهد واحد** إذا كانت مدتها أقل من 5 ثوانٍ.
- اجعل كل مشهد بين 5 و 15 ثانية.
- ken_burns: zoom_in, zoom_out, pan_left, pan_right.
- is_important = true للعبارات الحماسية أو المؤثرة.
- إذا لم توجد لحظات مهمة، أعد "important_moments": [].

شكل JSON:
{
  "scenes": [
    {
      "id": 1,
      "start": 0.0,
      "end": 8.0,
      "text": "النص الأصلي",
      "visual_type": "image",
      "arabic_query": "بحث بالعربية يذكر أسماء وأماكن محددة",
      "english_query": "Specific image search with names and places",
      "audio_note": "low ambient music",
      "is_important": false,
      "ken_burns": "zoom_in"
    }
  ],
  "important_moments": []
}"""

USER_PROMPT = """هذا المقطع يغطي الفترة الزمنية من {chunk_start:.1f} إلى {chunk_end:.1f} ثانية من الفيديو الأصلي.

النص المفرّغ:
{transcript}

قواعد صارمة لهذا المقطع:
- استخدم الأزمنة (start/end) الموجودة بين الأقواس في النص كما هي.
- كل قيم start و end يجب أن تكون بين {chunk_start:.1f} و {chunk_end:.1f}.
- املأ الحقول بقيم حقيقية من النص. لا تنسخ الأمثلة.

أعد JSON فقط."""


def plan(transcript_text: str) -> tuple[list[Scene], list[ImportantMoment]]:
    PLAN_DIR.mkdir(parents=True, exist_ok=True)

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
                    chunk_start=c_start,
                    chunk_end=c_end,
                    transcript=chunk_text,
                )},
            ],
            label=f"Scene Planner [{i}/{len(chunks)}]",
        )

        raw_content = result.get("message", {}).get("content", "")
        (PLAN_DIR / f"raw_chunk_{i:02d}.txt").write_text(
            raw_content or "<EMPTY>", encoding="utf-8"
        )

        if not raw_content.strip():
            log.warn(f"Chunk {i}: empty response — skipping")
            continue

        parsed = _try_parse_json(raw_content)
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

    # Sanitize moments too — drop placeholder ones
    all_moments = [
        m for m in all_moments
        if m.start < m.end and m.text and not _is_placeholder(m.text)
    ]

    if not all_scenes:
        log.error("No valid scenes after post-processing.")
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
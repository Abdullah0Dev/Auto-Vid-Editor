"""Step 1.5 — Extract global video context from the full transcript.

Reads the ENTIRE transcript once, produces structured knowledge:
entities, places, era, visual style, and reusable search keywords.
This context is injected into later stages so every chunk call has
the "big picture" instead of just local text.
"""
import json
import re

from config import MODEL_ORCHESTRATOR, PLAN_DIR
from utils.llm_client import chat
from utils.logger import log


# NOTE: We use <<TRANSCRIPT>> as the marker and .replace() instead of
# .format() because the JSON schema in this prompt contains literal
# braces, which .format() would try to interpret as placeholders.
CONTEXT_PROMPT = """You analyze an Arabic documentary transcript to prepare it for automated image retrieval.

TASK
Read the full transcript and extract structured GLOBAL CONTEXT as JSON.
This context will be reused by downstream modules (scene planning, image search).
Only include facts stated in or directly inferable from the transcript.

TRANSCRIPT:
<<TRANSCRIPT>>

OUTPUT — return ONLY this JSON object, no markdown, no commentary:

{
  "summary_ar": "ملخص من 2-3 جمل بالعربية",
  "main_subject": "person name or topic (Arabic, short)",
  "main_subject_ar": "الاسم أو الموضوع بالعربية",
  "time_period": "e.g. '7th century AH / 13th century CE' or 'غير محدد' if unclear",
  "region": "e.g. 'Damascus, Levant' — comma-separated, Arabic",
  "key_entities": [
    {"type": "person|book|place|event|dynasty",
     "name_en": "...", "name_ar": "...", "role": "one short phrase"}
  ],
  "historical_context": "3-5 sentences of background (Arabic) that will help pick era-appropriate visuals so it should be a summarization for the transcription so it's easy to understand",
  "visual_style_guidance": "concrete visual motifs, e.g. 'aged parchment manuscripts, Mamluk stonework, oil-lamp lighting, sepia palette'",
  "image_search_keywords_en": ["3-8 concrete English nouns for Wikimedia Commons"],
  "image_search_keywords_ar": ["3-8 concrete Arabic nouns for Arabic image sources"]
}

RULES
- 3 to 6 key_entities. Include people, books, places, dynasties that appear in the transcript.
- Search keywords MUST be concrete and visible (mosque, manuscript, minaret, astrolabe, courtyard). NEVER abstract (faith, justice, biography).
- If the era or region is genuinely unclear, write "غير محدد" / "unclear" — do NOT guess a specific century.
- Output must be valid JSON. Do not wrap in ```.
"""

def extract_context(full_transcript: str) -> dict:
    PLAN_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Extracting global video context...")

    prompt = CONTEXT_PROMPT.replace("<<TRANSCRIPT>>", full_transcript)

    result = chat(
        MODEL_ORCHESTRATOR,
        [{"role": "user", "content": prompt}],
        label="Context Extractor",
    )

    raw = result.get("message", {}).get("content", "")
    (PLAN_DIR / "raw_context.txt").write_text(raw or "<EMPTY>", encoding="utf-8")

    parsed = _try_parse_json(raw)
    if parsed is None:
        log.warn("Could not parse context — using empty fallback")
        return _empty_context()

    log.ok(
        f"Context: {parsed.get('main_subject', '?')[:50]} "
        f"| {parsed.get('time_period', '?')} "
        f"| {len(parsed.get('key_entities', []))} entities"
    )

    (PLAN_DIR / "video_context.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return parsed


def format_context_for_prompt(context: dict) -> str:
    """Render the context as compact text for injection into other prompts."""
    if not context or not context.get("summary"):
        return "(no context available)"

    lines = [
        f"Video summary: {context.get('summary', '')}",
        f"Main subject: {context.get('main_subject', '')}",
        f"Time period: {context.get('time_period', '')}",
        f"Region: {context.get('region', '')}",
    ]

    entities = context.get("key_entities", [])
    if entities:
        lines.append("Key entities:")
        for e in entities:
            lines.append(
                f"  - [{e.get('type', '?')}] {e.get('name_en', '')} "
                f"({e.get('name_ar', '')}) — {e.get('role', '')}"
            )

    places = context.get("key_places", [])
    if places:
        lines.append(f"Key places: {', '.join(places)}")

    style = context.get("visual_style_guidance", "")
    if style:
        lines.append(f"Visual style guidance: {style}")

    keywords = context.get("search_keywords", [])
    if keywords:
        lines.append("Suggested search keywords (image-search-friendly):")
        for k in keywords:
            lines.append(f"  - {k}")

    return "\n".join(lines)


def _try_parse_json(text: str) -> dict | None:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        try:
            return json.loads(text[first:last + 1])
        except json.JSONDecodeError:
            pass
    return None


def _empty_context() -> dict:
    return {
        "summary": "", "main_subject": "", "time_period": "", "region": "",
        "key_entities": [], "key_places": [], "historical_context": "",
        "visual_style_guidance": "", "search_keywords": [],
    }
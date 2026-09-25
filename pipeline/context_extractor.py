"""Step 1.5 — Extract global video context from the full transcript.

Reads the ENTIRE transcript once, produces structured knowledge:
entities, places, era, visual style, and reusable search keywords.
This context is injected into later stages so every chunk call has
the "big picture" instead of just local text.
"""
import json
import re

from config import MODEL_ORCHESTRATOR, PLAN_DIR
from utils.ollama_client import chat
from utils.logger import log


# NOTE: We use <<TRANSCRIPT>> as the marker and .replace() instead of
# .format() because the JSON schema in this prompt contains literal
# braces, which .format() would try to interpret as placeholders.
CONTEXT_PROMPT = """You are analyzing an Arabic historical documentary transcript
to prepare for automated visual asset search.

FULL TRANSCRIPT:
<<TRANSCRIPT>>

Extract the GLOBAL context. Return ONLY valid JSON matching this schema:

{
  "summary": "2-3 sentence summary of the whole video in English",
  "main_subject": "Primary subject (person, topic, or event)",
  "time_period": "Historical era, e.g. '13th century CE / 7th century AH'",
  "region": "Geographic region, e.g. 'Damascus, Levant, Egypt, Hijaz'",
  "key_entities": [
    {"type": "person", "name_en": "Al-Dhahabi", "name_ar": "الذهبي", "role": "historian"},
    {"type": "book",  "name_en": "Siyar A'lam al-Nubala", "name_ar": "سير أعلام النبلاء", "role": "biographical dictionary"}
  ],
  "key_places": ["Damascus", "Mecca", "Cairo", "Alexandria", "Baalbek"],
  "historical_context": "One paragraph of background to inform visual choices",
  "visual_style_guidance": "e.g. 'aged manuscript pages, medieval Islamic architecture, sepia tones'",
  "search_keywords": [
    "medieval Islamic manuscript",
    "13th century Damascus mosque",
    "Mamluk architecture",
    "Arabic calligraphy page"
  ]
}

Rules:
- Return only JSON, no commentary, no markdown fences.
- Extract 3-6 key entities with both English and Arabic spellings.
- search_keywords MUST be image-search-friendly English phrases (concrete nouns, no abstract ideas).
- If unsure of the exact era, use the closest century and mention uncertainty in historical_context.
- Focus on what will help find IMAGES, not what will help tell the STORY."""


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
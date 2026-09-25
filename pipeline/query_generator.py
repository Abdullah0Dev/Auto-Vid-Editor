"""Step 2.5 — Refine search queries using full video context.

Takes the scenes from the planner and rewrites their arabic_query and
english_query fields. Runs in batches to avoid model degradation.
"""
import json
import re

from config import MODEL_ORCHESTRATOR, PLAN_DIR
from models.types import Scene
from pipeline.context_extractor import format_context_for_prompt
from utils.ollama_client import chat
from utils.logger import log


BATCH_SIZE = 4    # scenes per LLM call


QUERY_PROMPT = """You write IMAGE SEARCH QUERIES for an Arabic historical documentary.

GLOBAL VIDEO CONTEXT:
{context}

You will be given {n} scenes. For EACH scene, produce TWO queries:
  - arabic_query: a search query in Arabic
  - english_query: a search query in English

The queries must find a PHOTOGRAPH, PAINTING, MANUSCRIPT, or ARCHITECTURAL IMAGE
that visually illustrates the scene. They are NOT translations of the narration.

SCENE FORMATTING RULES:
- Query must describe something VISIBLE.
- Include named entities from the global context when relevant.
- Prefer concrete nouns: mosque, manuscript, minaret, scroll, courtyard, calligraphy.
- If the scene is abstract/emotional, use a mood query.
- Each query should be 3-8 words.
- English query must be useful for Wikimedia Commons search — avoid stop words.

SCENES:
{scenes_block}

Return ONLY this JSON, no commentary:
{{
  "queries": [
    {{"id": <scene_id>, "arabic_query": "...", "english_query": "..."}},
    ...
  ]
}}

Rules:
- Return one entry per scene, in the same order.
- Use the exact scene ids given above.
- Return JSON only."""


def generate_queries(scenes: list[Scene], context: dict) -> list[Scene]:
    """Rewrite scene queries with context-aware, image-search-friendly terms."""
    if not scenes:
        return scenes

    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    context_str = format_context_for_prompt(context)

    log.info(f"Refining queries for {len(scenes)} scenes "
             f"(batch size {BATCH_SIZE})...")

    for start in range(0, len(scenes), BATCH_SIZE):
        batch = scenes[start:start + BATCH_SIZE]
        batch_num = start // BATCH_SIZE + 1
        total_batches = (len(scenes) + BATCH_SIZE - 1) // BATCH_SIZE

        log.info(f"Query batch {batch_num}/{total_batches} "
                 f"(scenes {[s.id for s in batch]})")

        result = chat(
            MODEL_ORCHESTRATOR,
            [{"role": "user", "content": QUERY_PROMPT.format(
                context=context_str,
                n=len(batch),
                scenes_block=_format_batch(batch),
            )}],
            label=f"Query Gen [{batch_num}/{total_batches}]",
        )

        raw = result.get("message", {}).get("content", "")
        (PLAN_DIR / f"raw_queries_{batch_num:02d}.txt").write_text(
            raw or "<EMPTY>", encoding="utf-8"
        )

        parsed = _try_parse_json(raw)
        if parsed is None:
            log.warn(f"Batch {batch_num}: invalid JSON — keeping original queries")
            continue

        _apply_queries(batch, parsed.get("queries", []))

    log.ok("Query refinement complete")
    return scenes


def _format_batch(batch: list[Scene]) -> str:
    lines = []
    for s in batch:
        lines.append(
            f"[id={s.id}] ({s.start:.1f}s–{s.end:.1f}s) {s.text}"
        )
    return "\n".join(lines)


def _apply_queries(batch: list[Scene], entries: list[dict]) -> None:
    by_id = {s.id: s for s in batch}
    for entry in entries:
        sid = entry.get("id")
        if sid not in by_id:
            continue
        scene = by_id[sid]
        ar = str(entry.get("arabic_query", "")).strip()
        en = str(entry.get("english_query", "")).strip()

        if ar and not _is_placeholder(ar):
            scene.arabic_query = ar
        if en and not _is_placeholder(en):
            scene.english_query = en

        log.info(f"  Scene {sid}: {scene.english_query[:60]}")


def _is_placeholder(text: str) -> bool:
    if not text:
        return True
    return any(p in text for p in [
        "وصف بحث", "search query", "English translation",
        "النص الأصلي", "...",
    ])


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
"""Step 4 — Pick the best image using Qwen3-VL."""
import base64
import re

from config import MODEL_VISION, VISION_FALLBACK_TO_FIRST
from models.types import Scene
from utils.llm_client import chat
from utils.logger import log


PROMPT_TEMPLATE = """You are an expert visual researcher for an Arabic historical documentary.
You evaluate candidate images and pick the single best one for a scene.

SCENE NARRATION:
{scene_text}

SEARCH INTENT (what we asked for):
{english_query}

You are shown {n_images} candidate images labelled A, B, C, ...

TASK — for EACH image, in order:
1. Describe what the image shows in ONE short factual sentence.
2. State whether it violates any EXCLUSION rule below.

EXCLUSION RULES — mark "Violates: YES" if the image has any of:
  - Visible watermark, logo, or prominent text overlay
  - Clearly modern elements (cars, contemporary clothing, modern buildings, electrical wires)
  - Low quality: blurry, pixelated, heavily compressed
  - Wrong subject (unrelated to the search intent)
  - Graphic violence or disturbing content

Then pick the SINGLE best image that fits the scene's era and search intent.
If NONE fit, choose NONE.

OUTPUT FORMAT — exactly these lines, nothing else:

IMAGE A: <description> | Violates: YES/NO
IMAGE B: <description> | Violates: YES/NO
IMAGE C: <description> | Violates: YES/NO
BEST: <A|B|C|NONE>
REASON: <one short sentence explaining the choice>

RULES
- Describe only what you actually see. Do not infer from the search intent.
- If an image is partially obscured or cropped, still describe it — do not skip.
- "BEST" must be a single letter or NONE. Never multiple letters.
"""


def judge(scene: Scene) -> str:
    """Evaluate candidates and return the path of the best image, or ''."""
    if not scene.candidates:
        return ""

    n = len(scene.candidates)
    # Pad the template so the letters label matches reality
    letters = ["A", "B", "C"][:n]

    images = [_b64(p) for p in scene.candidates]

    prompt = PROMPT_TEMPLATE.format(
        scene_text=scene.text,
        english_query=scene.english_query or scene.arabic_query,
        n_images=n,
    )

    log.info(f"Scene {scene.id}: evaluating {n} candidate(s)...")

    try:
        result = chat(
            MODEL_VISION,
            [{"role": "user", "content": prompt, "images": images}],
            label=f"Vision (scene {scene.id})",
            num_ctx=8192,           # ← add this line
        )
        answer = result["message"]["content"].strip()
        log.info(f"  → verdict preview: {answer[:200].replace(chr(10), ' | ')}")

        chosen_idx = _parse_verdict(answer, n)
        if chosen_idx is not None:
            chosen = scene.candidates[chosen_idx]
            log.ok(f"  → chose candidate {letters[chosen_idx]}: "
                   f"{chosen.split('/')[-1]}")
            return chosen

        if re.search(r"\bNONE\b", answer, re.IGNORECASE):
            log.warn(f"  → model said NONE for scene {scene.id}")
            return ""

        log.warn(f"  → could not parse verdict, using fallback")

    except Exception as e:
        log.warn(f"Vision judge failed for scene {scene.id}: {e}")

    # Fallback: first candidate
    if VISION_FALLBACK_TO_FIRST and scene.candidates:
        log.info(f"  → fallback to first candidate")
        return scene.candidates[0]

    return ""


def _parse_verdict(answer: str, n_images: int) -> int | None:
    """
    Extract the chosen letter (A/B/C) from the model's response.
    Returns the zero-based index, or None if NONE/unparseable.
    """
    # Primary: look for "BEST: X"
    m = re.search(r"BEST\s*:\s*([A-C])", answer, re.IGNORECASE)
    if m:
        idx = ord(m.group(1).upper()) - ord("A")
        if 0 <= idx < n_images:
            return idx
        return None

    # Secondary: look for "BEST: NONE"
    if re.search(r"BEST\s*:\s*NONE", answer, re.IGNORECASE):
        return None

    # Tertiary: find the last standalone "A"/"B"/"C" mentioned after "BEST"
    best_pos = answer.upper().find("BEST")
    if best_pos != -1:
        tail = answer[best_pos:]
        letters_found = re.findall(r"\b([A-C])\b", tail)
        if letters_found:
            idx = ord(letters_found[0].upper()) - ord("A")
            if 0 <= idx < n_images:
                return idx

    # Quaternary: whole answer is a single letter
    stripped = answer.strip().upper()
    if len(stripped) == 1 and stripped in "ABC":
        idx = ord(stripped) - ord("A")
        if idx < n_images:
            return idx

    return None


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()
"""Step 4 — Pick the best image using Qwen2.5-VL."""
import base64
from config import MODEL_VISION, VISION_FALLBACK_TO_FIRST
from models.types import Scene
from utils.ollama_client import chat
from utils.logger import log


PROMPT_TEMPLATE = """أنت مساعد مونتاج لفيديو تاريخي عربي.

وصف المشهد:
{scene_text}

البحث المطلوب: {arabic_query}

شروط الاستبعاد:
- تخطَّ الصور ذات العلامات المائية أو النصوص الواضحة
- تخطَّ الصور الحديثة أو غير التاريخية
- تخطَّ الصور منخفضة الجودة

المهمة:
1. صف كل صورة بإيجاز.
2. حدد أي صورة تنتهك الشروط.
3. اختر الأفضل.
4. إن لم تناسب أي صورة، أجب بـ NONE.

أخرج فقط الحرف (A/B/C/NONE) وسبباً في جملة."""


def judge(scene: Scene) -> str:
    if not scene.candidates:
        return ""

    images = [_b64(p) for p in scene.candidates]
    prompt = PROMPT_TEMPLATE.format(
        scene_text=scene.text, arabic_query=scene.arabic_query
    )

    try:
        result = chat(
            MODEL_VISION,
            [{"role": "user", "content": prompt, "images": images}],
            label=f"Vision (scene {scene.id})",
        )
        answer = result["message"]["content"].strip()
        log.debug(f"Vision: {answer[:100]}")

        for letter in ("A", "B", "C"):
            if answer.upper().startswith(letter):
                idx = ord(letter) - ord("A")
                if idx < len(scene.candidates):
                    return scene.candidates[idx]

        if "NONE" in answer.upper():
            return ""
    except Exception as e:
        log.warn(f"Vision judge failed: {e}")

    return scene.candidates[0] if VISION_FALLBACK_TO_FIRST else ""


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()
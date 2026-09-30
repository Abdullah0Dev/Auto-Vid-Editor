"""Google Gemini backend — mirrors the ollama_client interface."""
import base64
import time

from config import GEMINI_API_KEY
from utils.logger import log


_client = None


def _get_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Add it to .env or pass --api-key."
            )
        from google import genai
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def chat(model: str, messages: list, tools: list | None = None,
         timeout: int = 900, stream: bool | None = None,
         label: str = "") -> dict:
    """
    Send a chat to Gemini. Signature matches ollama_client.chat exactly.
    Returns the same response shape so callers don't need to care.
    """
    from google.genai import types

    if tools:
        log.warn("Gemini backend does not support tool calling in this build — "
                 "tools argument ignored")

    client = _get_client()

    # ── Extract system instruction + build contents ──
    system_instruction: str | None = None
    contents: list = []

    for msg in messages:
        role = msg.get("role", "user")

        if role == "system":
            # Gemini wants a single system instruction
            text = msg.get("content", "")
            if system_instruction:
                system_instruction += "\n\n" + text
            else:
                system_instruction = text
            continue

        # Gemini uses "model" instead of "assistant"
        gem_role = "model" if role == "assistant" else "user"

        parts: list = []
        text = msg.get("content", "")
        if text:
            parts.append(types.Part.from_text(text=text))

        # Attach images (base64 strings as Ollama would send them)
        for img_b64 in msg.get("images", []) or []:
            try:
                img_bytes = base64.b64decode(img_b64)
                parts.append(types.Part.from_bytes(
                    data=img_bytes,
                    mime_type=_detect_mime(img_bytes),
                ))
            except Exception as e:
                log.warn(f"Gemini: failed to decode image: {e}")

        if parts:
            contents.append(types.Content(role=gem_role, parts=parts))

    # ── Build request config ──
    config_kwargs: dict = {}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction

    log.info(f"[{label or model}] calling Gemini ({model})…")
    t0 = time.time()

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs)
            if config_kwargs else None,
        )
    except Exception as e:
        log.error(f"[{label or model}] Gemini error: {e}")
        raise

    elapsed = time.time() - t0
    content = getattr(response, "text", "") or ""

    log.ok(f"[{label or model}] Gemini responded in {elapsed:.1f}s "
           f"({len(content)} chars)")

    # Stream to console if enabled (mimics ollama_client's stream mode)
    from config import STREAM_OUTPUT
    if stream or STREAM_OUTPUT:
        from utils.logger import console
        console.print(f"[dim]─── {label or model} output ───[/dim]")
        console.print(content, markup=False, highlight=False)
        console.print(f"[dim]─── end {label or model} ───[/dim]")

    return {
        "model": model,
        "message": {"role": "assistant", "content": content},
        "done": True,
    }


def unload(model: str) -> None:
    """Gemini has no local model to unload — no-op for API symmetry."""
    pass


def ensure_available(model: str) -> bool:
    """Verify the SDK is importable and the key is set."""
    try:
        _get_client()
        return True
    except Exception as e:
        log.warn(f"Gemini not available: {e}")
        return False


def _detect_mime(data: bytes) -> str:
    """Sniff image format from magic bytes."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/jpeg"
"""Thin wrapper around Ollama's HTTP API with streaming and unload."""
import json
import time

import httpx

from config import OLLAMA_BASE, MODEL_KEEP_ALIVE, STREAM_OUTPUT
from utils.logger import log, console


def chat(model: str, messages: list, tools: list | None = None,
         timeout: int = 900, stream: bool | None = None,
         label: str = "") -> dict:
    """
    Send a chat request to Ollama.

    If `stream` is True (or STREAM_OUTPUT is on), prints tokens live to the
    console as they arrive. Always returns the full response dict.
    """
    if stream is None:
        stream = STREAM_OUTPUT

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "keep_alive": MODEL_KEEP_ALIVE,
    }
    if tools:
        payload["tools"] = tools

    if stream:
        return _chat_stream(model, payload, timeout, label)
    return _chat_block(model, payload, timeout)


def _chat_block(model: str, payload: dict, timeout: int) -> dict:
    """Non-streaming request — wait for the whole response."""
    log.info(f"[{model}] generating...")
    t0 = time.time()
    resp = httpx.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=timeout)
    resp.raise_for_status()
    elapsed = time.time() - t0
    log.ok(f"[{model}] done in {elapsed:.1f}s")
    return resp.json()


def _chat_stream(model: str, payload: dict, timeout: int,
                 label: str) -> dict:
    """
    Streaming request — print tokens as they arrive, then return
    the assembled response in the same shape as the non-streaming API.
    """
    label = label or model
    log.info(f"[{label}] streaming (Ctrl+C to abort)...")

    t0 = time.time()
    token_count = 0
    full_content = ""
    full_message: dict = {}

    with httpx.stream("POST", f"{OLLAMA_BASE}/api/chat",
                      json=payload, timeout=timeout) as r:
        r.raise_for_status()
        console.print(f"[dim]─── {label} output ───[/dim]")

        for line in r.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = chunk.get("message", {})
            piece = msg.get("content", "")
            if piece:
                # Print raw (no markup parsing) so Arabic and JSON stay intact
                console.print(piece, end="", markup=False, highlight=False,
                              soft_wrap=True)
                full_content += piece
                token_count += 1

            # Capture any tool calls / final message metadata
            if msg:
                full_message = msg

            if chunk.get("done"):
                break

        console.print()  # newline after stream ends
        console.print(f"[dim]─── end {label} ───[/dim]")

    elapsed = time.time() - t0
    tps = token_count / elapsed if elapsed > 0 else 0
    log.ok(f"[{label}] {token_count} chunks in {elapsed:.1f}s "
           f"({tps:.1f} chunks/s)")

    # Return in the same shape as the non-streaming API
    return {
        "model": model,
        "message": {**full_message, "content": full_content},
        "done": True,
    }


def unload(model: str):
    """Force Ollama to release a model from memory."""
    try:
        httpx.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=10,
        )
        time.sleep(1.0)
        log.debug(f"Unloaded {model}")
    except Exception as e:
        log.warning(f"Failed to unload {model}: {e}")


def ensure_available(model: str) -> bool:
    """Check that a model exists in Ollama's local library."""
    try:
        r = httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=10)
        names = [m["name"] for m in r.json().get("models", [])]
        return any(model in n for n in names)
    except Exception:
        return False
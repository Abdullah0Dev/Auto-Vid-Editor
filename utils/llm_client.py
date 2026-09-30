"""Unified LLM client — routes calls to the configured provider.

Public interface:
    from utils.llm_client import chat, unload, ensure_available

The provider is chosen by `config.LLM_PROVIDER` ("ollama" or "gemini").
Both backends expose the same function signatures and return shapes.
"""
from config import LLM_PROVIDER
from utils.logger import log


if LLM_PROVIDER == "ollama":
    from utils.ollama_client import chat, unload, ensure_available
    log.info(f"LLM provider: ollama (local)")

elif LLM_PROVIDER == "gemini":
    from utils.gemini_client import chat, unload, ensure_available
    log.info(f"LLM provider: gemini (cloud)")

else:
    raise ValueError(
        f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}. "
        f"Set LLM_PROVIDER=ollama or LLM_PROVIDER=gemini in .env"
    )


__all__ = ["chat", "unload", "ensure_available"]
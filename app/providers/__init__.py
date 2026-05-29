from functools import lru_cache

from app.config import settings
from app.providers.base import ChatMessage, LLMProvider
from app.providers.claude import ClaudeProvider
from app.providers.ollama import OllamaProvider


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    """Resolve the active LLM provider from settings. Singleton."""
    kind = settings.llm_provider.lower()
    if kind == "claude":
        if not settings.claude_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=claude but CLAUDE_API_KEY is not set. "
                "Add it to .env or switch to LLM_PROVIDER=ollama."
            )
        return ClaudeProvider(api_key=settings.claude_api_key, model=settings.claude_model)
    if kind == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r} (expected 'claude' or 'ollama')")


__all__ = ["ChatMessage", "LLMProvider", "get_provider"]

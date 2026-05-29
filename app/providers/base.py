from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TypedDict


class ChatMessage(TypedDict):
    role: str  # "user" | "assistant"
    content: str


class LLMProvider(ABC):
    """Provider-agnostic interface for LLM synthesis over retrieved context.

    RAG pipelines stay provider-neutral by calling generate/stream with the
    composed system prompt (which typically embeds the retrieved chunks) and
    the user's question(s).
    """

    name: str

    @abstractmethod
    async def generate(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """One-shot generation. Returns the complete response text."""

    @abstractmethod
    def stream(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        """Streaming generation. Yields text chunks as they're produced."""

from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from app.providers.base import ChatMessage, LLMProvider


class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider.

    Uses prompt caching (`cache_control: ephemeral`) on the system block so
    the system prompt + retrieved-chunks context is only billed at full price
    on the first call within the 5-minute cache window. Subsequent calls in
    the same window read the cached prefix at ~10% of input cost.
    """

    name = "claude"

    def __init__(self, api_key: str, model: str):
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    def _system_blocks(self, system: str) -> list[dict]:
        return [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    async def generate(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=self._system_blocks(system),
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        )
        parts = [block.text for block in response.content if block.type == "text"]
        return "".join(parts)

    async def stream(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=self._system_blocks(system),
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        ) as stream:
            async for text in stream.text_stream:
                yield text

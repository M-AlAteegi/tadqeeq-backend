import json
from collections.abc import AsyncIterator

import httpx

from app.providers.base import ChatMessage, LLMProvider


class OllamaProvider(LLMProvider):
    """Local Ollama provider — used by the desktop edition for data sovereignty.

    Talks to the local Ollama server over HTTP (`/api/chat`). The user must
    have Ollama running and the configured model pulled (`ollama pull aya:8b`).
    """

    name = "ollama"

    def __init__(self, base_url: str, model: str, request_timeout: float = 180.0):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = request_timeout

    def _payload(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int,
        temperature: float,
        stream: bool,
    ) -> dict:
        ollama_messages: list[dict] = [{"role": "system", "content": system}]
        ollama_messages.extend({"role": m["role"], "content": m["content"]} for m in messages)
        return {
            "model": self._model,
            "messages": ollama_messages,
            "stream": stream,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

    async def generate(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        payload = self._payload(
            system=system, messages=messages, max_tokens=max_tokens, temperature=temperature, stream=False
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        return data["message"]["content"]

    async def stream(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        payload = self._payload(
            system=system, messages=messages, max_tokens=max_tokens, temperature=temperature, stream=True
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", f"{self._base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        break

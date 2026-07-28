"""One client for GapGPT, OpenRouter and any local runtime.

All three speak the OpenAI wire format, so they differ only in base URL and headers.
Retries live in the router, not here.
"""

import time
from typing import Any

import httpx

from agah.llm.base import Completion

TIMEOUT_SECONDS = 120.0


class OpenAICompatProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._extra_headers = extra_headers or {}

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> Completion:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": schema},
            }

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=self._headers()
            )
            response.raise_for_status()
            body = response.json()

        usage = body.get("usage") or {}
        return Completion(
            text=body["choices"][0]["message"]["content"] or "",
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            model=model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                json={"model": model, "input": texts},
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
        return [item["embedding"] for item in body["data"]]

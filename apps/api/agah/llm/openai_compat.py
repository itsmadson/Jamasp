"""One client for GapGPT, OpenRouter and any local runtime.

All three speak the OpenAI wire format, so they differ only in base URL and headers.
Retries live in the router, not here.
"""

import time
from typing import Any

import httpx

from agah.llm.base import Completion
from agah.llm.schema import strict

TIMEOUT_SECONDS = 120.0


class ProviderResponseError(Exception):
    """The provider answered, but not with a usable completion.

    Kept distinct from a transport error because the cause is almost always in
    the request (an unsupported response_format, an exhausted quota) and the
    provider says so in the body.
    """


def _provider_message(body: Any) -> str | None:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str):
            return error
        if body.get("message"):
            return str(body["message"])
    return None


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
        # Overridden in tests with httpx.MockTransport.
        self._transport: httpx.AsyncBaseTransport | None = None

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=self._transport)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.post(
                f"{self._base_url}{path}", json=payload, headers=self._headers()
            )

        try:
            body = response.json()
        except ValueError:
            body = None

        if response.status_code >= 400:
            message = _provider_message(body) or response.text[:300] or response.reason_phrase
            raise ProviderResponseError(f"HTTP {response.status_code}: {message}")

        # Several gateways answer 200 with an error body rather than a status code.
        message = _provider_message(body)
        if message:
            raise ProviderResponseError(message)

        if not isinstance(body, dict):
            raise ProviderResponseError("provider returned a non-object response")
        return body

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
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": strict(schema),
                },
            }

        started = time.perf_counter()
        body = await self._post("/chat/completions", payload)

        choices = body.get("choices") or []
        if not choices:
            raise ProviderResponseError("provider returned no choices")

        usage = body.get("usage") or {}
        return Completion(
            text=(choices[0].get("message") or {}).get("content") or "",
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            model=model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        body = await self._post("/embeddings", {"model": model, "input": texts})
        data = body.get("data")
        if not data:
            raise ProviderResponseError("provider returned no embeddings")
        return [item["embedding"] for item in data]

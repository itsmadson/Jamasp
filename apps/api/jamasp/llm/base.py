from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    provider: str
    latency_ms: int


class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Completion: ...

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]: ...

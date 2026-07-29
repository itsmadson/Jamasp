"""Per-task model routing.

Pipeline code never constructs a provider: it names a task, and the admin decides
which provider and model serve it. Switching describe_entity from OpenRouter to a
local Ollama model is a settings change, not a code change.
"""

import asyncio
import base64
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agah.config import get_settings
from agah.llm.base import Completion
from agah.llm.openai_compat import OpenAICompatProvider
from agah.models.observability import LLMCall, Setting
from agah.security.crypto import decrypt, key_from_settings

PROVIDERS_KEY = "llm_providers"
ROUTES_KEY = "llm_routes"


class RouteExhaustedError(Exception):
    pass


@dataclass(frozen=True)
class TaskRoute:
    task: str
    provider: str
    model: str
    temperature: float = 0.2
    fallbacks: list[tuple[str, str]] = field(default_factory=list)


DEFAULT_ROUTES: dict[str, TaskRoute] = {
    "describe_entity": TaskRoute(
        task="describe_entity",
        provider="openrouter",
        model="nvidia/nemotron-3-ultra-550b-a55b:free",
        fallbacks=[("openrouter", "inclusionai/ling-3.0-flash:free"), ("gapgpt", "gpt-4o")],
    ),
    "describe_field_batch": TaskRoute(
        task="describe_field_batch",
        provider="openrouter",
        model="inclusionai/ling-3.0-flash:free",
        fallbacks=[("gapgpt", "gpt-4o-mini")],
    ),
    "generate_sql": TaskRoute(
        task="generate_sql",
        provider="openrouter",
        model="nvidia/nemotron-3-ultra-550b-a55b:free",
        temperature=0.0,
        fallbacks=[("openrouter", "inclusionai/ling-3.0-flash:free"), ("gapgpt", "gpt-4o")],
    ),
    "embed": TaskRoute(task="embed", provider="local", model="bge-m3"),
    "translate": TaskRoute(
        task="translate", provider="openrouter", model="inclusionai/ling-3.0-flash:free"
    ),
}



def build_provider(name: str, config: dict[str, Any]) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        name=name,
        base_url=config.get("base_url", ""),
        api_key=config.get("api_key", ""),
        extra_headers=config.get("extra_headers"),
    )


async def _load_setting(session: AsyncSession, key: str) -> dict[str, Any]:
    row = (await session.scalars(select(Setting).where(Setting.key == key))).one_or_none()
    return dict(row.value) if row is not None else {}


async def load_provider_config(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """Stored settings win; otherwise fall back to environment configuration."""
    stored = await _load_setting(session, PROVIDERS_KEY)
    # Settings reads .env; os.environ alone would miss anything configured there.
    resolved: dict[str, dict[str, Any]] = {
        name: dict(config) for name, config in get_settings().provider_defaults().items()
    }
    for name, config in stored.items():
        merged = {**config}
        stored_key = merged.get("api_key")
        if stored_key:
            merged["api_key"] = decrypt(base64.b64decode(stored_key), key_from_settings())
        resolved.setdefault(name, {}).update(
            {key: value for key, value in merged.items() if value}
        )
    return resolved


async def load_route(session: AsyncSession, task: str) -> TaskRoute:
    if task not in DEFAULT_ROUTES:
        raise KeyError(f"unknown LLM task: {task}")
    default = DEFAULT_ROUTES[task]
    override = (await _load_setting(session, ROUTES_KEY)).get(task)
    if not override:
        return default
    return TaskRoute(
        task=task,
        provider=override.get("provider", default.provider),
        model=override.get("model", default.model),
        temperature=override.get("temperature", default.temperature),
        fallbacks=[tuple(pair) for pair in override.get("fallbacks", default.fallbacks)],
    )


async def call_task(
    session: AsyncSession,
    task: str,
    messages: list[dict[str, str]],
    *,
    schema: dict[str, Any] | None = None,
    scan_id: UUID | None = None,
    max_attempts_per_model: int = 2,
) -> Completion:
    route = await load_route(session, task)
    providers_config = await load_provider_config(session)
    attempts = [(route.provider, route.model), *route.fallbacks]
    # Every attempt is kept: reporting only the last one hides why the primary
    # failed, which is the single most useful fact when a chain exhausts.
    failures: list[str] = []

    for provider_name, model in attempts:
        provider = build_provider(provider_name, providers_config.get(provider_name, {}))
        attempt_error: Exception | None = None

        for attempt in range(max_attempts_per_model):
            try:
                completion = await provider.complete(
                    messages, model=model, schema=schema, temperature=route.temperature
                )
            except Exception as exc:  # noqa: BLE001 - any failure should fall back, not crash
                attempt_error = exc
                if attempt + 1 < max_attempts_per_model:
                    await asyncio.sleep(2**attempt)
                continue
            attempt_error = None
            break

        if attempt_error is not None:
            detail = f"{provider_name}/{model}: {attempt_error}"
            failures.append(detail)
            session.add(
                LLMCall(
                    scan_id=scan_id, purpose=task, provider=provider_name, model=model,
                    tokens_in=0, tokens_out=0, status="failed", error=str(attempt_error)[:2000],
                )
            )
            continue

        session.add(
            LLMCall(
                scan_id=scan_id,
                purpose=task,
                provider=provider_name,
                model=model,
                tokens_in=completion.tokens_in,
                tokens_out=completion.tokens_out,
                latency_ms=completion.latency_ms,
                status="ok",
            )
        )
        return completion

    raise RouteExhaustedError(
        f"all providers failed for task {task}: " + " | ".join(failures)
    )

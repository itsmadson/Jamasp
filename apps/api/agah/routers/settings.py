import base64

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agah.db import get_session
from agah.llm.router import (
    DEFAULT_ROUTES,
    PROVIDERS_KEY,
    ROUTES_KEY,
    build_provider,
    load_provider_config,
)
from agah.models.observability import Setting
from agah.models.user import User
from agah.schemas.settings import (
    REDACTED,
    LLMSettingsOut,
    ProviderConfig,
    ProvidersUpdate,
    RouteConfig,
    RoutesUpdate,
)
from agah.security.crypto import encrypt, key_from_settings
from agah.security.deps import require_admin

router = APIRouter(prefix="/api/settings", tags=["settings"])


async def _upsert(session: AsyncSession, key: str, value: dict, admin: User) -> None:
    row = (await session.scalars(select(Setting).where(Setting.key == key))).one_or_none()
    if row is None:
        session.add(Setting(key=key, value=value, updated_by=admin.id))
    else:
        row.value = value
        row.updated_by = admin.id
    await session.flush()


async def _stored(session: AsyncSession, key: str) -> dict:
    row = (await session.scalars(select(Setting).where(Setting.key == key))).one_or_none()
    return dict(row.value) if row is not None else {}


@router.get("/llm", response_model=LLMSettingsOut)
async def get_llm_settings(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> LLMSettingsOut:
    stored_providers = await _stored(session, PROVIDERS_KEY)
    providers = {
        name: ProviderConfig(
            base_url=config.get("base_url", ""),
            # Redacted, never decrypted for display: the UI has no reason to see it.
            api_key=REDACTED if config.get("api_key") else "",
            extra_headers=config.get("extra_headers"),
        )
        for name, config in stored_providers.items()
    }

    stored_routes = await _stored(session, ROUTES_KEY)
    routes = {}
    for task, default in DEFAULT_ROUTES.items():
        override = stored_routes.get(task, {})
        routes[task] = RouteConfig(
            provider=override.get("provider", default.provider),
            model=override.get("model", default.model),
            temperature=override.get("temperature", default.temperature),
            fallbacks=[tuple(pair) for pair in override.get("fallbacks", default.fallbacks)],
        )

    return LLMSettingsOut(providers=providers, routes=routes)


@router.put("/llm/providers", response_model=LLMSettingsOut)
async def update_providers(
    payload: ProvidersUpdate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> LLMSettingsOut:
    existing = await _stored(session, PROVIDERS_KEY)
    key = key_from_settings()

    for name, config in payload.providers.items():
        stored = existing.get(name, {})
        api_key = stored.get("api_key", "")
        if config.api_key and config.api_key != REDACTED:
            api_key = base64.b64encode(encrypt(config.api_key, key)).decode()
        existing[name] = {
            "base_url": config.base_url,
            "api_key": api_key,
            "extra_headers": config.extra_headers,
        }

    await _upsert(session, PROVIDERS_KEY, existing, admin)
    return await get_llm_settings(session, admin)


@router.put("/llm/routes", response_model=LLMSettingsOut)
async def update_routes(
    payload: RoutesUpdate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> LLMSettingsOut:
    stored = await _stored(session, ROUTES_KEY)
    for task, route in payload.routes.items():
        stored[task] = route.model_dump()
    await _upsert(session, ROUTES_KEY, stored, admin)
    return await get_llm_settings(session, admin)


@router.post("/llm/test")
async def test_provider(
    provider: str,
    model: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    config = (await load_provider_config(session)).get(provider, {})
    client = build_provider(provider, config)
    try:
        await client.complete(
            [{"role": "user", "content": "ping"}], model=model, max_tokens=1
        )
    except Exception as exc:  # noqa: BLE001 - reachability check reports, never raises
        return {"reachable": False, "error": str(exc)}
    return {"reachable": True}

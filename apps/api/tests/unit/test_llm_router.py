import pytest
from sqlalchemy import select

from jamasp.llm.base import Completion
from jamasp.llm.router import RouteExhaustedError, call_task
from jamasp.models.observability import LLMCall


class FakeProvider:
    def __init__(self, name, *, fail=False, text='{"ok": true}'):
        self.name, self.fail, self.text, self.calls = name, fail, text, 0

    async def complete(self, messages, *, model, schema=None, **kw):
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} unavailable")
        return Completion(
            text=self.text, tokens_in=10, tokens_out=20,
            model=model, provider=self.name, latency_ms=5,
        )


@pytest.mark.asyncio
async def test_routes_task_to_configured_provider(session, monkeypatch):
    primary = FakeProvider("openrouter")
    monkeypatch.setattr("jamasp.llm.router.build_provider", lambda name, config: primary)

    result = await call_task(session, "describe_entity", [{"role": "user", "content": "hi"}])
    assert result.text == '{"ok": true}'
    assert primary.calls == 1


@pytest.mark.asyncio
async def test_falls_back_when_primary_fails(session, monkeypatch):
    providers = {
        "openrouter": FakeProvider("openrouter", fail=True),
        "gapgpt": FakeProvider("gapgpt"),
    }
    monkeypatch.setattr("jamasp.llm.router.build_provider", lambda name, config: providers[name])

    result = await call_task(
        session, "describe_entity", [{"role": "user", "content": "hi"}],
        max_attempts_per_model=1,
    )
    assert result.provider == "gapgpt"
    # The default chain tries a second, cheaper OpenRouter model before changing
    # provider, so the failing OpenRouter fake is exercised twice.
    assert providers["openrouter"].calls == 2


@pytest.mark.asyncio
async def test_raises_when_every_provider_fails(session, monkeypatch):
    monkeypatch.setattr(
        "jamasp.llm.router.build_provider", lambda name, config: FakeProvider(name, fail=True)
    )
    with pytest.raises(RouteExhaustedError):
        await call_task(
            session, "describe_entity", [{"role": "user", "content": "hi"}],
            max_attempts_per_model=1,
        )


@pytest.mark.asyncio
async def test_logs_token_usage_for_cost_visibility(session, monkeypatch):
    monkeypatch.setattr(
        "jamasp.llm.router.build_provider", lambda name, config: FakeProvider("openrouter")
    )
    await call_task(session, "describe_entity", [{"role": "user", "content": "hi"}])
    await session.flush()

    logged = (await session.scalars(select(LLMCall))).all()
    assert len(logged) == 1
    assert logged[0].purpose == "describe_entity"
    assert logged[0].tokens_in == 10
    assert logged[0].tokens_out == 20


@pytest.mark.asyncio
async def test_api_key_never_appears_in_log_row(session, monkeypatch):
    monkeypatch.setattr(
        "jamasp.llm.router.build_provider", lambda name, config: FakeProvider("openrouter")
    )
    await call_task(session, "describe_entity", [{"role": "user", "content": "hi"}])
    await session.flush()
    row = (await session.scalars(select(LLMCall))).one()
    assert "sk-" not in repr(row.__dict__)

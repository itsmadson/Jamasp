import pytest
from sqlalchemy import select

from agah.llm.base import Completion
from agah.llm.router import RouteExhaustedError, call_task
from agah.models.observability import LLMCall


class FailingProvider:
    def __init__(self, name: str, message: str) -> None:
        self.name = name
        self.message = message

    async def complete(self, messages, *, model, schema=None, **kwargs):
        raise RuntimeError(f"{self.name}: {self.message}")


@pytest.mark.asyncio
async def test_exhausted_chain_reports_every_provider_not_just_the_last(session, monkeypatch):
    """Otherwise the primary's failure is invisible behind the last fallback's."""
    messages = {
        "openrouter": "rate limit exceeded",
        "gapgpt": "model_not_found",
    }
    monkeypatch.setattr(
        "agah.llm.router.build_provider",
        lambda name, config: FailingProvider(name, messages.get(name, "unavailable")),
    )

    with pytest.raises(RouteExhaustedError) as caught:
        await call_task(
            session, "describe_entity", [{"role": "user", "content": "hi"}],
            max_attempts_per_model=1,
        )

    text = str(caught.value)
    assert "rate limit exceeded" in text, "the primary provider's error was swallowed"
    assert "model_not_found" in text
    assert "nvidia/nemotron-3-ultra-550b-a55b:free" in text


@pytest.mark.asyncio
async def test_each_failed_attempt_is_recorded_for_cost_and_diagnosis(session, monkeypatch):
    monkeypatch.setattr(
        "agah.llm.router.build_provider", lambda name, config: FailingProvider(name, "boom")
    )

    with pytest.raises(RouteExhaustedError):
        await call_task(
            session, "describe_entity", [{"role": "user", "content": "hi"}],
            max_attempts_per_model=1,
        )
    await session.flush()

    logged = (await session.scalars(select(LLMCall))).all()
    # One row per attempted (provider, model), so an admin can see what was tried.
    assert len(logged) == 3
    assert all(row.status == "failed" for row in logged)
    assert all(row.error for row in logged)


@pytest.mark.asyncio
async def test_a_successful_fallback_still_records_the_failure_before_it(session, monkeypatch):
    class Flaky:
        def __init__(self, name):
            self.name = name

        async def complete(self, messages, *, model, schema=None, **kwargs):
            if self.name == "openrouter":
                raise RuntimeError("rate limited")
            return Completion(
                text="{}", tokens_in=1, tokens_out=1,
                model=model, provider=self.name, latency_ms=1,
            )

    monkeypatch.setattr("agah.llm.router.build_provider", lambda name, config: Flaky(name))

    result = await call_task(
        session, "describe_entity", [{"role": "user", "content": "hi"}],
        max_attempts_per_model=1,
    )
    await session.flush()

    assert result.provider == "gapgpt"
    logged = (await session.scalars(select(LLMCall))).all()
    statuses = sorted(row.status for row in logged)
    assert statuses == ["failed", "failed", "ok"]

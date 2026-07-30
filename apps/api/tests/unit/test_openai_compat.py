import httpx
import pytest

from jamasp.llm.openai_compat import OpenAICompatProvider, ProviderResponseError


def _provider(handler) -> OpenAICompatProvider:
    provider = OpenAICompatProvider(
        name="test", base_url="https://example.test/v1", api_key="k"
    )
    provider._transport = httpx.MockTransport(handler)
    return provider


@pytest.mark.asyncio
async def test_reports_a_provider_error_returned_with_http_200():
    """Some gateways answer 200 with an error body. A bare KeyError on 'choices'
    tells an operator nothing; the provider's own message tells them everything."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": {"message": "rate limit exceeded for free tier", "code": 429}},
        )

    with pytest.raises(ProviderResponseError, match="rate limit exceeded"):
        await _provider(handler).complete(
            [{"role": "user", "content": "hi"}], model="m"
        )


@pytest.mark.asyncio
async def test_reports_a_response_with_no_choices_at_all():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "x", "choices": []})

    with pytest.raises(ProviderResponseError, match="no choices"):
        await _provider(handler).complete([{"role": "user", "content": "hi"}], model="m")


@pytest.mark.asyncio
async def test_includes_the_provider_message_on_an_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"message": "response_format json_schema not supported"}}
        )

    with pytest.raises(ProviderResponseError, match="json_schema not supported"):
        await _provider(handler).complete([{"role": "user", "content": "hi"}], model="m")


@pytest.mark.asyncio
async def test_returns_a_completion_on_a_normal_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            },
        )

    completion = await _provider(handler).complete(
        [{"role": "user", "content": "hi"}], model="m"
    )
    assert completion.text == '{"ok": true}'
    assert completion.tokens_in == 10
    assert completion.tokens_out == 4

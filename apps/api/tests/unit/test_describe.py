import json
from pathlib import Path

import pytest

from jamasp.llm.base import Completion
from jamasp.llm.prompts.describe_entity import build_describe_messages
from jamasp.pipeline.describe import DescribeFailed, describe_entity

CASSETTE = json.loads(
    (Path(__file__).parent.parent / "fixtures/cassettes/describe_leave_requests.json").read_text()
)


def _completion(text):
    return Completion(
        text=text, tokens_in=100, tokens_out=200, model="test", provider="test", latency_ms=1
    )


@pytest.mark.asyncio
async def test_produces_bilingual_description(session, monkeypatch, leave_entity, leave_profile):
    async def fake_call(*args, **kwargs):
        return _completion(json.dumps(CASSETTE))

    monkeypatch.setattr("jamasp.pipeline.describe.call_task", fake_call)

    result = await describe_entity(session, leave_entity, leave_profile, [], scan_id=None)
    assert result.summary["fa"] and result.summary["en"]
    assert "مرخصی" in result.summary["fa"]


@pytest.mark.asyncio
async def test_decodes_coded_status_column(session, monkeypatch, leave_entity, leave_profile):
    async def fake_call(*args, **kwargs):
        return _completion(json.dumps(CASSETTE))

    monkeypatch.setattr("jamasp.pipeline.describe.call_task", fake_call)

    result = await describe_entity(session, leave_entity, leave_profile, [], scan_id=None)
    status = next(field for field in result.fields if field["name"] == "status")
    assert status["enum_map"]["2"]["fa"] == "تایید شده"
    assert status["enum_map"]["2"]["en"] == "approved"


@pytest.mark.asyncio
async def test_repairs_malformed_json_on_second_attempt(
    session, monkeypatch, leave_entity, leave_profile
):
    responses = [_completion("not json at all"), _completion(json.dumps(CASSETTE))]

    async def fake_call(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr("jamasp.pipeline.describe.call_task", fake_call)

    result = await describe_entity(session, leave_entity, leave_profile, [], scan_id=None)
    assert result.summary["fa"]
    assert responses == []


@pytest.mark.asyncio
async def test_raises_after_repair_also_fails(session, monkeypatch, leave_entity, leave_profile):
    async def fake_call(*args, **kwargs):
        return _completion("still not json")

    monkeypatch.setattr("jamasp.pipeline.describe.call_task", fake_call)

    with pytest.raises(DescribeFailed):
        await describe_entity(session, leave_entity, leave_profile, [], scan_id=None)


def test_prompt_contains_masked_samples_but_no_raw_pii(employees_entity, employees_profile):
    messages = build_describe_messages(employees_entity, employees_profile, [])
    blob = json.dumps(messages, ensure_ascii=False)
    assert "national_id" in blob  # the column name is useful context
    assert "0079542619" not in blob  # the value is not
    assert "09121234567" not in blob


def test_prompt_includes_neighbor_tables_for_join_reasoning(
    leave_entity, leave_profile, employees_entity
):
    messages = build_describe_messages(leave_entity, leave_profile, [employees_entity])
    blob = json.dumps(messages, ensure_ascii=False)
    assert "employees" in blob

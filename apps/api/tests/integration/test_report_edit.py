import json

import pytest

from jamasp.llm.base import Completion
from jamasp.report.edit import EditRejected, edit_report_spec

COLUMNS = [
    {"name": "status_label", "type": "text"},
    {"name": "request_count", "type": "number"},
]
DATASETS = [
    {"key": "main", "question": "leave by status", "columns": COLUMNS, "row_count": 3}
]

SPEC = {
    "schema_version": "1.0",
    "title": {"fa": "مرخصی به تفکیک وضعیت", "en": "Leave by status"},
    "summary": {"fa": "خلاصه", "en": "Summary"},
    "blocks": [
        {"type": "bar", "title": {"fa": "نمودار", "en": "Chart"},
         "x": "status_label", "y": "request_count", "series": None},
    ],
}


def _completion(payload) -> Completion:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return Completion(
        text=text, tokens_in=10, tokens_out=10, model="stub", provider="stub", latency_ms=1
    )


@pytest.mark.asyncio
async def test_applies_a_requested_block_type_change(session, monkeypatch):
    async def fake_call(session_, task, messages, **kwargs):
        return _completion({
            **SPEC,
            "blocks": [
                {"type": "table", "title": {"fa": "جدول", "en": "Table"},
                 "columns": ["status_label", "request_count"]},
            ],
        })

    monkeypatch.setattr("jamasp.report.edit.call_task", fake_call)

    updated = await edit_report_spec(
        session, SPEC, DATASETS, "به جای نمودار، جدول نشان بده"
    )
    assert [block["type"] for block in updated["blocks"]] == ["table"]


@pytest.mark.asyncio
async def test_keeps_the_title_the_user_did_not_mention(session, monkeypatch):
    async def fake_call(session_, task, messages, **kwargs):
        return _completion({
            **SPEC,
            "blocks": [
                {"type": "line", "title": {"fa": "خطی", "en": "Line"},
                 "x": "status_label", "y": "request_count", "series": None},
            ],
        })

    monkeypatch.setattr("jamasp.report.edit.call_task", fake_call)

    updated = await edit_report_spec(
        session, SPEC, DATASETS, "make it a line")
    assert updated["title"]["fa"] == "مرخصی به تفکیک وضعیت"


@pytest.mark.asyncio
async def test_a_block_naming_a_missing_column_is_dropped_by_the_same_validator(
    session, monkeypatch
):
    async def fake_call(session_, task, messages, **kwargs):
        return _completion({
            **SPEC,
            "blocks": [
                {"type": "bar", "title": {"fa": "الف", "en": "a"},
                 "x": "status_label", "y": "request_count"},
                {"type": "bar", "title": {"fa": "ب", "en": "b"},
                 "x": "invented", "y": "request_count"},
            ],
        })

    monkeypatch.setattr("jamasp.report.edit.call_task", fake_call)

    updated = await edit_report_spec(
        session, SPEC, DATASETS, "add a chart")
    assert len(updated["blocks"]) == 1


@pytest.mark.asyncio
async def test_an_unusable_edit_leaves_the_report_alone(session, monkeypatch):
    async def fake_call(session_, task, messages, **kwargs):
        return _completion("not json at all")

    monkeypatch.setattr("jamasp.report.edit.call_task", fake_call)

    with pytest.raises(EditRejected):
        await edit_report_spec(
        session, SPEC, DATASETS, "??")


@pytest.mark.asyncio
async def test_an_edit_that_would_empty_the_report_is_refused(session, monkeypatch):
    async def fake_call(session_, task, messages, **kwargs):
        # coerce_spec would rescue this into a table; the guard exists for the case
        # where there is genuinely nothing left to show.
        return _completion({**SPEC, "blocks": []})

    monkeypatch.setattr("jamasp.report.edit.call_task", fake_call)

    # An edit that strips a working report down to nothing is refused, so the
    # caller keeps the layout it already had.
    with pytest.raises(EditRejected, match="nothing to show"):
        await edit_report_spec(session, SPEC, [], 0, "remove everything")

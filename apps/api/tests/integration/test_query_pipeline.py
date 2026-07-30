import json

import pytest
import pytest_asyncio

from jamasp.adapters.postgres import PostgresAdapter
from jamasp.llm.base import Completion
from jamasp.query.pipeline import QueryFailed, answer_question

KNOWLEDGE = {
    "schema_version": "1.0",
    "source": {"id": "s1", "name": "HR", "kind": "postgres", "dialect": "postgres"},
    "entities": [
        {
            "id": "e1", "kind": "table", "schema_name": "public", "name": "leave_requests",
            "summary": {"fa": "درخواست‌های مرخصی کارکنان", "en": "Employee leave requests"},
            "grain": "one row per leave request",
            "fields": [
                {"name": "id", "type": "integer", "nullable": False,
                 "meaning": {"fa": "شناسه", "en": "Identifier"},
                 "enum_map": None, "unit": None, "pii_class": "none"},
                {"name": "emp_id", "type": "integer", "nullable": False,
                 "meaning": {"fa": "شناسه کارمند", "en": "Employee id"},
                 "enum_map": None, "unit": None, "pii_class": "none"},
                {"name": "status", "type": "smallint", "nullable": False,
                 "meaning": {"fa": "وضعیت", "en": "Status"},
                 "enum_map": {
                     "1": {"fa": "در انتظار", "en": "pending"},
                     "2": {"fa": "تایید شده", "en": "approved"},
                     "3": {"fa": "رد شده", "en": "rejected"},
                 },
                 "unit": None, "pii_class": "none"},
            ],
            "relationships": [
                {"from": "emp_id", "to": "employees.id", "kind": "inferred",
                 "cardinality": "many_to_one", "confidence": 1.0},
            ],
            "sample_questions": ["افرادی که مرخصی گرفتند"],
        },
        {
            "id": "e2", "kind": "table", "schema_name": "public", "name": "employees",
            "summary": {"fa": "کارکنان", "en": "Employees"},
            "grain": "one row per employee",
            "fields": [
                {"name": "id", "type": "integer", "nullable": False,
                 "meaning": {"fa": "شناسه", "en": "Identifier"},
                 "enum_map": None, "unit": None, "pii_class": "none"},
                {"name": "full_name", "type": "text", "nullable": False,
                 "meaning": {"fa": "نام", "en": "Full name"},
                 "enum_map": None, "unit": None, "pii_class": "low"},
            ],
            "relationships": [],
            "sample_questions": [],
        },
    ],
}


def _completion(payload) -> Completion:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return Completion(
        text=text, tokens_in=100, tokens_out=50, model="stub", provider="stub", latency_ms=1
    )


@pytest_asyncio.fixture
async def adapter(hr_dsn):
    return PostgresAdapter(hr_dsn)


@pytest.mark.asyncio
async def test_answers_a_persian_question_with_real_rows(session, adapter, monkeypatch):
    async def fake_call(session_, task, messages, **kwargs):
        return _completion({
            "sql": (
                "SELECT e.full_name, l.start_date FROM leave_requests l "
                "JOIN employees e ON e.id = l.emp_id WHERE l.status = 2"
            ),
            "explanation": {
                "fa": "کارکنانی که مرخصی تاییدشده دارند",
                "en": "Employees with approved leave",
            },
            "tables_used": ["leave_requests", "employees"],
        })

    monkeypatch.setattr("jamasp.query.pipeline.call_task", fake_call)

    result = await answer_question(
        session, adapter, KNOWLEDGE, "چه کسانی مرخصی تاییدشده دارند؟"
    )

    assert result.row_count == 2  # fixture has two approved leave rows
    assert "full_name" in result.rows[0]
    assert result.explanation["fa"]
    assert result.explanation["en"]
    assert {column["name"] for column in result.columns} == {"full_name", "start_date"}


@pytest.mark.asyncio
async def test_infers_column_types_for_downstream_charting(session, adapter, monkeypatch):
    async def fake_call(session_, task, messages, **kwargs):
        return _completion({
            "sql": "SELECT status, count(*) AS total FROM leave_requests GROUP BY status",
            "explanation": {"fa": "شمارش بر اساس وضعیت", "en": "Count by status"},
            "tables_used": ["leave_requests"],
        })

    monkeypatch.setattr("jamasp.query.pipeline.call_task", fake_call)

    result = await answer_question(session, adapter, KNOWLEDGE, "تعداد مرخصی به تفکیک وضعیت")
    types = {column["name"]: column["type"] for column in result.columns}
    assert types == {"status": "number", "total": "number"}


@pytest.mark.asyncio
async def test_refuses_sql_naming_a_table_nobody_approved(session, adapter, monkeypatch):
    async def fake_call(session_, task, messages, **kwargs):
        return _completion({
            "sql": "SELECT * FROM salaries_secret",
            "explanation": {"fa": "…", "en": "…"},
            "tables_used": ["salaries_secret"],
        })

    monkeypatch.setattr("jamasp.query.pipeline.call_task", fake_call)

    with pytest.raises(QueryFailed) as caught:
        await answer_question(session, adapter, KNOWLEDGE, "مرخصی کارکنان را نشان بده")
    assert caught.value.status == "unsafe"


@pytest.mark.asyncio
async def test_never_executes_a_write(session, adapter, monkeypatch):
    async def fake_call(session_, task, messages, **kwargs):
        return _completion({
            "sql": "DELETE FROM leave_requests",
            "explanation": {"fa": "…", "en": "…"},
            "tables_used": ["leave_requests"],
        })

    monkeypatch.setattr("jamasp.query.pipeline.call_task", fake_call)

    with pytest.raises(QueryFailed) as caught:
        await answer_question(session, adapter, KNOWLEDGE, "مرخصی‌ها را پاک کن")
    assert caught.value.status == "unsafe"

    # And the table is still there.
    rows = await adapter.execute_readonly("SELECT count(*) AS n FROM leave_requests", limit=1)
    assert rows[0]["n"] == 4


@pytest.mark.asyncio
async def test_reports_no_match_instead_of_guessing(session, adapter, monkeypatch):
    async def fake_call(session_, task, messages, **kwargs):
        raise AssertionError("the model must not be called when nothing matched")

    monkeypatch.setattr("jamasp.query.pipeline.call_task", fake_call)

    with pytest.raises(QueryFailed) as caught:
        await answer_question(session, adapter, KNOWLEDGE, "weather forecast for Tehran")
    assert caught.value.status == "no_match"


@pytest.mark.asyncio
async def test_empty_result_is_success_not_failure(session, adapter, monkeypatch):
    async def fake_call(session_, task, messages, **kwargs):
        return _completion({
            "sql": "SELECT * FROM leave_requests WHERE status = 99",
            "explanation": {"fa": "بدون نتیجه", "en": "No matching rows"},
            "tables_used": ["leave_requests"],
        })

    monkeypatch.setattr("jamasp.query.pipeline.call_task", fake_call)

    result = await answer_question(session, adapter, KNOWLEDGE, "مرخصی با وضعیت نامعتبر")
    # An empty answer is an answer.
    assert result.row_count == 0
    assert result.rows == []


@pytest.mark.asyncio
async def test_repairs_malformed_json_once(session, adapter, monkeypatch):
    responses = [
        _completion("not json"),
        _completion({
            "sql": "SELECT count(*) AS n FROM leave_requests",
            "explanation": {"fa": "شمارش", "en": "Count"},
            "tables_used": ["leave_requests"],
        }),
    ]

    async def fake_call(session_, task, messages, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr("jamasp.query.pipeline.call_task", fake_call)

    result = await answer_question(session, adapter, KNOWLEDGE, "چند مرخصی داریم؟")
    assert result.rows[0]["n"] == 4
    assert responses == []


def test_prompt_carries_enum_codes_not_labels():
    from jamasp.query.prompts.generate_sql import build_sql_messages

    messages = build_sql_messages(
        "approved leave", KNOWLEDGE["entities"], "postgres", "en"
    )
    blob = messages[1]["content"]
    # Without the codes the model compares a smallint against a label string and
    # silently returns nothing.
    assert '"2": "approved"' in blob or '"2":"approved"' in blob
    assert "inferred" in blob

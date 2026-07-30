"""Building a multi-panel report against the HR fixture database."""

import json

import pytest
import pytest_asyncio
from sqlalchemy import select

from jamasp.llm.base import Completion
from jamasp.models.query import Query
from jamasp.models.report import Report, ReportStatus
from jamasp.models.source import DataSource, SamplingPolicy, SourceKind
from jamasp.report.build import ReportProgress, build_report
from jamasp.security.crypto import encrypt

TEST_KEY = b"0" * 32

KNOWLEDGE = {
    "entities": [
        {
            "name": "leave_requests",
            "schema_name": "public",
            "summary": {"fa": "درخواست‌های مرخصی", "en": "Leave requests"},
            "fields": [
                {"name": "id", "data_type": "integer"},
                {"name": "emp_id", "data_type": "integer"},
                {"name": "status", "data_type": "integer"},
                {"name": "requested_at", "data_type": "timestamp"},
            ],
        },
        {
            "name": "employees",
            "schema_name": "public",
            "summary": {"fa": "کارمندان", "en": "Employees"},
            "fields": [
                {"name": "id", "data_type": "integer"},
                {"name": "dept_id", "data_type": "integer"},
            ],
        },
    ],
    "relationships": [],
}

PLAN = {
    "title": {"fa": "گزارش مرخصی", "en": "Leave report"},
    "panels": [
        {"key": "by_status", "question": "how many leave requests per status?"},
        {"key": "by_employee", "question": "how many leave requests per employee?"},
    ],
}

DESIGN = {
    "title": {"fa": "گزارش مرخصی", "en": "Leave report"},
    "summary": {"fa": "دو نما", "en": "Two views"},
    "blocks": [
        {"type": "bar", "title": {"fa": "بر اساس وضعیت", "en": "By status"},
         "dataset": "by_status", "span": 2, "x": "status", "y": "total"},
        {"type": "bar", "title": {"fa": "بر اساس کارمند", "en": "By employee"},
         "dataset": "by_employee", "span": 1, "x": "emp_id", "y": "total"},
    ],
}

SQL_BY_STATUS = "SELECT status::text AS status, COUNT(*) AS total FROM leave_requests GROUP BY status"
SQL_BY_EMPLOYEE = "SELECT emp_id::text AS emp_id, COUNT(*) AS total FROM leave_requests GROUP BY emp_id"


@pytest_asyncio.fixture
async def report(session, hr_dsn, monkeypatch):
    monkeypatch.setattr("jamasp.report.build.decrypt_config", lambda source: {"dsn": hr_dsn})
    source = DataSource(
        name="HR",
        kind=SourceKind.POSTGRES,
        config_encrypted=encrypt(json.dumps({"dsn": hr_dsn}), TEST_KEY),
        sampling_policy=SamplingPolicy.MASKED,
    )
    session.add(source)
    await session.flush()
    row = Report(
        data_source_id=source.id,
        question="leave requests by status and by employee",
        locale="fa",
        title={"fa": "x", "en": "x"},
        spec={},
        status=ReportStatus.QUEUED,
    )
    session.add(row)
    await session.flush()
    return row


@pytest.fixture
def model(monkeypatch):
    """Plans two panels, writes SQL for each, then designs a two-block layout."""
    sql_for = {
        "how many leave requests per status?": SQL_BY_STATUS,
        "how many leave requests per employee?": SQL_BY_EMPLOYEE,
    }

    async def fake_call(session_, task, messages, **kwargs):
        if task == "plan_report":
            payload = PLAN
        elif task == "design_report":
            payload = DESIGN
        elif task == "generate_sql":
            asked = json.loads(messages[-1]["content"])["question"]
            payload = {
                "sql": sql_for[asked],
                "explanation": {"fa": "توضیح", "en": "explanation"},
                "tables_used": ["leave_requests"],
                "assumptions": [],
            }
        else:
            raise AssertionError(f"unexpected task {task}")
        return Completion(
            text=json.dumps(payload), tokens_in=10, tokens_out=10,
            model="stub", provider="stub", latency_ms=1,
        )

    monkeypatch.setattr("jamasp.report.build.call_task", fake_call)
    monkeypatch.setattr("jamasp.query.pipeline.call_task", fake_call)


@pytest.mark.asyncio
async def test_each_panel_becomes_its_own_query_and_block(session, report, model):
    steps: list[ReportProgress] = []
    built = await build_report(session, report.id, KNOWLEDGE, progress=steps.append)

    assert built.status is ReportStatus.SUCCEEDED

    datasets = built.spec["datasets"]
    assert [dataset["key"] for dataset in datasets] == ["by_status", "by_employee"]

    # Each block draws from its own panel — the bug that made every chart a chart
    # of everything at once.
    charts = [block for block in built.spec["blocks"] if block["type"] in {"bar", "line"}]
    assert [block["dataset"] for block in charts] == ["by_status", "by_employee"]

    # The page opens with numbers rather than a chart, and every block says
    # something about its own data.
    assert built.spec["blocks"][0]["type"] == "kpi"
    assert all(block.get("narrative", {}).get("fa") for block in built.spec["blocks"])

    # Every panel is a Query of its own, so it lands in history and can be re-run.
    # The stored SQL is the validated form, so match on what distinguishes them.
    saved = (await session.scalars(select(Query))).all()
    assert len(saved) == 2
    assert {"GROUP BY status", "GROUP BY emp_id"} == {
        "GROUP BY status" if "GROUP BY status" in (query.sql or "") else "GROUP BY emp_id"
        for query in saved
    }
    assert all("LIMIT" in (query.sql or "") for query in saved)

    # The steps are reported as they happen, not summarised at the end.
    assert [step.stage for step in steps][:2] == ["plan", "plan"]
    assert any(step.stage == "query" for step in steps)
    assert steps[-1].stage == "design"


@pytest.mark.asyncio
async def test_one_failed_panel_does_not_lose_the_others(session, report, monkeypatch):
    async def fake_call(session_, task, messages, **kwargs):
        if task == "plan_report":
            payload = PLAN
        elif task == "design_report":
            payload = DESIGN
        else:
            asked = json.loads(messages[-1]["content"])["question"]
            if "per employee" in asked:
                # Valid SQL against a table that is not in the knowledge export:
                # the validator must refuse it.
                payload = {"sql": "SELECT * FROM salaries", "explanation": {"fa": "", "en": ""},
                           "tables_used": ["salaries"], "assumptions": []}
            else:
                payload = {"sql": SQL_BY_STATUS, "explanation": {"fa": "", "en": ""},
                           "tables_used": ["leave_requests"], "assumptions": []}
        return Completion(
            text=json.dumps(payload), tokens_in=10, tokens_out=10,
            model="stub", provider="stub", latency_ms=1,
        )

    monkeypatch.setattr("jamasp.report.build.call_task", fake_call)
    monkeypatch.setattr("jamasp.query.pipeline.call_task", fake_call)

    built = await build_report(session, report.id, KNOWLEDGE, progress=lambda event: None)

    assert built.status is ReportStatus.PARTIAL
    assert [dataset["key"] for dataset in built.spec["datasets"]] == ["by_status"]
    assert "by_employee" in (built.error or "")
    # The panel that worked is still drawn.
    assert built.spec["blocks"]


@pytest.mark.asyncio
async def test_a_failed_plan_falls_back_to_one_panel(session, report, monkeypatch):
    """Planning is an optimisation; losing it must not lose the report."""

    async def fake_call(session_, task, messages, **kwargs):
        if task == "plan_report":
            raise ConnectionError("planner unreachable")
        if task == "design_report":
            return Completion(
                text=json.dumps({
                    "title": {"fa": "گ", "en": "R"}, "summary": {"fa": "", "en": ""},
                    "blocks": [{"type": "bar", "title": {"fa": "الف", "en": "a"},
                                "dataset": "main", "x": "status", "y": "total"}],
                }),
                tokens_in=1, tokens_out=1, model="stub", provider="stub", latency_ms=1,
            )
        return Completion(
            text=json.dumps({"sql": SQL_BY_STATUS, "explanation": {"fa": "", "en": ""},
                             "tables_used": ["leave_requests"], "assumptions": []}),
            tokens_in=1, tokens_out=1, model="stub", provider="stub", latency_ms=1,
        )

    monkeypatch.setattr("jamasp.report.build.call_task", fake_call)
    monkeypatch.setattr("jamasp.query.pipeline.call_task", fake_call)

    built = await build_report(session, report.id, KNOWLEDGE, progress=lambda event: None)

    assert built.status is ReportStatus.SUCCEEDED
    assert [dataset["key"] for dataset in built.spec["datasets"]] == ["main"]

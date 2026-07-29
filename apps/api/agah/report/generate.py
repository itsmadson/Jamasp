"""Turn an answered question into a report layout."""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agah.llm.router import call_task
from agah.query.pipeline import QueryResult
from agah.report.prompts.design_report import REPORT_SCHEMA, build_report_messages
from agah.report.spec import coerce_spec, fallback_spec


async def design_report(
    session: AsyncSession,
    answer: QueryResult,
    locale: str = "fa",
) -> dict[str, Any]:
    """Never raises: a report that renders the data plainly beats an error page."""
    title = {"fa": answer.question, "en": answer.question}

    messages = build_report_messages(
        answer.question, answer.columns, answer.rows, answer.row_count, locale
    )

    try:
        completion = await call_task(
            session, "design_report", messages, schema=REPORT_SCHEMA
        )
        proposed = json.loads(completion.text)
    except json.JSONDecodeError:
        proposed = None
    except Exception:  # noqa: BLE001 - a missing model must not cost the user their data
        return fallback_spec(title, answer.columns, answer.row_count)

    if proposed is None:
        return fallback_spec(title, answer.columns, answer.row_count)

    return coerce_spec(proposed, answer.columns, answer.row_count)

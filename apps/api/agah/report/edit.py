"""Stage S4: change a report by describing the change.

Editing a spec rather than regenerating code is what makes this tractable — the
model returns a layout, the same validator that guards generation guards the edit,
and a nonsensical instruction leaves the report exactly as it was.
"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agah.llm.router import call_task
from agah.report.prompts.edit_report import EDIT_SCHEMA, build_edit_messages
from agah.report.spec import coerce_spec


class EditRejected(Exception):
    pass


async def edit_report_spec(
    session: AsyncSession,
    spec: dict[str, Any],
    columns: list[dict[str, str]],
    row_count: int,
    instruction: str,
    locale: str = "fa",
) -> dict[str, Any]:
    messages = build_edit_messages(spec, columns, instruction, locale)

    try:
        completion = await call_task(session, "edit_report", messages, schema=EDIT_SCHEMA)
        proposed = json.loads(completion.text)
    except json.JSONDecodeError as exc:
        raise EditRejected(f"the model returned no usable layout: {exc}") from exc
    except Exception as exc:
        raise EditRejected(str(exc)) from exc

    updated = coerce_spec(proposed, columns, row_count)

    # An instruction the data cannot support should be a no-op, not a report that
    # silently lost its charts.
    if not updated.get("blocks") and spec.get("blocks"):
        raise EditRejected("that change would leave the report with nothing to show")

    return updated

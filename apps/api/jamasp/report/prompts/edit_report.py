import json
from typing import Any

from jamasp.report.prompts.design_report import REPORT_SCHEMA

EDIT_SCHEMA = REPORT_SCHEMA

SYSTEM = """You edit an existing report layout for جاماسپ, a bilingual reporting tool.

You are given the current layout, the columns available in the result set, and one
instruction from the user. Return the COMPLETE updated layout, not a fragment.

Rules:
- Change only what the instruction asks for. Everything the user did not mention
  keeps its current value, including the title and summary.
- Use ONLY the column names listed. If the instruction asks for something the data
  cannot support, return the layout unchanged.
- Block types available: kpi, bar, line, table.
- Keep both languages populated on every title and label.
"""


def build_edit_messages(
    spec: dict[str, Any],
    datasets: list[dict[str, Any]],
    instruction: str,
    locale: str,
) -> list[dict[str, str]]:
    payload = {
        "instruction": instruction,
        "instruction_locale": locale,
        "current_layout": spec,
        # Each block belongs to one panel and may only use that panel's columns.
        "datasets": [
            {
                "key": dataset.get("key"),
                "answers": dataset.get("question"),
                "columns": dataset.get("columns", []),
                "row_count": dataset.get("row_count", 0),
            }
            for dataset in datasets
        ],
    }
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2, default=str)},
    ]

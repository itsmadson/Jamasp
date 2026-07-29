import json
from typing import Any

BILINGUAL = {
    "type": "object",
    "properties": {"fa": {"type": "string"}, "en": {"type": "string"}},
    "required": ["fa", "en"],
}

REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": BILINGUAL,
        "summary": BILINGUAL,
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["kpi", "bar", "line", "table"]},
                    "title": BILINGUAL,
                    "x": {"type": ["string", "null"]},
                    "y": {"type": ["string", "null"]},
                    "series": {"type": ["string", "null"]},
                    "column": {"type": ["string", "null"]},
                    "aggregate": {"type": ["string", "null"]},
                    "columns": {"type": ["array", "null"], "items": {"type": "string"}},
                },
                "required": ["type", "title"],
            },
        },
    },
    "required": ["title", "summary", "blocks"],
}

SYSTEM = """You design report layouts for آگاه, a bilingual (Persian/English) tool.

You are given the question a user asked, the columns the query returned, and a few
sample rows. Choose how to present the answer.

Block types, and when each is right:
- "kpi"   a single headline number. Use when the answer is one value.
- "bar"   a numeric value across a small set of categories.
- "line"  a numeric value over time. Use whenever a date or timestamp column exists.
- "table" the honest choice for detail rows, many categories, or text-only results.

Rules:
- Use ONLY the column names given. Do not invent columns.
- Title and summary in BOTH Persian and English. The summary states what the reader
  is looking at, in one sentence — not how the query worked.
- Lead with the block that answers the question. Add a table only when the detail
  rows are worth reading.
- Two or three blocks is usually right. A page of charts about the same number is
  noise, not analysis.
"""


def build_report_messages(
    question: str,
    columns: list[dict[str, str]],
    rows: list[dict[str, Any]],
    row_count: int,
    locale: str,
) -> list[dict[str, str]]:
    payload = {
        "question": question,
        "question_locale": locale,
        "row_count": row_count,
        "columns": columns,
        "sample_rows": rows[:5],
    }
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2, default=str)},
    ]

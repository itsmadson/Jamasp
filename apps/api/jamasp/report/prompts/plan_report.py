"""Split one request into the focused questions a report is actually made of.

A request like "user growth by month, province and role" is three questions, not
one. Asked as one, the model writes a UNION that welds unrelated rows into a
single result set, and every chart drawn from it is a chart of everything at once.
Planning first means each panel gets its own query and its own honest axes.
"""

import json
from typing import Any

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "object",
            "properties": {"fa": {"type": "string"}, "en": {"type": "string"}},
            "required": ["fa", "en"],
        },
        "panels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "question": {"type": "string"},
                    "intent": {"type": "string"},
                },
                "required": ["key", "question"],
            },
        },
    },
    "required": ["title", "panels"],
}

SYSTEM = """You plan reports for جاماسپ, a bilingual (Persian/English) data tool.

You are given a user's request and a summary of the tables available. Break the
request into the separate questions the report needs to answer.

Each panel becomes its own SQL query, drawn as its own chart.

Rules:
- One measurement per panel. "Users per month" and "users per province" are two
  panels, never one — they share no axis and cannot share a chart.
- Write each panel's `question` as a complete, standalone question in the same
  language the user used. It will be handed to a SQL writer that sees only that
  sentence, so it must not depend on the other panels or on the original wording.
- `key` is a short lowercase ascii slug: monthly_growth, by_province, by_role.
- Between 1 and 6 panels. If the request truly asks one thing, return one panel.
- Never plan a panel the available tables cannot answer.
- `title` describes the whole report, in both languages.
"""


def build_plan_messages(
    question: str,
    knowledge: dict[str, Any],
    locale: str,
) -> list[dict[str, str]]:
    entities = [
        {
            "name": entity.get("name"),
            "summary": (entity.get("summary") or {}).get(locale)
            or (entity.get("summary") or {}).get("en"),
            "columns": [field.get("name") for field in (entity.get("fields") or [])],
        }
        for entity in (knowledge.get("entities") or [])
    ]
    payload = {
        "request": question,
        "request_locale": locale,
        "tables": entities,
    }
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2, default=str)},
    ]

import json
from typing import Any

GENERATE_SQL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sql": {"type": "string"},
        "explanation": {
            "type": "object",
            "properties": {"fa": {"type": "string"}, "en": {"type": "string"}},
            "required": ["fa", "en"],
        },
        "tables_used": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sql", "explanation", "tables_used"],
}

SYSTEM = """You write SQL for آگاه, a bilingual (Persian/English) reporting tool.

You are given a verified description of the only tables you may use, and a question
in Persian or English. Return one SQL SELECT that answers it.

Rules:
- {dialect} dialect. A single SELECT statement. Never write, never modify, never DDL.
- Use ONLY the tables and columns given below. If the question cannot be answered
  from them, return an empty sql string and say why in the explanation.
- Coded columns carry a decoding. Compare against the CODE, never the label:
  `WHERE status = 2`, never `WHERE status = 'approved'`.
- But when a coded column is GROUPED BY or SELECTED for display, also project the
  human label with a CASE, aliased clearly:
  `CASE status WHEN 1 THEN 'در انتظار' WHEN 2 THEN 'تایید شده' END AS status_label`.
  Use the labels in the question's language. A chart axis reading 1, 2, 3 is one
  nobody can read.
- Relationships marked "inferred" are real and verified; join on them exactly as given.
- Persian questions about dates refer to the Jalali calendar as the user experiences
  it, but the stored values are Gregorian. "این ماه" means the current Gregorian month
  unless the schema says otherwise. State any such reading in `assumptions`.
- Explain what the query does in BOTH Persian and English. The person reading it may
  not read SQL, and that explanation is how they judge whether you answered them.
"""


def _render_entity(entity: dict[str, Any]) -> dict[str, Any]:
    summary = entity.get("summary") or {}
    columns = []
    for field in entity.get("fields") or []:
        meaning = field.get("meaning") or {}
        column: dict[str, Any] = {
            "name": field["name"],
            "type": field.get("type"),
            "meaning_fa": meaning.get("fa", ""),
            "meaning_en": meaning.get("en", ""),
        }
        if field.get("enum_map"):
            # The single highest-value line in this prompt: without it the model
            # compares a smallint against a label string and silently returns nothing.
            column["codes"] = {
                code: label.get("en") or label.get("fa")
                for code, label in field["enum_map"].items()
            }
        if field.get("unit"):
            column["unit"] = field["unit"]
        columns.append(column)

    return {
        "table": f"{entity['schema_name']}.{entity['name']}",
        "purpose_fa": summary.get("fa", ""),
        "purpose_en": summary.get("en", ""),
        "grain": entity.get("grain"),
        "columns": columns,
        "joins": [
            {
                "from": f"{entity['name']}.{relationship['from']}",
                "to": relationship["to"],
                "kind": relationship.get("kind"),
            }
            for relationship in entity.get("relationships") or []
        ],
    }


def build_sql_messages(
    question: str,
    entities: list[dict[str, Any]],
    dialect: str,
    locale: str,
) -> list[dict[str, str]]:
    payload = {
        "question": question,
        "question_locale": locale,
        "schema": [_render_entity(entity) for entity in entities],
    }
    return [
        {"role": "system", "content": SYSTEM.format(dialect=dialect)},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]

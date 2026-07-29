import json
from typing import Any

from agah.pipeline.profile import EntityProfile
from agah.pipeline.snapshot import EntitySnapshot

BILINGUAL = {
    "type": "object",
    "properties": {"fa": {"type": "string"}, "en": {"type": "string"}},
    "required": ["fa", "en"],
}

DESCRIBE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": BILINGUAL,
        "grain": {"type": "string"},
        "business_domain": {"type": "string"},
        "common_questions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "meaning": BILINGUAL,
                    "unit": {"type": ["string", "null"]},
                    "enum_values": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string"},
                                "fa": {"type": "string"},
                                "en": {"type": "string"},
                            },
                            "required": ["code", "fa", "en"],
                        },
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["name", "meaning", "confidence"],
            },
        },
    },
    "required": ["summary", "grain", "fields", "confidence"],
}

SYSTEM = """You are a database analyst for آگاه, a bilingual (Persian/English) reporting tool.
Given a table's structure and masked sample values, explain what it means in business terms.

Rules:
- Write every summary and meaning in BOTH Persian (fa) and English (en). They must say the same
  thing.
- Coded columns (integer status/type columns with few distinct values) are the priority: infer
  what each code means and fill enum_values with one entry per code. Column comments often contain the decoding.
- Values shown as *** are masked personal data. Never speculate about the hidden characters.
- Report low confidence honestly when the evidence is weak. A wrong confident guess is worse than
  an admitted uncertainty, because a human reviews this and trusts your confidence signal.
"""


def build_describe_messages(
    entity: EntitySnapshot,
    profile: EntityProfile,
    neighbors: list[EntitySnapshot],
) -> list[dict[str, str]]:
    # Keyed by name, never by position: a reordered profile must not shift meanings
    # onto the wrong columns.
    profiles = {column.name: column for column in profile.columns}

    columns = []
    for column in entity.columns:
        column_profile = profiles.get(column.name)
        columns.append({
            "name": column.name,
            "type": column.data_type,
            "nullable": column.nullable,
            "is_pk": column.is_pk,
            "comment": column.comment,
            "distinct_count": column_profile.distinct_count if column_profile else None,
            "null_ratio": column_profile.null_ratio if column_profile else None,
            "sample_values": column_profile.sample_values if column_profile else [],
            "pii_class": str(column_profile.pii_class) if column_profile else "unknown",
        })

    payload = {
        "table": {
            "schema": entity.schema_name,
            "name": entity.name,
            "kind": entity.kind,
            "comment": entity.comment,
            "row_count_approx": entity.row_count_approx,
            "columns": columns,
            "foreign_keys": [
                {
                    "from": list(foreign_key.from_columns),
                    "to": f"{foreign_key.to_table}.{foreign_key.to_columns[0]}",
                }
                for foreign_key in entity.foreign_keys
            ],
            "sample_rows": profile.sample_rows[:5],
        },
        "related_tables": [
            {"name": neighbor.name, "columns": [column.name for column in neighbor.columns]}
            for neighbor in neighbors
        ],
    }

    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2, default=str)},
    ]

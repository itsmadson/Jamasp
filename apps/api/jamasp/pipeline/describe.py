"""Stage 3: turn structure plus masked samples into bilingual business meaning."""

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from jamasp.llm.prompts.describe_entity import DESCRIBE_SCHEMA, build_describe_messages
from jamasp.llm.router import call_task
from jamasp.pipeline.profile import EntityProfile
from jamasp.pipeline.snapshot import EntitySnapshot

REQUIRED_KEYS = ("summary", "grain", "fields", "confidence")


class DescribeFailed(Exception):
    pass


@dataclass
class EntityDescription:
    summary: dict[str, str]
    grain: str
    business_domain: str | None
    common_questions: list[str]
    fields: list[dict[str, Any]]
    confidence: float

    def to_json(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "grain": self.grain,
            "business_domain": self.business_domain,
            "common_questions": self.common_questions,
            "confidence": self.confidence,
        }


def _normalise_enum(field: dict[str, Any]) -> dict[str, Any]:
    """Accept the list the schema asks for, and the map older records already hold.

    Strict JSON schema cannot describe an open-ended map, so the model returns a
    list of {code, fa, en}; everything downstream expects {code: {fa, en}}.
    """
    values = field.pop("enum_values", None)
    if isinstance(values, list):
        field["enum_map"] = {
            str(item["code"]): {"fa": item.get("fa", ""), "en": item.get("en", "")}
            for item in values
            if isinstance(item, dict) and item.get("code") is not None
        } or None
    elif "enum_map" not in field:
        field["enum_map"] = None
    return field


def _parse(text: str) -> EntityDescription:
    payload = json.loads(text)
    missing = [key for key in REQUIRED_KEYS if key not in payload]
    if missing:
        raise ValueError(f"response missing required keys: {missing}")
    summary = payload["summary"]
    if not isinstance(summary, dict) or not {"fa", "en"} <= summary.keys():
        raise ValueError("summary must contain both 'fa' and 'en'")
    return EntityDescription(
        summary=summary,
        grain=payload["grain"],
        business_domain=payload.get("business_domain"),
        common_questions=payload.get("common_questions", []),
        fields=[_normalise_enum(dict(field)) for field in payload["fields"]],
        confidence=float(payload["confidence"]),
    )


async def describe_entity(
    session: AsyncSession,
    entity: EntitySnapshot,
    profile: EntityProfile,
    neighbors: list[EntitySnapshot],
    scan_id: UUID | None,
) -> EntityDescription:
    messages = build_describe_messages(entity, profile, neighbors)

    completion = await call_task(
        session, "describe_entity", messages, schema=DESCRIBE_SCHEMA, scan_id=scan_id
    )
    try:
        return _parse(completion.text)
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as first_error:
        repair = [
            *messages,
            {"role": "assistant", "content": completion.text},
            {
                "role": "user",
                "content": (
                    f"That response could not be parsed: {first_error}. "
                    f"Reply with valid JSON matching the schema and nothing else."
                ),
            },
        ]
        retry = await call_task(
            session, "describe_entity", repair, schema=DESCRIBE_SCHEMA, scan_id=scan_id
        )
        try:
            return _parse(retry.text)
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as second_error:
            raise DescribeFailed(
                f"{entity.schema_name}.{entity.name}: unparseable after repair "
                f"({second_error})"
            ) from second_error

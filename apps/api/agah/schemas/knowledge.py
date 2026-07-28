"""The contract S2 consumes. Stable independent of internal storage."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

SCHEMA_VERSION = "1.0"


class Bilingual(BaseModel):
    fa: str = ""
    en: str = ""


class KnowledgeField(BaseModel):
    name: str
    type: str
    nullable: bool
    meaning: Bilingual
    enum_map: dict[str, Any] | None = None
    unit: str | None = None
    pii_class: str


class KnowledgeRelationship(BaseModel):
    from_: str
    to: str
    kind: str
    cardinality: str | None = None
    confidence: float | None = None

    model_config = {"populate_by_name": True}

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        data["from"] = data.pop("from_")
        return data


class KnowledgeEntity(BaseModel):
    id: UUID
    kind: str
    schema_name: str
    name: str
    summary: Bilingual
    grain: str | None = None
    business_domain: str | None = None
    row_count_approx: int | None = None
    fields: list[KnowledgeField]
    relationships: list[dict[str, Any]]
    sample_questions: list[str] = []


class KnowledgeSource(BaseModel):
    id: UUID
    name: str
    kind: str
    dialect: str


class KnowledgeExport(BaseModel):
    schema_version: str = SCHEMA_VERSION
    source: KnowledgeSource
    generated_at: datetime
    entities: list[KnowledgeEntity]

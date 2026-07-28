from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from agah.models.entity import EntityStatus, PIIClass


class FieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    data_type: str
    nullable: bool
    is_pk: bool
    ordinal: int
    meaning_ai: dict[str, Any] | None = None
    meaning_human: dict[str, Any] | None = None
    enum_map: dict[str, Any] | None = None
    unit: str | None = None
    pii_class: PIIClass
    confidence: float | None = None


class EntitySummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    schema_name: str
    name: str
    status: EntityStatus
    confidence: float | None = None
    row_count_approx: int | None = None
    version: int


class EntityOut(EntitySummaryOut):
    structural: dict[str, Any]
    description_ai: dict[str, Any] | None = None
    description_human: dict[str, Any] | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    fields: list[FieldOut] = []


class EntityListOut(BaseModel):
    items: list[EntitySummaryOut]
    total: int


class FieldPatch(BaseModel):
    id: UUID
    meaning_human: dict[str, Any] | None = None
    enum_map: dict[str, Any] | None = None
    unit: str | None = None


class EntityPatch(BaseModel):
    description_human: dict[str, Any] | None = None
    fields: list[FieldPatch] | None = None


class BulkApproveRequest(BaseModel):
    min_confidence: float = 0.0


class BulkApproveResult(BaseModel):
    approved_count: int

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jamasp.models.base import Base, TimestampMixin, UUIDMixin

EMBEDDING_DIM = 1024


class EntityStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    STALE = "stale"
    IGNORED = "ignored"
    ARCHIVED = "archived"
    DESCRIBE_FAILED = "describe_failed"


class PIIClass(enum.StrEnum):
    NONE = "none"
    LOW = "low"
    HIGH = "high"


class Entity(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("data_source_id", "schema_name", "name", name="uq_entity_identity"),
    )

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    schema_name: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    structural: Mapped[dict[str, Any]] = mapped_column(JSONB)
    structural_hash: Mapped[str] = mapped_column(String(64))
    description_ai: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    description_human: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False), default=EntityStatus.PENDING, index=True
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    version: Mapped[int] = mapped_column(Integer, default=1)
    row_count_approx: Mapped[int | None] = mapped_column(Integer)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source = relationship("DataSource", back_populates="entities")
    fields = relationship(
        "Field", back_populates="entity", cascade="all, delete-orphan", order_by="Field.ordinal"
    )


class Field(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "fields"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    data_type: Mapped[str] = mapped_column(String(100))
    nullable: Mapped[bool] = mapped_column(default=True)
    is_pk: Mapped[bool] = mapped_column(default=False)
    ordinal: Mapped[int] = mapped_column(Integer)
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    meaning_ai: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    meaning_human: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    enum_map: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    unit: Mapped[str | None] = mapped_column(String(50))
    pii_class: Mapped[PIIClass] = mapped_column(
        Enum(PIIClass, native_enum=False), default=PIIClass.NONE
    )
    confidence: Mapped[float | None] = mapped_column(Float)

    entity = relationship("Entity", back_populates="fields")

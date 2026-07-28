import enum
import uuid
from typing import Any

from sqlalchemy import Enum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agah.models.base import Base, TimestampMixin, UUIDMixin


class RelationshipKind(enum.StrEnum):
    DECLARED = "declared"
    INFERRED = "inferred"


class RelationshipStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Relationship(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "relationships"

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), index=True
    )
    from_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    from_field: Mapped[str] = mapped_column(String(200))
    to_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    to_field: Mapped[str] = mapped_column(String(200))
    kind: Mapped[RelationshipKind] = mapped_column(Enum(RelationshipKind, native_enum=False))
    cardinality: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[RelationshipStatus] = mapped_column(
        Enum(RelationshipStatus, native_enum=False), default=RelationshipStatus.PENDING
    )

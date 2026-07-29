import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agah.models.base import Base, TimestampMixin, UUIDMixin


class QueryStatus(enum.StrEnum):
    SUCCEEDED = "succeeded"
    NO_MATCH = "no_match"
    GENERATION_FAILED = "generation_failed"
    UNSAFE = "unsafe"
    EXECUTION_FAILED = "execution_failed"


class Query(Base, UUIDMixin, TimestampMixin):
    """One asked question. History is what S4 later edits and what makes a
    report reproducible."""

    __tablename__ = "queries"

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(String(5), default="fa")
    sql: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    tables_used: Mapped[list[str] | None] = mapped_column(JSONB)
    assumptions: Mapped[list[str] | None] = mapped_column(JSONB)
    status: Mapped[QueryStatus] = mapped_column(Enum(QueryStatus, native_enum=False))
    row_count: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

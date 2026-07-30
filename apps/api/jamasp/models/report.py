import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jamasp.models.base import Base, TimestampMixin, UUIDMixin


class ReportStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class Report(Base, UUIDMixin, TimestampMixin):
    """A saved report: its layout and the queries that fill it.

    Building one means planning panels, writing SQL for each, and designing a
    layout — several model calls, minutes on a slow provider. So it is built as a
    background job with a status, exactly like a scan, and the browser follows
    along instead of holding a request open until it gives up.
    """

    __tablename__ = "reports"

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), index=True
    )
    query_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("queries.id", ondelete="SET NULL")
    )
    question: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status", native_enum=False),
        default=ReportStatus.QUEUED,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text)
    title: Mapped[dict[str, Any]] = mapped_column(JSONB)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    locale: Mapped[str] = mapped_column(String(5), default="fa")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

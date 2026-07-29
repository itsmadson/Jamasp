import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agah.models.base import Base, TimestampMixin, UUIDMixin


class Report(Base, UUIDMixin, TimestampMixin):
    """A saved report: its layout and the query that fills it.

    Both are stored so a report can be re-run against fresh data without asking
    the model to design it again.
    """

    __tablename__ = "reports"

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), index=True
    )
    query_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("queries.id", ondelete="SET NULL")
    )
    title: Mapped[dict[str, Any]] = mapped_column(JSONB)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    locale: Mapped[str] = mapped_column(String(5), default="fa")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

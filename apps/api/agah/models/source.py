import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agah.models.base import Base, TimestampMixin, UUIDMixin


class SourceKind(enum.StrEnum):
    POSTGRES = "postgres"
    MYSQL = "mysql"
    MSSQL = "mssql"
    ORACLE = "oracle"
    REST = "rest"
    MCP = "mcp"


class SamplingPolicy(enum.StrEnum):
    MASKED = "masked"
    SCHEMA_ONLY = "schema_only"


class SourceStatus(enum.StrEnum):
    DRAFT = "draft"
    SCANNING = "scanning"
    READY = "ready"
    ERROR = "error"


class DataSource(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[SourceKind] = mapped_column(Enum(SourceKind, native_enum=False))
    config_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    sampling_policy: Mapped[SamplingPolicy] = mapped_column(
        Enum(SamplingPolicy, native_enum=False), default=SamplingPolicy.MASKED
    )
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, native_enum=False), default=SourceStatus.DRAFT
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    entities = relationship("Entity", back_populates="source", cascade="all, delete-orphan")
    scans = relationship("Scan", back_populates="source", cascade="all, delete-orphan")

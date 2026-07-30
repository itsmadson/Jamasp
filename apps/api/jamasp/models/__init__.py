"""SQLAlchemy models. Import every module here so Alembic autogenerate sees them."""

from jamasp.models.base import Base
from jamasp.models.entity import Entity, EntityStatus, Field, PIIClass
from jamasp.models.observability import LLMCall, Setting
from jamasp.models.query import Query, QueryStatus
from jamasp.models.relationship import Relationship, RelationshipKind, RelationshipStatus
from jamasp.models.report import Report
from jamasp.models.scan import Scan, ScanStatus
from jamasp.models.source import DataSource, SamplingPolicy, SourceKind, SourceStatus
from jamasp.models.user import User, UserRole

__all__ = [
    "Base",
    "DataSource",
    "Entity",
    "EntityStatus",
    "Field",
    "LLMCall",
    "PIIClass",
    "Query",
    "QueryStatus",
    "Relationship",
    "RelationshipKind",
    "RelationshipStatus",
    "Report",
    "SamplingPolicy",
    "Scan",
    "ScanStatus",
    "Setting",
    "SourceKind",
    "SourceStatus",
    "User",
    "UserRole",
]

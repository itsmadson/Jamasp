from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr

from agah.models.source import SamplingPolicy, SourceKind, SourceStatus


class SourceCreate(BaseModel):
    name: str
    kind: SourceKind
    dsn: SecretStr
    sampling_policy: SamplingPolicy = SamplingPolicy.MASKED


class ConnectionTestRequest(BaseModel):
    kind: SourceKind
    dsn: SecretStr


class ConnectionTestResult(BaseModel):
    healthy: bool
    server_version: str = ""
    error: str | None = None


class SourceOut(BaseModel):
    """Carries no credential field of any kind, by construction rather than by exclusion."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    kind: SourceKind
    sampling_policy: SamplingPolicy
    status: SourceStatus
    created_at: datetime
    last_scan_at: datetime | None = None

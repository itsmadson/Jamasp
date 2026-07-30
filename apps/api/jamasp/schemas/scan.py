from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from jamasp.models.scan import ScanStatus


class ScanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    data_source_id: UUID
    status: ScanStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stats: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

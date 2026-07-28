import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agah.adapters.registry import adapter_for
from agah.db import get_session
from agah.models.scan import Scan, ScanStatus
from agah.models.source import DataSource
from agah.models.user import User
from agah.queue import JobQueue, get_queue
from agah.schemas.scan import ScanOut
from agah.schemas.source import (
    ConnectionTestRequest,
    ConnectionTestResult,
    SourceCreate,
    SourceOut,
)
from agah.security.crypto import encrypt, key_from_settings
from agah.security.deps import current_user, require_admin

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[SourceOut])
async def list_sources(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> list[SourceOut]:
    rows = (await session.scalars(select(DataSource).order_by(DataSource.created_at))).all()
    return [SourceOut.model_validate(row) for row in rows]


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> SourceOut:
    source = DataSource(
        name=payload.name,
        kind=payload.kind,
        config_encrypted=encrypt(
            json.dumps({"dsn": payload.dsn.get_secret_value()}), key_from_settings()
        ),
        sampling_policy=payload.sampling_policy,
        created_by=admin.id,
    )
    session.add(source)
    await session.flush()
    return SourceOut.model_validate(source)


@router.post("/test-connection", response_model=ConnectionTestResult)
async def test_connection(
    payload: ConnectionTestRequest,
    admin: User = Depends(require_admin),
) -> ConnectionTestResult:
    adapter = adapter_for(payload.kind, {"dsn": payload.dsn.get_secret_value()})
    report = await adapter.test_connection()
    return ConnectionTestResult(
        healthy=report.healthy, server_version=report.server_version, error=report.error
    )


@router.get("/{source_id}", response_model=SourceOut)
async def get_source(
    source_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> SourceOut:
    source = await session.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    return SourceOut.model_validate(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: UUID,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> None:
    source = await session.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    await session.delete(source)
    await session.flush()


@router.post("/{source_id}/scans", response_model=ScanOut, status_code=status.HTTP_202_ACCEPTED)
async def start_scan(
    source_id: UUID,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
    queue: JobQueue = Depends(get_queue),
) -> ScanOut:
    source = await session.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")

    scan = Scan(data_source_id=source.id, status=ScanStatus.QUEUED)
    session.add(scan)
    await session.flush()
    await queue.enqueue_job("scan_task", str(scan.id))
    return ScanOut.model_validate(scan)

import json
from collections.abc import AsyncIterator
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agah.config import get_settings
from agah.db import get_session
from agah.models.scan import Scan
from agah.models.user import User
from agah.pipeline.worker import progress_channel
from agah.schemas.scan import ScanOut
from agah.security.deps import current_user

router = APIRouter(prefix="/api/scans", tags=["scans"])

TERMINAL_STAGE = "done"


async def get_progress_source():
    """Redis pub/sub, isolated so tests can substitute a finite stream."""
    return aioredis.from_url(get_settings().redis_url)


@router.get("/{scan_id}", response_model=ScanOut)
async def get_scan(
    scan_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> ScanOut:
    scan = await session.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scan not found")
    return ScanOut.model_validate(scan)


@router.get("/{scan_id}/events")
async def scan_events(
    scan_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
    progress_source=Depends(get_progress_source),
) -> StreamingResponse:
    scan = await session.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scan not found")

    async def stream() -> AsyncIterator[str]:
        # Emit current state first, so a client attaching late is never blank.
        yield f"data: {json.dumps({'stage': 'status', 'status': str(scan.status)})}\n\n"

        pubsub = progress_source.pubsub()
        await pubsub.subscribe(progress_channel(scan_id))
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                payload = message["data"]
                if isinstance(payload, bytes):
                    payload = payload.decode()
                yield f"data: {payload}\n\n"
                if json.loads(payload).get("stage") == TERMINAL_STAGE:
                    break
        finally:
            await pubsub.unsubscribe(progress_channel(scan_id))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

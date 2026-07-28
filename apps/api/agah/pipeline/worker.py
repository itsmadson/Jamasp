"""arq worker: runs scans off the request path and publishes progress to Redis.

The API streams that Redis channel to the browser as SSE, so a scan of a
200-table database reports live instead of blocking a request for minutes.
"""

import json
from dataclasses import asdict
from typing import Any, ClassVar
from uuid import UUID

from arq.connections import RedisSettings

from agah.config import get_settings
from agah.db import SessionLocal
from agah.pipeline.orchestrator import ProgressEvent, run_scan


def progress_channel(scan_id: UUID | str) -> str:
    return f"agah:scan:{scan_id}"


async def scan_task(ctx: dict[str, Any], scan_id: str) -> str:
    redis = ctx["redis"]
    channel = progress_channel(scan_id)

    def publish(event: ProgressEvent) -> None:
        ctx["pending"].append(json.dumps(asdict(event), ensure_ascii=False))

    ctx["pending"] = []
    async with SessionLocal() as session:
        scan = await run_scan(session, UUID(scan_id), progress=publish)

    for payload in ctx["pending"]:
        await redis.publish(channel, payload)
    await redis.publish(
        channel, json.dumps({"stage": "done", "status": str(scan.status)}, ensure_ascii=False)
    )
    return str(scan.status)


class WorkerSettings:
    functions: ClassVar[list] = [scan_task]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = 3600

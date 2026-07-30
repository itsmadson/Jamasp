"""arq worker: runs scans off the request path and publishes progress to Redis.

The API streams that Redis channel to the browser as SSE, so a scan of a
200-table database reports live instead of blocking a request for minutes.
"""

import asyncio
import json
from dataclasses import asdict
from typing import Any, ClassVar
from uuid import UUID

from arq.connections import RedisSettings

from jamasp.config import get_settings
from jamasp.db import SessionLocal
from jamasp.pipeline.orchestrator import ProgressEvent, run_scan


def progress_channel(scan_id: UUID | str) -> str:
    return f"jamasp:scan:{scan_id}"


def report_channel(report_id: UUID | str) -> str:
    return f"jamasp:report:{report_id}"


async def scan_task(ctx: dict[str, Any], scan_id: str) -> str:
    redis = ctx["redis"]
    channel = progress_channel(scan_id)
    inflight: set[asyncio.Task[Any]] = set()

    def publish(event: ProgressEvent) -> None:
        # Fire-and-forget: published as it happens, so the progress bar moves
        # while the scan runs rather than all at once after it ends. The pipeline
        # is never blocked by the progress channel.
        payload = json.dumps(asdict(event), ensure_ascii=False)
        task = asyncio.create_task(redis.publish(channel, payload))
        inflight.add(task)
        task.add_done_callback(inflight.discard)

    async with SessionLocal() as session:
        scan = await run_scan(session, UUID(scan_id), progress=publish)

    if inflight:
        await asyncio.gather(*inflight, return_exceptions=True)
    await redis.publish(
        channel, json.dumps({"stage": "done", "status": str(scan.status)}, ensure_ascii=False)
    )
    return str(scan.status)


async def report_task(ctx: dict[str, Any], report_id: str) -> str:
    """Build a report in the background, narrating each step to the browser."""
    from jamasp.models.report import Report, ReportStatus
    from jamasp.report.build import build_report
    from jamasp.routers.knowledge import knowledge_payload

    redis = ctx["redis"]
    channel = report_channel(report_id)
    inflight: set[asyncio.Task[Any]] = set()

    def publish(event: Any) -> None:
        payload = json.dumps(asdict(event), ensure_ascii=False)
        task = asyncio.create_task(redis.publish(channel, payload))
        inflight.add(task)
        task.add_done_callback(inflight.discard)

    status = ReportStatus.FAILED
    async with SessionLocal() as session:
        try:
            report = await session.get(Report, UUID(report_id))
            if report is None:
                raise LookupError(f"report {report_id} not found")
            knowledge = await knowledge_payload(report.data_source_id, session)
            report = await build_report(session, UUID(report_id), knowledge, progress=publish)
            status = report.status
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - the browser is waiting on an answer
            await session.rollback()
            report = await session.get(Report, UUID(report_id))
            if report is not None:
                report.status = ReportStatus.FAILED
                report.error = json.dumps({"fatal": str(exc)}, ensure_ascii=False)
                await session.commit()

    if inflight:
        await asyncio.gather(*inflight, return_exceptions=True)
    await redis.publish(
        channel, json.dumps({"stage": "done", "status": status.value}, ensure_ascii=False)
    )
    return status.value


class WorkerSettings:
    functions: ClassVar[list] = [scan_task, report_task]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = 1800
    # No silent resurrection: a retried scan competes with its own replacement
    # for the same database.
    max_tries = 1

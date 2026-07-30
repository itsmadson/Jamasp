"""Job queue access, isolated behind one function so tests can substitute it."""

from typing import Any, Protocol

from arq import create_pool
from arq.connections import RedisSettings

from jamasp.config import get_settings


class JobQueue(Protocol):
    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> Any: ...


async def get_queue() -> JobQueue:
    return await create_pool(RedisSettings.from_dsn(get_settings().redis_url))

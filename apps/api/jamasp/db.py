from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from jamasp.config import get_settings

_engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Request-scoped session with commit-on-success, rollback-on-error.

    Routers only flush; without this commit their writes would be discarded when
    the session closes. Test fixtures override this dependency with a session
    bound to a transaction they roll back themselves.
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

import os
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

API_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def metadata_dsn() -> Iterator[str]:
    """A pgvector-capable Postgres with the full schema migrated in."""
    with PostgresContainer("pgvector/pgvector:pg16", driver=None) as container:
        sync_dsn = container.get_connection_url()
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=API_ROOT,
            env={**os.environ, "AGAH_DATABASE_URL": sync_dsn},
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}")
        yield sync_dsn.replace("postgresql://", "postgresql+asyncpg://")


@pytest.fixture(scope="session")
def hr_dsn() -> Iterator[str]:
    """A Postgres seeded with the HR fixture schema, standing in for a customer database."""
    schema = (Path(__file__).parent / "fixtures" / "hr_schema.sql").read_text()
    with PostgresContainer("postgres:16", driver=None) as container:
        engine = create_engine(container.get_connection_url().replace(
            "postgresql://", "postgresql+psycopg://", 1
        ))
        with engine.begin() as connection:
            connection.execute(text(schema))
        engine.dispose()
        yield container.get_connection_url().replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )


@pytest_asyncio.fixture(scope="session")
async def hr_snapshot(hr_dsn: str):
    from agah.adapters.postgres import PostgresAdapter

    return await PostgresAdapter(hr_dsn).introspect()


def _entity(snapshot, name: str):
    return next(entity for entity in snapshot.entities if entity.name == name)


@pytest_asyncio.fixture
async def leave_entity(hr_snapshot):
    return _entity(hr_snapshot, "leave_requests")


@pytest_asyncio.fixture
async def employees_entity(hr_snapshot):
    return _entity(hr_snapshot, "employees")


@pytest_asyncio.fixture
async def leave_profile(hr_dsn, leave_entity):
    from agah.adapters.postgres import PostgresAdapter
    from agah.models.source import SamplingPolicy
    from agah.pipeline.profile import profile_entity

    return await profile_entity(PostgresAdapter(hr_dsn), leave_entity, SamplingPolicy.MASKED)


@pytest_asyncio.fixture
async def employees_profile(hr_dsn, employees_entity):
    from agah.adapters.postgres import PostgresAdapter
    from agah.models.source import SamplingPolicy
    from agah.pipeline.profile import profile_entity

    return await profile_entity(PostgresAdapter(hr_dsn), employees_entity, SamplingPolicy.MASKED)


@pytest_asyncio.fixture
async def session(metadata_dsn: str) -> AsyncIterator[AsyncSession]:
    """Per-test session on a transaction that is always rolled back."""
    engine = create_async_engine(metadata_dsn)
    connection = await engine.connect()
    transaction = await connection.begin()
    # create_savepoint lets code under test call commit() without escaping the
    # outer transaction this fixture rolls back.
    maker = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

    async with maker() as active_session:
        yield active_session

    await transaction.rollback()
    await connection.close()
    await engine.dispose()

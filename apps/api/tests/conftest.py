import base64
import json
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


class _RecordingQueue:
    """Substitute for arq: records enqueues instead of needing a live Redis."""

    current: "_RecordingQueue"

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str]] = []

    async def enqueue_job(self, function: str, *args, **kwargs):
        self.enqueued.append((function, *args))


class _FinitePubSub:
    def __init__(self, messages):
        self._messages = messages

    async def subscribe(self, *channels):
        return None

    async def unsubscribe(self, *channels):
        return None

    async def listen(self):
        for message in self._messages:
            yield message


class _FiniteProgressSource:
    """Emits one progress event then a terminal one, so SSE tests terminate."""

    def pubsub(self):
        return _FinitePubSub([
            {"type": "message", "data": json.dumps(
                {"stage": "introspect", "current": 0, "total": 1, "message": "reading schema"}
            )},
            {"type": "message", "data": json.dumps({"stage": "done", "status": "succeeded"})},
        ])


@pytest.fixture
def fake_queue():
    _RecordingQueue.current = _RecordingQueue()
    return _RecordingQueue.current


@pytest_asyncio.fixture
async def client(session, monkeypatch, fake_queue):
    """App wired to the rolled-back test session, so HTTP tests stay isolated."""
    from httpx import ASGITransport, AsyncClient

    from agah.config import get_settings
    from agah.db import get_session
    from agah.main import create_app
    from agah.queue import get_queue
    from agah.routers.scans import get_progress_source

    monkeypatch.setenv("AGAH_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("AGAH_SECRET_KEY", base64.urlsafe_b64encode(b"0" * 32).decode())
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_queue] = lambda: _RecordingQueue.current
    app.dependency_overrides[get_progress_source] = lambda: _FiniteProgressSource()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _make_user(session, email: str, role) -> object:
    from agah.models.user import User
    from agah.security.password import hash_password

    user = User(email=email, password_hash=hash_password("correct-horse"), role=role)
    session.add(user)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def admin_user(session):
    from agah.models.user import UserRole

    return await _make_user(session, "admin@agah.local", UserRole.ADMIN)


@pytest_asyncio.fixture
async def analyst_user(session):
    from agah.models.user import UserRole

    return await _make_user(session, "analyst@agah.local", UserRole.ANALYST)


async def _cookie_for(client, user) -> dict[str, str]:
    response = await client.post(
        "/api/auth/login", json={"email": user.email, "password": "correct-horse"}
    )
    response.raise_for_status()
    return {"agah_session": response.cookies["agah_session"]}


@pytest_asyncio.fixture
async def admin_cookie(client, admin_user):
    return await _cookie_for(client, admin_user)


@pytest_asyncio.fixture
async def scanned_source(session, hr_dsn, monkeypatch):
    """A source that has completed one scan, with every entity described and pending."""
    from agah.llm.base import Completion
    from agah.models.scan import Scan
    from agah.models.source import DataSource, SamplingPolicy, SourceKind
    from agah.pipeline.orchestrator import run_scan
    from agah.security.crypto import encrypt

    key = b"0" * 32
    monkeypatch.setattr("agah.pipeline.orchestrator.key_from_settings", lambda: key)

    cassette = json.loads(
        (Path(__file__).parent / "fixtures/cassettes/describe_leave_requests.json").read_text()
    )

    async def fake_call(session_, task, messages, **kwargs):
        return Completion(
            text=json.dumps(cassette), tokens_in=10, tokens_out=20,
            model="stub", provider="stub", latency_ms=1,
        )

    async def fake_embed(session_, texts, scan_id=None):
        return [[0.0] * 1024 for _ in texts]

    monkeypatch.setattr("agah.pipeline.describe.call_task", fake_call)
    monkeypatch.setattr("agah.pipeline.embed.embed_texts", fake_embed)

    source = DataSource(
        name="HR",
        kind=SourceKind.POSTGRES,
        config_encrypted=encrypt(json.dumps({"dsn": hr_dsn}), key),
        sampling_policy=SamplingPolicy.MASKED,
    )
    session.add(source)
    await session.flush()
    scan = Scan(data_source_id=source.id)
    session.add(scan)
    await session.flush()
    await run_scan(session, scan.id)
    return source


@pytest_asyncio.fixture
async def entity(session, scanned_source):
    from sqlalchemy import select

    from agah.models.entity import Entity

    return (
        await session.scalars(
            select(Entity).where(
                Entity.data_source_id == scanned_source.id, Entity.name == "leave_requests"
            )
        )
    ).one()


@pytest_asyncio.fixture
async def analyst_cookie(client, analyst_user):
    return await _cookie_for(client, analyst_user)

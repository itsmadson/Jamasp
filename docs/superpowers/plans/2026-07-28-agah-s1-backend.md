# جاماسپ S1 Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the جاماسپ backend that registers a data source, introspects its schema deterministically, has an LLM describe it, lets a human approve the descriptions, and exports the approved semantic model as a stable JSON contract.

**Architecture:** FastAPI service over a Postgres+pgvector metadata database. A five-stage scan pipeline (Introspect → Profile → Describe → Embed → Diff) runs as an arq background job. Stages 1, 2 and 5 are deterministic and contain no AI, which makes them testable against fixture databases. Stages 3 and 4 call an LLM through a provider abstraction with per-task model routing. Only human-approved entities appear in the export.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, asyncpg, pgvector, arq + Redis, sqlglot, argon2-cffi, cryptography, httpx, pytest + pytest-asyncio, testcontainers, uv, ruff.

**Spec:** `docs/superpowers/specs/2026-07-28-jamasp-s1-semantic-layer-design.md`

**Scope note:** This plan covers the backend through the knowledge-export endpoint, using the **PostgreSQL adapter only**. It produces working, independently testable software: a complete scan-describe-approve-export cycle driven over HTTP. Two follow-up plans complete S1 — the remaining adapters (MySQL, SQL Server, Oracle, REST, MCP) behind the same `SourceAdapter` protocol, and the Next.js frontend.

## Global Constraints

- Python 3.12; dependency management with `uv`; all backend code under `apps/api/`.
- All database access is async (`asyncpg` + SQLAlchemy 2.0 async session). No sync engine in application code; Alembic uses its own sync engine, which is fine.
- **No API key, password, or connection string may be written to any file in the repository, any log line, or any API response.** Secrets come from `.env` (gitignored) or the encrypted `settings` table.
- Every LLM call goes through `llm.router.call_task()` — never construct a provider client directly in pipeline code.
- CI makes zero live LLM calls. All Describer/Embedder tests use recorded fixtures.
- Every generated or profiled SQL statement passes `safety.readonly.assert_readonly()` before execution. No exceptions.
- Descriptions are bilingual: every `summary` and `meaning` field carries both `fa` and `en` keys.
- Timestamps are UTC, stored as `timestamptz`.
- Line length 100, `ruff` for lint and format, `ruff check` clean before every commit.
- Test command is always `uv run pytest` from `apps/api/`.

---

## File Structure

```
apps/api/
  pyproject.toml
  alembic.ini
  alembic/versions/
  jamasp/
    main.py                 FastAPI app factory, router registration
    config.py               pydantic-settings, env loading
    db.py                   async engine, session dependency
    models/
      base.py               DeclarativeBase, TimestampMixin
      user.py               users
      source.py             data_sources
      scan.py               scans
      entity.py             entities, fields
      relationship.py       relationships
      observability.py      llm_calls, settings
    security/
      crypto.py             AES-GCM encrypt/decrypt for credentials
      password.py           argon2 hash/verify
      tokens.py             JWT issue/verify
      deps.py               current_user / require_admin dependencies
    safety/
      readonly.py           sqlglot AST validation
      pii.py                PII classification + masking
    adapters/
      base.py               SourceAdapter protocol + shared dataclasses
      postgres.py           PostgresAdapter
      registry.py           kind -> adapter factory
    pipeline/
      snapshot.py           StructuralSnapshot types + hashing
      introspect.py         stage 1 driver
      profile.py            stage 2 driver
      probe.py              stage 2b join probe
      describe.py           stage 3 LLM describer
      embed.py              stage 4 embedder
      diff.py               stage 5 snapshot diff
      orchestrator.py       stage sequencing, checkpointing, progress events
      worker.py             arq worker settings + scan job
    llm/
      base.py               LLMProvider protocol, Completion, Vector types
      openai_compat.py      shared OpenAI-compatible client (GapGPT/OpenRouter/local)
      router.py             per-task model routing, fallback chain, cost logging
      prompts/
        describe_entity.py  prompt builder + JSON schema
    routers/
      auth.py               login, me
      sources.py            CRUD, test-connection, trigger scan
      scans.py              status, SSE progress
      entities.py           list, patch, approve, bulk approve
      knowledge.py          export endpoint
    schemas/
      source.py  scan.py  entity.py  knowledge.py  auth.py
  tests/
    conftest.py             fixtures: db, client, fixture-source container
    fixtures/
      hr_schema.sql         seeded test database (the hard cases)
      cassettes/            recorded LLM responses
    unit/                   pii, readonly, diff, router, crypto
    integration/            adapters, profiler, probe, pipeline
    e2e/                    full scan -> approve -> export
docker/
  compose.yml               api, postgres+pgvector, redis, fixture-postgres
```

---

### Task 1: Project scaffold, config, and health endpoint

**Files:**
- Create: `apps/api/pyproject.toml`, `apps/api/jamasp/__init__.py`, `apps/api/jamasp/config.py`, `apps/api/jamasp/main.py`, `apps/api/tests/conftest.py`, `apps/api/tests/unit/test_health.py`, `docker/compose.yml`, `.env.example`

**Interfaces:**
- Consumes: nothing
- Produces: `create_app() -> FastAPI`; `Settings` (pydantic-settings) with fields `database_url: str`, `redis_url: str`, `secret_key: str`, `jwt_secret: str`, `environment: str`; `get_settings() -> Settings` (lru_cached)

- [ ] **Step 1: Write the failing test**

`apps/api/tests/unit/test_health.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from jamasp.main import create_app


@pytest.mark.asyncio
async def test_health_returns_ok():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jamasp'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/pyproject.toml`:

```toml
[project]
name = "jamasp-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pgvector>=0.3.6",
    "arq>=0.26",
    "sqlglot>=25.0",
    "argon2-cffi>=23.1",
    "pyjwt>=2.10",
    "cryptography>=43.0",
    "httpx>=0.27",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "ruff>=0.7",
    "testcontainers[postgres]>=4.8",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.hatch.build.targets.wheel]
packages = ["jamasp"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

`apps/api/jamasp/config.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="JAMASP_", extra="ignore")

    database_url: str = "postgresql+asyncpg://jamasp:jamasp@localhost:5432/jamasp"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = ""
    jwt_secret: str = ""
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`apps/api/jamasp/main.py`:

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="جاماسپ API", version="0.1.0")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

`apps/api/tests/conftest.py`:

```python
import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
```

`.env.example` (key names only, no values):

```bash
JAMASP_DATABASE_URL=postgresql+asyncpg://jamasp:jamasp@localhost:5432/jamasp
JAMASP_REDIS_URL=redis://localhost:6379/0
JAMASP_SECRET_KEY=
JAMASP_JWT_SECRET=
JAMASP_ENVIRONMENT=development
```

`docker/compose.yml`:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: jamasp
      POSTGRES_PASSWORD: jamasp
      POSTGRES_DB: jamasp
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U jamasp"]
      interval: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  fixture-postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: fixture
      POSTGRES_PASSWORD: fixture
      POSTGRES_DB: hr
    ports: ["5433:5432"]
    volumes:
      - ../apps/api/tests/fixtures/hr_schema.sql:/docker-entrypoint-initdb.d/01.sql:ro
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv sync && uv run pytest tests/unit/test_health.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api docker/compose.yml .env.example
git commit -m "feat: scaffold FastAPI service with health endpoint and compose stack"
```

---

### Task 2: Credential encryption

**Files:**
- Create: `apps/api/jamasp/security/__init__.py`, `apps/api/jamasp/security/crypto.py`, `apps/api/tests/unit/test_crypto.py`

**Interfaces:**
- Consumes: `get_settings()` from Task 1
- Produces: `encrypt(plaintext: str, key: bytes) -> bytes`, `decrypt(ciphertext: bytes, key: bytes) -> str`, `key_from_settings() -> bytes`

Built before the models because `data_sources.config_encrypted` cannot be written without it.

- [ ] **Step 1: Write the failing test**

`apps/api/tests/unit/test_crypto.py`:

```python
import os

import pytest

from jamasp.security.crypto import decrypt, encrypt


def test_roundtrip_recovers_plaintext():
    key = os.urandom(32)
    secret = "postgresql://user:p@ssw0rd@db.internal:5432/hr"
    assert decrypt(encrypt(secret, key), key) == secret


def test_ciphertext_differs_across_calls():
    key = os.urandom(32)
    assert encrypt("same", key) != encrypt("same", key)


def test_wrong_key_raises():
    blob = encrypt("secret", os.urandom(32))
    with pytest.raises(ValueError):
        decrypt(blob, os.urandom(32))


def test_tampered_ciphertext_raises():
    key = os.urandom(32)
    blob = bytearray(encrypt("secret", key))
    blob[-1] ^= 0xFF
    with pytest.raises(ValueError):
        decrypt(bytes(blob), key)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_crypto.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jamasp.security'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/jamasp/security/crypto.py`:

```python
import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from jamasp.config import get_settings

NONCE_BYTES = 12


def encrypt(plaintext: str, key: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext.encode(), None)


def decrypt(ciphertext: bytes, key: bytes) -> str:
    nonce, body = ciphertext[:NONCE_BYTES], ciphertext[NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, body, None).decode()
    except InvalidTag as exc:
        raise ValueError("decryption failed: wrong key or tampered ciphertext") from exc


def key_from_settings() -> bytes:
    raw = get_settings().secret_key
    if not raw:
        raise RuntimeError("JAMASP_SECRET_KEY is not set; refusing to start")
    key = base64.urlsafe_b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("JAMASP_SECRET_KEY must decode to 32 bytes")
    return key
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/unit/test_crypto.py -v`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/security apps/api/tests/unit/test_crypto.py
git commit -m "feat: add AES-GCM credential encryption"
```

---

### Task 3: Metadata models and migrations

**Files:**
- Create: `apps/api/jamasp/db.py`, `apps/api/jamasp/models/base.py`, `apps/api/jamasp/models/user.py`, `apps/api/jamasp/models/source.py`, `apps/api/jamasp/models/scan.py`, `apps/api/jamasp/models/entity.py`, `apps/api/jamasp/models/relationship.py`, `apps/api/jamasp/models/observability.py`, `apps/api/alembic.ini`, `apps/api/alembic/env.py`, `apps/api/alembic/versions/0001_initial.py`, `apps/api/tests/integration/test_models.py`
- Modify: `apps/api/tests/conftest.py`

**Interfaces:**
- Consumes: `Settings` (Task 1)
- Produces: `Base`, `User`, `DataSource`, `Scan`, `Entity`, `Field`, `Relationship`, `LLMCall`, `Setting` ORM classes; enums `SourceKind`, `EntityStatus`, `ScanStatus`, `PIIClass`, `RelationshipKind`, `UserRole`, `SamplingPolicy`; `get_session()` FastAPI dependency yielding `AsyncSession`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/integration/test_models.py`:

```python
import pytest
from sqlalchemy import select

from jamasp.models.entity import Entity, EntityStatus
from jamasp.models.source import DataSource, SamplingPolicy, SourceKind


@pytest.mark.asyncio
async def test_entity_defaults_to_pending_and_cascades(session):
    source = DataSource(
        name="HR",
        kind=SourceKind.POSTGRES,
        config_encrypted=b"x",
        sampling_policy=SamplingPolicy.MASKED,
    )
    session.add(source)
    await session.flush()

    entity = Entity(
        data_source_id=source.id,
        kind="table",
        schema_name="public",
        name="leave_requests",
        structural={"columns": []},
        structural_hash="abc",
    )
    session.add(entity)
    await session.flush()

    assert entity.status is EntityStatus.PENDING
    assert entity.version == 1

    await session.delete(source)
    await session.flush()
    remaining = await session.scalars(select(Entity))
    assert remaining.all() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/integration/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jamasp.models'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/jamasp/models/base.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

`apps/api/jamasp/models/source.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jamasp.models.base import Base, TimestampMixin, UUIDMixin


class SourceKind(enum.StrEnum):
    POSTGRES = "postgres"
    MYSQL = "mysql"
    MSSQL = "mssql"
    ORACLE = "oracle"
    REST = "rest"
    MCP = "mcp"


class SamplingPolicy(enum.StrEnum):
    MASKED = "masked"
    SCHEMA_ONLY = "schema_only"


class SourceStatus(enum.StrEnum):
    DRAFT = "draft"
    SCANNING = "scanning"
    READY = "ready"
    ERROR = "error"


class DataSource(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[SourceKind] = mapped_column(Enum(SourceKind, native_enum=False))
    config_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    sampling_policy: Mapped[SamplingPolicy] = mapped_column(
        Enum(SamplingPolicy, native_enum=False), default=SamplingPolicy.MASKED
    )
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, native_enum=False), default=SourceStatus.DRAFT
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    entities = relationship("Entity", back_populates="source", cascade="all, delete-orphan")
    scans = relationship("Scan", back_populates="source", cascade="all, delete-orphan")
```

`apps/api/jamasp/models/entity.py`:

```python
import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jamasp.models.base import Base, TimestampMixin, UUIDMixin

EMBEDDING_DIM = 1024


class EntityStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    STALE = "stale"
    IGNORED = "ignored"
    ARCHIVED = "archived"
    DESCRIBE_FAILED = "describe_failed"


class PIIClass(enum.StrEnum):
    NONE = "none"
    LOW = "low"
    HIGH = "high"


class Entity(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("data_source_id", "schema_name", "name", name="uq_entity_identity"),
    )

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    schema_name: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    structural: Mapped[dict[str, Any]] = mapped_column(JSONB)
    structural_hash: Mapped[str] = mapped_column(String(64))
    description_ai: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    description_human: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False), default=EntityStatus.PENDING, index=True
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    version: Mapped[int] = mapped_column(Integer, default=1)
    row_count_approx: Mapped[int | None] = mapped_column(Integer)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source = relationship("DataSource", back_populates="entities")
    fields = relationship(
        "Field", back_populates="entity", cascade="all, delete-orphan", order_by="Field.ordinal"
    )


class Field(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "fields"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    data_type: Mapped[str] = mapped_column(String(100))
    nullable: Mapped[bool] = mapped_column(default=True)
    is_pk: Mapped[bool] = mapped_column(default=False)
    ordinal: Mapped[int] = mapped_column(Integer)
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    meaning_ai: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    meaning_human: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    enum_map: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    unit: Mapped[str | None] = mapped_column(String(50))
    pii_class: Mapped[PIIClass] = mapped_column(
        Enum(PIIClass, native_enum=False), default=PIIClass.NONE
    )
    confidence: Mapped[float | None] = mapped_column(Float)

    entity = relationship("Entity", back_populates="fields")
```

Write `user.py` (`User`: `email` unique, `password_hash`, `role: UserRole{ADMIN,ANALYST}`, `locale: str = "fa"`), `scan.py` (`Scan`: `data_source_id` FK cascade, `status: ScanStatus{QUEUED,RUNNING,SUCCEEDED,PARTIAL,FAILED}`, `started_at`, `finished_at`, `structural_snapshot: JSONB`, `stats: JSONB`, `error: JSONB`), `relationship.py` (`Relationship`: `data_source_id`, `from_entity_id`, `from_field`, `to_entity_id`, `to_field`, `kind: RelationshipKind{DECLARED,INFERRED}`, `cardinality`, `confidence`, `evidence: JSONB`, `status`) and `observability.py` (`LLMCall`: `scan_id` nullable FK, `purpose`, `provider`, `model`, `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms`, `status`; `Setting`: `key` primary key `String(100)`, `value: JSONB`, `updated_by`, `updated_at`) following the same column and mixin conventions.

`apps/api/jamasp/db.py`:

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from jamasp.config import get_settings

_engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
```

Initialize Alembic (`uv run alembic init alembic`), point `alembic/env.py` at `Base.metadata` and the `JAMASP_DATABASE_URL` env var, then autogenerate `0001_initial`. Hand-edit that revision to add `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` as its first upgrade statement.

Add to `apps/api/tests/conftest.py` a `session` fixture that spins up a Postgres testcontainer once per session, runs `alembic upgrade head` against it, and yields a rolled-back `AsyncSession` per test.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/integration/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/models apps/api/jamasp/db.py apps/api/alembic apps/api/alembic.ini apps/api/tests
git commit -m "feat: add metadata models and initial migration"
```

---

### Task 4: Read-only SQL guard

**Files:**
- Create: `apps/api/jamasp/safety/__init__.py`, `apps/api/jamasp/safety/readonly.py`, `apps/api/tests/unit/test_readonly.py`

**Interfaces:**
- Consumes: nothing
- Produces: `assert_readonly(sql: str, dialect: str) -> None` (raises `UnsafeQueryError`), `UnsafeQueryError(Exception)`, `apply_limit(sql: str, dialect: str, limit: int) -> str`

Built early because Tasks 6 and 7 execute queries and must be guarded from their first line.

- [ ] **Step 1: Write the failing test**

`apps/api/tests/unit/test_readonly.py`:

```python
import pytest

from jamasp.safety.readonly import UnsafeQueryError, apply_limit, assert_readonly

SAFE = [
    "SELECT * FROM employees",
    "SELECT e.id, d.name FROM employees e JOIN departments d ON d.id = e.dept_id",
    "WITH recent AS (SELECT * FROM leave_requests WHERE created_at > now()) SELECT * FROM recent",
    "SELECT count(*) FROM orders WHERE status = 3",
]

UNSAFE = [
    "DELETE FROM employees",
    "UPDATE employees SET salary = 0",
    "INSERT INTO employees (name) VALUES ('x')",
    "DROP TABLE employees",
    "TRUNCATE employees",
    "ALTER TABLE employees ADD COLUMN x int",
    "CREATE TABLE t (id int)",
    "GRANT ALL ON employees TO public",
    "SELECT 1; DROP TABLE employees",
    "WITH d AS (DELETE FROM employees RETURNING *) SELECT * FROM d",
    "SELECT * FROM employees /* */ ; TRUNCATE employees",
    "COPY employees TO '/tmp/out.csv'",
    "SELECT pg_sleep(100)",
]


@pytest.mark.parametrize("sql", SAFE)
def test_safe_queries_pass(sql):
    assert_readonly(sql, "postgres")


@pytest.mark.parametrize("sql", UNSAFE)
def test_unsafe_queries_rejected(sql):
    with pytest.raises(UnsafeQueryError):
        assert_readonly(sql, "postgres")


def test_apply_limit_wraps_query():
    out = apply_limit("SELECT * FROM employees", "postgres", 100)
    assert "LIMIT 100" in out.upper()


def test_apply_limit_tightens_existing_limit():
    out = apply_limit("SELECT * FROM employees LIMIT 5000", "postgres", 100)
    assert "5000" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_readonly.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jamasp.safety'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/jamasp/safety/readonly.py`:

```python
import sqlglot
from sqlglot import exp

WRITE_EXPRESSIONS = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.TruncateTable, exp.Grant, exp.Merge, exp.Copy, exp.Command,
)

BANNED_FUNCTIONS = {"pg_sleep", "dblink", "pg_read_file", "lo_import", "lo_export"}


class UnsafeQueryError(Exception):
    pass


def assert_readonly(sql: str, dialect: str) -> None:
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except Exception as exc:
        raise UnsafeQueryError(f"unparseable SQL: {exc}") from exc

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise UnsafeQueryError(f"expected exactly one statement, got {len(statements)}")

    statement = statements[0]
    if not isinstance(statement, (exp.Select, exp.Union, exp.Subquery)):
        raise UnsafeQueryError(f"only SELECT is permitted, got {type(statement).__name__}")

    for node in statement.walk():
        if isinstance(node, WRITE_EXPRESSIONS):
            raise UnsafeQueryError(f"write operation not permitted: {type(node).__name__}")
        if isinstance(node, exp.Anonymous) and node.name.lower() in BANNED_FUNCTIONS:
            raise UnsafeQueryError(f"banned function: {node.name}")


def apply_limit(sql: str, dialect: str, limit: int) -> str:
    statement = sqlglot.parse_one(sql, read=dialect)
    return statement.limit(limit, override=True).sql(dialect=dialect)
```

Note: `Command` covers statements sqlglot cannot classify (including `COPY` on some versions) — treating them as unsafe is deliberate, so anything unrecognized is rejected rather than allowed.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/unit/test_readonly.py -v`
Expected: PASS — 19 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/safety apps/api/tests/unit/test_readonly.py
git commit -m "feat: add sqlglot-based read-only query guard"
```

---

### Task 5: PII classification and masking

**Files:**
- Create: `apps/api/jamasp/safety/pii.py`, `apps/api/tests/unit/test_pii.py`

**Interfaces:**
- Consumes: `PIIClass` (Task 3)
- Produces: `classify_column(name: str, data_type: str, samples: list[object]) -> PIIClass`, `mask_value(value: object, pii_class: PIIClass) -> object | None`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/unit/test_pii.py`:

```python
import pytest

from jamasp.models.entity import PIIClass
from jamasp.safety.pii import classify_column, mask_value


@pytest.mark.parametrize(
    "name,samples,expected",
    [
        ("national_id", ["0079542619"], PIIClass.HIGH),
        ("کدملی", ["0079542619"], PIIClass.HIGH),
        ("salary", [12000000], PIIClass.HIGH),
        ("حقوق", [12000000], PIIClass.HIGH),
        ("mobile", ["09121234567"], PIIClass.LOW),
        ("شماره_موبایل", ["09121234567"], PIIClass.LOW),
        ("email", ["ali@example.com"], PIIClass.LOW),
        ("iban", ["IR062960000000100324200001"], PIIClass.HIGH),
        ("status", [1, 2, 3], PIIClass.NONE),
        ("created_at", ["2026-07-28"], PIIClass.NONE),
    ],
)
def test_classify_column(name, samples, expected):
    assert classify_column(name, "text", samples) is expected


def test_classify_detects_pii_by_value_shape_despite_opaque_name():
    assert classify_column("fld_003", "text", ["09121234567", "09354445566"]) is PIIClass.LOW


def test_high_class_values_are_dropped_entirely():
    assert mask_value("0079542619", PIIClass.HIGH) is None


def test_low_class_mobile_is_partially_masked():
    masked = mask_value("09121234567", PIIClass.LOW)
    assert masked == "0912***4567"
    assert "1234" not in masked[4:7]


def test_low_class_email_keeps_domain_only():
    assert mask_value("ali@example.com", PIIClass.LOW) == "a***@example.com"


def test_none_class_passes_through():
    assert mask_value(3, PIIClass.NONE) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_pii.py -v`
Expected: FAIL — `ImportError: cannot import name 'classify_column'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/jamasp/safety/pii.py`:

```python
import re

from jamasp.models.entity import PIIClass

HIGH_NAME_PATTERNS = [
    r"national_?id", r"کدملی", r"کد_?ملی", r"ssn", r"passport", r"شماره_?گذرنامه",
    r"salary", r"حقوق", r"دستمزد", r"iban", r"شبا", r"card_?number", r"شماره_?کارت",
    r"account_?number", r"شماره_?حساب", r"password", r"secret", r"token",
]
LOW_NAME_PATTERNS = [
    r"mobile", r"phone", r"tel", r"موبایل", r"تلفن", r"همراه",
    r"email", r"ایمیل", r"address", r"آدرس", r"نشانی",
    r"birth", r"تولد", r"first_?name", r"last_?name", r"full_?name", r"نام",
]

IRAN_MOBILE = re.compile(r"^09\d{9}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
IRAN_IBAN = re.compile(r"^IR\d{24}$")
CARD = re.compile(r"^\d{16}$")
NATIONAL_ID = re.compile(r"^\d{10}$")


def _matches(patterns: list[str], name: str) -> bool:
    lowered = name.lower()
    return any(re.search(p, lowered) for p in patterns)


def _valid_iranian_national_id(value: str) -> bool:
    if not NATIONAL_ID.match(value) or len(set(value)) == 1:
        return False
    checksum = sum(int(value[i]) * (10 - i) for i in range(9)) % 11
    control = int(value[9])
    return control == checksum if checksum < 2 else control == 11 - checksum


def classify_column(name: str, data_type: str, samples: list[object]) -> PIIClass:
    if _matches(HIGH_NAME_PATTERNS, name):
        return PIIClass.HIGH
    if _matches(LOW_NAME_PATTERNS, name):
        return PIIClass.LOW

    strings = [str(s) for s in samples if s is not None]
    if strings:
        if all(IRAN_IBAN.match(s) or CARD.match(s) for s in strings):
            return PIIClass.HIGH
        if all(_valid_iranian_national_id(s) for s in strings):
            return PIIClass.HIGH
        if all(IRAN_MOBILE.match(s) or EMAIL.match(s) for s in strings):
            return PIIClass.LOW
    return PIIClass.NONE


def mask_value(value: object, pii_class: PIIClass) -> object | None:
    if pii_class is PIIClass.HIGH:
        return None
    if pii_class is PIIClass.NONE or value is None:
        return value

    text = str(value)
    if EMAIL.match(text):
        local, _, domain = text.partition("@")
        return f"{local[0]}***@{domain}"
    if IRAN_MOBILE.match(text):
        return f"{text[:4]}***{text[-4:]}"
    if len(text) <= 4:
        return "***"
    return f"{text[:2]}***{text[-2:]}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/unit/test_pii.py -v`
Expected: PASS — 16 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/safety/pii.py apps/api/tests/unit/test_pii.py
git commit -m "feat: add PII classification and masking with Persian patterns"
```

---

### Task 6: Adapter protocol and Postgres introspection

**Files:**
- Create: `apps/api/jamasp/adapters/__init__.py`, `apps/api/jamasp/adapters/base.py`, `apps/api/jamasp/adapters/postgres.py`, `apps/api/jamasp/adapters/registry.py`, `apps/api/jamasp/pipeline/__init__.py`, `apps/api/jamasp/pipeline/snapshot.py`, `apps/api/tests/fixtures/hr_schema.sql`, `apps/api/tests/integration/test_postgres_adapter.py`
- Modify: `apps/api/tests/conftest.py`

**Interfaces:**
- Consumes: `assert_readonly`, `apply_limit` (Task 4)
- Produces:
  - `ColumnInfo(name, data_type, nullable, is_pk, ordinal, default, comment)`
  - `ForeignKeyInfo(from_columns, to_schema, to_table, to_columns)`
  - `EntitySnapshot(kind, schema_name, name, comment, row_count_approx, columns, foreign_keys, unique_constraints, indexes)`
  - `StructuralSnapshot(dialect, taken_at, entities)` with `.hash_for(entity) -> str` and `.by_identity() -> dict[tuple[str, str], EntitySnapshot]`
  - `SourceAdapter` protocol: `async test_connection() -> HealthReport`, `async introspect() -> StructuralSnapshot`, `async sample(entity, columns, limit) -> list[dict]`, `async distinct_values(entity, column, limit) -> list`, `async execute_readonly(sql, limit, timeout_s) -> list[dict]`
  - `PostgresAdapter(dsn: str)`
  - `adapter_for(kind: SourceKind, config: dict) -> SourceAdapter`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/fixtures/hr_schema.sql` — deliberately includes the hard cases from the spec: a table with **no** declared FK, cryptic names, Persian data, and coded status columns.

```sql
CREATE TABLE departments (
    id serial PRIMARY KEY,
    name text NOT NULL
);
COMMENT ON TABLE departments IS 'واحدهای سازمانی';

CREATE TABLE employees (
    id serial PRIMARY KEY,
    full_name text NOT NULL,
    national_id char(10),
    mobile varchar(11),
    dept_id integer NOT NULL REFERENCES departments(id),
    salary bigint,
    hired_on date
);

-- No declared foreign key: emp_id must be discovered by the join probe.
CREATE TABLE leave_requests (
    id serial PRIMARY KEY,
    emp_id integer NOT NULL,
    status smallint NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL
);
COMMENT ON COLUMN leave_requests.status IS '1=در انتظار 2=تایید شده 3=رد شده';

-- Cryptic legacy table, the case that motivates value sampling.
CREATE TABLE t_mst_01 (
    fld_001 serial PRIMARY KEY,
    fld_002 integer NOT NULL,
    fld_003 varchar(11)
);

CREATE VIEW v_active_employees AS
    SELECT id, full_name, dept_id FROM employees WHERE hired_on IS NOT NULL;

INSERT INTO departments (name) VALUES ('مالی'), ('فناوری اطلاعات'), ('منابع انسانی');
INSERT INTO employees (full_name, national_id, mobile, dept_id, salary, hired_on) VALUES
    ('علی رضایی', '0079542619', '09121234567', 1, 120000000, '2020-03-01'),
    ('مریم کریمی', '0084575941', '09354445566', 2, 180000000, '2021-06-15'),
    ('حسن محمدی', '0068518123', '09127778899', 2, 150000000, '2019-01-20');
INSERT INTO leave_requests (emp_id, status, start_date, end_date) VALUES
    (1, 2, '2026-07-01', '2026-07-05'),
    (2, 1, '2026-07-10', '2026-07-12'),
    (3, 3, '2026-07-15', '2026-07-16'),
    (1, 2, '2026-07-20', '2026-07-21');
INSERT INTO t_mst_01 (fld_002, fld_003) VALUES
    (1, '09121234567'), (2, '09354445566'), (3, '09127778899');
```

`apps/api/tests/integration/test_postgres_adapter.py`:

```python
import pytest

from jamasp.adapters.postgres import PostgresAdapter
from jamasp.safety.readonly import UnsafeQueryError


@pytest.mark.asyncio
async def test_test_connection_reports_healthy(hr_dsn):
    report = await PostgresAdapter(hr_dsn).test_connection()
    assert report.healthy is True
    assert "PostgreSQL" in report.server_version


@pytest.mark.asyncio
async def test_introspect_finds_tables_and_views(hr_dsn):
    snapshot = await PostgresAdapter(hr_dsn).introspect()
    names = {e.name: e for e in snapshot.entities}
    assert {"departments", "employees", "leave_requests", "t_mst_01"} <= names.keys()
    assert names["v_active_employees"].kind == "view"
    assert snapshot.dialect == "postgres"


@pytest.mark.asyncio
async def test_introspect_captures_columns_pk_fk_and_comments(hr_dsn):
    snapshot = await PostgresAdapter(hr_dsn).introspect()
    by_name = {e.name: e for e in snapshot.entities}

    employees = by_name["employees"]
    assert [c.name for c in employees.columns][:3] == ["id", "full_name", "national_id"]
    assert next(c for c in employees.columns if c.name == "id").is_pk is True
    assert next(c for c in employees.columns if c.name == "full_name").nullable is False
    assert employees.foreign_keys[0].to_table == "departments"

    assert by_name["departments"].comment == "واحدهای سازمانی"
    status = next(c for c in by_name["leave_requests"].columns if c.name == "status")
    assert "در انتظار" in status.comment


@pytest.mark.asyncio
async def test_leave_requests_has_no_declared_foreign_key(hr_dsn):
    snapshot = await PostgresAdapter(hr_dsn).introspect()
    by_name = {e.name: e for e in snapshot.entities}
    assert by_name["leave_requests"].foreign_keys == []


@pytest.mark.asyncio
async def test_snapshot_hash_is_stable_across_runs(hr_dsn):
    first = await PostgresAdapter(hr_dsn).introspect()
    second = await PostgresAdapter(hr_dsn).introspect()
    entity = next(e for e in first.entities if e.name == "employees")
    other = next(e for e in second.entities if e.name == "employees")
    assert first.hash_for(entity) == second.hash_for(other)


@pytest.mark.asyncio
async def test_execute_readonly_rejects_writes(hr_dsn):
    with pytest.raises(UnsafeQueryError):
        await PostgresAdapter(hr_dsn).execute_readonly("DELETE FROM employees", limit=10)


@pytest.mark.asyncio
async def test_execute_readonly_enforces_row_limit(hr_dsn):
    rows = await PostgresAdapter(hr_dsn).execute_readonly("SELECT * FROM employees", limit=2)
    assert len(rows) == 2
```

Add an `hr_dsn` session fixture to `conftest.py` that starts a `postgres:16` testcontainer, applies `hr_schema.sql`, and yields the DSN.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/integration/test_postgres_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jamasp.adapters'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/jamasp/pipeline/snapshot.py`:

```python
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    is_pk: bool
    ordinal: int
    default: str | None = None
    comment: str | None = None


@dataclass(frozen=True)
class ForeignKeyInfo:
    from_columns: tuple[str, ...]
    to_schema: str
    to_table: str
    to_columns: tuple[str, ...]


@dataclass(frozen=True)
class EntitySnapshot:
    kind: str
    schema_name: str
    name: str
    columns: tuple[ColumnInfo, ...]
    foreign_keys: tuple[ForeignKeyInfo, ...] = ()
    unique_constraints: tuple[tuple[str, ...], ...] = ()
    indexes: tuple[str, ...] = ()
    comment: str | None = None
    row_count_approx: int | None = None

    @property
    def identity(self) -> tuple[str, str]:
        return (self.schema_name, self.name)


@dataclass(frozen=True)
class StructuralSnapshot:
    dialect: str
    entities: tuple[EntitySnapshot, ...]
    taken_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def by_identity(self) -> dict[tuple[str, str], EntitySnapshot]:
        return {e.identity: e for e in self.entities}

    def hash_for(self, entity: EntitySnapshot) -> str:
        payload = asdict(entity)
        # Volatile — must not affect the hash, or every rescan would look changed.
        payload.pop("row_count_approx", None)
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def to_json(self) -> dict:
        return {
            "dialect": self.dialect,
            "taken_at": self.taken_at.isoformat(),
            "entities": [asdict(e) for e in self.entities],
        }


@dataclass(frozen=True)
class HealthReport:
    healthy: bool
    server_version: str = ""
    error: str | None = None
```

`apps/api/jamasp/adapters/base.py` defines the `SourceAdapter` Protocol with the five async methods listed in the Interfaces block above, re-exporting the snapshot dataclasses.

`apps/api/jamasp/adapters/postgres.py` implements it with SQLAlchemy async reflection plus these dialect queries:

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from jamasp.adapters.base import SourceAdapter
from jamasp.pipeline.snapshot import (
    ColumnInfo, EntitySnapshot, ForeignKeyInfo, HealthReport, StructuralSnapshot,
)
from jamasp.safety.readonly import apply_limit, assert_readonly

SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")

ROW_COUNTS_SQL = text("""
    SELECT schemaname, relname, n_live_tup
    FROM pg_stat_user_tables
""")

COMMENTS_SQL = text("""
    SELECT n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
           d.description
    FROM pg_description d
    JOIN pg_class c ON c.oid = d.objoid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
""")


class PostgresAdapter(SourceAdapter):
    dialect = "postgres"

    def __init__(self, dsn: str) -> None:
        self._engine = create_async_engine(dsn, pool_pre_ping=True)

    async def test_connection(self) -> HealthReport:
        try:
            async with self._engine.connect() as conn:
                version = (await conn.execute(text("SELECT version()"))).scalar_one()
            return HealthReport(healthy=True, server_version=version)
        except Exception as exc:
            return HealthReport(healthy=False, error=str(exc))

    async def introspect(self) -> StructuralSnapshot:
        # Use run_sync + sqlalchemy.inspect for reflection, then overlay comments
        # (COMMENTS_SQL) and approximate row counts (ROW_COUNTS_SQL). Build
        # EntitySnapshot per table and view, skipping SYSTEM_SCHEMAS, sorted by
        # (schema_name, name) so snapshots are byte-stable across runs.
        ...

    async def execute_readonly(self, sql: str, limit: int = 1000, timeout_s: int = 30):
        assert_readonly(sql, self.dialect)
        bounded = apply_limit(sql, self.dialect, limit)
        async with self._engine.connect() as conn:
            await conn.execute(text(f"SET LOCAL statement_timeout = {timeout_s * 1000}"))
            result = await conn.execute(text(bounded))
            return [dict(row) for row in result.mappings()]
```

`sample()` and `distinct_values()` build parameterized `SELECT`s with quoted identifiers and route through `execute_readonly()`. `registry.py` maps `SourceKind.POSTGRES` to `PostgresAdapter` and raises `NotImplementedError` with a clear message for kinds not yet built.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/integration/test_postgres_adapter.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/adapters apps/api/jamasp/pipeline/snapshot.py apps/api/tests
git commit -m "feat: add source adapter protocol and Postgres introspection"
```

---

### Task 7: Profiler with masking, and the negative privacy test

**Files:**
- Create: `apps/api/jamasp/pipeline/profile.py`, `apps/api/tests/integration/test_profile.py`

**Interfaces:**
- Consumes: `SourceAdapter` (Task 6), `classify_column`, `mask_value` (Task 5), `SamplingPolicy` (Task 3)
- Produces: `ColumnProfile(name, pii_class, distinct_count, null_ratio, min_value, max_value, sample_values)`, `EntityProfile(identity, row_count, columns, sample_rows)`, `async profile_entity(adapter, entity, policy, max_rows=20, max_distinct=50) -> EntityProfile`

This task carries the spec's central privacy guarantee. The decisive test is negative.

- [ ] **Step 1: Write the failing test**

`apps/api/tests/integration/test_profile.py`:

```python
import pytest

from jamasp.adapters.postgres import PostgresAdapter
from jamasp.models.entity import PIIClass
from jamasp.models.source import SamplingPolicy
from jamasp.pipeline.profile import profile_entity


@pytest.fixture
async def employees_snapshot(hr_dsn):
    snapshot = await PostgresAdapter(hr_dsn).introspect()
    return next(e for e in snapshot.entities if e.name == "employees")


@pytest.mark.asyncio
async def test_profile_collects_distinct_values_for_low_cardinality(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    snapshot = await adapter.introspect()
    leave = next(e for e in snapshot.entities if e.name == "leave_requests")

    profile = await profile_entity(adapter, leave, SamplingPolicy.MASKED)
    status = next(c for c in profile.columns if c.name == "status")
    assert sorted(status.sample_values) == [1, 2, 3]
    assert status.distinct_count == 3


@pytest.mark.asyncio
async def test_high_class_columns_have_no_sample_values(hr_dsn, employees_snapshot):
    profile = await profile_entity(PostgresAdapter(hr_dsn), employees_snapshot,
                                   SamplingPolicy.MASKED)
    national_id = next(c for c in profile.columns if c.name == "national_id")
    assert national_id.pii_class is PIIClass.HIGH
    assert national_id.sample_values == []


@pytest.mark.asyncio
async def test_no_raw_pii_anywhere_in_profile(hr_dsn, employees_snapshot):
    """The load-bearing privacy test: real PII must not survive profiling."""
    profile = await profile_entity(PostgresAdapter(hr_dsn), employees_snapshot,
                                   SamplingPolicy.MASKED)
    blob = repr(profile)
    for secret in ("0079542619", "0084575941", "09121234567", "09354445566", "120000000"):
        assert secret not in blob


@pytest.mark.asyncio
async def test_schema_only_policy_collects_no_values(hr_dsn, employees_snapshot):
    profile = await profile_entity(PostgresAdapter(hr_dsn), employees_snapshot,
                                   SamplingPolicy.SCHEMA_ONLY)
    assert profile.sample_rows == []
    assert all(c.sample_values == [] for c in profile.columns)
    assert all(c.null_ratio is not None for c in profile.columns)


@pytest.mark.asyncio
async def test_opaque_column_name_still_masked_by_value_shape(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    snapshot = await adapter.introspect()
    legacy = next(e for e in snapshot.entities if e.name == "t_mst_01")
    profile = await profile_entity(adapter, legacy, SamplingPolicy.MASKED)
    fld_003 = next(c for c in profile.columns if c.name == "fld_003")
    assert fld_003.pii_class is PIIClass.LOW
    assert all("***" in str(v) for v in fld_003.sample_values)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/integration/test_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jamasp.pipeline.profile'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/jamasp/pipeline/profile.py`:

```python
from dataclasses import dataclass, field
from typing import Any

from jamasp.adapters.base import SourceAdapter
from jamasp.models.entity import PIIClass
from jamasp.models.source import SamplingPolicy
from jamasp.pipeline.snapshot import EntitySnapshot
from jamasp.safety.pii import classify_column, mask_value


@dataclass
class ColumnProfile:
    name: str
    data_type: str
    pii_class: PIIClass
    distinct_count: int | None = None
    null_ratio: float | None = None
    min_value: Any = None
    max_value: Any = None
    sample_values: list[Any] = field(default_factory=list)


@dataclass
class EntityProfile:
    schema_name: str
    name: str
    row_count: int | None
    columns: list[ColumnProfile]
    sample_rows: list[dict[str, Any]] = field(default_factory=list)


async def profile_entity(
    adapter: SourceAdapter,
    entity: EntitySnapshot,
    policy: SamplingPolicy,
    max_rows: int = 20,
    max_distinct: int = 50,
) -> EntityProfile:
    columns: list[ColumnProfile] = []

    for column in entity.columns:
        stats = await adapter.column_stats(entity, column.name)
        # Classify from a small unmasked probe that never leaves this function.
        probe = await adapter.distinct_values(entity, column.name, limit=5) \
            if policy is SamplingPolicy.MASKED else []
        pii_class = classify_column(column.name, column.data_type, probe)

        profile = ColumnProfile(
            name=column.name,
            data_type=column.data_type,
            pii_class=pii_class,
            distinct_count=stats.distinct_count,
            null_ratio=stats.null_ratio,
        )

        if policy is SamplingPolicy.MASKED and pii_class is not PIIClass.HIGH:
            if stats.distinct_count is not None and stats.distinct_count <= max_distinct:
                values = await adapter.distinct_values(entity, column.name, limit=max_distinct)
                profile.sample_values = [
                    v for v in (mask_value(x, pii_class) for x in values) if v is not None
                ]
            profile.min_value = mask_value(stats.min_value, pii_class)
            profile.max_value = mask_value(stats.max_value, pii_class)

        columns.append(profile)

    sample_rows: list[dict[str, Any]] = []
    if policy is SamplingPolicy.MASKED:
        pii_by_name = {c.name: c.pii_class for c in columns}
        for row in await adapter.sample(entity, [c.name for c in entity.columns], max_rows):
            masked = {
                k: mask_value(v, pii_by_name[k])
                for k, v in row.items()
                if pii_by_name[k] is not PIIClass.HIGH
            }
            sample_rows.append(masked)

    return EntityProfile(
        schema_name=entity.schema_name,
        name=entity.name,
        row_count=entity.row_count_approx,
        columns=columns,
        sample_rows=sample_rows,
    )
```

Add `column_stats(entity, column) -> ColumnStats(distinct_count, null_ratio, min_value, max_value)` to `SourceAdapter` and `PostgresAdapter`, implemented as a single aggregate query per column routed through `execute_readonly`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/integration/test_profile.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/pipeline/profile.py apps/api/jamasp/adapters apps/api/tests/integration/test_profile.py
git commit -m "feat: add profiler with PII masking and privacy regression test"
```

---

### Task 8: Join probe for undeclared relationships

**Files:**
- Create: `apps/api/jamasp/pipeline/probe.py`, `apps/api/tests/integration/test_probe.py`

**Interfaces:**
- Consumes: `SourceAdapter` (Task 6), `StructuralSnapshot` (Task 6)
- Produces: `CandidateRelationship(from_identity, from_column, to_identity, to_column, hit_rate, distinct_source_values, confidence)`, `async probe_relationships(adapter, snapshot, min_hit_rate=0.9) -> list[CandidateRelationship]`

This is the compensation for rejecting the agentic-explorer architecture. Fixture table `leave_requests.emp_id → employees.id` has no declared FK and must be found.

- [ ] **Step 1: Write the failing test**

`apps/api/tests/integration/test_probe.py`:

```python
import pytest

from jamasp.adapters.postgres import PostgresAdapter
from jamasp.pipeline.probe import probe_relationships


@pytest.mark.asyncio
async def test_finds_undeclared_relationship(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    found = await probe_relationships(adapter, await adapter.introspect())

    match = next(
        (c for c in found
         if c.from_identity[1] == "leave_requests" and c.from_column == "emp_id"),
        None,
    )
    assert match is not None, "join probe missed leave_requests.emp_id -> employees.id"
    assert match.to_identity[1] == "employees"
    assert match.to_column == "id"
    assert match.hit_rate == 1.0


@pytest.mark.asyncio
async def test_does_not_report_already_declared_relationships(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    found = await probe_relationships(adapter, await adapter.introspect())
    assert not any(c.from_column == "dept_id" and c.from_identity[1] == "employees"
                   for c in found)


@pytest.mark.asyncio
async def test_rejects_candidates_below_hit_rate_threshold(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    found = await probe_relationships(adapter, await adapter.introspect(), min_hit_rate=0.99)
    assert all(c.hit_rate >= 0.99 for c in found)


@pytest.mark.asyncio
async def test_ignores_type_mismatched_candidates(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    found = await probe_relationships(adapter, await adapter.introspect())
    assert not any(c.from_column == "mobile" for c in found)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/integration/test_probe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jamasp.pipeline.probe'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/jamasp/pipeline/probe.py`:

```python
import re
from dataclasses import dataclass

from jamasp.adapters.base import SourceAdapter
from jamasp.pipeline.snapshot import EntitySnapshot, StructuralSnapshot

INTEGER_TYPES = {"integer", "bigint", "smallint", "serial", "bigserial", "numeric"}


@dataclass(frozen=True)
class CandidateRelationship:
    from_identity: tuple[str, str]
    from_column: str
    to_identity: tuple[str, str]
    to_column: str
    hit_rate: float
    distinct_source_values: int
    confidence: float


def _stem(column: str) -> str:
    return re.sub(r"_?(id|code|key|no)$", "", column.lower()).strip("_")


def _singularize(name: str) -> str:
    if name.endswith("ies"):
        return name[:-3] + "y"
    return name[:-1] if name.endswith("s") else name


def _looks_like_reference(column_name: str, target: EntitySnapshot) -> bool:
    stem = _stem(column_name)
    if not stem:
        return False
    target_name = _singularize(target.name.lower())
    return stem in {target_name, target.name.lower()} or target_name.startswith(stem)


def _pk_of(entity: EntitySnapshot):
    return next((c for c in entity.columns if c.is_pk), None)


async def probe_relationships(
    adapter: SourceAdapter,
    snapshot: StructuralSnapshot,
    min_hit_rate: float = 0.9,
    sample_limit: int = 1000,
) -> list[CandidateRelationship]:
    declared = {
        (e.identity, col)
        for e in snapshot.entities
        for fk in e.foreign_keys
        for col in fk.from_columns
    }
    tables = [e for e in snapshot.entities if e.kind == "table"]
    results: list[CandidateRelationship] = []

    for source in tables:
        for column in source.columns:
            if column.is_pk or (source.identity, column.name) in declared:
                continue
            if column.data_type.lower() not in INTEGER_TYPES:
                continue

            for target in tables:
                if target.identity == source.identity:
                    continue
                pk = _pk_of(target)
                if pk is None or pk.data_type.lower() not in INTEGER_TYPES:
                    continue
                if not _looks_like_reference(column.name, target):
                    continue

                stats = await adapter.containment(
                    source, column.name, target, pk.name, limit=sample_limit
                )
                if stats.distinct_source_values == 0 or stats.hit_rate < min_hit_rate:
                    continue

                results.append(
                    CandidateRelationship(
                        from_identity=source.identity,
                        from_column=column.name,
                        to_identity=target.identity,
                        to_column=pk.name,
                        hit_rate=stats.hit_rate,
                        distinct_source_values=stats.distinct_source_values,
                        confidence=round(min(1.0, stats.hit_rate * 0.9 + 0.1), 3),
                    )
                )
    return results
```

Add `containment(source, source_col, target, target_col, limit) -> ContainmentStats(hit_rate, distinct_source_values)` to `SourceAdapter` and `PostgresAdapter`, implemented as one bounded aggregate query routed through `execute_readonly`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/integration/test_probe.py -v`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/pipeline/probe.py apps/api/jamasp/adapters apps/api/tests/integration/test_probe.py
git commit -m "feat: infer undeclared relationships via bounded join probe"
```

---

### Task 9: LLM provider abstraction with task routing

**Files:**
- Create: `apps/api/jamasp/llm/__init__.py`, `apps/api/jamasp/llm/base.py`, `apps/api/jamasp/llm/openai_compat.py`, `apps/api/jamasp/llm/router.py`, `apps/api/tests/unit/test_llm_router.py`

**Interfaces:**
- Consumes: `Setting`, `LLMCall` models (Task 3)
- Produces:
  - `Completion(text, tokens_in, tokens_out, model, provider, latency_ms)`
  - `LLMProvider` protocol: `async complete(messages, *, model, schema=None, **kw) -> Completion`, `async embed(texts, *, model) -> list[list[float]]`
  - `OpenAICompatProvider(name, base_url, api_key, extra_headers=None)`
  - `TaskRoute(task, provider, model, temperature, fallbacks)`
  - `async call_task(session, task: str, messages, *, schema=None, scan_id=None) -> Completion`
  - `DEFAULT_ROUTES: dict[str, TaskRoute]`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/unit/test_llm_router.py`:

```python
import pytest

from jamasp.llm.base import Completion
from jamasp.llm.router import RouteExhaustedError, call_task
from jamasp.models.observability import LLMCall


class FakeProvider:
    def __init__(self, name, *, fail=False, text='{"ok": true}'):
        self.name, self.fail, self.text, self.calls = name, fail, text, 0

    async def complete(self, messages, *, model, schema=None, **kw):
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} unavailable")
        return Completion(text=self.text, tokens_in=10, tokens_out=20,
                          model=model, provider=self.name, latency_ms=5)


@pytest.mark.asyncio
async def test_routes_task_to_configured_provider(session, monkeypatch):
    primary = FakeProvider("openrouter")
    monkeypatch.setattr("jamasp.llm.router.build_provider", lambda name, cfg: primary)

    result = await call_task(session, "describe_entity", [{"role": "user", "content": "hi"}])
    assert result.text == '{"ok": true}'
    assert primary.calls == 1


@pytest.mark.asyncio
async def test_falls_back_when_primary_fails(session, monkeypatch):
    providers = {"openrouter": FakeProvider("openrouter", fail=True),
                 "gapgpt": FakeProvider("gapgpt")}
    monkeypatch.setattr("jamasp.llm.router.build_provider", lambda name, cfg: providers[name])

    result = await call_task(session, "describe_entity", [{"role": "user", "content": "hi"}])
    assert result.provider == "gapgpt"
    assert providers["openrouter"].calls == 1


@pytest.mark.asyncio
async def test_raises_when_every_provider_fails(session, monkeypatch):
    monkeypatch.setattr("jamasp.llm.router.build_provider",
                        lambda name, cfg: FakeProvider(name, fail=True))
    with pytest.raises(RouteExhaustedError):
        await call_task(session, "describe_entity", [{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_logs_token_usage_for_cost_visibility(session, monkeypatch):
    monkeypatch.setattr("jamasp.llm.router.build_provider",
                        lambda name, cfg: FakeProvider("openrouter"))
    await call_task(session, "describe_entity", [{"role": "user", "content": "hi"}])
    await session.flush()

    logged = (await session.scalars(__import__("sqlalchemy").select(LLMCall))).all()
    assert len(logged) == 1
    assert logged[0].purpose == "describe_entity"
    assert logged[0].tokens_in == 10 and logged[0].tokens_out == 20


@pytest.mark.asyncio
async def test_api_key_never_appears_in_log_row(session, monkeypatch):
    monkeypatch.setattr("jamasp.llm.router.build_provider",
                        lambda name, cfg: FakeProvider("openrouter"))
    await call_task(session, "describe_entity", [{"role": "user", "content": "hi"}])
    await session.flush()
    row = (await session.scalars(__import__("sqlalchemy").select(LLMCall))).one()
    assert "sk-" not in repr(row.__dict__)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_llm_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jamasp.llm'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/jamasp/llm/base.py`:

```python
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    provider: str
    latency_ms: int


class LLMProvider(Protocol):
    name: str

    async def complete(self, messages: list[dict[str, str]], *, model: str,
                       schema: dict[str, Any] | None = None, **kw) -> Completion: ...

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]: ...
```

`apps/api/jamasp/llm/openai_compat.py` — one `httpx.AsyncClient`-based implementation serving all three providers, since GapGPT, OpenRouter and local runtimes are all OpenAI-compatible and differ only in base URL and headers. Uses `response_format={"type": "json_schema", ...}` when `schema` is given. Timeout 120s, no retry (the router owns retry).

`apps/api/jamasp/llm/router.py`:

```python
import asyncio
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from jamasp.llm.base import Completion
from jamasp.llm.openai_compat import OpenAICompatProvider
from jamasp.models.observability import LLMCall


class RouteExhaustedError(Exception):
    pass


@dataclass(frozen=True)
class TaskRoute:
    task: str
    provider: str
    model: str
    temperature: float = 0.2
    fallbacks: list[tuple[str, str]] = field(default_factory=list)


DEFAULT_ROUTES: dict[str, TaskRoute] = {
    "describe_entity": TaskRoute(
        task="describe_entity",
        provider="openrouter",
        model="nvidia/nemotron-3-ultra-550b-a55b:free",
        fallbacks=[("openrouter", "inclusionai/ling-3.0-flash:free"), ("gapgpt", "gpt-4o")],
    ),
    "describe_field_batch": TaskRoute(
        task="describe_field_batch",
        provider="openrouter",
        model="inclusionai/ling-3.0-flash:free",
        fallbacks=[("gapgpt", "gpt-4o-mini")],
    ),
    "embed": TaskRoute(task="embed", provider="local", model="bge-m3"),
    "translate": TaskRoute(
        task="translate", provider="openrouter", model="inclusionai/ling-3.0-flash:free"
    ),
}


def build_provider(name: str, config: dict) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        name=name,
        base_url=config["base_url"],
        api_key=config["api_key"],
        extra_headers=config.get("extra_headers"),
    )


async def call_task(session: AsyncSession, task: str, messages, *, schema=None,
                    scan_id=None, max_attempts_per_model: int = 2) -> Completion:
    route = await load_route(session, task)
    providers_config = await load_provider_config(session)
    attempts = [(route.provider, route.model), *route.fallbacks]
    last_error: Exception | None = None

    for provider_name, model in attempts:
        provider = build_provider(provider_name, providers_config.get(provider_name, {}))
        for attempt in range(max_attempts_per_model):
            try:
                completion = await provider.complete(
                    messages, model=model, schema=schema, temperature=route.temperature
                )
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(2**attempt)
                continue

            session.add(LLMCall(
                scan_id=scan_id, purpose=task, provider=provider_name, model=model,
                tokens_in=completion.tokens_in, tokens_out=completion.tokens_out,
                latency_ms=completion.latency_ms, status="ok",
            ))
            return completion

    session.add(LLMCall(scan_id=scan_id, purpose=task, provider=route.provider,
                        model=route.model, tokens_in=0, tokens_out=0, status="failed"))
    raise RouteExhaustedError(f"all providers failed for task {task}: {last_error}")
```

`load_route()` reads `settings["llm_routes"]` falling back to `DEFAULT_ROUTES`; `load_provider_config()` reads `settings["llm_providers"]`, decrypting each `api_key` with `jamasp.security.crypto`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/unit/test_llm_router.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/llm apps/api/tests/unit/test_llm_router.py
git commit -m "feat: add LLM provider abstraction with per-task routing and cost logging"
```

---

### Task 10: Describer

**Files:**
- Create: `apps/api/jamasp/llm/prompts/__init__.py`, `apps/api/jamasp/llm/prompts/describe_entity.py`, `apps/api/jamasp/pipeline/describe.py`, `apps/api/tests/fixtures/cassettes/describe_leave_requests.json`, `apps/api/tests/unit/test_describe.py`

**Interfaces:**
- Consumes: `call_task` (Task 9), `EntityProfile` (Task 7), `EntitySnapshot` (Task 6)
- Produces: `DESCRIBE_SCHEMA: dict` (JSON schema), `build_describe_messages(entity, profile, neighbors) -> list[dict]`, `EntityDescription(summary, grain, business_domain, common_questions, fields, confidence)`, `async describe_entity(session, entity, profile, neighbors, scan_id) -> EntityDescription`, `DescribeFailed(Exception)`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/unit/test_describe.py`:

```python
import json
from pathlib import Path

import pytest

from jamasp.llm.base import Completion
from jamasp.llm.prompts.describe_entity import build_describe_messages
from jamasp.pipeline.describe import DescribeFailed, describe_entity

CASSETTE = json.loads(
    (Path(__file__).parent.parent / "fixtures/cassettes/describe_leave_requests.json").read_text()
)


def _completion(text):
    return Completion(text=text, tokens_in=100, tokens_out=200,
                      model="test", provider="test", latency_ms=1)


@pytest.mark.asyncio
async def test_produces_bilingual_description(session, monkeypatch, leave_entity, leave_profile):
    async def fake_call(*a, **kw):
        return _completion(json.dumps(CASSETTE))
    monkeypatch.setattr("jamasp.pipeline.describe.call_task", fake_call)

    result = await describe_entity(session, leave_entity, leave_profile, [], scan_id=None)
    assert result.summary["fa"] and result.summary["en"]
    assert "مرخصی" in result.summary["fa"]


@pytest.mark.asyncio
async def test_decodes_coded_status_column(session, monkeypatch, leave_entity, leave_profile):
    async def fake_call(*a, **kw):
        return _completion(json.dumps(CASSETTE))
    monkeypatch.setattr("jamasp.pipeline.describe.call_task", fake_call)

    result = await describe_entity(session, leave_entity, leave_profile, [], scan_id=None)
    status = next(f for f in result.fields if f["name"] == "status")
    assert status["enum_map"]["2"]["fa"] == "تایید شده"
    assert status["enum_map"]["2"]["en"] == "approved"


@pytest.mark.asyncio
async def test_repairs_malformed_json_on_second_attempt(session, monkeypatch,
                                                        leave_entity, leave_profile):
    responses = [_completion("not json at all"), _completion(json.dumps(CASSETTE))]

    async def fake_call(*a, **kw):
        return responses.pop(0)
    monkeypatch.setattr("jamasp.pipeline.describe.call_task", fake_call)

    result = await describe_entity(session, leave_entity, leave_profile, [], scan_id=None)
    assert result.summary["fa"]
    assert responses == []


@pytest.mark.asyncio
async def test_raises_after_repair_also_fails(session, monkeypatch, leave_entity, leave_profile):
    async def fake_call(*a, **kw):
        return _completion("still not json")
    monkeypatch.setattr("jamasp.pipeline.describe.call_task", fake_call)

    with pytest.raises(DescribeFailed):
        await describe_entity(session, leave_entity, leave_profile, [], scan_id=None)


def test_prompt_contains_masked_samples_but_no_raw_pii(employees_entity, employees_profile):
    messages = build_describe_messages(employees_entity, employees_profile, [])
    blob = json.dumps(messages, ensure_ascii=False)
    assert "national_id" in blob          # the column name is context
    assert "0079542619" not in blob       # the value is not
    assert "09121234567" not in blob


def test_prompt_includes_neighbor_tables_for_join_reasoning(leave_entity, leave_profile,
                                                            employees_entity):
    messages = build_describe_messages(leave_entity, leave_profile, [employees_entity])
    blob = json.dumps(messages, ensure_ascii=False)
    assert "employees" in blob
```

Add `leave_entity`, `leave_profile`, `employees_entity`, `employees_profile` fixtures to `conftest.py`, built from the fixture database via the Task 6/7 code. Write the cassette as a realistic model response conforming to `DESCRIBE_SCHEMA`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_describe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jamasp.pipeline.describe'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/jamasp/llm/prompts/describe_entity.py`:

```python
import json

BILINGUAL = {
    "type": "object",
    "properties": {"fa": {"type": "string"}, "en": {"type": "string"}},
    "required": ["fa", "en"],
}

DESCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": BILINGUAL,
        "grain": {"type": "string"},
        "business_domain": {"type": "string"},
        "common_questions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "meaning": BILINGUAL,
                    "unit": {"type": ["string", "null"]},
                    "enum_map": {"type": ["object", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["name", "meaning", "confidence"],
            },
        },
    },
    "required": ["summary", "grain", "fields", "confidence"],
}

SYSTEM = """You are a database analyst for جاماسپ, a bilingual (Persian/English) reporting tool.
Given a table's structure and masked sample values, explain what it means in business terms.

Rules:
- Write every summary and meaning in BOTH Persian (fa) and English (en). They must say the same thing.
- Coded columns (integer status/type columns with few distinct values) are the priority:
  infer what each code means and fill enum_map. Column comments often contain the decoding.
- Values shown as *** are masked personal data. Never speculate about the hidden characters.
- Report low confidence honestly when the evidence is weak. A wrong confident guess is worse
  than an admitted uncertainty, because a human reviews this and trusts your confidence signal.
"""


def build_describe_messages(entity, profile, neighbors) -> list[dict[str, str]]:
    payload = {
        "table": {
            "schema": entity.schema_name,
            "name": entity.name,
            "kind": entity.kind,
            "comment": entity.comment,
            "row_count_approx": entity.row_count_approx,
            "columns": [
                {
                    "name": c.name, "type": c.data_type, "nullable": c.nullable,
                    "is_pk": c.is_pk, "comment": c.comment,
                    "distinct_count": p.distinct_count, "null_ratio": p.null_ratio,
                    "sample_values": p.sample_values, "pii_class": str(p.pii_class),
                }
                for c, p in zip(entity.columns,
                                sorted(profile.columns, key=lambda x: x.name), strict=False)
            ],
            "foreign_keys": [
                {"from": list(fk.from_columns), "to": f"{fk.to_table}.{list(fk.to_columns)[0]}"}
                for fk in entity.foreign_keys
            ],
        },
        "related_tables": [
            {"name": n.name, "columns": [c.name for c in n.columns]} for n in neighbors
        ],
    }
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]
```

Note the column zip must key on column name rather than position — implement it as a name-indexed lookup so a reordered profile cannot misalign meanings with columns.

`apps/api/jamasp/pipeline/describe.py` calls `call_task(session, "describe_entity", messages, schema=DESCRIBE_SCHEMA, scan_id=scan_id)`, parses the JSON, and on `JSONDecodeError` or schema-validation failure retries **once** with the parse error appended as a user message; a second failure raises `DescribeFailed`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/unit/test_describe.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/llm/prompts apps/api/jamasp/pipeline/describe.py apps/api/tests
git commit -m "feat: add bilingual LLM entity describer with JSON repair pass"
```

---

### Task 11: Snapshot diff engine

**Files:**
- Create: `apps/api/jamasp/pipeline/diff.py`, `apps/api/tests/unit/test_diff.py`

**Interfaces:**
- Consumes: `StructuralSnapshot`, `EntitySnapshot` (Task 6), `EntityStatus` (Task 3)
- Produces: `EntityChange(identity, change, previous_hash, current_hash, column_changes)`, `SnapshotDiff(added, changed, unchanged, removed)`, `diff_snapshots(previous: StructuralSnapshot | None, current: StructuralSnapshot) -> SnapshotDiff`, `status_for(change: str) -> EntityStatus`

This is what makes re-scans cheap and preserves human review effort — the behavior chosen in the spec.

- [ ] **Step 1: Write the failing test**

`apps/api/tests/unit/test_diff.py`:

```python
from dataclasses import replace

import pytest

from jamasp.models.entity import EntityStatus
from jamasp.pipeline.diff import diff_snapshots, status_for
from jamasp.pipeline.snapshot import ColumnInfo, EntitySnapshot, StructuralSnapshot


def _column(name, data_type="integer", ordinal=0, nullable=True, is_pk=False):
    return ColumnInfo(name=name, data_type=data_type, nullable=nullable,
                      is_pk=is_pk, ordinal=ordinal)


def _entity(name, columns):
    return EntitySnapshot(kind="table", schema_name="public", name=name,
                          columns=tuple(columns))


def _snapshot(entities):
    return StructuralSnapshot(dialect="postgres", entities=tuple(entities))


BASE = _snapshot([
    _entity("employees", [_column("id", is_pk=True), _column("full_name", "text", 1)]),
    _entity("departments", [_column("id", is_pk=True)]),
])


def test_first_scan_marks_everything_added():
    result = diff_snapshots(None, BASE)
    assert {i[1] for i in result.added} == {"employees", "departments"}
    assert result.changed == [] and result.removed == []


def test_identical_snapshots_produce_no_changes():
    result = diff_snapshots(BASE, BASE)
    assert result.added == [] and result.changed == [] and result.removed == []
    assert len(result.unchanged) == 2


def test_added_column_marks_only_that_table_changed():
    current = _snapshot([
        _entity("employees", [_column("id", is_pk=True), _column("full_name", "text", 1),
                              _column("email", "text", 2)]),
        _entity("departments", [_column("id", is_pk=True)]),
    ])
    result = diff_snapshots(BASE, current)
    assert [i[1] for i in [c.identity for c in result.changed]] == ["employees"]
    assert ("public", "departments") in result.unchanged
    assert result.changed[0].column_changes == {"added": ["email"], "removed": [], "retyped": []}


def test_retyped_column_is_reported():
    current = _snapshot([
        _entity("employees", [_column("id", is_pk=True), _column("full_name", "varchar", 1)]),
        _entity("departments", [_column("id", is_pk=True)]),
    ])
    result = diff_snapshots(BASE, current)
    assert result.changed[0].column_changes["retyped"] == ["full_name"]


def test_dropped_table_is_removed_not_changed():
    current = _snapshot([_entity("departments", [_column("id", is_pk=True)])])
    result = diff_snapshots(BASE, current)
    assert [i[1] for i in result.removed] == ["employees"]


def test_row_count_change_alone_is_not_a_schema_change():
    grown = _snapshot([
        replace(BASE.entities[0], row_count_approx=999999),
        BASE.entities[1],
    ])
    assert diff_snapshots(BASE, grown).changed == []


@pytest.mark.parametrize("change,expected", [
    ("added", EntityStatus.PENDING),
    ("changed", EntityStatus.STALE),
    ("removed", EntityStatus.ARCHIVED),
])
def test_status_mapping(change, expected):
    assert status_for(change) is expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_diff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jamasp.pipeline.diff'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/jamasp/pipeline/diff.py`:

```python
from dataclasses import dataclass, field

from jamasp.models.entity import EntityStatus
from jamasp.pipeline.snapshot import EntitySnapshot, StructuralSnapshot

Identity = tuple[str, str]


@dataclass
class EntityChange:
    identity: Identity
    change: str
    previous_hash: str | None
    current_hash: str | None
    column_changes: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SnapshotDiff:
    added: list[Identity] = field(default_factory=list)
    changed: list[EntityChange] = field(default_factory=list)
    unchanged: list[Identity] = field(default_factory=list)
    removed: list[Identity] = field(default_factory=list)


def _column_changes(before: EntitySnapshot, after: EntitySnapshot) -> dict[str, list[str]]:
    old = {c.name: c for c in before.columns}
    new = {c.name: c for c in after.columns}
    return {
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "retyped": sorted(
            name for name in old.keys() & new.keys()
            if old[name].data_type != new[name].data_type
        ),
    }


def diff_snapshots(
    previous: StructuralSnapshot | None, current: StructuralSnapshot
) -> SnapshotDiff:
    result = SnapshotDiff()
    current_map = current.by_identity()

    if previous is None:
        result.added = sorted(current_map.keys())
        return result

    previous_map = previous.by_identity()

    for identity, entity in sorted(current_map.items()):
        if identity not in previous_map:
            result.added.append(identity)
            continue
        before = previous_map[identity]
        previous_hash = previous.hash_for(before)
        current_hash = current.hash_for(entity)
        if previous_hash == current_hash:
            result.unchanged.append(identity)
        else:
            result.changed.append(EntityChange(
                identity=identity, change="changed",
                previous_hash=previous_hash, current_hash=current_hash,
                column_changes=_column_changes(before, entity),
            ))

    result.removed = sorted(previous_map.keys() - current_map.keys())
    return result


def status_for(change: str) -> EntityStatus:
    return {
        "added": EntityStatus.PENDING,
        "changed": EntityStatus.STALE,
        "removed": EntityStatus.ARCHIVED,
    }[change]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/unit/test_diff.py -v`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/pipeline/diff.py apps/api/tests/unit/test_diff.py
git commit -m "feat: add structural snapshot diff engine"
```

---

### Task 12: Scan orchestrator

**Files:**
- Create: `apps/api/jamasp/pipeline/embed.py`, `apps/api/jamasp/pipeline/orchestrator.py`, `apps/api/jamasp/pipeline/worker.py`, `apps/api/tests/integration/test_orchestrator.py`

**Interfaces:**
- Consumes: every pipeline stage (Tasks 6–11), `adapter_for` (Task 6), models (Task 3)
- Produces: `async run_scan(session, scan_id: UUID, progress: ProgressSink | None = None) -> Scan`, `ProgressEvent(stage, current, total, message)`, `ProgressSink` protocol, `async embed_entities(session, entities, scan_id) -> None`, arq `WorkerSettings` with `scan_task(ctx, scan_id)`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/integration/test_orchestrator.py`:

```python
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from jamasp.llm.base import Completion
from jamasp.models.entity import Entity, EntityStatus
from jamasp.models.relationship import Relationship, RelationshipKind
from jamasp.models.scan import Scan, ScanStatus
from jamasp.pipeline.orchestrator import run_scan

CASSETTE = json.loads(
    (Path(__file__).parent.parent / "fixtures/cassettes/describe_generic.json").read_text()
)


@pytest.fixture
def stub_llm(monkeypatch):
    async def fake_call(session, task, messages, **kw):
        return Completion(text=json.dumps(CASSETTE), tokens_in=50, tokens_out=80,
                          model="stub", provider="stub", latency_ms=1)
    monkeypatch.setattr("jamasp.pipeline.describe.call_task", fake_call)
    monkeypatch.setattr("jamasp.pipeline.embed.embed_texts",
                        lambda session, texts, **kw: [[0.0] * 1024 for _ in texts])


@pytest.mark.asyncio
async def test_full_scan_creates_described_pending_entities(session, hr_source, stub_llm):
    scan = await run_scan(session, hr_source.pending_scan_id)

    assert scan.status is ScanStatus.SUCCEEDED
    entities = (await session.scalars(
        select(Entity).where(Entity.data_source_id == hr_source.id)
    )).all()
    names = {e.name for e in entities}
    assert {"employees", "departments", "leave_requests", "t_mst_01"} <= names
    assert all(e.status is EntityStatus.PENDING for e in entities)
    assert all(e.description_ai is not None for e in entities)
    assert all(e.embedding is not None for e in entities)


@pytest.mark.asyncio
async def test_scan_persists_inferred_relationship(session, hr_source, stub_llm):
    await run_scan(session, hr_source.pending_scan_id)
    inferred = (await session.scalars(
        select(Relationship).where(Relationship.kind == RelationshipKind.INFERRED)
    )).all()
    assert any(r.from_field == "emp_id" for r in inferred)


@pytest.mark.asyncio
async def test_rescan_preserves_approved_entities(session, hr_source, stub_llm, hr_engine):
    await run_scan(session, hr_source.pending_scan_id)
    employees = (await session.scalars(
        select(Entity).where(Entity.name == "employees")
    )).one()
    employees.status = EntityStatus.APPROVED
    employees.description_human = {"summary_fa": "دست‌نویس من", "summary_en": "my text"}
    await session.flush()

    await hr_engine.execute("ALTER TABLE departments ADD COLUMN budget bigint")
    second = await run_scan(session, await new_scan(session, hr_source.id))

    await session.refresh(employees)
    assert employees.status is EntityStatus.APPROVED
    assert employees.description_human["summary_fa"] == "دست‌نویس من"

    departments = (await session.scalars(
        select(Entity).where(Entity.name == "departments")
    )).one()
    assert departments.status is EntityStatus.STALE
    assert second.status is ScanStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_describe_failure_isolates_to_one_entity(session, hr_source, monkeypatch):
    from jamasp.pipeline.describe import DescribeFailed

    calls = {"n": 0}

    async def flaky(session_, entity, profile, neighbors, scan_id):
        calls["n"] += 1
        if entity.name == "t_mst_01":
            raise DescribeFailed("model refused")
        return _valid_description()
    monkeypatch.setattr("jamasp.pipeline.orchestrator.describe_entity", flaky)

    scan = await run_scan(session, hr_source.pending_scan_id)

    assert scan.status is ScanStatus.PARTIAL
    failed = (await session.scalars(
        select(Entity).where(Entity.status == EntityStatus.DESCRIBE_FAILED)
    )).all()
    assert [e.name for e in failed] == ["t_mst_01"]


@pytest.mark.asyncio
async def test_progress_events_cover_every_stage(session, hr_source, stub_llm):
    seen = []
    await run_scan(session, hr_source.pending_scan_id, progress=seen.append)
    stages = {e.stage for e in seen}
    assert stages == {"introspect", "profile", "probe", "describe", "embed", "diff"}
```

Add an `hr_source` fixture creating a `DataSource` row pointing at the fixture container with an encrypted DSN, plus a queued `Scan`, and a `new_scan()` helper.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/integration/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jamasp.pipeline.orchestrator'`

- [ ] **Step 3: Write minimal implementation**

`apps/api/jamasp/pipeline/orchestrator.py` — sequences the stages, persisting after each so a worker restart resumes at the last completed stage:

```python
async def run_scan(session, scan_id, progress=None):
    scan = await session.get(Scan, scan_id)
    source = await session.get(DataSource, scan.data_source_id)
    adapter = adapter_for(source.kind, decrypt_config(source))

    scan.status, scan.started_at = ScanStatus.RUNNING, utcnow()
    await session.flush()
    failures: list[dict] = []

    try:
        emit(progress, "introspect", 0, 1, "reading schema")
        snapshot = await adapter.introspect()
        scan.structural_snapshot = snapshot.to_json()
        await session.flush()

        previous = await load_previous_snapshot(session, source.id, exclude=scan.id)
        delta = diff_snapshots(previous, snapshot)
        entities = await upsert_entities(session, source, snapshot, delta)
        # Only entities needing work: newly added, changed, or previously failed.
        todo = [e for e in entities if e.status in (
            EntityStatus.PENDING, EntityStatus.STALE, EntityStatus.DESCRIBE_FAILED)]

        profiles = {}
        for index, entity in enumerate(todo):
            emit(progress, "profile", index, len(todo), entity.name)
            profiles[entity.id] = await profile_entity(
                adapter, snapshot_for(snapshot, entity), source.sampling_policy)

        emit(progress, "probe", 0, 1, "inferring relationships")
        await persist_relationships(session, source, snapshot,
                                    await probe_relationships(adapter, snapshot))

        for index, entity in enumerate(todo):
            emit(progress, "describe", index, len(todo), entity.name)
            try:
                description = await describe_entity(
                    session, snapshot_for(snapshot, entity), profiles[entity.id],
                    neighbors_of(snapshot, entity), scan.id)
            except DescribeFailed as exc:
                entity.status = EntityStatus.DESCRIBE_FAILED
                failures.append({"entity": entity.name, "error": str(exc)})
                continue
            apply_description(entity, description)
            await session.flush()

        emit(progress, "embed", 0, 1, "indexing descriptions")
        await embed_entities(session, [e for e in todo
                                       if e.status is not EntityStatus.DESCRIBE_FAILED], scan.id)

        emit(progress, "diff", 0, 1, "finalizing")
        await archive_removed(session, source, delta)

        scan.status = ScanStatus.PARTIAL if failures else ScanStatus.SUCCEEDED
        scan.error = {"failures": failures} if failures else None
        source.status = SourceStatus.READY
        source.last_scan_at = utcnow()
    except Exception as exc:
        scan.status, scan.error = ScanStatus.FAILED, {"fatal": str(exc)}
        source.status = SourceStatus.ERROR
        raise
    finally:
        scan.finished_at = utcnow()
        scan.stats = await scan_stats(session, scan.id)
        await session.commit()

    return scan
```

Critical detail in `upsert_entities`: entities whose identity is in `delta.unchanged` are **not touched** — their `status`, `description_human` and `approved_at` survive verbatim. Entities in `delta.changed` get new `structural`/`structural_hash` and `status = STALE`, but `description_human` is preserved.

`embed.py` concatenates each entity's bilingual summary, field meanings, and common questions, then calls `call_task(session, "embed", ...)`. `worker.py` defines arq `WorkerSettings` with `scan_task(ctx, scan_id)` opening its own session and publishing progress events to a Redis pub/sub channel keyed by scan id.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/integration/test_orchestrator.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/pipeline apps/api/tests/integration/test_orchestrator.py
git commit -m "feat: add scan orchestrator with per-entity failure isolation"
```

---

### Task 13: Auth and admin authorization

**Files:**
- Create: `apps/api/jamasp/security/password.py`, `apps/api/jamasp/security/tokens.py`, `apps/api/jamasp/security/deps.py`, `apps/api/jamasp/routers/__init__.py`, `apps/api/jamasp/routers/auth.py`, `apps/api/jamasp/schemas/auth.py`, `apps/api/tests/integration/test_auth.py`
- Modify: `apps/api/jamasp/main.py`

**Interfaces:**
- Consumes: `User`, `UserRole` (Task 3), `Settings` (Task 1)
- Produces: `hash_password(raw) -> str`, `verify_password(raw, hashed) -> bool`, `issue_token(user) -> str`, `decode_token(token) -> dict`, `current_user` and `require_admin` FastAPI dependencies

- [ ] **Step 1: Write the failing test**

`apps/api/tests/integration/test_auth.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_login_sets_httponly_cookie(client, admin_user):
    response = await client.post("/api/auth/login",
                                 json={"email": admin_user.email, "password": "correct-horse"})
    assert response.status_code == 200
    cookie = response.cookies.jar._cookies
    assert "jamasp_session" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(client, admin_user):
    response = await client.post("/api/auth/login",
                                 json={"email": admin_user.email, "password": "wrong"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_password_hash_never_returned(client, admin_user, admin_cookie):
    response = await client.get("/api/auth/me", cookies=admin_cookie)
    assert response.status_code == 200
    assert "password" not in response.text.lower()
    assert response.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_analyst_cannot_access_admin_route(client, analyst_cookie):
    response = await client.post("/api/sources", cookies=analyst_cookie,
                                 json={"name": "x", "kind": "postgres", "dsn": "postgresql://x"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(client):
    assert (await client.get("/api/sources")).status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/integration/test_auth.py -v`
Expected: FAIL — 404 on `/api/auth/login`

- [ ] **Step 3: Write minimal implementation**

`password.py` wraps `argon2.PasswordHasher`. `tokens.py` issues a PyJWT HS256 token carrying `sub`, `role`, `exp` (12h), signed with `settings.jwt_secret`. `deps.py` reads the `jamasp_session` cookie, decodes it, loads the `User`, and raises 401/403 as appropriate. `routers/auth.py` exposes `POST /api/auth/login` (sets the httpOnly, SameSite=Lax cookie), `POST /api/auth/logout`, and `GET /api/auth/me`. `schemas/auth.py` defines `LoginRequest` and `UserOut` — `UserOut` has no password field at all, so the hash cannot leak by omission of `exclude`.

Register the router in `create_app()`. Add a `seed-admin` CLI entrypoint that creates the first admin from env vars.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/integration/test_auth.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/security apps/api/jamasp/routers apps/api/jamasp/schemas apps/api/jamasp/main.py apps/api/tests/integration/test_auth.py
git commit -m "feat: add cookie auth with admin/analyst roles"
```

---

### Task 14: Sources and scans API with SSE progress

**Files:**
- Create: `apps/api/jamasp/routers/sources.py`, `apps/api/jamasp/routers/scans.py`, `apps/api/jamasp/schemas/source.py`, `apps/api/jamasp/schemas/scan.py`, `apps/api/tests/integration/test_sources_api.py`
- Modify: `apps/api/jamasp/main.py`

**Interfaces:**
- Consumes: `require_admin` (Task 13), `adapter_for` (Task 6), arq queue (Task 12)
- Produces: `POST /api/sources`, `GET /api/sources`, `GET /api/sources/{id}`, `POST /api/sources/test-connection`, `DELETE /api/sources/{id}`, `POST /api/sources/{id}/scans`, `GET /api/scans/{id}`, `GET /api/scans/{id}/events` (SSE)

- [ ] **Step 1: Write the failing test**

`apps/api/tests/integration/test_sources_api.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_create_source_never_echoes_dsn(client, admin_cookie, hr_dsn):
    response = await client.post("/api/sources", cookies=admin_cookie,
                                 json={"name": "HR", "kind": "postgres", "dsn": hr_dsn})
    assert response.status_code == 201
    body = response.json()
    assert "dsn" not in body
    assert "fixture" not in response.text          # the fixture DB password
    assert body["status"] == "draft"


@pytest.mark.asyncio
async def test_list_sources_omits_credentials(client, admin_cookie, hr_source):
    response = await client.get("/api/sources", cookies=admin_cookie)
    assert response.status_code == 200
    assert "config_encrypted" not in response.text
    assert "postgresql://" not in response.text


@pytest.mark.asyncio
async def test_test_connection_reports_failure_legibly(client, admin_cookie):
    response = await client.post(
        "/api/sources/test-connection", cookies=admin_cookie,
        json={"kind": "postgres", "dsn": "postgresql+asyncpg://nobody@127.0.0.1:1/none"})
    assert response.status_code == 200
    body = response.json()
    assert body["healthy"] is False
    assert body["error"]


@pytest.mark.asyncio
async def test_trigger_scan_enqueues_job(client, admin_cookie, hr_source, fake_queue):
    response = await client.post(f"/api/sources/{hr_source.id}/scans", cookies=admin_cookie)
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert fake_queue.enqueued == [("scan_task", response.json()["id"])]


@pytest.mark.asyncio
async def test_scan_events_stream_emits_progress(client, admin_cookie, running_scan):
    async with client.stream("GET", f"/api/scans/{running_scan.id}/events",
                             cookies=admin_cookie) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        first = await anext(response.aiter_lines())
        assert first.startswith("data:") or first.startswith("event:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/integration/test_sources_api.py -v`
Expected: FAIL — 404 on `/api/sources`

- [ ] **Step 3: Write minimal implementation**

`schemas/source.py` defines `SourceCreate` (`name`, `kind`, `dsn: SecretStr`, `sampling_policy`) and `SourceOut` — `SourceOut` deliberately contains no credential field of any kind, so leaking one requires adding a field rather than forgetting to remove it. `routers/sources.py` encrypts the DSN with `crypto.encrypt` on create, runs `adapter.test_connection()` for the test endpoint without persisting anything, and enqueues `scan_task` via arq on scan creation. `routers/scans.py` streams `StreamingResponse` over the Redis pub/sub channel for the scan, formatted as SSE, terminating when a terminal status arrives.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/integration/test_sources_api.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/routers apps/api/jamasp/schemas apps/api/tests/integration/test_sources_api.py
git commit -m "feat: add sources and scans API with SSE progress stream"
```

---

### Task 15: Review API

**Files:**
- Create: `apps/api/jamasp/routers/entities.py`, `apps/api/jamasp/schemas/entity.py`, `apps/api/tests/integration/test_entities_api.py`
- Modify: `apps/api/jamasp/main.py`

**Interfaces:**
- Consumes: `Entity`, `Field`, `Relationship` (Task 3), `require_admin` (Task 13)
- Produces: `GET /api/sources/{id}/entities` (filter by `status`, `min_confidence`, `q`), `GET /api/entities/{id}`, `PATCH /api/entities/{id}`, `POST /api/entities/{id}/approve`, `POST /api/entities/{id}/ignore`, `POST /api/sources/{id}/entities/bulk-approve`, `POST /api/relationships/{id}/approve`, `POST /api/entities/{id}/redescribe`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/integration/test_entities_api.py`:

```python
import pytest

from jamasp.models.entity import EntityStatus


@pytest.mark.asyncio
async def test_list_entities_filters_by_status(client, admin_cookie, scanned_source):
    response = await client.get(
        f"/api/sources/{scanned_source.id}/entities?status=pending", cookies=admin_cookie)
    assert response.status_code == 200
    assert all(e["status"] == "pending" for e in response.json()["items"])


@pytest.mark.asyncio
async def test_list_entities_sorts_low_confidence_first(client, admin_cookie, scanned_source):
    response = await client.get(
        f"/api/sources/{scanned_source.id}/entities?sort=confidence_asc", cookies=admin_cookie)
    scores = [e["confidence"] for e in response.json()["items"] if e["confidence"] is not None]
    assert scores == sorted(scores)


@pytest.mark.asyncio
async def test_patch_stores_human_edit_without_destroying_ai_text(client, admin_cookie, entity):
    original_ai = entity.description_ai
    response = await client.patch(
        f"/api/entities/{entity.id}", cookies=admin_cookie,
        json={"description_human": {"summary_fa": "اصلاح شده", "summary_en": "corrected"}})
    assert response.status_code == 200
    body = response.json()
    assert body["description_human"]["summary_fa"] == "اصلاح شده"
    assert body["description_ai"] == original_ai


@pytest.mark.asyncio
async def test_approve_records_reviewer_and_timestamp(client, admin_cookie, entity, admin_user):
    response = await client.post(f"/api/entities/{entity.id}/approve", cookies=admin_cookie)
    assert response.json()["status"] == "approved"
    assert response.json()["approved_by"] == str(admin_user.id)
    assert response.json()["approved_at"] is not None


@pytest.mark.asyncio
async def test_bulk_approve_respects_confidence_threshold(client, admin_cookie, scanned_source):
    response = await client.post(
        f"/api/sources/{scanned_source.id}/entities/bulk-approve",
        cookies=admin_cookie, json={"min_confidence": 0.8})
    assert response.status_code == 200
    approved = response.json()["approved_count"]

    remaining = await client.get(
        f"/api/sources/{scanned_source.id}/entities?status=pending", cookies=admin_cookie)
    assert all(e["confidence"] < 0.8 for e in remaining.json()["items"])
    assert approved > 0


@pytest.mark.asyncio
async def test_patching_field_meaning_updates_only_that_field(client, admin_cookie, entity):
    field_id = entity.fields[0].id
    response = await client.patch(
        f"/api/entities/{entity.id}", cookies=admin_cookie,
        json={"fields": [{"id": str(field_id),
                          "meaning_human": {"fa": "شناسه", "en": "identifier"}}]})
    assert response.status_code == 200
    changed = next(f for f in response.json()["fields"] if f["id"] == str(field_id))
    assert changed["meaning_human"]["fa"] == "شناسه"
    assert all(f["meaning_human"] is None
               for f in response.json()["fields"] if f["id"] != str(field_id))


@pytest.mark.asyncio
async def test_analyst_cannot_approve(client, analyst_cookie, entity):
    response = await client.post(f"/api/entities/{entity.id}/approve", cookies=analyst_cookie)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_ignore_excludes_entity_from_pending_work(client, admin_cookie, entity):
    await client.post(f"/api/entities/{entity.id}/ignore", cookies=admin_cookie)
    response = await client.get(f"/api/entities/{entity.id}", cookies=admin_cookie)
    assert response.json()["status"] == EntityStatus.IGNORED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/integration/test_entities_api.py -v`
Expected: FAIL — 404 on the entities routes

- [ ] **Step 3: Write minimal implementation**

`routers/entities.py` with paginated listing (`limit`/`offset`, default 50), filters, and `sort` in `{name, confidence_asc, status}`. `PATCH` accepts partial `description_human` and a `fields` array of `{id, meaning_human?, enum_map?, unit?}`, writing only the keys present. Approve sets `status`, `approved_by`, `approved_at` and bumps `version`. Bulk approve updates every `pending` entity at or above the threshold in one statement and returns the count. `redescribe` re-enqueues a single-entity describe job for `describe_failed` recovery.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/integration/test_entities_api.py -v`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/routers/entities.py apps/api/jamasp/schemas/entity.py apps/api/tests/integration/test_entities_api.py
git commit -m "feat: add entity review API with inline edit and bulk approve"
```

---

### Task 16: Settings API for providers and model routing

**Files:**
- Create: `apps/api/jamasp/routers/settings.py`, `apps/api/jamasp/schemas/settings.py`, `apps/api/tests/integration/test_settings_api.py`
- Modify: `apps/api/jamasp/main.py`

**Interfaces:**
- Consumes: `Setting` model (Task 3), `crypto` (Task 2), `DEFAULT_ROUTES` (Task 9)
- Produces: `GET /api/settings/llm`, `PUT /api/settings/llm/providers`, `PUT /api/settings/llm/routes`, `POST /api/settings/llm/test`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/integration/test_settings_api.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_get_returns_defaults_before_configuration(client, admin_cookie):
    response = await client.get("/api/settings/llm", cookies=admin_cookie)
    assert response.status_code == 200
    assert response.json()["routes"]["describe_entity"]["model"] == \
        "nvidia/nemotron-3-ultra-550b-a55b:free"


@pytest.mark.asyncio
async def test_api_key_is_redacted_on_read(client, admin_cookie):
    await client.put("/api/settings/llm/providers", cookies=admin_cookie, json={
        "providers": {"openrouter": {"base_url": "https://openrouter.ai/api/v1",
                                     "api_key": "sk-or-v1-supersecret"}}})
    response = await client.get("/api/settings/llm", cookies=admin_cookie)
    body = response.text
    assert "supersecret" not in body
    assert response.json()["providers"]["openrouter"]["api_key"] == "••••••••"


@pytest.mark.asyncio
async def test_switching_describe_model_to_local_requires_no_code_change(client, admin_cookie):
    response = await client.put("/api/settings/llm/routes", cookies=admin_cookie, json={
        "routes": {"describe_entity": {"provider": "local", "model": "qwen2.5:32b",
                                       "temperature": 0.1, "fallbacks": []}}})
    assert response.status_code == 200
    updated = await client.get("/api/settings/llm", cookies=admin_cookie)
    assert updated.json()["routes"]["describe_entity"]["provider"] == "local"
    assert updated.json()["routes"]["describe_entity"]["model"] == "qwen2.5:32b"


@pytest.mark.asyncio
async def test_analyst_cannot_change_provider_settings(client, analyst_cookie):
    response = await client.put("/api/settings/llm/providers", cookies=analyst_cookie,
                                json={"providers": {}})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unknown_task_name_rejected(client, admin_cookie):
    response = await client.put("/api/settings/llm/routes", cookies=admin_cookie,
                                json={"routes": {"not_a_task": {"provider": "local",
                                                                "model": "x"}}})
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/integration/test_settings_api.py -v`
Expected: FAIL — 404 on `/api/settings/llm`

- [ ] **Step 3: Write minimal implementation**

Store providers under the `llm_providers` settings key with each `api_key` AES-GCM encrypted; store routes under `llm_routes`. Reads merge stored values over `DEFAULT_ROUTES` and replace every `api_key` with the literal `"••••••••"`. Route keys are validated against `DEFAULT_ROUTES.keys()`, rejecting unknown task names with 422. `POST /api/settings/llm/test` issues a one-token completion against a named provider and returns reachability without exposing the key.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/integration/test_settings_api.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/routers/settings.py apps/api/jamasp/schemas/settings.py apps/api/tests/integration/test_settings_api.py
git commit -m "feat: add LLM provider and model routing settings API"
```

---

### Task 17: Knowledge export and end-to-end acceptance

**Files:**
- Create: `apps/api/jamasp/routers/knowledge.py`, `apps/api/jamasp/schemas/knowledge.py`, `apps/api/tests/e2e/test_scan_to_export.py`, `apps/api/tests/fixtures/expected_knowledge.json`
- Modify: `apps/api/jamasp/main.py`

**Interfaces:**
- Consumes: everything above
- Produces: `GET /api/sources/{id}/knowledge` returning the §9 contract, `KnowledgeExport` Pydantic model with `schema_version = "1.0"`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/e2e/test_scan_to_export.py`:

```python
import json
from pathlib import Path

import pytest

EXPECTED = json.loads(
    (Path(__file__).parent.parent / "fixtures/expected_knowledge.json").read_text()
)


@pytest.mark.asyncio
async def test_export_contains_only_approved_entities(client, admin_cookie, scanned_source):
    response = await client.get(f"/api/sources/{scanned_source.id}/knowledge",
                                cookies=admin_cookie)
    assert response.status_code == 200
    body = response.json()
    assert body["entities"] == []          # nothing approved yet


@pytest.mark.asyncio
async def test_full_cycle_scan_approve_export(client, admin_cookie, scanned_source):
    """The S1 acceptance test: register -> scan -> approve -> export."""
    await client.post(f"/api/sources/{scanned_source.id}/entities/bulk-approve",
                      cookies=admin_cookie, json={"min_confidence": 0.0})

    response = await client.get(f"/api/sources/{scanned_source.id}/knowledge",
                                cookies=admin_cookie)
    body = response.json()

    assert body["schema_version"] == "1.0"
    assert body["source"]["dialect"] == "postgresql"
    names = {e["name"] for e in body["entities"]}
    assert {"employees", "departments", "leave_requests"} <= names

    leave = next(e for e in body["entities"] if e["name"] == "leave_requests")
    assert leave["summary"]["fa"] and leave["summary"]["en"]
    status_field = next(f for f in leave["fields"] if f["name"] == "status")
    assert status_field["enum_map"]["2"]["en"] == "approved"
    assert any(r["kind"] == "inferred" and r["from"] == "emp_id"
               for r in leave["relationships"])


@pytest.mark.asyncio
async def test_export_prefers_human_text_over_ai_text(client, admin_cookie, scanned_source):
    entities = (await client.get(f"/api/sources/{scanned_source.id}/entities",
                                 cookies=admin_cookie)).json()["items"]
    target = next(e for e in entities if e["name"] == "employees")
    await client.patch(f"/api/entities/{target['id']}", cookies=admin_cookie,
                       json={"description_human": {"summary_fa": "کارکنان شرکت",
                                                   "summary_en": "Company staff"}})
    await client.post(f"/api/entities/{target['id']}/approve", cookies=admin_cookie)

    body = (await client.get(f"/api/sources/{scanned_source.id}/knowledge",
                             cookies=admin_cookie)).json()
    employees = next(e for e in body["entities"] if e["name"] == "employees")
    assert employees["summary"]["fa"] == "کارکنان شرکت"


@pytest.mark.asyncio
async def test_export_excludes_ignored_and_archived(client, admin_cookie, scanned_source):
    entities = (await client.get(f"/api/sources/{scanned_source.id}/entities",
                                 cookies=admin_cookie)).json()["items"]
    legacy = next(e for e in entities if e["name"] == "t_mst_01")
    await client.post(f"/api/entities/{legacy['id']}/ignore", cookies=admin_cookie)
    await client.post(f"/api/sources/{scanned_source.id}/entities/bulk-approve",
                      cookies=admin_cookie, json={"min_confidence": 0.0})

    body = (await client.get(f"/api/sources/{scanned_source.id}/knowledge",
                             cookies=admin_cookie)).json()
    assert "t_mst_01" not in {e["name"] for e in body["entities"]}


@pytest.mark.asyncio
async def test_export_matches_golden_contract_shape(client, admin_cookie, scanned_source):
    await client.post(f"/api/sources/{scanned_source.id}/entities/bulk-approve",
                      cookies=admin_cookie, json={"min_confidence": 0.0})
    body = (await client.get(f"/api/sources/{scanned_source.id}/knowledge",
                             cookies=admin_cookie)).json()

    def shape(node):
        if isinstance(node, dict):
            return {k: shape(v) for k, v in sorted(node.items())}
        if isinstance(node, list):
            return [shape(node[0])] if node else []
        return type(node).__name__

    assert shape(body) == shape(EXPECTED)


@pytest.mark.asyncio
async def test_export_never_contains_raw_pii(client, admin_cookie, scanned_source):
    await client.post(f"/api/sources/{scanned_source.id}/entities/bulk-approve",
                      cookies=admin_cookie, json={"min_confidence": 0.0})
    body = (await client.get(f"/api/sources/{scanned_source.id}/knowledge",
                             cookies=admin_cookie)).text
    for secret in ("0079542619", "09121234567", "120000000"):
        assert secret not in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/e2e/test_scan_to_export.py -v`
Expected: FAIL — 404 on the knowledge route

- [ ] **Step 3: Write minimal implementation**

`routers/knowledge.py` selects entities with `status == APPROVED` for the source, eagerly loading fields and relationships, and merges human over AI text per field with a helper:

```python
def _merged(ai: dict | None, human: dict | None, key: str) -> dict[str, str]:
    ai_value = (ai or {}).get(key) or {}
    human_value = (human or {}).get(key) or {}
    return {
        "fa": human_value.get("fa") or ai_value.get("fa") or "",
        "en": human_value.get("en") or ai_value.get("en") or "",
    }
```

Only relationships whose **both** endpoints are approved entities are included, so the export never references a table it does not contain. `schemas/knowledge.py` mirrors §9 exactly and is the contract S2 will import.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest -v`
Expected: PASS — the full suite green

- [ ] **Step 5: Commit**

```bash
git add apps/api/jamasp/routers/knowledge.py apps/api/jamasp/schemas/knowledge.py apps/api/tests
git commit -m "feat: add knowledge export endpoint with end-to-end acceptance test"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Covered by |
|---|---|
| §3 architecture, repo layout | Task 1 |
| §4 data model | Task 3 (all nine tables) |
| §5.1 introspector | Task 6 |
| §5.2 profiler + PII | Tasks 5, 7 |
| §5.3 join probe | Task 8 |
| §5.4 describer | Task 10 |
| §5.5 embedder | Task 12 (`embed.py`) |
| §5.6 diff & stage | Tasks 11, 12 |
| §6 review UI | Task 15 provides the API; the UI itself is the frontend plan |
| §7.1 provider abstraction | Tasks 9, 16 |
| §7.2 secrets | Tasks 2, 16 |
| §7.3 auth | Task 13 |
| §7.4 i18n | Frontend plan; backend stores bilingual text from Task 10 |
| §8 read-only guarantee | Task 4, enforced in Tasks 6–8 |
| §9 knowledge export | Task 17 |
| §10 error handling | Tasks 12 (isolation, partial), 14 (connection errors), 10 (JSON repair) |
| §11 testing | Every task |
| §12 acceptance criteria | 1–2 → Task 14; 3–4 → Tasks 8, 10; 5 → Tasks 5, 7, 17; 6 → Task 15; 7 → Tasks 11, 12; 8 → Task 17; 10 → Task 16 |

**Gaps deferred by design:** acceptance criteria 9 (Persian RTL UI) and 11 (the other five adapters) belong to the two follow-up plans named in the scope note. Criterion 11's foundation — the `SourceAdapter` protocol and registry — is built here in Task 6, so each remaining adapter is an isolated addition with no changes to the pipeline.

**Type consistency checked:** `EntitySnapshot.identity` is `tuple[schema_name, name]` everywhere (Tasks 6, 8, 11, 12). `PIIClass` is imported from `jamasp.models.entity` in both `safety/pii.py` and `pipeline/profile.py`. `call_task(session, task, messages, *, schema, scan_id)` has one signature across Tasks 9, 10, 12. `EntityStatus.ARCHIVED` (Task 3) is produced by `status_for("removed")` (Task 11) and consumed by `archive_removed` (Task 12). Adapter methods added incrementally — `column_stats` (Task 7) and `containment` (Task 8) — are declared on the `SourceAdapter` protocol in the task that introduces them.

---

## Execution Handoff

Plan complete. Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — tasks executed in this session via executing-plans, batched with checkpoints.

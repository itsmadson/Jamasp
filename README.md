# آگاه

An AI report builder. Connect a database, verify what the AI understood about it,
then ask for reports in Persian or English.

The platform is built in five subsystems. **S1 — the connector and semantic layer —
is implemented.** It registers a data source, introspects its schema, has an LLM
describe every table in Persian and English, lets a human verify and correct those
descriptions, and exports the approved result as a stable JSON contract.

| # | Subsystem | Status |
|---|-----------|--------|
| S1 | Connector & semantic layer | Built (PostgreSQL adapter) |
| S2 | NL → query engine | Not started — consumes S1's export |
| S3 | Report renderer | Not started |
| S4 | Interactive chat editing | Not started |
| S5 | Platform shell | Built alongside S1 |

Design and plans live in `docs/superpowers/`.

## Running it

Prerequisites: Docker, `uv`, Node 24+.

### 1. Configure secrets

```bash
cp .env.example apps/api/.env
```

Fill in `apps/api/.env`. It is gitignored; never commit it.

```bash
# Both keys must be 32 random bytes, urlsafe-base64 encoded:
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

`AGAH_OPENROUTER_API_KEY` is the only LLM key required to run a scan.

### 2. Start the whole stack

```bash
AGAH_ADMIN_PASSWORD=choose-something docker compose -f docker/compose.dev.yml up --build
```

This starts Postgres (with pgvector), Redis, the API, the scan worker, the web app,
and a seeded fixture database standing in for a customer system. The API applies
migrations and creates the first admin on startup.

Open <http://localhost:3000> — it redirects to `/fa`, the Persian default.

### 3. Or run the pieces directly

```bash
# infrastructure
docker compose -f docker/compose.yml up -d

# API
cd apps/api
uv sync
uv run alembic upgrade head
AGAH_ADMIN_EMAIL=admin@agah.local AGAH_ADMIN_PASSWORD=... uv run python -m agah.cli seed-admin
uv run uvicorn agah.main:app --port 8000

# scan worker (separate terminal)
cd apps/api && uv run arq agah.pipeline.worker.WorkerSettings

# web (separate terminal)
cd apps/web && npm install && npm run dev
```

The fixture database is reachable at
`postgresql+asyncpg://fixture:fixture@127.0.0.1:5433/hr` — register it as a source
to try the full flow.

## Tests

```bash
cd apps/api && uv run pytest     # 116 tests, uses throwaway Postgres containers
cd apps/web && npm test          # 54 tests
```

Neither suite makes a live LLM call: describer tests replay recorded responses.

## How a scan works

```
Introspect → Profile → Probe → Describe → Embed → Diff
 no AI       no AI      no AI    LLM        LLM     no AI
```

Only the two middle stages involve a model. Everything else is deterministic, which
is what makes re-scans cheap: an unchanged table keeps its approval and costs nothing
to scan again.

Two properties are load-bearing and covered by tests:

- **Personal data never reaches the LLM.** Columns are classified before sampling;
  high-risk ones (national ID, salary, IBAN) are never sampled at all, and the rest
  are masked. `test_no_raw_pii_anywhere_in_profile` asserts this against the prompt.
- **Only approved descriptions are exported.** The knowledge endpoint excludes
  anything a human has not verified, which is what makes the review gate real.

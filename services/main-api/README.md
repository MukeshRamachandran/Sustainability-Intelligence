# K-COSMOS Backend API

This directory contains the FastAPI and PostgreSQL foundation for the K-COSMOS
sustainability system. Phase D3 provides configuration, database connectivity,
health endpoints, Docker infrastructure, Alembic wiring, logging and tests.

Checkpoint D4-B.1 adds the PostgreSQL business schema, canonical metric seeds,
real opaque-session authentication, CSRF protection, role/domain authorization,
and safe local/production account bootstrap. Manager submission APIs, review,
publication building, evidence uploads and frontend integration remain the next
checkpoint.

## Prerequisites

- Docker Desktop with Linux containers, or Docker Engine with Compose
- Python 3.12 for running without Docker
- PostgreSQL client tools are optional for D3

## Local configuration

Copy `.env.example` to `.env` for non-Docker local development and replace local
values as needed. `.env` is ignored by Git. Never place production secrets in the
repository or container image.

## Docker

Copy `.env.example` to `.env` and set `POSTGRES_PASSWORD` and `DATABASE_URL`
before starting. Compose does not publish PostgreSQL and does not run migrations.

```bash
docker compose up -d postgres
docker compose run --rm --no-deps api alembic upgrade head
docker compose up -d
```

The API is bound to `127.0.0.1:8000` on the host. Check:

```bash
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health/ready
```

Stop the services while preserving named volumes:

```bash
docker compose down
```

Do not use `docker compose down --volumes` unless destruction of the local database
and evidence volumes is explicitly intended. Production deployment is documented
in `../../docs/DEPLOYMENT.md`.

### Aeron environment worker

`compose.yaml` also defines `environment-worker`. It is built from the same
`Dockerfile` as the API and runs `python -m app.environment.worker`. It polls
Aeron's REST API v1 (`GET /timeseries?station=…`, Bearer `AERON_API_KEY`) every
5 minutes and stores new readings in `environment.readings`. No browser is used.

Set `AERON_API_KEY` in `.env` (the other `AERON_*` defaults are in
`.env.example`), then:

```bash
docker compose up -d environment-worker
docker compose logs --tail 30 environment-worker
curl http://127.0.0.1:8000/api/environment/status
```

One cycle only, for a test (stop the running worker first; a second copy exits
with code 2 because of the advisory lock):

```bash
docker compose stop environment-worker
docker compose run --rm environment-worker python -m app.environment.worker --once
docker compose up -d environment-worker
```

Exit codes: 0 success, 1 cycle failed, 2 another worker holds the lock, 3
`AERON_API_KEY` missing. Full guide:
`../../docs/reports/AERON_INTEGRATION_ARCHITECTURE.md`.

### Evidence recovery

Evidence audit recovery requires both a PostgreSQL backup and a backup of the
private evidence volume. PostgreSQL contains evidence metadata, submission
relationships and revision history; the private volume contains the actual file
content. Compose stores that content in the `evidence_clean` volume. Restoring
only one side does not restore a usable evidence audit record. Use
`../../deployment/scripts/backup-db.sh` for the database dump.

## Local Python checks

Create a Python 3.12 environment and install development dependencies:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

On Windows, use `.venv\\Scripts\\python.exe`.

Run checks:

```bash
ruff check .
mypy app
pytest
```

## Alembic

Migrations live in `alembic/versions/`. Apply them explicitly. The API process
does not migrate on startup. Once PostgreSQL is running, inspect the current
revision with:

```bash
alembic current
```

Apply the business schema:

```bash
alembic upgrade head
```

Create the five synthetic local accounts (development only):

```bash
MICROCOSM_DEV_BOOTSTRAP_PASSWORD='choose-a-local-password' python -m app.bootstrap development
```

Create the first real administrator interactively:

```bash
python -m app.bootstrap admin --username admin --display-name "MICROCOSM Admin"
```

The production command prompts for the password and never stores plaintext in
the repository or database.

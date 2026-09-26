# K-COSMOS Sustainability Intelligence

Public sustainability dashboard, manager and administrator portal, and a FastAPI service backed by PostgreSQL. The public site does not require a login. Manager and administrator actions go through the API. The browser never connects to the database.

Production origin: `https://sustainability.kct.ac.in`

## Architecture

Cloudflare proxies the domain to Nginx on port 443. Nginx sends `/` to the public dashboard on `127.0.0.1:3001`, `/admin/` to the portal on `127.0.0.1:3002`, and `/api/` plus `/health/` to FastAPI on `127.0.0.1:8000`. PostgreSQL and the environment worker stay on the Docker network. Ports 3001, 3002, 8000, and 5432 are not public.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Folder structure

```text
apps/public-dashboard/     anonymous dashboard
apps/manager-admin/        administrator and manager portal
services/main-api/         FastAPI, Alembic, Compose, worker
deployment/                Nginx, systemd, backup and deploy scripts
docs/                      operations documents
tests/frontend/            browser URL contract
tests/api/                 pointer to the pytest suite
tests/integration/         production path contract
```

Historical design notes are in [docs/reports](docs/reports).

## Local development

```bash
cp services/main-api/.env.example services/main-api/.env
```

For a laptop, set `APP_ENV=development`, `SESSION_COOKIE_SECURE=false`, `PUBLIC_BASE_URL=http://localhost:8000`, and `ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`. Put a real local password in `POSTGRES_PASSWORD` and the same password inside `DATABASE_URL`. Do not commit that file.

```bash
cd services/main-api
docker compose up -d postgres
docker compose run --rm --no-deps api alembic upgrade head
docker compose up -d api
```

Serve the portal on port 3000 if you want `auth-client.js` to call port 8000. That port split is development-only. Production pages use `/api/...`.

## Environment variables

The API, worker, Compose, and backup scripts read one file: `services/main-api/.env`. Required production values:

| Variable | Role |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | SQLAlchemy URL for `microcosm_app` |
| `POSTGRES_DB` | `microcosm` |
| `POSTGRES_USER` | `microcosm_app` |
| `POSTGRES_PASSWORD` | Database password |
| `SECRET_KEY` | Session signing secret, at least 32 characters |
| `CSRF_SECRET` | CSRF signing secret, at least 32 characters |
| `PASSWORD_MIN_LENGTH` | Minimum 12 |
| `ALLOWED_ORIGINS` | `https://sustainability.kct.ac.in` |
| `SESSION_COOKIE_SECURE` | `true` in production |
| `AERON_STATION_ID`, `AERON_USERNAME`, `AERON_PASSWORD` | Environment worker only |

`OPENAPI_ENABLED` overrides the default, which hides `/docs` in production.

## Database setup

PostgreSQL 17 is the `postgres` service in `services/main-api/compose.yaml`. It has no published port. See [docs/DATABASE.md](docs/DATABASE.md).

## Alembic migrations

```bash
cd services/main-api
docker compose run --rm --no-deps api alembic upgrade head
```

Startup does not migrate.

## Running the API

```bash
cd services/main-api
docker compose up -d api
```

Local process, with `DATABASE_URL` pointing at a reachable database:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Running the frontend

Production uses the systemd units in `deployment/systemd/`. For a local look at the files:

```bash
python deployment/scripts/static-server.py --host 127.0.0.1 --port 3001 --directory apps/public-dashboard
python deployment/scripts/static-server.py --host 127.0.0.1 --port 3002 --directory apps/manager-admin
```

The manager portal is written to be browsed under `/admin/`.

## Running the worker

```bash
cd services/main-api
docker compose up -d environment-worker
```

The worker polls Aeron and writes environment readings. It needs the `AERON_*` variables in `.env`.

## Production deployment

Follow [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Short form on the server:

```bash
cd /opt/kcosmos/Sustainability-Intelligence
deployment/scripts/deploy.sh
```

## Nginx

`deployment/nginx/sustainability.kct.ac.in.conf` is the public virtual host. Install the snippet files next to it, then `nginx -t` and reload. See the deployment document for the copy commands.

## Cloudflare

Proxied DNS for `sustainability.kct.ac.in`, SSL mode Full (strict), origin certificate on the VPS. The application does not embed Cloudflare Analytics.

## User management

Administrators create managers with `POST /api/admin/users`. The temporary password is hashed, `must_change_password` is set, and an audit event is stored. The password is not returned. See [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md).

## Backups

```bash
BACKUP_DIR=/var/backups/kcosmos deployment/scripts/backup-db.sh
```

## Restore

Stop the API and worker, then:

```bash
CONFIRM_RESTORE=yes deployment/scripts/restore-db.sh --replace /var/backups/kcosmos/microcosm-TIMESTAMP.dump
```

The script refuses to run without both `CONFIRM_RESTORE=yes` and `--replace`.

## Troubleshooting

[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Security notes

- Argon2id password hashes, server-side sessions, CSRF on authenticated writes, login lockout.
- Authorization is enforced in FastAPI, including manager domain.
- Production CORS is the single site origin. Wildcards are rejected. Loopback origins are rejected in production.
- Errors returned to browsers include a request id and a safe message. Stack traces stay in the server log.
- Do not commit `.env`, passwords, or session secrets. `services/main-api/.env.example` has empty secret fields.

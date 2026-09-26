# Database

Production database: PostgreSQL 17, database name `microcosm`, application role `microcosm_app`. The password comes from `POSTGRES_PASSWORD` and from the password embedded in `DATABASE_URL`. Neither value is stored in Git.

```text
DATABASE_URL=postgresql+psycopg://microcosm_app:YOUR_PASSWORD@postgres:5432/microcosm
```

Inside Compose, the host name `postgres` is the database service. From the host, PostgreSQL is not listening on a published port.

## Schemas

Alembic revision `0001` creates the application schemas, including:

- `identity` — users, roles, sessions, manager domains
- `sustainability` — periods, submissions, metrics, factors
- `publication` — releases
- `audit` — audit events
- later revisions add evidence, outreach, waste, LPG units, emission-factor governance, historical data, and environment readings

Current revisions are in `services/main-api/alembic/versions/`. Apply them with:

```bash
cd services/main-api
docker compose run --rm --no-deps api alembic upgrade head
```

Do not point the API container at `alembic upgrade head` as its start command. A failed or destructive migration must not run just because the process restarted.

## Users

Create manager accounts with `POST /api/admin/users` while signed in as an administrator. The handler hashes the temporary password with Argon2id, inserts `identity.users`, `identity.user_role_assignments`, and `identity.manager_domain_assignments`, sets `must_change_password`, and writes an audit event. The response does not include the password or the hash.

Direct SQL inserts are for emergency recovery only, after the API is unavailable and the steps above cannot be used.

## Backups

`deployment/scripts/backup-db.sh` runs `pg_dump --format=custom` inside the PostgreSQL container and writes the file to `BACKUP_DIR` on the host. That path and `BACKUP_RETENTION_DAYS` come from `services/main-api/.env` (default `/var/backups/kcosmos`, 14 days). A shell variable with the same name overrides the file.

`deployment/scripts/restore-db.sh` loads one of those files only when invoked as:

```bash
CONFIRM_RESTORE=yes deployment/scripts/restore-db.sh --replace /var/backups/kcosmos/microcosm-TIMESTAMP.dump
```

Stop the API and the worker first. The script does not drop the backup files and does not run from deploy.

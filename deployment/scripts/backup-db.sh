#!/usr/bin/env bash
# Write a timestamped PostgreSQL custom-format dump outside the database container.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
API_DIR="${REPO_ROOT}/services/main-api"
ENV_FILE="${API_DIR}/.env"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "${ENV_FILE}" ]] || die "missing ${ENV_FILE}"

env_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 || true)"
  printf '%s' "${line#*=}"
}

BACKUP_DIR="${BACKUP_DIR:-$(env_value BACKUP_DIR)}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/kcosmos}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-$(env_value BACKUP_RETENTION_DAYS)}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

db_name="$(env_value POSTGRES_DB)"
db_user="$(env_value POSTGRES_USER)"
db_password="$(env_value POSTGRES_PASSWORD)"
[[ -n "${db_name}" && -n "${db_user}" && -n "${db_password}" ]] || die "database credentials are incomplete"

mkdir -p "${BACKUP_DIR}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${BACKUP_DIR}/microcosm-${stamp}.dump"

cd "${API_DIR}"
PGPASSWORD="${db_password}" docker compose exec -T -e PGPASSWORD postgres \
  pg_dump --format=custom --no-owner --no-privileges -U "${db_user}" -d "${db_name}" \
  > "${target}"

[[ -s "${target}" ]] || die "backup file is empty"
chmod 600 "${target}"
printf 'backup written: %s\n' "${target}"

find "${BACKUP_DIR}" -type f -name 'microcosm-*.dump' -mtime +"${RETENTION_DAYS}" -delete
printf 'retention: removed dumps older than %s days from %s\n' "${RETENTION_DAYS}" "${BACKUP_DIR}"

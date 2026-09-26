#!/usr/bin/env bash
# Restore a pg_dump custom-format backup.
# This script never runs unless both safeguards are present:
#   CONFIRM_RESTORE=yes deployment/scripts/restore-db.sh --replace /path/to/backup.dump
# It does not delete backup files. --replace drops existing objects in the
# target database before loading the dump. Stop the API and worker first.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
API_DIR="${REPO_ROOT}/services/main-api"
ENV_FILE="${API_DIR}/.env"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${CONFIRM_RESTORE:-}" == "yes" ]] || die "refusing to restore; set CONFIRM_RESTORE=yes"
[[ "${1:-}" == "--replace" ]] || die "refusing to restore; pass --replace and the backup path"
backup="${2:-}"
[[ -n "${backup}" && -f "${backup}" ]] || die "backup file not found"
[[ -f "${ENV_FILE}" ]] || die "missing ${ENV_FILE}"

env_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 || true)"
  printf '%s' "${line#*=}"
}

db_name="$(env_value POSTGRES_DB)"
db_user="$(env_value POSTGRES_USER)"
db_password="$(env_value POSTGRES_PASSWORD)"
[[ -n "${db_name}" && -n "${db_user}" && -n "${db_password}" ]] || die "database credentials are incomplete"

printf 'Restoring %s into database %s\n' "${backup}" "${db_name}"
printf 'Stop the API and worker before continuing. This replaces objects in that database.\n'

cd "${API_DIR}"
PGPASSWORD="${db_password}" docker compose exec -T -e PGPASSWORD postgres \
  pg_restore --clean --if-exists --no-owner --no-privileges -U "${db_user}" -d "${db_name}" - \
  < "${backup}"

printf 'Restore finished. Start the API only after you have checked the data.\n'

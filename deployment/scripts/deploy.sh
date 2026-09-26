#!/usr/bin/env bash
# Deploy K-COSMOS on the Ubuntu VPS. Stops on the first critical error.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
API_DIR="${REPO_ROOT}/services/main-api"
ENV_FILE="${API_DIR}/.env"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://sustainability.kct.ac.in}"

log() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

env_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 || true)"
  printf '%s' "${line#*=}"
}

log "1. Updating repository"
cd "${REPO_ROOT}"
git pull --ff-only

log "2. Validating environment"
[[ -f "${ENV_FILE}" ]] || die "missing ${ENV_FILE}; copy services/main-api/.env.example and fill it in"
require_cmd docker
require_cmd git
require_cmd curl

app_env="$(env_value APP_ENV)"
database_url="$(env_value DATABASE_URL)"
postgres_password="$(env_value POSTGRES_PASSWORD)"
secret_key="$(env_value SECRET_KEY)"
csrf_secret="$(env_value CSRF_SECRET)"
allowed_origins="$(env_value ALLOWED_ORIGINS)"
cookie_secure="$(env_value SESSION_COOKIE_SECURE)"
public_base="$(env_value PUBLIC_BASE_URL)"

[[ "${app_env}" == "production" ]] || die "APP_ENV must be production"
[[ -n "${database_url}" ]] || die "DATABASE_URL is empty"
[[ "${database_url}" != *'${'* ]] || die "DATABASE_URL still contains an unexpanded variable"
[[ "${database_url}" != *microcosm_dev_only* ]] || die "DATABASE_URL still uses the development password"
[[ -n "${postgres_password}" ]] || die "POSTGRES_PASSWORD is empty"
[[ "${#secret_key}" -ge 32 ]] || die "SECRET_KEY must be at least 32 characters"
[[ "${#csrf_secret}" -ge 32 ]] || die "CSRF_SECRET must be at least 32 characters"
[[ "${allowed_origins}" == "https://sustainability.kct.ac.in" ]] || die "ALLOWED_ORIGINS must be https://sustainability.kct.ac.in"
[[ "${cookie_secure}" == "true" ]] || die "SESSION_COOKIE_SECURE must be true"
[[ "${public_base}" == https://* ]] || die "PUBLIC_BASE_URL must use HTTPS"

for aeron_key in AERON_STATION_ID AERON_USERNAME AERON_PASSWORD; do
  [[ -n "$(env_value "${aeron_key}")" ]] || die "${aeron_key} is empty"
done

if ! id kcosmos >/dev/null 2>&1; then
  die "system user kcosmos does not exist; create it before deploying the frontends"
fi

log "3. Building containers"
cd "${API_DIR}"
docker compose build

log "4. Starting PostgreSQL"
docker compose up -d postgres

log "5. Waiting for PostgreSQL"
ready=0
for _ in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U "$(env_value POSTGRES_USER)" -d "$(env_value POSTGRES_DB)" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
[[ "${ready}" == "1" ]] || die "PostgreSQL did not become ready"

log "6. Running Alembic migrations"
docker compose run --rm --no-deps api alembic upgrade head

log "7. Restarting API"
docker compose up -d api

log "8. Restarting worker"
docker compose up -d environment-worker

log "9. Restarting frontend services"
if command -v systemctl >/dev/null 2>&1; then
  for unit in kcosmos-public-dashboard.service kcosmos-manager-admin.service; do
    rendered="$(mktemp)"
    sed "s|@REPO_ROOT@|${REPO_ROOT}|g" "${REPO_ROOT}/deployment/systemd/${unit}" > "${rendered}"
    sudo cp "${rendered}" "/etc/systemd/system/${unit}"
    rm -f "${rendered}"
  done
  sudo systemctl daemon-reload
  sudo systemctl enable kcosmos-public-dashboard.service kcosmos-manager-admin.service
  sudo systemctl restart kcosmos-public-dashboard.service kcosmos-manager-admin.service
else
  die "systemctl is not available"
fi

log "10. Validating local health"
curl -fsS "http://127.0.0.1:8000/health/live" >/dev/null
curl -fsS "http://127.0.0.1:8000/health/ready" >/dev/null

log "11. Validating public dashboard"
curl -fsS "http://127.0.0.1:3001/" >/dev/null

log "12. Validating admin portal"
curl -fsS "http://127.0.0.1:3002/admin-login.html" >/dev/null

if command -v nginx >/dev/null 2>&1; then
  sudo nginx -t
  sudo systemctl reload nginx
fi

log "13. Public health check"
if curl -fsS "${PUBLIC_BASE_URL}/health/live" >/dev/null; then
  "${SCRIPT_DIR}/health-check.sh"
else
  log "Public URL is not reachable yet. Finish Nginx and Cloudflare, then run deployment/scripts/health-check.sh"
fi

log "Deployment status: local API, worker, and frontend services were restarted."
docker compose ps

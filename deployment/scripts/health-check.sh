#!/usr/bin/env bash
# Check the public origin. Login with a real account is a manual step.
set -euo pipefail

BASE_URL="${PUBLIC_BASE_URL:-https://sustainability.kct.ac.in}"
BASE_URL="${BASE_URL%/}"

die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
ok() { printf 'OK   %s\n' "$*"; }

check() {
  local path="$1"
  curl -fsS "${BASE_URL}${path}" >/dev/null || die "${path}"
  ok "${path}"
}

check /health/live
check /health/ready
check /
check /admin/admin-login.html

session_code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/auth/session")"
[[ "${session_code}" == "401" ]] || die "/api/auth/session returned ${session_code}, expected 401"
ok "/api/auth/session -> 401"

printf 'Health check passed for %s\n' "${BASE_URL}"
printf 'Manual: sign in with a configured account and confirm logout, wrong portal, and password change.\n'

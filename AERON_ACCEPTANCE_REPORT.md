# Aeron integration — acceptance report

Date: 2026-09-25. Branch `feature-aeron-integration`, starting commit `2686a87` (uncommitted work below). Local stack: the main API container on `127.0.0.1:8000`, PostgreSQL `microcosm_clean_20260922`, and the staging UI on `127.0.0.1:3001`.

**Result: the pipeline is accepted on real data.**
- Accepted: real persisted readings, correct values, units and timestamps, server-side freshness, the history chart, the read-only API, and no secrets.
- **One item is not yet observed live:** a *fresh* LIVE reading and an advancing `latest` timestamp. The Aeron station itself has not reported since 2026-09-24 22:34 UTC (04:04 IST).

## Verification gate

| Gate | Result |
| --- | --- |
| Playwright / Chromium | Pass: Python 3.13.14 in the AQI project `.venv`, Playwright 1.63.0, Chromium 153 headless |
| Login | Pass: one headless login per session; the stored cookie was expired (401) |
| Real endpoint | Pass: `GET /api/stations/{id}/readings?mode=latest&region=india`, 200 `application/json` |
| Real non-empty response | Pass: 35 metrics plus health; sanitized fixture committed |
| Metrics and units | Pass: from Aeron's own `/parameters` metadata (35/35 match the map) |
| Timestamp semantics | Pass: true UTC; +330 **not required** (see the contract document) |

## Live acceptance (staging UI, real persisted data)

The browser ran headless Chromium with the viewer timezone deliberately set to America/New_York.

| # | Check | Result |
| --- | --- | --- |
| 1 | Latest values correct | **Pass.** 19/19 displayed values equal `/api/environment/latest` at UI precision (e.g. 27.1 °C, 69.4 %, PM2.5 4.7, AQI 107). |
| 2 | Units | **Pass.** Source units are unchanged; UI unit labels match (°C, %, mm, km/h, °, µg/m³, mg/m³, ppm, dB). |
| 3 | Timestamp | **Pass.** "Measured: Sep 25, 2026 · 04:04:00 AM IST (5h ago)" = `2026-09-24T22:34:00Z`. The New York viewer still sees IST. |
| 4 | LIVE with a fresh reading | **Not observable live**, because the station is silent. The server classifier is unit-tested at the 9:59 / 10:00 / 30:00 / 30:01 boundaries. The UI renders LIVE correctly when the server says LIVE (checked by overriding `freshness` in the browser). |
| 5 | STALE logic | **Pass** in tests and in UI rendering (override): "STALE — station may be offline". |
| 6 | OFFLINE logic | **Pass, live.** A 5 h 43 m old reading shows OFFLINE "— station offline", the dock dot is red, and `/status` reports `freshness: OFFLINE`. |
| 7 | History chart | **Pass.** It plots the persisted rows (currently 1 point, labelled 04:04 IST). |
| 8 | Refresh behaviour | **Pass.** 20 s latest / 60 s history polling is unchanged. "Refresh" issues 3 GETs and no POST. |
| 9 | No browser-triggered Playwright | **Pass.** The page made no request to any `aeronsystems` host and no POST. The API has no sync route (POST → 405/501). |
| 10 | No secrets in browser/network | **Pass.** Environment responses contain no cookie/token/auth strings. `raw_payload` and `quality_flags` are not served. |
| 11 | No old-backend dependency | **Pass.** There are no `:8000`/`:8001` host URLs in the UI. The old service was removed after parity. |

Sustainability safety: the `/api/public/dashboard`, `/timeline` and `/history` responses are **byte-identical** before and after the rebuild and migration (SHA-256 compared). The only schema change is the new `environment` schema.

## Worker evidence (real)

| Run | Time (UTC) | Outcome | Login | Note |
| --- | --- | --- | --- | --- |
| 1 | 03:57:49 | INSERTED | yes | first reading, `observed_at 22:34:00Z` |
| 2 | 03:58:52 | DUPLICATE | yes | new process, same reading, no duplicate row |
| 3 | 04:03:52 | DUPLICATE | **no** | session reused over HTTP |
| 4 | 04:08:52 | DUPLICATE | no | |
| 5 | 04:13:52 | DUPLICATE | no | 5-minute cadence |

A second concurrent worker was refused by the advisory lock (exit 2).

## Automated checks

| Check | Result |
| --- | --- |
| Backend pytest (`services/main-api`) | 78 passed, 117 skipped. The skips are the existing PostgreSQL-integration tests that need `TEST_DATABASE_URL`. The new environment suite is 62 tests. |
| PostgreSQL integration (`test_environment_postgres_integration.py`, real migrated DB) | 1 passed; test rows cleaned up |
| Ruff | All checks passed |
| Mypy (strict, `app`) | No issues in 75 files |
| Staging frontend tests (`node --test …/public-api-contract.test.js`) | 48/48 passed (4 new Weather contract tests) |
| `node --check` (both `weather.js`, test file) | Pass |
| `git diff --check` | Clean |
| Secret scan of all changed/new files against the actual configured secret values | 0 matches |

Covered by tests: normalizer (real fixture, both timestamp formats, no +330, missing/null/non-numeric/unknown metrics, malformed payloads), freshness boundaries and future readings, duplicate vs new timestamps, session expiry → single re-login, login backoff, missing credentials, timeout, malformed upstream (HTML, invalid JSON, `{}`, `[]`, `null`, 502), `latest`/`history`/`status` contract, read-only routes, and UI field-to-schema compatibility.

## Remaining blockers and follow-ups

1. **Station silent since 22:34 UTC.** A LIVE status and an advancing `latest` timestamp need the station to report again. With the worker running, the next new reading is stored automatically; confirm LIVE then.
2. **Docker:** the worker image, compose service, secrets and Nginx route are not yet created (exact list in the architecture document).
3. **Sensor quality (source-side):** barometric pressure is a constant 150 "mBa"; battery/supply/device temperature are 0 and location is 0/0/0. Raise these with Aeron and the station owner.
4. Optional: backfill from the verified history route (the source reports every minute; the worker keeps one reading per 5 minutes).
5. **Unrelated working-tree change found and left untouched:** `apps/manager-admin/admin-overview.html` had its sidebar logo `src` emptied at 09:40 IST by something other than this integration. It needs owner review.

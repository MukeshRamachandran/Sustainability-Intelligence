# K-COSMOS — work completed and current handoff

Prepared: 29 September 2026. Aeron sections updated: 3 November 2026.

Authoritative project: `C:\Projects\K-COSMOS-FINAL`

This document summarizes the conversation, the project-owner baseline, and the current Aeron integration. It distinguishes completed or reported work from requests whose completion is not evidenced. The terminal tool was unavailable when this summary was prepared, so current Git state, test counts, running services, and database contents were not rechecked today.

## 1. What you have been building

K-COSMOS is a sustainability platform with manager entry, administrator review, controlled publication, and a public dashboard. You have repeatedly required the existing architecture and visual design to be preserved while replacing prototype behavior with backend-controlled workflows.

The authoritative application is K-COSMOS-FINAL. The separate V2 project at `C:\Projects\Mukesh_sustainability\Microcosm-Dashboard` was identified as an old/reference prototype, not the authoritative application. Its audit did not authorize wholesale copying or merging.

## 2. Manager, admin, and security foundation

Your earlier tasks established the intended role-specific entry flow:

| Entry | Required access | Destination |
| --- | --- | --- |
| Admin login | `microcosm_admin` | Admin overview |
| Transport login | Manager with domain `transport` | Transport entry |
| Energy login | Manager with domain `energy` | Energy entry |
| LPG login | Manager with domain `lpg` | LPG entry |
| Water login | Manager with domain `water` | Water entry |
| Outreach login | Manager with domain `outreach` | Community outreach entry |

The authentication requirements were server-side sessions, credentialed requests, CSRF protection, exact role/domain verification, session guards on protected pages, and preservation of mandatory password changes. Prototype authentication and submission state in localStorage/sessionStorage were to be replaced with backend APIs.

In your explicit verified-baseline update, you reported these features already completed and regression-protected:

- Authentication, server-side sessions, CSRF, and exact manager-domain authorization.
- Current-month-only manager entry using Asia/Kolkata as the authoritative month.
- One active monthly submission per domain and submit-once behavior.
- Admin correction exceptions and revision resubmission.
- Temporary/committed evidence lifecycle and the Admin Evidence Repository.
- Five-domain approval readiness, prepare locking, immutable release candidates, and publish safety.

At that earlier baseline you reported **79 PostgreSQL tests passed**, **17 frontend contract tests passed**, **17 JavaScript files passed syntax checks**, Ruff passed, and Mypy passed for **47 source files**. The migration head then was `0005_evidence_committed_at`. These are historical results, not a claim about today's checkout.

## 3. Submission and evidence workflows

You requested shared backend workflows for Transport, Energy, LPG, and Water using the existing generic models: `Submission`, `SubmissionValue`, `ReviewAction`, `ReportingPeriod`, and `MetricDefinition`.

You later stated that the generic backend workflow was complete and provided the manager APIs. Each domain supports periods, metrics, listing/loading submissions, creating/updating drafts, and submitting for review. Admin APIs support the review queue, detail, begin review, correction requests, and approval.

The intended lifecycle is:

`draft → submitted → under_review → approved`

with `correction_requested` enabling editing and revision resubmission. Submitted, under-review, and approved values must not be silently editable. Submission, approval, and publication are separate states. Managers must not directly write calculated metrics; zero and blank have different meanings.

You also requested frontend API wiring, submission history, admin queues, evidence removal/re-upload fixes, save/submit/refresh regression checks, and security hardening. Your baseline confirms the core evidence/security features above. The full individual implementation and test results for every attachment are not present in this conversation record, so they should not all be represented as independently verified here.

## 4. Calculations, publication, and the public dashboard

Your later work covered emission-factor governance, authoritative calculations, LPG handling, institution aggregation, monthly publication contracts, public API wiring, and dashboard acceptance checks.

You supplied emission-factor values during those discussions and subsequently requested LPG kilogram governance. This summary does not establish which factor values or units are currently approved in the database; those must be read from the authoritative calculation configuration and contracts before future calculation changes.

You later supplied this project baseline:

- Branch at that point: `feature-waste-domain`.
- Accepted dashboard commit at that point: `265c63d`.
- Active clean development database: `microcosm_clean_20260922`.
- Alembic head at that point: `0009_waste_domain`.
- Published release: `sustainability-2026-09-v1`, September 2026, schema 1.2.
- Six September submissions were part of the later preservation checks you requested.

You requested historical-data auditing before importing any history, final calculation contracts, release-preservation checks, and resolution of a reported 109-versus-110-test difference. The results of all those individual tasks are not available here; neither the test-count discrepancy nor current release checksum can be certified from this summary.

At the switch to Aeron work, the recorded task update said **v2 remained active and no v3 candidate had been prepared or published**. That is the last recorded publication statement in this conversation, not a fresh database verification.

## 5. Aeron AQI integration — current state (3 November 2026)

The Aeron integration is built and runs on Aeron's **REST API v1 with a Bearer API key**. The earlier browser-login approach has been removed from the code, the images and the dependencies. The production guide is [docs/reports/AERON_INTEGRATION_ARCHITECTURE.md](docs/reports/AERON_INTEGRATION_ARCHITECTURE.md); the verified source contract is [docs/reports/AERON_REAL_API_CONTRACT.md](docs/reports/AERON_REAL_API_CONTRACT.md).

How it works:

1. The `environment-worker` container (`python -m app.environment.worker`, same image as the API) calls `GET https://live3.aeronsystems.com/api/v1/timeseries?station=b1ce41c2-586a-4a26-9382-9d8bfe757e78` every 5 minutes with `Authorization: Bearer $AERON_API_KEY`.
2. It normalizes the reading (UTC timestamp, no +330 correction, 35 parameters in source units) and inserts it into `environment.readings` only if the observation time is new. Each cycle is recorded in `environment.ingestion_runs`.
3. The API serves stored rows at `GET /api/environment/latest`, `/history`, `/status` and `/parameters`. These routes never contact Aeron.
4. The Weather page (`apps/public-dashboard/weather.js`) reads those routes on the same origin every 60 seconds (charts every 5 minutes) and keeps the last good reading if the API is unreachable.

Settled facts:

| Question | Answer |
| --- | --- |
| Authentication | Bearer API key in `services/main-api/.env` only |
| Rate limits | 60 requests/minute, 10,000/day; the 5-minute poll uses 288/day; the interval is clamped to 120–3600 s |
| Timestamp | `reading.timestamp` is true UTC; no +330 shift |
| Parameters | 35 codes; all match the K-COSMOS map |
| Single worker | PostgreSQL advisory lock; a second copy exits with code 2 |
| Missing key | Worker exits with code 3; the API keeps serving stored data |
| Schema | `0012_environment_readings` plus additive `0018_aeron_api_v1` |
| Device health | Not available in API v1 |

Verified on 2026-11-02 against the live API: `/stations`, `/parameters` and `/timeseries` all returned 200 JSON for station Air Quality KCT. A sanitized copy is in `services/main-api/tests/fixtures/aeron/aeron_v1_sample_sanitized.json`.

## 6. Production server

| Item | Value |
| --- | --- |
| URL | `https://sustainability.kct.ac.in` |
| Project root | `/opt/sustainability_intelligence_system` |
| Backend / Compose | `/opt/sustainability_intelligence_system/services/main-api` |
| Compose project | `sustainability-production` (`compose.production.yaml`) |
| Containers | `sustainability-production-api-1` (127.0.0.1:8000), `sustainability-production-environment-worker-1`, `sustainability-production-postgres-1` |

The live server still runs the older worker image until it is upgraded. The step-by-step upgrade (back up, pull, update `.env`, change the worker service to use `Dockerfile`, migrate to `0018`, restart, check) is section 4 of the architecture guide. Always pass `-p sustainability-production -f compose.production.yaml` so Compose works on the existing database.

## 7. Aeron files

| File | Purpose |
| --- | --- |
| `docs/reports/AERON_INTEGRATION_ARCHITECTURE.md` | Production guide: design, configuration, install, server upgrade, checks, troubleshooting |
| `docs/reports/AERON_REAL_API_CONTRACT.md` | Verified API v1 contract and parameter map |
| `services/main-api/app/environment/` | Worker, API client, normalizer, parameters, repository, freshness |
| `services/main-api/app/routers/environment.py` | Read-only public routes |
| `services/main-api/alembic/versions/0012_*.py`, `0018_*.py` | `environment` schema |
| `services/main-api/tests/test_environment_*.py` | Client, normalizer, worker, API and PostgreSQL tests |

## 8. Next work

1. Upgrade the live server to the API v1 worker and confirm `/api/environment/status` reports `LIVE` with no error code.
2. Confirm which directory serves the public dashboard on the server, so the updated `weather.js` is live.
3. Change the old Aeron account password; it remains in Git history from earlier commits.
4. Ask Aeron to confirm the AQI standard, the humidity unit "Per", the constant 150 "mBa" pressure and the `CO_ppm`/ppb naming.
5. Optional later work: hourly and daily aggregates, a diagnostics view for the mV and ppb channels, and Aeron history import once its v1 parameters are documented.

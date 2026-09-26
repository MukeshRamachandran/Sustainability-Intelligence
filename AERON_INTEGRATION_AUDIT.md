# AERON integration — Phase 1 read-only architecture audit

Date: 2026-09-25. Scope: `C:\Projects\AERON-PLAYWRIGHT` and `C:\Projects\K-COSMOS-FINAL`. This document is analysis only: no ingestion, deployment, UI, database, sustainability, or publication changes were made. No live Aeron call or credentialed browser run was performed.

## Executive finding and provenance

K-COSMOS is on branch `feature-aeron-integration` at `2686a87ed41498b2583431bb0697057b502363f1`. Before this audit its working tree had only pre-existing untracked `.claude/` and `FINAL_CALCULATION_ACCEPTANCE.md`. The supplied Playwright source is the nested `C:\Projects\AERON-PLAYWRIGHT\AQI-integration--main`, **without `.git` metadata**. Its branch, commit, Git history, and whether any source-file secret was ever tracked cannot be established from this copy. The directory name is not evidence of a branch.

Crucially, the supplied code is **not a proven page-reading Playwright scraper**. Playwright obtains an authenticated browser session/cookies; ingestion then requests Aeron's internal HTTP readings endpoint. A public API path is attempted first. The sample `api_response.json` is empty, tests use synthetic payloads, and no live source output is available. Neither approach is proven production-reliable by this snapshot. Implementing the desired replacement requires a verified, sanitized real payload and a controlled authentication/source test first.

## A–M. Supplied Playwright source

| Question | Finding |
| --- | --- |
| Entry point | `backend/main.py` creates FastAPI, mounts its own frontend, creates tables via `Base.metadata.create_all`, and launches a 60-second `auto_sync_task` at startup. `uvicorn backend.main:app` is the app entry. `test_login_flow.py` is a diagnostic browser script, not ingestion. |
| Browser / login | `backend/services/cookie_manager.py` launches headless Chromium, creates a context/page, navigates to configured `AERON_LOGIN_URL`, fills username, optionally clicks Continue, fills password, submits, waits for `**/dashboard**`, then reads context cookies. The diagnostic script navigates to `https://live3.aeronsystems.com/`; the operational login URL is configuration-dependent, not hardcoded in the manager. |
| Exact selectors | Username: `input[name="username"], input[type="email"], input#username`; Continue: `button[type="submit"], button[name="action"][value="default"]`; password: `input[name="password"], input[type="password"]`; final submit: `button[type="submit"], button[name="action"]`; dashboard URL glob `**/dashboard**`. These selectors are auth-only; no sensor-value DOM selectors exist. |
| Session reuse / expiry | Cookie header is cached in process behind a lock, with a 60-second refresh double-check. An optional configured static cookie is fallback. Internal HTTP 401/403 triggers one forced browser-cookie refresh and request retry. No persistent Playwright `storage_state` or session file was found. Browser is explicitly closed on success and selector timeout; general exception cleanup is not visibly guaranteed. |
| Page sequence | Login page → possible username Continue → password submit → dashboard wait → cookie extraction. There is no dashboard page-navigation/extraction sequence. |
| Direct API | `backend/services/aeron_client.py` first calls `{aeron_base_url}/devices/{station_id}/latest` with API key (10-second HTTP timeout); fallback calls `{aeron_internal_base_url}/stations/{station_id}/readings?mode=latest&region=india` with acquired cookie. Station, parameter, and historical API methods are unimplemented. This is a plausible API-based ingestion path, not a validated public contract. |
| Raw output | Expected JSON has `recordedAt`, sensor parameter entries containing Aeron parameter IDs and values, and health fields such as network/battery/charging/DeviceTemp. `raw_payload` retains entire JSON. No real populated sample was supplied (`api_response.json` is zero bytes); details such as exact sensor-array envelope must be confirmed from a sanitized live sample. |
| Timestamps | `recordedAt` is parsed as ISO 8601, replacing `Z` with `+00:00`; the old normalizer then adds a hardcoded 330 minutes. Its comment claims Aeron timestamp semantics need correction, but that assertion is not independently verified. A supplied normalizer test expects unchanged UTC and conflicts with that code. |
| Retry / errors | Sync has a lock, three attempts with exponential 2/4-second waits, public-then-internal fallback, and a sync log. Login selector waits are 10 seconds, dashboard wait 20 seconds, fallback wait 3 seconds. Some exception/error strings and login URL are logged; this is a potential secret/URL disclosure surface and should be sanitized before reuse. DB sync error messages may also contain upstream exception detail. |
| Files / screenshots | No automated screenshot production or saved browser session was found. A `login_dom.html` diagnostic file exists; its provenance is unknown and it should be reviewed before any future distribution. |
| Dependencies | `requirements.txt`: FastAPI 0.110.0, Uvicorn 0.28.0, SQLAlchemy 2.0.28, psycopg2-binary 2.9.9, Pydantic 2.6.4, pydantic-settings 2.2.1, python-dotenv 1.0.1, requests 2.31.0, httpx 0.27.0, Playwright 1.42.0. No `pyproject.toml`/package manifest was found in supplied source. Chromium installation/runtime provision is not demonstrated by requirements alone. |
| Credentials | `backend/config.py` loads environment / optional `.env` via Pydantic settings. Names referenced include `AERON_USERNAME`, `AERON_PASSWORD`, `AERON_LOGIN_URL`, API key, station ID, public/internal base URLs, optional session cookie, and database URL. No credential value is reproduced here. No `.env` file was found in the supplied snapshot. A guide contains a cookie-assignment example classified by a pattern scan as a placeholder, not evidence of a live secret. **Secrets tracked in Git: UNKNOWN**, because this snapshot has no Git metadata; do not assert “NO” or infer history from file presence. K-COSMOS only tracks an Aeron `.env.example` among environment-like files inspected. |
| Tests / confidence | `backend/tests/test_aeron_normalizer.py` uses a synthetic payload and conflicts with the +330 implementation. `backend/tests/test_aeron_sync.py` uses SQLite despite PostgreSQL-specific insert behavior; a duplicate test is incomplete. `test_login_flow.py` is a diagnostic that would contact the external site. No reliable end-to-end, live authenticated ingestion test was found. None was run in this audit. |

`backend/services/sync_service.py` and `data_processor.py` in the snapshot appear to be stale/placeholder paths, not the `aeron_sync_service.py` registered by the app. Their imports/usage require final confirmation before eventual deletion.

### Canonical field inventory from the supplied mapping

These are **configured parameter mappings**, not proof that a real station emitted every field. Raw unit is the source mapping's literal unit; normalized units below express the existing K-COSMOS field convention. No physical conversion is performed by the normalizer. “Not shown” means retained in data/API but not surfaced by the current weather UI. Both the supplied snapshot and current `services/aeron-api` carry this same mapping.

| Aeron raw parameter ID | Raw unit | Normalized field | Normalized/UI unit | Existing UI element |
| --- | --- | --- | --- | --- |
| `63d0da020016a` | mg/m3 | `co_mg_m3` | mg/m³ | CO pollutant |
| `63d0da885f1a0` | ug/m3 | `no2_ug_m3` | µg/m³ | NO₂ pollutant |
| `63d0daa4740ba` | ug/m3 | `so2_ug_m3` | µg/m³ | SO₂ pollutant |
| `63d0daf2bcb74` | ug/m3 | `o3_ug_m3` | µg/m³ | O₃ pollutant |
| `63d0db066e993` | ug/m3 | `no_ug_m3` | µg/m³ | NO pollutant |
| `63d0db8f77ecb` | ug/m3 | `pm25_ug_m3` | µg/m³ | PM2.5 tile/chart |
| `63d0dbb867a7c` | ug/m3 | `pm10_ug_m3` | µg/m³ | PM10 tile/chart |
| `63d0dbfe0a111` | degC | `temperature_c` | °C | temperature tile/chart |
| `63d0dc28f109d` | Per | `relative_humidity_percent` | % (assumed) | humidity tile/chart |
| `63d0dc5164112` | mm | `rain_mm` | mm | rain tile/chart, daily total |
| `63d0dd3721886` | kmph | `wind_speed_kmph` | km/h | wind tile/chart, peak |
| `63d0dd4ff30c9` | Deg | `wind_direction_deg` | ° | wind direction/compass |
| `63d0ddf115956` | db | `noise_average_db` | dB | noise average |
| `63d0de104027f` | db | `noise_min_db` | dB | noise minimum |
| `63d0de34a0b72` | db | `noise_max_db` | dB | noise maximum |
| `63d0de7568a3b` | index | `uv_index` | index | UV tile |
| `63d0ea1253e8f` | ppm | `co2_ppm` | ppm | CO₂ tile/pollutant |
| `63d0ea927306d` | mv | `co_we_mv` | mV | not shown |
| `63d0eb32b7070` | mV | `co_aux_mv` | mV | not shown |
| `63d0eb591ee3a` | mV | `no2_we_mv` | mV | not shown |
| `63d0eb7f49e34` | mV | `no2_aux_mv` | mV | not shown |
| `63d0eba20cd96` | mV | `so2_we_mv` | mV | not shown |
| `63d0ebc89f18d` | mV | `so2_aux_mv` | mV | not shown |
| `63d0ebfa17c49` | mV | `o3_we_mv` | mV | not shown |
| `63d0ec7aa5a61` | mV | `o3_aux_mv` | mV | not shown |
| `63d0ec9873bc3` | mV | `no_we_mv` | mV | not shown |
| `63d0ecc9829f2` | mV | `no_aux_mv` | mV | not shown |
| `63d0ee3fcd99a` | mBa | `barometric_pressure_mba` | mBa | pressure tile |
| `63d0eeb2aaeef` | ltr | `molecular_volume_ltr` | L | not shown |
| `641d7b36d4413` | ppb | `co_ppb` | ppb | not shown (source caption says `CO_ppm`, conflicting with unit) |
| `6421673518c4f` | ppb | `no2_ppb` | ppb | not shown |
| `64216914170b7` | ppb | `so2_ppb` | ppb | not shown |
| `64216a7500e46` | ppb | `o3_ppb` | ppb | not shown |
| `64216b8187e5e` | ppb | `no_ppb` | ppb | not shown |
| `6422ae0f8147e` | Unit | `air_quality_index` | dimensionless index | AQI tile/chart |

Additional payload fields: `recordedAt` → source/observed timestamp → freshness and chart x-axis; `network` → network badge/status; `battery`, `charging`, `DeviceTemp` → device-health rows in the production weather UI (the staging variant is narrower). Their exact raw type/unit and casing should be confirmed against a sanitized real payload. Source `rain_mm` accumulation semantics and humidity `Per` semantics must be verified before treating the UI's daily-rain sum and percent display as authoritative. The source caption `Baromteric Pressure` is misspelled; this does not change its field key.

## N–P. Existing public Aeron UI and its contract

There are **two** public dashboard copies: `apps/public-dashboard/index.html` + `weather.js` (production-oriented) and `apps/public-dashboard-final-staging/index.html` + `weather.js` (local final staging, port 3001). The Weather section is in each `index.html`; JS builds/fills the cards/charts without a separate framework component. Existing styling/layout should remain unchanged.

Production JS requests same-origin `GET /api/environment/latest` and `GET /api/environment/history?limit=500`; it does not expose a sync action. It polls latest about every 20 seconds and history about every 60 seconds while Weather is active. It expects the flat `AeronMeasurementResponse` fields above, ISO timestamps, nullable metrics, and uses `--` for missing values. It shows temperature/humidity/PM2.5/PM10, wind/rain/UV/pressure, gases, CO₂, noise, network/battery/charging/device temperature and charts. It contains no synthetic reading fallback.

Final-staging JS instead builds `http://{candidate host}:8000/api/environment` and calls `/latest`, `/history?limit=500`, and `POST /api/sync/aeron` from a public “Sync Now” control. Candidate hosts include the page hostname and loopback alternatives. This targets **main-api port 8000**, but main-api does not register those environment routes. The current `services/aeron-api` listens on **8001** and its protected sync route is `POST /api/environment/sync`, not `/api/sync/aeron`. Thus the 3001 Weather integration is contract-incompatible even if both services start. Any future public sync control should be removed/disabled via a separate approved UI change; scheduled ingestion must never be triggered per visitor. Production same-origin routing is documented as a reverse-proxy expectation, but no Nginx configuration implementing it was found in this checkout.

Both JS variants format timestamps in the **viewer browser's local timezone**, not explicitly Asia/Kolkata. The latest-reading time is a sensor observation time, not proof of fetch/ingest time; some labels imply otherwise. The frontend freshness threshold treats exactly 10 minutes as LIVE (`> 10` becomes STALE), unlike desired `< 10`; the backend status classifier has the desired boundary. Future timestamps can be marked LIVE because negative age is not rejected (backend clamps it to zero). The UI's historical charts use up to 500 returned rows and normally a rolling 24-hour slice, falling back to all returned history when there are no points within 24 hours; that fallback can show old data on apparently current charts. Request failures show offline/error/no-data UI rather than fabricated readings. Staging sums `rain_mm` readings for “today”; whether this is valid depends on Aeron's raw rainfall semantics.

## Q–U. Current K-COSMOS backend and deployment

`services/aeron-api` is a standalone FastAPI service, not the same app as `services/main-api`. Its registered routes are `GET /api/environment/latest`, `GET /api/environment/history` (optional `station_id`, `start`, `end`, `limit` ≤1000), `GET /api/environment/status`, `POST /api/environment/sync` (requires `X-Internal-Sync-Token`), plus `/health/live` and `/health/ready`. The service's optional sync loop starts in the API process and runs at least every 60 seconds; public reads themselves do not launch a browser or sync. Direct upstream API key call is followed by a static-cookie fallback; **there is no Playwright code/dependency in this service**. The backend is therefore redundant only in its *upstream acquisition/authentication method* relative to the proposed worker, not in its useful schema, normalization, read contract, or freshness logic.

Its PostgreSQL `environmental` schema contains Aeron stations, parameter metadata, measurements and sync logs. Measurements include `station_id`, `source_recorded_at`, corrected `recorded_at`, nullable normalized sensor/health columns, `raw_payload`, `created_at` and uniqueness on station plus `recorded_at`. `created_at` can inform an `ingested_at` migration but is not yet an explicit ingest timestamp. The normalizer parses `recordedAt` as UTC and adds configurable `AERON_TIMESTAMP_CORRECTION_MINUTES` (default 330). Preserve the ID map, nullable field handling, schema intent, route response shape, sync audit/idempotence concept, and token-protected manual sync until a replacement is proven. Do **not** carry the unverified manual offset forward as canonical.

`services/main-api` contains no registered `/api/environment/*` route, Aeron proxy, environmental model/migration, calibration function, or sensor map in its app/migrations. Main API does not own the existing environmental tables. Current production `weather.js` is designed to talk through a same-origin proxy to `aeron-api`, not directly to main-api. Current staging JS directly targets port 8000, so it effectively talks to neither valid environmental API in the checked-in deployment.

The only compose file found is `services/main-api/compose.yaml`: PostgreSQL and main API (loopback host port 8000), **no Aeron service, worker, or Aeron volume**. `services/aeron-api/Dockerfile` exposes/listens on 8001, installs Python requirements but not Playwright/Chromium. No Nginx config was found under deployment; the README describes intended same-origin proxy behavior, not a checked-in implementation. Environment names in `services/aeron-api/backend/config.py` cover API key, station, public/fallback URLs, static cookie, sync enable/interval, retry/timeout, timestamp correction, internal sync token, CORS and database URL. Its `.env.example` is tracked; secret values are not reproduced. Existing contract/normalizer/sync tests under `services/aeron-api/backend/tests` depend on the service and public JS path. Legacy `backend/routes/weather.py`, `air_quality.py`, `device.py`, old `services/sync_service.py` and `data_processor.py`, and the service-local frontend are not registered by current `backend/main.py`; they are **candidates for later removal**, not safely deletable in this phase without full import/reference review.

## V–AD. Smallest production-safe target design (proposal, not implementation)

1. **Ownership:** use one environmental PostgreSQL schema with a single migration owner. For the requested end state, make `services/main-api` the public read-API owner and migrate/adapt the existing `environmental` models/read-route contracts there. Keep `services/aeron-api` operational until parity, backfill strategy (if needed), and deployment routing are proven; retire it only in a later controlled rollout. This is more work than retaining it, but avoids an otherwise redundant permanent API service and gives K-COSMOS one public backend. A lower-change interim path is retaining/refactoring `aeron-api` behind the same-origin proxy while replacing only its collector; that is valid if the owner accepts a permanent separate environment API. Do not have both services independently own migrations or schedule ingestion.
2. **Ingestion:** a separate, single-instance Playwright-enabled worker image/process launched by a scheduler/one-shot job, not by a public API request or every API replica. Prefer verified direct API access if officially supported and robust; use Playwright only for session acquisition where necessary, followed by the observed internal readings request. The supplied code has no DOM sensor scraper to transplant. Use a scheduler lock/lease or DB advisory lock, bounded timeout/retry, safe cookie refresh, guaranteed browser/context close, dedupe on station + canonical `observed_at`, sanitized logs, and health/last-success monitoring.
3. **Storage:** propose `station_id`, raw source timestamp/text and provenance, timezone-aware UTC `observed_at`, UTC `ingested_at`, nullable normalized sensor fields listed above, health fields, optional raw payload with retention/redaction policy, source/normalization version and quality flags. Map legacy `source_recorded_at` and `recorded_at` only after timestamp semantics are verified; do not mass-shift existing data by 330 minutes without evidence. A nullable field means unavailable, not zero. Keep raw IDs in parameter metadata and exact unit annotations.
4. **API:** preserve `GET /api/environment/latest`, `GET /api/environment/history` and `GET /api/environment/status` response compatibility for current production UI. Include station selection and timestamp/quality metadata as additive fields only. History should be bounded and ordered, status should distinguish sensor observation freshness from worker/ingestion health. Manual sync, if retained, must be internal/authenticated and not callable by the public UI. Main-api can expose these reads directly in the final state; an interim reverse proxy may route the same paths to `aeron-api`.
5. **Freshness and time:** establish Aeron's actual timestamp timezone from a real record and independent device/portal clock comparison. Parse zone-qualified input into aware UTC; for naive input, use one documented source timezone and attach it once. `observed_at` is sensor time; `ingested_at` is successful durable storage time. Never silently apply a global +330 to a timestamp already UTC-qualified. Compute freshness centrally: LIVE for `0 <= age < 10 min`, STALE for `10 <= age <= 30 min`, OFFLINE for `age > 30 min`, missing/invalid, or materially future-dated readings. Define a small permissible clock-skew tolerance if needed. Display in Asia/Kolkata intentionally, with timezone label, and use `ingested_at` only for fetch/ingest labels.
6. **Deployment eventually:** add worker dependencies (Playwright package **and browser binaries/system libraries**) to a dedicated image; configure env/secret injection rather than committed `.env`; add scheduler/one-instance and PostgreSQL connectivity; ensure `environmental` migrations run once; wire same-origin `/api/environment/*` to final API; remove staging's port-8000 mismatch/public sync action via a separately approved minimal compatibility change; expose readiness based on DB/config/last ingest; keep existing main-api publication setup untouched. Do not remove old service/image until parity and rollback are tested.

Potential eventual removal: old direct-API/static-cookie acquisition and API-lifespan sync loop once the worker replaces them; old service only after main-api API parity; unregistered legacy modules and duplicate service frontend only after confirmed unused. Retain/adapt: parameter map, normalizer field mapping (not unverified time shift), `environmental` schema concepts, `/api/environment` read contract, freshness tests, sync logs and protected internal operations, and the existing Weather UI design.

## AE–AG. Risks, readiness and exact blockers

**Ready to implement the replacement: NO.** Ready to plan a limited validation spike: YES, after the owner approves safe credentialed source access.

1. No Git metadata for the supplied source: branch/commit/history/secret-tracking status unknown. Obtain a proper Git checkout or source revision manifest and perform a secret-history scan without exposing values.
2. No sanitized real Aeron response; `api_response.json` is empty. Verify actual envelope, field IDs, units, zero/null behavior, station ID, recordedAt type/timezone, and health fields.
3. The only Playwright code authenticates; it does not scrape readings from DOM. Test whether direct API or cookie-backed internal endpoint remains usable and authorized; do not label either “working ingestion” without an end-to-end result.
4. The +330-minute interpretation is contradictory across implementation and tests. Independently establish source clock semantics and evaluate existing stored timestamps before any migration.
5. Select final API owner (main-api migration versus permanent retained `aeron-api`) and identify who owns environmental migrations. Current main-api has none.
6. Resolve production same-origin proxy and staging port/API mismatch; prevent public-triggered ingestion. These need a later approved deployment/UI change.
7. Agree on credential storage/rotation, access rights, raw-payload retention, sanitized error logging, single-worker scheduling, and browser cleanup. Never commit real credentials or session artifacts.
8. Confirm rainfall semantics, humidity unit, pressure unit/caption, CO ppb caption, sensor calibration/quality, future timestamps, and chart-history behavior before declaring the display scientifically trustworthy.
9. Add PostgreSQL integration, authenticated upstream contract (with sanitized fixture), idempotence, expiry/re-login, failure, clock-skew, and frontend compatibility tests before cutover. No tests were run as part of this read-only audit.

No published sustainability release, historical data, database, Docker configuration, frontend, or backend application file was modified in this phase.

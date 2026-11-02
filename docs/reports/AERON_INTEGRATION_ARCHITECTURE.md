# Aeron integration architecture

Environmental readings from the Aeron station reach the Weather page through the K-COSMOS main API. A separate worker does the ingestion, and no visitor request ever contacts Aeron. The worker uses Aeron's REST API v1 with a Bearer API key. The earlier Playwright login and session cookie have been removed. The source contract is in [AERON_REAL_API_CONTRACT.md](AERON_REAL_API_CONTRACT.md).

```
Aeron Live3 REST API v1  (https://live3.aeronsystems.com/api/v1)
   ▲  GET /timeseries?station={id}   Authorization: Bearer $AERON_API_KEY   (every 60 s)
   │  GET /parameters?station={id}   once at worker start (metadata drift check, logged by ID only)
Aeron worker  (python -m app.environment.worker, one instance via PostgreSQL advisory lock)
   │  normalize → validate → INSERT … ON CONFLICT (station_id, observed_at) DO NOTHING
PostgreSQL  environment.readings / environment.ingestion_runs
   │
Main API  GET /api/environment/latest | /history | /status | /parameters   (read-only, no Aeron calls)
   │  same-origin: Nginx (production) / deployment/scripts/dev-server.py (local)
Weather UI  (apps/public-dashboard/weather.js)
```

## Components

| Piece | Location | Responsibility |
| --- | --- | --- |
| Parameter map | `services/main-api/app/environment/parameters.py` | `PARAMETER_MAP` (owner-supplied name, unit and category for 35 IDs), `READING_COLUMNS` (ID → existing column) and `VERIFICATION_NOTES` |
| Normalizer | `…/environment/normalizer.py` (v2) | Parses `reading.timestamp` into an aware UTC datetime (no +330, timestamps without a zone rejected). Checks `epoch_ms` against it and flags a mismatch. Missing or non-numeric values become `NULL` with a quality flag, never 0. Unknown IDs go to `unmapped_values`. A response for another station is rejected. |
| API client | `…/environment/source.py` | `AeronApiClient`: one pooled `httpx.Client` with Bearer auth, separate connect and read timeouts, redirects refused, and fixed error codes. Retries only timeouts, network errors and 5xx, up to `AERON_MAX_ATTEMPTS` times, with exponential backoff and full jitter capped at 8 s. Never retries 401, 403, 404 or 429. |
| Scheduler | `…/environment/worker.py` `PollScheduler` | Normal interval after success or a transient failure. `Retry-After` (or `X-Ratelimit-Reset`) after a 429, capped at 1 h. 5 min doubling to 1 h after AUTH_FAILED, FORBIDDEN, NOT_FOUND or STATION_MISMATCH, reset by the next success. |
| Worker | `…/environment/worker.py` | Single-threaded loop, so cycles never overlap. `--once` mode. The advisory lock is released explicitly on exit, and a second worker exits with code 2. SIGTERM-safe. Exits with code 3 if `AERON_API_KEY` is missing. |
| Worker config | `…/environment/config.py` | `AeronWorkerSettings`, read from `services/main-api/.env`. The key is held as `SecretStr`. HTTPS is enforced. |
| Repository | `…/environment/repository.py` | Idempotent insert. A repeated observation keeps the first stored row unchanged. Latest, bounded history, and run records. |
| API | `…/routers/environment.py`, `…/schemas/environment.py` | Public read-only routes |
| Schema | `alembic/versions/0012_environment_readings.py`, `0018_aeron_api_v1.py` | `environment` schema. 0018 only adds nullable columns. |

## Worker cycle

1. `GET /timeseries?station=…` with the Bearer key. Rate-limit headers are read and logged as counts only.
2. Normalize and validate. Insert only if `(station_id, observed_at)` is new; otherwise the outcome is `DUPLICATE`. A restarted worker relies on the database alone, so it never inserts the same observation twice.
3. Record one `ingestion_runs` row: outcome `INSERTED`, `DUPLICATE` or `FAILED`, with a fixed `error_code`. `login_performed` is always false; it is only meaningful on rows from the retired worker.
4. Wait as `PollScheduler` decides.

Error codes: `AUTH_FAILED` (401), `FORBIDDEN` (403), `NOT_FOUND` (404), `RATE_LIMITED` (429), `HTTP_ERROR` (other non-200 responses, including redirects), `TIMEOUT`, `NETWORK_ERROR`, `MALFORMED_RESPONSE`, `INVALID_READING`, `STATION_MISMATCH`, `DATABASE_ERROR`, `UNEXPECTED_ERROR`. Logs and run rows contain codes, timestamps and counts only. They never contain the key, request headers or upstream bodies.

## Storage: `environment.readings`

| Column | Meaning |
| --- | --- |
| `observed_at` | Sensor observation instant (UTC), from `reading.timestamp` |
| `fetched_at` | When the worker received the response (UTC). Added in 0018; NULL on older rows. |
| `ingested_at` | When K-COSMOS stored the row (UTC) |
| `source_recorded_at_raw` | `reading.timestamp`, verbatim |
| `source_epoch_ms` | `reading.epoch_ms`, verbatim (0018) |
| `source_route` | `GET /api/v1/timeseries?station={station_id}` (older rows: the retired cookie route) |
| `normalizer_version` | `2` (older rows: `1`) |
| `quality_flags` | `missing:<field>`, `non_numeric:<field>`, `unknown_parameter:<id>`, `epoch_ms_mismatch` |
| `raw_payload` | `station`, `resolution`, `reading` exactly as received. Contains no credentials. Not served by the API. |
| `unmapped_values` | Unknown parameter IDs and their raw values (0018). Not served by the API. |
| 35 metric columns | One per parameter. Values are in source units, with no conversion. |
| `network`, `battery`, `charging`, `device_temp` | Filled only by the retired worker. API v1 has no device-health block, so new rows leave these NULL. |

### Parameter → column mapping

| Category | Parameters → columns |
| --- | --- |
| air_quality | CO→`co_mg_m3`, NO2→`no2_ug_m3`, SO2→`so2_ug_m3`, O3→`o3_ug_m3`, NO→`no_ug_m3`, PM2.5→`pm25_ug_m3`, PM10→`pm10_ug_m3`, CO2→`co2_ppm`, AQI→`air_quality_index` |
| weather | Ambient Temperature→`temperature_c`, Relative Humidity→`relative_humidity_percent`, Rainfall→`rain_mm`, Wind Speed→`wind_speed_kmph`, Wind Direction→`wind_direction_deg`, UV Index→`uv_index`, Barometric Pressure→`barometric_pressure_mba`, Molecular Volume→`molecular_volume_ltr` |
| noise | Noise Average/Minimum/Maximum→`noise_average_db`/`noise_min_db`/`noise_max_db` |
| diagnostics | CO/NO2/SO2/O3/NO `_WE` and `_AUX` → `co_we_mv` … `no_aux_mv` |
| pollutant_ppb | CO_ppm→`co_ppb`, NO2_ppb→`no2_ppb`, SO2_ppb→`so2_ppb`, O3_ppb→`o3_ppb`, NO_ppb→`no_ppb` |

The existing column names are kept on purpose: old history and the Weather UI contract stay valid. Example: `relative_humidity_percent` still holds the source value in "Per".

## API (main API, port 8000 internally)

| Route | Behaviour |
| --- | --- |
| `GET /api/environment/latest?station_id=` | Newest persisted reading plus server-side `freshness`; 404 if none. Now also includes `fetched_at`. |
| `GET /api/environment/history?station_id=&start=&end=&limit=` | Newest first; `limit` 1–1000 (default 100); inverted range → 422 |
| `GET /api/environment/status` | `freshness`, `age_seconds`, `observed_at`, `ingested_at`, thresholds, last sync outcome and error code, `last_successful_sync`, DB connectivity |
| `GET /api/environment/parameters` | Static map: ID, field, name, unit, category, verification note. No Aeron call. |

All reading routes send `Cache-Control: no-store`. There is no POST or sync route.

## Weather UI changes

- The status footer adds "· Last sync HH:MM:SS IST" from `/status`.
- If the API can't be reached, the last values stay on screen with "server unreachable, showing last stored reading", and the status changes to OFFLINE. No value is fabricated.
- AQI shows the number with "Index standard unconfirmed" and a neutral colour. The US-EPA categories have been removed until Aeron confirms the standard.
- Humidity shows the source unit "Per" with a note, instead of "%".
- The network badge hides itself when `network` is NULL, which is always the case for v1 rows.

## Retired

- The Playwright login (`PlaywrightLogin`), the in-memory session cookie (`AeronSession`) and the cookie-authenticated route `GET /api/stations/{id}/readings?mode=latest&region=india`.
- `Dockerfile.worker` (Chromium image). The worker now runs from the API image.
- The `aeron-worker` (Playwright) extra and its lock entries (`playwright`, `pyee`).
- Environment variables: `AERON_INTERNAL_BASE_URL`, `AERON_DASHBOARD_URL`, `AERON_REGION`, `AERON_USERNAME`, `AERON_PASSWORD`, `AERON_SESSION_COOKIE`, `AERON_HTTP_TIMEOUT_SECONDS`, `AERON_LOGIN_TIMEOUT_SECONDS`.
- There is no browser fallback of any kind.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `AERON_STATION_ID` | required | `b1ce41c2-586a-4a26-9382-9d8bfe757e78` |
| `AERON_API_KEY` | required | Secret. Belongs only in `services/main-api/.env`. |
| `AERON_API_BASE_URL` | `https://live3.aeronsystems.com/api/v1` | HTTPS only |
| `AERON_POLL_INTERVAL_SECONDS` | `60` | 30–3600 |
| `AERON_CONNECT_TIMEOUT_SECONDS` / `AERON_READ_TIMEOUT_SECONDS` | `5` / `15` | |
| `AERON_MAX_ATTEMPTS` | `3` | 1–5. Applies to transient failures only. |

## Remaining limitations

1. **Aeron history is not used.** The v1 history parameters for `/timeseries` have not been verified, so they are not implemented. K-COSMOS builds its own history from the readings it stores, one per observation. Older rows are kept.
2. **`latest` lags.** Aeron reports a 60 s interval (`reportingIntervalMs`), but on 2026-11-02 the `latest` timestamp was 4–5 minutes old when fetched, so most 60 s polls return `DUPLICATE`. This is expected and costs about 1,440 of the 10,000 daily requests.
3. **Unconfirmed source metadata** (values are stored as received): pressure is a constant 150 "mBa"; the CO_ppm name carries a ppb unit; the AQI standard is unknown; humidity's unit is "Per". These are listed in `VERIFICATION_NOTES` and served by `/api/environment/parameters`.
4. **No device health.** Network, battery, charging and device temperature are no longer available.
5. **Hourly and daily aggregation** endpoints and new Diagnostics or Historical Analytics UI sections are not built yet. Diagnostic and ppb values are stored and served in `/latest` and `/history`.

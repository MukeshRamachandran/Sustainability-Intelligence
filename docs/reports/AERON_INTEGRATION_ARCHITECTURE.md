# Aeron integration architecture

Environmental readings from the Aeron station reach the existing Weather UI through the K-COSMOS main API. Ingestion is a separate worker, and no visitor request ever contacts Aeron or starts a browser. The source contract is in [AERON_REAL_API_CONTRACT.md](AERON_REAL_API_CONTRACT.md).

```
Aeron (live3.aeronsystems.com)
   ▲  Playwright login only when the session is missing/expired (~hourly at most)
   │  HTTP GET …/stations/{id}/readings?mode=latest&region=india   (every 5 min)
Aeron worker  (python -m app.environment.worker, single instance)
   │  normalize → validate → INSERT … ON CONFLICT (station_id, observed_at) DO NOTHING
PostgreSQL  environment.readings / environment.ingestion_runs
   │
Main API  GET /api/environment/latest | /history | /status   (read-only)
   │  same-origin: Nginx (production) / serve-staging.py :3001 (local staging)
Existing Weather UI  (apps/public-dashboard*/weather.js — layout unchanged)
```

## Components

| Piece | Location | Responsibility |
| --- | --- | --- |
| Parameter map | `services/main-api/app/environment/parameters.py` | 35 source-verified IDs → fields, captions, source units |
| Normalizer | `…/environment/normalizer.py` | Parses `recordedAt` to an aware UTC datetime (no +330); numeric-only metrics; missing or non-numeric values become `NULL` plus a quality flag; unknown IDs are flagged and kept in `raw_payload`; rejects payloads with no timestamp or no metrics |
| Freshness | `…/environment/freshness.py` | Single classifier on server time: LIVE `< 10 min`, STALE `10–30 min`, OFFLINE `> 30 min`, missing, or more than 2 min in the future |
| Source client | `…/environment/source.py` | `AeronReadingsClient` (stdlib HTTPS, fixed error codes), `PlaywrightLogin` (browser always closed), `AeronSession` (in-memory cookie, login backoff) |
| Repository | `…/environment/repository.py` | Idempotent insert, latest, bounded history, run records |
| Worker | `…/environment/worker.py` | 5-minute loop, `--once`, PostgreSQL advisory lock, SIGTERM-safe |
| Worker config | `…/environment/config.py` | `AeronWorkerSettings`: environment only, secrets as `SecretStr`, HTTPS enforced |
| API | `…/routers/environment.py`, `…/schemas/environment.py` | Public read-only routes |
| Schema | `alembic/versions/0012_environment_readings.py` | `environment` schema; no FKs into other schemas |

## Worker cycle

1. Reuse the in-memory session cookie. If there is none, run the Playwright login (dashboard URL → Auth0 form → dashboard), take the cookies for the API origin, and close the browser.
2. `GET …/readings?mode=latest&region=india`. On 401/403, log in once and retry once. A second rejection fails the cycle rather than looping.
3. Normalize and validate. Insert only if `(station_id, observed_at)` is new.
4. Record one `ingestion_runs` row: outcome `INSERTED` / `DUPLICATE` / `FAILED`, fixed `error_code`, `login_performed`.
5. Sleep for the rest of the 5-minute interval.

A failed login pauses further logins for 5 minutes, doubling up to 1 hour, so a bad password cannot lock the account. Logs and run rows contain codes and timestamps only.

## Storage — `environment.readings`

`id`, `station_id`, `observed_at` (Aeron measurement, UTC), `ingested_at` (K-COSMOS storage, UTC), `source_recorded_at_raw` (verbatim source string), `source` (`aeron-live3`), `source_route`, `normalizer_version`, `quality_flags` (JSONB), `raw_payload` (JSONB: `recordedAt`/`health`/`location`/`data` only), the 35 verified metrics (double precision; the legacy `Numeric(10,4)` truncated values such as `0.000789`), and `network` / `battery` / `charging` / `device_temp`.

The table is append-only with unique `(station_id, observed_at)`. `environment.ingestion_runs` holds per-cycle health.

## API (main API, port 8000 internally)

| Route | Behaviour |
| --- | --- |
| `GET /api/environment/latest?station_id=` | Newest persisted reading plus server-side `freshness`; 404 if none. Response is a superset of the legacy flat shape; `recorded_at` and `source_recorded_at` equal `observed_at`. |
| `GET /api/environment/history?station_id=&start=&end=&limit=` | Newest first; `limit` 1–1000 (default 100); inverted range → 422 |
| `GET /api/environment/status` | `freshness`, `age_seconds`, `observed_at`, `ingested_at`, thresholds, last sync outcome and error code, last successful sync, DB connectivity |

All three send `Cache-Control: no-store`. There is no POST or sync route.

## UI compatibility changes

The layout, cards, charts, labels and styling are unchanged.

- **Staging `weather.js`:** now uses same-origin `/api/environment` (the hard-coded `http://{host}:8000/api` and the public `POST /api/sync/aeron` are removed). "Sync Now" became "Refresh" and only re-reads. Status comes from server `freshness`. The station time shows in IST regardless of the viewer's timezone, and the footer reads "Measured:" instead of "Data fetched:".
- **Production `weather.js`:** status comes from server `freshness`, with the 10-minute boundary corrected in the fallback.
- **`serve-staging.py`:** allowlists the three GET routes only.

## Retired

`services/aeron-api` has been removed from Git, after parity was verified and no runtime references remained. It was the separate `:8001` service, with the +330 bug, no Playwright, and an unauthenticated public sync in staging. Its ignored local files (`.venv`, caches, `aeron_dashboard.db`) were moved to `C:\K-COSMOS-PRIVATE\retired\services-aeron-api-local-20260925`. The supplied `C:\Projects\AERON-PLAYWRIGHT` source is untouched.

## Docker changes still required (not yet made)

1. **Main API:** no code or config change beyond rebuilding the image. Run `alembic upgrade head` once per environment (it adds `0012`).
2. **Worker service:** a new image built from `services/main-api`. Base it on `python:3.12.11-slim-bookworm` with `pip install ".[aeron-worker]"` then `python -m playwright install --with-deps chromium`, or use `mcr.microsoft.com/playwright/python:v1.63.0-*`. Run it as a non-root user with `CMD ["python", "-m", "app.environment.worker"]`. Use exactly one replica, `restart: unless-stopped`, and a memory limit of at least 1 GB for Chromium. No published ports.
3. **Environment and secrets:**
   - Worker: `DATABASE_URL`, `AERON_STATION_ID`, `AERON_USERNAME`, `AERON_PASSWORD` (via Docker secrets or the host secret store, never in compose or the image), and optionally `AERON_POLL_INTERVAL_SECONDS` / `AERON_*_TIMEOUT_SECONDS`.
   - No longer needed: `AERON_API_KEY`, `AERON_BASE_URL`, `AERON_LOGIN_URL`, `AERON_SESSION_COOKIE`, `AERON_TIMESTAMP_CORRECTION_MINUTES`, `AERON_INTERNAL_SYNC_TOKEN`.
4. **Scheduling:** the long-running loop is the scheduler. The advisory lock makes extra replicas exit (code 2) instead of double-polling. A cron or one-shot `--once` job is an equivalent alternative.
5. **PostgreSQL:** the existing server and volume; nothing new. No host port. The worker connects over the compose network.
6. **Nginx:** route `location /api/environment/ { proxy_pass http://api:8000; }` for GET only. Do not route to `:8001`. No `/sync` path.
7. **Monitoring:** alert when `/api/environment/status` shows `last_sync_outcome=FAILED` repeatedly, or `freshness=OFFLINE` for longer than an agreed window.

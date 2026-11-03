# Aeron AQI integration (production)

The Weather and air-quality page shows readings from the Aeron station on campus (station **Air Quality KCT**, type XTM-XG930). K-COSMOS gets those readings from Aeron's **REST API v1** with a **Bearer API key**. There is no browser, no login form and no session cookie anywhere in the pipeline.

Only one process talks to Aeron: the `environment-worker` container. Visitors never trigger an Aeron call. They read stored rows from the K-COSMOS API.

The verified source contract (endpoints, payload, parameter IDs, timestamps) is in [AERON_REAL_API_CONTRACT.md](AERON_REAL_API_CONTRACT.md).

```text
Aeron Live3 REST API v1   https://live3.aeronsystems.com/api/v1
   ▲  GET /timeseries?station={id}    Authorization: Bearer $AERON_API_KEY   every 300 s
   │  GET /parameters?station={id}    once at worker start (drift check, logged by ID only)
   │
environment-worker container        python -m app.environment.worker
   │  same image as the API (services/main-api/Dockerfile)
   │  normalize → validate → INSERT … ON CONFLICT (station_id, observed_at) DO NOTHING
   ▼
PostgreSQL   environment.readings, environment.ingestion_runs
   ▲
api container (FastAPI, 127.0.0.1:8000)
   │  GET /api/environment/latest | /history | /status | /parameters   (read-only)
   ▼
Nginx (same origin, https://sustainability.kct.ac.in/api/…)
   ▼
Weather page   apps/public-dashboard/weather.js   (polls every 60 s, charts every 5 min)
```

## 1. What runs in production

| Container | Image | Command | Ports | Talks to |
| --- | --- | --- | --- | --- |
| `…-api-1` | built from `services/main-api/Dockerfile` | `uvicorn app.main:app` | `127.0.0.1:8000` | PostgreSQL |
| `…-environment-worker-1` | **same Dockerfile as the API** | `python -m app.environment.worker` | none | PostgreSQL, Aeron (outbound HTTPS 443) |
| `…-postgres-1` | `postgres:17` | default | none | — |

The worker needs no extra system packages, no browser binaries and no extra Python extra. Its only new runtime dependency is `httpx`, which is part of the normal `pip install .` of `services/main-api`.

On the existing VPS the Compose project is called `sustainability-production`, so the containers are `sustainability-production-api-1`, `sustainability-production-environment-worker-1` and `sustainability-production-postgres-1`. The repository's `compose.yaml` uses the project name `kcosmos`. See [section 4](#4-upgrade-the-existing-production-server) before you run anything on that server.

## 2. Configuration

All settings live in the one environment file, `services/main-api/.env`. It is git-ignored. Copy it from `.env.example`.

| Variable | Default | Notes |
| --- | --- | --- |
| `AERON_STATION_ID` | required | `b1ce41c2-586a-4a26-9382-9d8bfe757e78` |
| `AERON_API_KEY` | required | Secret. Only in `.env` on the server. Never in Git, a frontend file, a log or a ticket. |
| `AERON_API_BASE_URL` | `https://live3.aeronsystems.com/api/v1` | Must be plain HTTPS, no query string |
| `AERON_POLL_INTERVAL_SECONDS` | `300` | Clamped to 120–3600: a smaller value is raised to 120, a larger one lowered to 3600. Never rejected, so a typo cannot stop the worker. |
| `AERON_CONNECT_TIMEOUT_SECONDS` | `5` | |
| `AERON_READ_TIMEOUT_SECONDS` | `15` | |
| `AERON_MAX_ATTEMPTS` | `3` | 1–5. Retries timeouts, network errors and 5xx only. |

Aeron limits the key to **60 requests per minute and 10,000 per day**. The default 300 s poll uses **288 a day (about 3 %)**. Even at the 120 s floor, with every retry used, the worker stays far below both limits. See [section 10](#10-reliability-and-fallback) for why 300 s was chosen.

The API process does not read these variables. If `AERON_API_KEY` is empty the worker logs `environment_worker_not_configured` and exits with code 3. The API keeps serving stored readings.

## 3. Fresh install

This is the path for a new server that uses the repository's `compose.yaml` and `deployment/scripts/deploy.sh`. The full host setup is in [docs/DEPLOYMENT.md](../DEPLOYMENT.md).

```bash
cd /opt/kcosmos/Sustainability-Intelligence/services/main-api
cp .env.example .env
nano .env                          # fill the database, secrets and AERON_API_KEY
cd ../..
deployment/scripts/deploy.sh       # build, migrate, start api + environment-worker + frontends
```

`deploy.sh` stops if `AERON_STATION_ID` or `AERON_API_KEY` is empty. It runs `alembic upgrade head`, which applies `0012_environment_readings` and `0018_aeron_api_v1`.

Manual equivalent:

```bash
cd services/main-api
docker compose build
docker compose up -d postgres
docker compose run --rm --no-deps api alembic upgrade head
docker compose up -d api environment-worker
```

## 4. Upgrade the existing production server

Use this on `sustainability.kct.ac.in`. It keeps the current method: Docker Compose with `compose.production.yaml`, run from the backend directory. It does not create a new database or a new Compose project.

Server paths:

| Item | Path |
| --- | --- |
| Project root | `/opt/sustainability_intelligence_system` |
| Backend and Compose files | `/opt/sustainability_intelligence_system/services/main-api` |
| Environment file | `/opt/sustainability_intelligence_system/services/main-api/.env` |

### 4.1 Set the Compose command

Always pass the existing project name and file. If you leave out `-p`, Compose may start a second, empty PostgreSQL under another project name.

```bash
cd /opt/sustainability_intelligence_system/services/main-api
docker compose ls                                  # expect: sustainability-production
DC="docker compose -p sustainability-production -f compose.production.yaml"
$DC ps                                             # expect: api, environment-worker, postgres
```

If `docker compose ls` shows a different config file for `sustainability-production`, use that file in `DC`.

### 4.2 Back up the database

```bash
sudo mkdir -p /var/backups/kcosmos
$DC exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  | sudo tee /var/backups/kcosmos/pre-aeron-v1-$(date +%Y%m%d-%H%M%S).dump >/dev/null
ls -lh /var/backups/kcosmos
```

The dump must not be 0 bytes.

### 4.3 Pull the code

```bash
cd /opt/sustainability_intelligence_system
git status                      # must be clean apart from untracked server files
git branch --show-current       # confirm the production branch with the developer
git pull --ff-only
```

### 4.4 Update `.env`

Add the API key and the v1 settings:

```text
AERON_STATION_ID=b1ce41c2-586a-4a26-9382-9d8bfe757e78
AERON_API_BASE_URL=https://live3.aeronsystems.com/api/v1
AERON_API_KEY=<key from Aeron>
AERON_POLL_INTERVAL_SECONDS=300
AERON_CONNECT_TIMEOUT_SECONDS=5
AERON_READ_TIMEOUT_SECONDS=15
AERON_MAX_ATTEMPTS=3
```

Delete these old lines. The worker no longer reads them, and they hold the old Aeron account password:

```text
AERON_USERNAME  AERON_PASSWORD  AERON_SESSION_COOKIE  AERON_LOGIN_URL
AERON_INTERNAL_BASE_URL  AERON_DASHBOARD_URL  AERON_REGION
AERON_HTTP_TIMEOUT_SECONDS  AERON_LOGIN_TIMEOUT_SECONDS
```

```bash
chmod 600 .env
```

### 4.5 Update the worker service in `compose.production.yaml`

`compose.production.yaml` is a server file; it is not in Git. Back it up, then replace only the `environment-worker:` service with the block below. Leave `api` and `postgres` as they are.

```bash
cp compose.production.yaml compose.production.yaml.bak-$(date +%Y%m%d)
nano compose.production.yaml
```

```yaml
  environment-worker:
    build:
      context: .
      dockerfile: Dockerfile            # was Dockerfile.worker (deleted from the repository)
    command: ["python", "-m", "app.environment.worker"]
    env_file:
      - path: .env
        required: false
    environment:
      DATABASE_URL: ${DATABASE_URL:?Set DATABASE_URL in .env}
    depends_on:
      postgres:
        condition: service_healthy
    init: true
    restart: unless-stopped
    stop_grace_period: 20s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
```

Add the same `logging:` block to `api` and `postgres` in that file. Without it, Docker's logs grow until the disk is full.

Keep the worker's database settings the same as the `api` service in that file. If `api` takes `DATABASE_URL` from a different variable, use the same one here. Remove any old `AERON_USERNAME: ${AERON_USERNAME:?…}` style lines. They make Compose stop with an error once the old values are gone from `.env`.

Check the file:

```bash
$DC config --quiet && echo OK
$DC config | grep -n -i -E "dockerfile|playwright|AERON_USERNAME|AERON_PASSWORD"
```

The second command should print only `dockerfile: Dockerfile` lines.

### 4.6 Build, migrate, restart

```bash
$DC build api environment-worker
$DC run --rm --no-deps api alembic upgrade head      # applies 0018_aeron_api_v1
$DC up -d api environment-worker
$DC ps
```

Migration `0018_aeron_api_v1` only adds three nullable columns to `environment.readings`. It does not change or delete existing rows.

Optional: remove the old Chromium image layers that are now unused.

```bash
docker image prune
```

This removes dangling images only. Do not use `docker system prune -a` or `docker compose down -v`.

### 4.7 Frontend

The Weather page code is `apps/public-dashboard/weather.js`. It shows the KPI cards without a status bar or calibration notes, shows humidity in %, shows pressure in hPa with a "!" marker while the sensor reports an impossible value (outside 870–1085 hPa), and shows AQI without a health category. Freshness is shown only as the dot on the Weather navigation button. Confirm which directory the production web server serves for `/`. If it is still `apps/public-dashboard-final-staging`, that copy does not have these changes; it must be switched to `apps/public-dashboard` or updated.

### 4.8 Rollback

The schema change is additive, so the database does not need a downgrade.

```bash
cd /opt/sustainability_intelligence_system
git log --oneline -5                                 # pick the previous commit
git checkout <previous-commit>
cd services/main-api
cp compose.production.yaml.bak-YYYYMMDD compose.production.yaml
# restore the old AERON_* lines in .env
$DC up -d --build api environment-worker
```

## 5. Check that it works

Run these after a fresh install or an upgrade. `DC` is the Compose command from section 4.1, or plain `docker compose` on a fresh install.

```bash
$DC logs --tail 50 environment-worker
```

Expected log events:

| Event | Meaning |
| --- | --- |
| `environment_worker_started` | Worker running, with its interval |
| `environment_parameter_metadata` | Start-up drift check. `unmapped` and `absent` should be empty. |
| `environment_ingestion_cycle outcome=INSERTED` | A new reading was stored |
| `environment_ingestion_cycle outcome=DUPLICATE` | Aeron still has the same latest reading. Normal; see section 9. |

```bash
curl -s http://127.0.0.1:8000/api/environment/status
curl -s http://127.0.0.1:8000/api/environment/latest | head -c 400; echo
curl -s https://sustainability.kct.ac.in/api/environment/status
```

In `/status`, `last_sync_outcome` should be `INSERTED` or `DUPLICATE`, `last_sync_error_code` should be `null`, and `freshness` should be `LIVE` (reading less than 20 minutes old).

Database check:

```bash
$DC exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
select outcome, error_code, count(*)
from environment.ingestion_runs
where started_at > now() - interval '1 hour'
group by 1, 2;
SQL
```

Do not run `python -m app.environment.worker --once` while the worker container is running. The second copy cannot take the advisory lock and exits with code 2. To test one cycle, stop the worker first:

```bash
$DC stop environment-worker
$DC run --rm environment-worker python -m app.environment.worker --once ; echo "exit=$?"
$DC up -d environment-worker
```

Exit code 0 means the cycle succeeded, 1 means it failed (the code is in the log), 3 means `AERON_API_KEY` is missing.

## 6. How a cycle works

1. `GET /timeseries?station=…` with the Bearer key. The rate-limit headers are logged as counts.
2. Normalize and validate the reading.
3. Insert it only if `(station_id, observed_at)` is new. Otherwise the outcome is `DUPLICATE`. A restarted worker relies on this, so it never stores the same observation twice.
4. Write one `environment.ingestion_runs` row: `INSERTED`, `DUPLICATE` or `FAILED` with a fixed `error_code`.
5. Wait. `PollScheduler` decides how long:

| Last result | Next poll |
| --- | --- |
| Success, or timeout / network / 5xx | After the normal interval |
| HTTP 429 | After `Retry-After` (or `X-Ratelimit-Reset`), at least the interval, at most 1 h |
| 401, 403, 404, station mismatch | 5 min, doubling up to 1 h. Resets on the next success. |
| Aeron reports fewer than 500 requests left today | 30 min, until the daily allowance resets |
| Worker just restarted | Waits until one interval has passed since the last recorded run, so restarts and redeploys add no extra calls |

The loop is single-threaded, so cycles never overlap. A PostgreSQL advisory lock allows one worker per database. SIGTERM stops it cleanly between cycles.

## 7. Components

| Piece | File (under `services/main-api/`) | Responsibility |
| --- | --- | --- |
| Settings | `app/environment/config.py` | `AeronWorkerSettings` from `.env`. Key held as `SecretStr`. HTTPS enforced. |
| API client | `app/environment/source.py` | `AeronApiClient`: one pooled `httpx.Client`, Bearer header, separate connect/read timeouts, redirects refused so the key never leaves the origin, jittered retries capped at 8 s for transient errors only, fixed error codes. |
| Parameter map | `app/environment/parameters.py` | 35 Aeron parameter IDs → name, source unit, category, column; verification notes |
| Normalizer | `app/environment/normalizer.py` (v2) | Parses `reading.timestamp` as UTC (no +330 shift; timestamps without a zone are rejected). Checks `epoch_ms`. Missing or non-numeric values become `NULL` plus a quality flag, never 0. Unknown IDs go to `unmapped_values`. A response for another station is rejected. |
| Repository | `app/environment/repository.py` | Idempotent insert, latest, bounded history, run records |
| Worker | `app/environment/worker.py` | Loop, `--once`, `PollScheduler`, advisory lock, signal handling |
| Freshness | `app/environment/freshness.py` | LIVE < 20 min ≤ STALE ≤ 60 min < OFFLINE, from server time |
| Public API | `app/routers/environment.py`, `app/schemas/environment.py` | Read-only routes |
| Schema | `alembic/versions/0012_environment_readings.py`, `0018_aeron_api_v1.py` | `environment` schema |
| Tests | `tests/test_environment_*.py`, `tests/fixtures/aeron/aeron_v1_sample_sanitized.json` | Client, normalizer, worker, API, PostgreSQL |

## 8. Public API

| Route | Behaviour |
| --- | --- |
| `GET /api/environment/latest?station_id=` | Newest stored reading plus `freshness`. 404 if none yet. |
| `GET /api/environment/history?station_id=&start=&end=&limit=` | Newest first. `limit` 1–1000 (default 100). `start` after `end` → 422. |
| `GET /api/environment/status` | Freshness, age, last sync time, outcome and error code, last successful sync, database connectivity |
| `GET /api/environment/parameters` | Static parameter list with units and verification notes. No Aeron call. |

All routes are `GET` and send `Cache-Control: no-store`. There is no sync or write route.

### Stored columns (`environment.readings`)

| Column | Meaning |
| --- | --- |
| `observed_at` | Sensor time (UTC), from `reading.timestamp` |
| `fetched_at` | When the worker received the response (UTC) |
| `ingested_at` | When K-COSMOS stored the row (UTC) |
| `source_recorded_at_raw`, `source_epoch_ms` | Source timestamp and `epoch_ms`, verbatim |
| `source_route` | `GET /api/v1/timeseries?station={station_id}` |
| `normalizer_version` | `2` |
| `quality_flags` | `missing:<field>`, `non_numeric:<field>`, `unknown_parameter:<id>`, `epoch_ms_mismatch` |
| `raw_payload`, `unmapped_values` | Response as received, unknown IDs. Never served by the API. Contain no credentials. |
| 35 metric columns | Source units, no conversion. Mapping in [AERON_REAL_API_CONTRACT.md](AERON_REAL_API_CONTRACT.md). |
| `network`, `battery`, `charging`, `device_temp` | Not provided by API v1. NULL on new rows. |

Rows stored before 0018 keep their values; their new columns are NULL and their `normalizer_version` is `1`.

## 9. Troubleshooting

Find the code in the worker log or in `/api/environment/status` → `last_sync_error_code`.

| Code | Cause | Fix |
| --- | --- | --- |
| exit code 3, `environment_worker_not_configured` | `AERON_API_KEY` empty or not passed to the container | Set it in `.env`; check `env_file` in the Compose file; `$DC up -d environment-worker` |
| `AUTH_FAILED` (401) | Key wrong, revoked or has extra spaces | Get a new key from Aeron, update `.env`, restart the worker |
| `FORBIDDEN` (403) | Key cannot read this station | Ask Aeron to grant the key access to the station |
| `NOT_FOUND` (404) | Wrong `AERON_STATION_ID` or base URL | Compare with section 2 |
| `STATION_MISMATCH` | Response is for another station | Check `AERON_STATION_ID` |
| `RATE_LIMITED` (429) | Over 60/min or 10,000/day; with one worker this should not happen | Make sure only one worker runs (`docker ps \| grep environment-worker`) and that nothing else uses the same key |
| `TIMEOUT`, `NETWORK_ERROR` | VPS cannot reach `live3.aeronsystems.com:443` | `$DC exec environment-worker python -c "import httpx; print(httpx.get('https://live3.aeronsystems.com').status_code)"`; check DNS and outbound firewall |
| `HTTP_ERROR` | Other non-200, including a redirect | Usually Aeron-side; retried next cycle |
| `MALFORMED_RESPONSE`, `INVALID_READING` | Response not usable | Nothing is stored; report to Aeron if it continues |
| `DATABASE_ERROR` | PostgreSQL down or `DATABASE_URL` wrong | `$DC ps`, `$DC logs postgres` |
| `environment_worker_already_running`, exit code 2 | A second worker is running on the same database | Run exactly one worker. Look for an old container: `docker ps -a \| grep environment-worker` |

After 401, 403 or 404 the worker waits 5 minutes or more before it tries again. After fixing the cause, restart it to retry at once: `$DC restart environment-worker`.

| Symptom | Meaning |
| --- | --- |
| Some `DUPLICATE` | Normal. Aeron publishes a new reading about every 7 minutes, so some 5-minute polls see the same reading. |
| Page says STALE or OFFLINE, worker shows `DUPLICATE` | The station itself has stopped reporting. Check the station's status with Aeron. |
| Cards show `--` and the nav dot is red | The browser cannot reach `/api/environment/*`, or there is no reading yet. Check the API container and Nginx. |
| "!" on the Pressure card | Expected while the sensor reports a value outside 870–1085 hPa (currently a constant 150). It disappears once Aeron fixes the calibration. |

The worker never logs the key, request headers or response bodies. Do not add `print` statements or debug logging that would.

## 10. Reliability and fallback

### Why 300 seconds

Measured on 2026-11-03: Aeron's `latest` reading changes about **every 7 minutes**, and arrives 1.6–7.6 minutes after the sensor time. Polling every 60 s mostly fetched the same reading again. Polling every 300 s catches almost every new reading, uses 288 of the 10,000 daily requests, and leaves room for retries, restarts and manual tests.

Because a reading can be up to about 20 minutes old in normal operation (7 min cadence + up to 8 min delivery + 5 min poll), the freshness thresholds are LIVE < 20 min, STALE 20–60 min, OFFLINE after 60 min. With the old 10-minute limit, the page would have flickered to STALE while everything was healthy.

### Safeguards against blocking the Aeron key

| Risk | Safeguard |
| --- | --- |
| Polling too often (misconfigured `.env`) | Interval clamped to 120–3600 s |
| Two workers on one key | PostgreSQL advisory lock; the second exits with code 2 |
| Crash or redeploy loop | First poll after a restart waits out the rest of the interval; startup without a key or database makes no Aeron call |
| Retry storm on errors | Only timeouts, network errors and 5xx are retried, at most 3 attempts, 1–8 s apart |
| Wrong or revoked key | No retry; pause 5 min doubling to 1 h |
| HTTP 429 | Waits for `Retry-After`, up to 1 h |
| Daily allowance running low | Below 500 left: one poll every 30 min |
| Visitors | Never reach Aeron. They only read the K-COSMOS database through the API. |

### Other failure modes

| Failure | What happens |
| --- | --- |
| Aeron down or slow | 5 s connect / 15 s read timeout; the cycle fails with `TIMEOUT` or `NETWORK_ERROR`; nothing is stored; the next poll is normal |
| Bad or partial payload | `MALFORMED_RESPONSE` or `INVALID_READING`; nothing is stored. Missing single values are stored as NULL, never 0. |
| PostgreSQL down | Cycle records `DATABASE_ERROR`; at startup the worker exits and Docker restarts it with backoff, without calling Aeron |
| API down | Weather page keeps the last values on screen (see below) |
| Docker logs growing | `compose.yaml` keeps 5 × 10 MB per container |
| Database growth | One row per new reading (~200/day) and one per poll (288/day); small |

### Weather page fallback

| Situation | What the visitor sees |
| --- | --- |
| Worker stopped or Aeron down, API up | The last stored reading from PostgreSQL. The dot on the Weather button turns amber after 20 min and red after 60 min. |
| API unreachable while the page is open | The values already on screen stay. The dot turns red. Requests are abandoned after 10 s and never pile up. |
| API unreachable on a fresh visit | The last reading this browser saved (localStorage). The dot is red. |
| No reading ever seen by this browser and API down | Cards show `--`. |
| API back | The next poll (within 60 s, or immediately when the tab becomes visible) shows current data. |

The page polls `/latest` every 60 s and `/history` every 5 minutes, one request at a time, and pauses while the browser tab is in the background.

## 11. Security

- The key is only in `services/main-api/.env` (mode 600) and in the worker's memory. The API container never uses it.
- Rotate the key if it ever appears in Git, a log, a screenshot or a chat. Update `.env`, then `$DC up -d environment-worker`.
- The worker refuses redirects, so the `Authorization` header is only sent to `live3.aeronsystems.com`.
- The old Aeron account password was committed to Git history in earlier commits. It must be changed on the Aeron side; the K-COSMOS system no longer uses it.

## 12. Known limits

1. **No Aeron history import.** The v1 history parameters are not verified, so K-COSMOS builds its own history from the readings it stores.
2. **Source metadata not confirmed by Aeron.** Values are stored as received: pressure is a constant 150 "mBa", the `CO_ppm` parameter carries a ppb unit, the AQI standard is unknown, and humidity's unit is "Per". These notes are served by `/api/environment/parameters` for operators; the public page does not show them. It shows humidity as %, and marks pressure with "!" until a plausible value arrives.
3. **No device health.** API v1 has no network, battery, charging or device-temperature fields.
4. **No hourly or daily aggregates** yet. Diagnostic (mV) and ppb channels are stored and returned by `/latest` and `/history` but not shown on the page.

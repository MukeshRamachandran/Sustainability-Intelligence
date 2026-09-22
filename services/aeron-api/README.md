# Aeron Environment Dashboard

Standalone environmental-monitoring component for the Microcosm platform. It
collects weather and air-quality readings from an Aeron Live3 station, stores
normalized measurements, and exposes them through a FastAPI service.

This component is separate from the public sustainability dashboard in the
parent directory and from the manager/admin submission portal.

## Components

- `backend/` — FastAPI routes, SQLAlchemy models, schemas, and Aeron services.
- `frontend/` — standalone HTML/CSS/JavaScript monitoring interface.
- `database/schema.sql` — PostgreSQL `environmental` schema contract.
- `database/database.py` and `database/models.py` — inactive legacy helpers retained for compatibility.
- `backend/tests/` — normalization and synchronization tests.

## Configuration

Copy `.env.example` to `.env` and configure:

- `AERON_PUBLIC_API_URL`
- `AERON_FALLBACK_API_URL`
- `AERON_API_KEY`
- `AERON_STATION_ID`
- `AERON_SYNC_INTERVAL_SECONDS`
- `AERON_REQUEST_TIMEOUT_SECONDS`
- `AERON_RETRY_COUNT`
- `AERON_FALLBACK_ENABLED`
- `AERON_INTERNAL_SYNC_TOKEN`
- `DATABASE_URL`

Never commit `.env` or live Aeron credentials.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8001
```

The API starts at `http://127.0.0.1:8001`. The standalone monitoring page is
`frontend/environmental_monitoring.html`.

## Current API wiring

`backend/main.py` registers the canonical `/api/environment` read routes and
the protected manual-sync route. The legacy `air_quality.py`, `weather.py`, and
`device.py` modules remain unregistered to avoid duplicate API contracts.

The service listens on internal port `8001` in Docker. The public browser uses
same-origin `/api/environment/*` paths; Nginx will proxy those requests to this
service. Tables are created explicitly from `database/schema.sql` in the shared
PostgreSQL database under the `environmental` schema. Application startup never
creates tables and never silently falls back to SQLite.

Manual synchronization is `POST /api/environment/sync` and requires the
server-side `X-Internal-Sync-Token`. It must not be exposed as a public UI
control. Normal collection runs in the service every 60 seconds by default.

Known data-quality cautions:

- barometric pressure and CO2 require calibration verification;
- the configured timestamp correction must be revalidated against the station
  clock before exact timestamp claims are made;
- raw upstream payloads and raw source timestamps are retained for audit.

## Testing

Install `pytest` in the active environment, then run:

```powershell
python -m pytest backend/tests -q
```

## Repository note

This directory currently has its own Git metadata and is checked out at a
detached commit. Decide separately whether it should remain an independent
repository, become a proper submodule, or be absorbed into the parent project.
No conversion is implied by this documentation cleanup.

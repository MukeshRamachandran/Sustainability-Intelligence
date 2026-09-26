# Docker decisions

## Aeron environmental monitoring

- The former separate `services/aeron-api` service (port `8001`) has been
  retired. The main K-COSMOS API serves the read-only `/api/environment/*`
  routes from persisted readings; public requests never contact Aeron.
- Ingestion runs in a separate, single-instance worker process
  (`python -m app.environment.worker`) built from the main API code with the
  `aeron-worker` extra (Playwright + Chromium). The API image stays browser-free.
- Nginx proxies `/api/environment/*` to the main API. Browsers use only
  relative same-origin URLs and never learn internal hostnames or ports.
- Readings live in the `environment` schema of the shared PostgreSQL database
  (migration `0012_environment_readings`) and never mix with sustainability
  submissions. A PostgreSQL advisory lock keeps one worker active.
- Worker configuration is supplied through environment variables or secrets:
  station ID, internal base URL, Aeron username/password, poll interval,
  timeouts, and the database URL. No timestamp correction is configured: the
  Aeron source timestamp is verified true UTC.
- PostgreSQL will not publish a host port in the final stack. Only the
  frontend/Nginx service will be publicly exposed.
- There is no manual sync endpoint. `python -m app.environment.worker --once`
  runs a single cycle for operators.

See `AERON_INTEGRATION_ARCHITECTURE.md` at the repository root. Production
Compose packaging remains deferred until the full application stack is
assembled.

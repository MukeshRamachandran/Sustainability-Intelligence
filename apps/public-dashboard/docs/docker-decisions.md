# Docker decisions

## Aeron environmental service

- Aeron remains a separate FastAPI service because its upstream polling,
  normalization, retry, and sensor lifecycle are independent of the
  sustainability submission workflow.
- The container listens on private port `8001`; the main K-COSMOS backend keeps
  its existing port.
- Nginx will proxy `/api/environment/*` to the Aeron service. Browsers use only
  relative same-origin URLs and never learn internal hostnames or ports.
- Aeron and the main backend share one PostgreSQL server. Aeron tables live in
  the `environmental` schema and never mix with sustainability submissions.
- PostgreSQL storage uses the existing database volume. Environmental readings
  persist across Aeron container replacement.
- Required configuration is supplied through environment variables or secrets:
  upstream URLs, station ID, sync interval, timeouts, retry count, database URL,
  optional fallback configuration, timestamp correction, and internal sync
  token.
- Liveness checks only the process. Readiness checks PostgreSQL connectivity and
  required configuration; temporary upstream Aeron failure does not make the
  container unready.
- PostgreSQL will not publish a host port in the final stack. Only the
  frontend/Nginx service will be publicly exposed.
- Manual sync is protected by a server-side token and is not available from the
  anonymous Weather UI.

Production Compose packaging remains deferred until the full application stack
is assembled.

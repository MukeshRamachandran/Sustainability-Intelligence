# Architecture

K-COSMOS Sustainability Intelligence has one public name, `https://sustainability.kct.ac.in`. Cloudflare proxies that name to Nginx. Nginx is the only process that accepts public traffic.

```text
Internet
    |
    v
Cloudflare
    |
    | HTTPS :443
    v
Nginx
    |
    +------------------------------+
    |                              |
    | /api/*                       | /*
    | /health/*                    |
    v                              v
FastAPI 127.0.0.1:8000        Public dashboard
    |                         127.0.0.1:3001
    +----------+
    |          |
    v          v
PostgreSQL   Environment worker
(Docker      (Docker network)
 network)

Nginx /admin/* -> Manager/Admin static files on 127.0.0.1:3002
```

| Browser URL | Upstream |
| --- | --- |
| `https://sustainability.kct.ac.in/` | Public dashboard |
| `https://sustainability.kct.ac.in/admin/` | Manager and admin portal |
| `https://sustainability.kct.ac.in/api/*` | FastAPI |
| `https://sustainability.kct.ac.in/health/live` | FastAPI liveness |
| `https://sustainability.kct.ac.in/health/ready` | FastAPI readiness |

The browser calls `/api/...` on the same HTTPS origin. It does not call port 8000, 3000, 3001, or 3002. Those ports are not published to the Internet.

## Applications

- `apps/public-dashboard` is anonymous. It reads published data from `/api/public/...` and local CSV files shipped with the page.
- `apps/manager-admin` is the administrator portal and the six manager domains: transport, energy, LPG, water, outreach, and waste. Authentication is shared. The API enforces role and domain.
- `services/main-api` is the FastAPI application, Alembic migrations, and the Aeron environment worker.

The frontend never opens a database connection.

## API namespaces

| Prefix | Who can call it |
| --- | --- |
| `/health/` | Anyone. Liveness does not touch the database. |
| `/api/auth/` | Login is public. Session, logout, and password change use the session cookie. |
| `/api/public/` | Anyone. Published dashboard data only. |
| `/api/manager/` | A signed-in manager, and only for the assigned domain. |
| `/api/admin/` | A signed-in administrator. |
| `/api/access/` | Signed-in users, for their own access description. |
| `/api/environment/` | Read-only environment readings served by the API. |

OpenAPI (`/docs`, `/redoc`, `/openapi.json`) is on when `APP_ENV` is not `production`. Set `OPENAPI_ENABLED=true` or `false` to override that.

## URL classification

| Match | Class | Where |
| --- | --- | --- |
| `/api/...` from the browser | Production required | Public dashboard and manager portal behind Nginx |
| `http://127.0.0.1:8000` when the page port is 3000, 5500, or 8080 | Development only | Local static servers. Disabled for `sustainability.kct.ac.in` |
| `127.0.0.1:8000`, `:3001`, `:3002` in Nginx, Compose, and systemd | Production required | Loopback binds. Not public listeners |
| `postgres:5432` inside Compose | Production required | Docker DNS only |
| `file://` | Remove | Not used by the production pages |
| Cloudflare Insights script tags | Remove | Not added by this application |
| Passwords, `SECRET_KEY`, `CSRF_SECRET`, `DATABASE_URL` values | Configure | `.env` on the server, never Git |

## What does not start by itself

Container startup does not run Alembic. `deployment/scripts/deploy.sh` runs `alembic upgrade head` as its own step. The static frontends are systemd units, not an SSH session.

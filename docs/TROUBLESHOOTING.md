# Troubleshooting

## `/health/live` fails

The API process is not accepting connections on `127.0.0.1:8000`.

```bash
cd services/main-api
docker compose ps
docker compose logs api --tail 100
```

A production `.env` that still has `SECRET_KEY=development-only-change-me`, `SESSION_COOKIE_SECURE=false`, or a `http://` public URL will refuse to start. The error is in the API log, not in the browser.

## `/health/ready` returns 503

The body says which dependency failed.

- `database: unavailable` — PostgreSQL is down, `DATABASE_URL` points at the wrong host, or the password does not match `POSTGRES_PASSWORD`.
- `evidence: unavailable` — `/data/evidence` or `/data/evidence/clean` is missing or not writable by the `microcosm` user in the API container.

Liveness can still be `ok` while readiness is 503.

## `/api/auth/session` returns 500

An anonymous call must return 401. A 500 means an exception. Read the API log for the request id printed in the JSON error body. The browser response does not include a stack trace.

## Login says the account is not authorized

The password was accepted and the session was then rejected because the role or domain does not match that login page. The page logs the session out. Use the login page for the assigned domain, or correct the domain in the admin user screen.

## Manager pages load without CSS

The site is being opened as `/admin-login.html` on the public origin, so the browser asks the public dashboard for `styles.css`. Use `/admin/admin-login.html`. Relative links are required. A leading `/styles.css` would leave the `/admin/` prefix.

## Weather page shows OFFLINE, STALE or no data

The Aeron data comes from the `environment-worker` container, not from the API.

```bash
cd services/main-api
docker compose ps environment-worker
docker compose logs --tail 50 environment-worker
curl -s http://127.0.0.1:8000/api/environment/status
```

On the existing production server use `docker compose -p sustainability-production -f compose.production.yaml` in place of `docker compose`.

Read `last_sync_error_code` in `/status`, or `error_code` in the `environment_ingestion_cycle` log line:

| Code or message | Fix |
| --- | --- |
| `environment_worker_not_configured` (container exits with code 3) | Set `AERON_API_KEY` in `services/main-api/.env`, then `docker compose up -d environment-worker` |
| `AUTH_FAILED` | The API key is wrong or revoked. Put a valid key in `.env` and restart the worker. |
| `FORBIDDEN`, `NOT_FOUND`, `STATION_MISMATCH` | Check `AERON_STATION_ID` and `AERON_API_BASE_URL` against `.env.example`, or ask Aeron to grant the key access |
| `RATE_LIMITED` | More than one worker, or another system using the same key. Run one worker. |
| `TIMEOUT`, `NETWORK_ERROR` | The VPS cannot reach `live3.aeronsystems.com:443`. Check DNS and outbound firewall. |
| `DATABASE_ERROR` | PostgreSQL is down or `DATABASE_URL` is wrong |
| `environment_worker_already_running` (exit code 2) | Another worker is already running on this database. Keep one. |

After 401, 403 or 404 the worker waits at least 5 minutes before retrying. Restart it after fixing the cause: `docker compose restart environment-worker`.

If the outcome is `DUPLICATE` and the page is STALE or OFFLINE, the station itself is not sending new readings; check it with Aeron. A few `DUPLICATE` results in a row are normal.

Full table: [docs/reports/AERON_INTEGRATION_ARCHITECTURE.md](reports/AERON_INTEGRATION_ARCHITECTURE.md#9-troubleshooting).

## Cloudflare or the origin certificate

Use SSL mode Full (strict) and a Cloudflare Origin certificate at the paths in `deployment/nginx/sustainability.kct.ac.in.conf`. Flexible mode speaks HTTP to the origin while the session cookie is marked Secure, so the browser will not send the cookie on that hop.

If visitor IPs in the Nginx log are Cloudflare addresses, update `deployment/nginx/cloudflare-real-ip.conf` from <https://www.cloudflare.com/ips/> and reload Nginx.

A Cloudflare Insights error in the browser console is outside this application. The pages do not load that script, and a failed beacon must not block the dashboard.

## Ports

```bash
sudo ss -tulpn | grep -E ':3001|:3002|:8000|:5432|:443'
```

3001, 3002, and 8000 should show `127.0.0.1` only. 5432 should not show a public or wildcard bind from this project. 443 should be Nginx.

## Logs

Run from `services/main-api` (production: add `-p sustainability-production -f compose.production.yaml`).

```bash
docker compose logs api environment-worker postgres
journalctl -u kcosmos-public-dashboard.service -u kcosmos-manager-admin.service
sudo tail -f /var/log/nginx/sustainability.error.log
```

## After a reboot

Docker services use `restart: unless-stopped`. The frontend units are `enabled`. Nginx is `enabled`. If a unit is not running after reboot, check that it was enabled and that `/opt/kcosmos` is mounted before `network-online.target`.

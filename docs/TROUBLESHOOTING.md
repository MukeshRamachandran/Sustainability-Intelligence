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

```bash
docker compose logs api environment-worker postgres
journalctl -u kcosmos-public-dashboard.service -u kcosmos-manager-admin.service
sudo tail -f /var/log/nginx/sustainability.error.log
```

## After a reboot

Docker services use `restart: unless-stopped`. The frontend units are `enabled`. Nginx is `enabled`. If a unit is not running after reboot, check that it was enabled and that `/opt/kcosmos` is mounted before `network-online.target`.

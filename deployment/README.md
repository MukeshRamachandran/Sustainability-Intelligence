# Deployment files

These files are the production entry point for an Ubuntu VPS. Nginx on ports 80 and 443 is the only public service. PostgreSQL, the API, and both frontends stay on loopback or the Docker network.

| Path | Purpose |
| --- | --- |
| `nginx/sustainability.kct.ac.in.conf` | Public virtual host |
| `nginx/cloudflare-real-ip.conf` | Visitor IP from Cloudflare |
| `nginx/security-headers.conf` | Headers repeated on API locations |
| `systemd/*.service` | Static frontends on 127.0.0.1:3001 and :3002 |
| `scripts/static-server.py` | Loopback static server used by those units |
| `scripts/deploy.sh` | Pull, build, migrate, restart, check |
| `scripts/backup-db.sh` | Timestamped `pg_dump` outside the container |
| `scripts/restore-db.sh` | Explicit restore; never runs on its own |
| `scripts/health-check.sh` | Public HTTPS checks, including unauthenticated 401 |

The static server is Python's standard library because the dashboards have no build step. It binds only to loopback, disables directory listings, and is supervised by systemd. Do not start it from an SSH shell.

Copy `services/main-api/.env.example` to `services/main-api/.env` on the server. The commands and firewall rules are in `docs/DEPLOYMENT.md`.

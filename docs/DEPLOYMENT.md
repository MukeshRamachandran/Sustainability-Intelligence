# Deployment

Target host: Ubuntu VPS. Public ports: 22, 80, and 443. Do not open 3001, 3002, 8000, or 5432. Outbound HTTPS (443) to `live3.aeronsystems.com` must be allowed for the environment worker.

This document is for a new server. The live server at `/opt/sustainability_intelligence_system` already runs under the Compose project `sustainability-production`; for that server read [section 10](#10-existing-production-server) first.

Clone path used below: `/opt/kcosmos/Sustainability-Intelligence`. The systemd units are rendered with the real checkout path by `deploy.sh`.

## 1. Host packages

```bash
sudo apt update
sudo apt install -y ca-certificates curl git nginx python3 ufw
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and back in so the `docker` group applies.

## 2. Service user

```bash
sudo useradd --system --create-home --home-dir /opt/kcosmos --shell /usr/sbin/nologin kcosmos
sudo mkdir -p /opt/kcosmos /var/backups/kcosmos
sudo chown kcosmos:kcosmos /var/backups/kcosmos
```

## 3. Firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Leave 3001, 3002, 8000, and 5432 closed. Nginx reaches them on loopback. PostgreSQL has no published port.

## 4. Checkout and secrets

```bash
sudo git clone <repository-url> /opt/kcosmos/Sustainability-Intelligence
sudo chown -R kcosmos:kcosmos /opt/kcosmos/Sustainability-Intelligence
cd /opt/kcosmos/Sustainability-Intelligence/services/main-api
cp .env.example .env
nano .env
```

Fill `POSTGRES_PASSWORD`, `DATABASE_URL`, `SECRET_KEY`, `CSRF_SECRET`, and `AERON_API_KEY` (the Aeron REST API v1 key; `AERON_STATION_ID` and the other `AERON_*` defaults are already set). `DATABASE_URL` must be a complete URL. Compose does not expand `${POSTGRES_PASSWORD}` inside the `.env` file.

```text
DATABASE_URL=postgresql+psycopg://microcosm_app:YOUR_PASSWORD@postgres:5432/microcosm
```

Generate secrets:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

`APP_ENV=production`, `SESSION_COOKIE_SECURE=true`, and `ALLOWED_ORIGINS=https://sustainability.kct.ac.in`.

```bash
chmod 600 .env
```

## 5. Database and API

```bash
cd /opt/kcosmos/Sustainability-Intelligence/services/main-api
docker compose up -d postgres
docker compose ps
docker compose run --rm --no-deps api alembic upgrade head
docker compose up -d
```

`docker compose up` does not migrate. Run `alembic upgrade head` yourself, or use `deployment/scripts/deploy.sh`, which does it in order.

`docker compose up -d` starts three services: `postgres`, `api` and `environment-worker`. The worker is built from the same `Dockerfile` as the API and runs `python -m app.environment.worker`. It needs no browser or extra packages.

Check the worker:

```bash
docker compose logs --tail 30 environment-worker      # expect environment_ingestion_cycle outcome=INSERTED or DUPLICATE
curl -s http://127.0.0.1:8000/api/environment/status
```

Details, error codes and fixes: [docs/reports/AERON_INTEGRATION_ARCHITECTURE.md](reports/AERON_INTEGRATION_ARCHITECTURE.md).

## 6. Frontends

```bash
cd /opt/kcosmos/Sustainability-Intelligence
sudo sed "s|@REPO_ROOT@|/opt/kcosmos/Sustainability-Intelligence|g" \
  deployment/systemd/kcosmos-public-dashboard.service \
  | sudo tee /etc/systemd/system/kcosmos-public-dashboard.service >/dev/null
sudo sed "s|@REPO_ROOT@|/opt/kcosmos/Sustainability-Intelligence|g" \
  deployment/systemd/kcosmos-manager-admin.service \
  | sudo tee /etc/systemd/system/kcosmos-manager-admin.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now kcosmos-public-dashboard.service kcosmos-manager-admin.service
```

The units run `deployment/scripts/static-server.py` as `kcosmos`, restart on failure, and log to the journal:

```bash
journalctl -u kcosmos-public-dashboard.service -u kcosmos-manager-admin.service
```

## 7. Nginx and Cloudflare origin TLS

Create a Cloudflare Origin certificate for `sustainability.kct.ac.in` and save it as:

```text
/etc/ssl/cloudflare/sustainability.kct.ac.in.pem
/etc/ssl/cloudflare/sustainability.kct.ac.in.key
```

```bash
sudo mkdir -p /etc/ssl/cloudflare /etc/nginx/snippets
sudo cp deployment/nginx/cloudflare-real-ip.conf /etc/nginx/snippets/kcosmos-cloudflare-real-ip.conf
sudo cp deployment/nginx/security-headers.conf /etc/nginx/snippets/kcosmos-security-headers.conf
sudo cp deployment/nginx/sustainability.kct.ac.in.conf /etc/nginx/sites-available/sustainability.kct.ac.in.conf
sudo ln -sfn /etc/nginx/sites-available/sustainability.kct.ac.in.conf /etc/nginx/sites-enabled/sustainability.kct.ac.in.conf
sudo nginx -t
sudo systemctl reload nginx
```

In Cloudflare:

- DNS `A` or `AAAA` record for `sustainability.kct.ac.in` points at the VPS and is proxied (orange cloud).
- SSL/TLS mode is Full (strict).
- Do not inject a required Analytics snippet into the application. The pages do not load Cloudflare Insights.

Refresh `deployment/nginx/cloudflare-real-ip.conf` from <https://www.cloudflare.com/ips/> if Cloudflare publishes new ranges.

## 8. Check

```bash
curl -f https://sustainability.kct.ac.in/health/live
curl -f https://sustainability.kct.ac.in/health/ready
curl -f https://sustainability.kct.ac.in/api/environment/status
deployment/scripts/health-check.sh
```

Later deploys:

```bash
deployment/scripts/deploy.sh
```

That script pulls, checks `.env` (including that `AERON_STATION_ID` and `AERON_API_KEY` are set), builds images, starts PostgreSQL, migrates, restarts the API and worker, restarts the frontend units, and runs the health check when the public name answers. It uses the repository's `compose.yaml` (project `kcosmos`); do not run it on the existing production server, see section 10.

## 9. Backups

```bash
sudo BACKUP_DIR=/var/backups/kcosmos deployment/scripts/backup-db.sh
```

Schedule that with cron or a systemd timer. The dump is a custom-format file outside the PostgreSQL container. Files older than `BACKUP_RETENTION_DAYS` (default 14) are removed from the backup directory only.

Restore is manual:

```bash
cd /opt/kcosmos/Sustainability-Intelligence/services/main-api
docker compose stop api environment-worker
cd /opt/kcosmos/Sustainability-Intelligence
sudo CONFIRM_RESTORE=yes deployment/scripts/restore-db.sh --replace /var/backups/kcosmos/microcosm-TIMESTAMP.dump
cd services/main-api
docker compose start api environment-worker
```

Nothing in deploy or container startup calls the restore script.

## 10. Existing production server

The live VPS keeps its own deployment method. Do not run `deploy.sh` or a plain `docker compose up` there: the project name would differ and Compose would create a new, empty database volume.

| Item | Value |
| --- | --- |
| Project root | `/opt/sustainability_intelligence_system` |
| Backend and Compose file | `services/main-api/compose.production.yaml` (server file, not in Git) |
| Compose project | `sustainability-production` |
| Containers | `sustainability-production-api-1`, `-environment-worker-1`, `-postgres-1` |

```bash
cd /opt/sustainability_intelligence_system/services/main-api
DC="docker compose -p sustainability-production -f compose.production.yaml"

# back up first
$DC exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  | sudo tee /var/backups/kcosmos/microcosm-$(date +%Y%m%d-%H%M%S).dump >/dev/null

# update code (confirm the branch first)
cd /opt/sustainability_intelligence_system && git pull --ff-only && cd services/main-api

# build, migrate, restart
$DC build api environment-worker
$DC run --rm --no-deps api alembic upgrade head
$DC up -d api environment-worker
$DC ps
$DC logs --tail 30 environment-worker
```

The first deploy after the switch to the Aeron API key also needs a one-time change to `.env` and to the `environment-worker` service in `compose.production.yaml`. Follow section 4 of [AERON_INTEGRATION_ARCHITECTURE.md](reports/AERON_INTEGRATION_ARCHITECTURE.md#4-upgrade-the-existing-production-server).

Never run `docker compose down -v` on this server.

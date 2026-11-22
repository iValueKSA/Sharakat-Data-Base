# Deployment (staging / production, no Docker)

This runbook covers a Linux fleet managed directly with systemd units and nginx. The units and the HTTPS proxy
configuration are in [`deploy/`](../../deploy). For a single server on any OS (Windows Server, Linux or macOS),
including HTTPS, start at boot and external databases, use the native runtime's server mode instead; see
[server.md](server.md). For a workstation, see [native-runtime.md](native-runtime.md).

## Topology

| Component | Runs as | Notes |
|---|---|---|
| HTTPS edge | nginx ([`deploy/nginx.conf`](../../deploy/nginx.conf)) | The only public listener (80 redirects to 443). Serves `app/static` and proxies everything else to the API. |
| API + UI | `sharakat-api.service` (uvicorn on `127.0.0.1:8000`) | Trusts `X-Forwarded-*` only from `FORWARDED_ALLOW_IPS` (the proxy, `127.0.0.1`). |
| Worker | `sharakat-worker.service` (Celery, `source_sync,maintenance,notifications`) | Runs the daily `pg_dump` backup, so it needs `postgresql-client-16`. |
| Scheduler | `sharakat-beat.service` (Celery Beat) | Exactly one per environment. |
| Migrations | `sharakat-migrate.service` (one-shot `alembic upgrade head`) | API, worker and Beat require it, so a failed migration stops the rollout. |
| PostgreSQL 16 | Managed service or a dedicated host | Private network only. |
| Redis 7 | Managed service or a dedicated host | Private network only, with authentication (and TLS where available). |

`sharakat.target` starts and stops the platform as a whole.

## Server layout

```
/opt/sharakat/releases/<version>/   one directory per release (git tag or archive), read-only
/opt/sharakat/current -> releases/<version>   symlink switched on release and rollback
/opt/sharakat/venv/                 Python 3.12 virtual environment (rebuilt when requirements.txt changes)
/etc/sharakat/platform.env          secrets and settings: root:sharakat, mode 0640, written by the secret manager
/var/lib/sharakat/                  BACKUP_DIR, ATTACHMENT_DIR and run/ (Beat schedule), owned by sharakat
```

## First-time server setup

1. Install packages: `python3.12 python3.12-venv nginx postgresql-client-16` (Debian/Ubuntu via the PGDG
   repository for the client), plus `certbot` if certificates come from ACME.
2. Create the service account and directories:
   `useradd --system --home /var/lib/sharakat sharakat` and
   `install -d -o sharakat -g sharakat /var/lib/sharakat/{backups,attachments,run}`.
3. Write `/etc/sharakat/platform.env` from the secret manager. Variable names are listed in
   [`.env.example`](../../.env.example). Required values:
   * `ENVIRONMENT=production` (or `staging`)
   * PostgreSQL `DATABASE_URL`
   * authenticated `REDIS_URL`
   * `SECRET_KEY`
   * HTTPS `PUBLIC_BASE_URL`
   * exact `CORS_ORIGINS`
   * `FORWARDED_ALLOW_IPS=127.0.0.1`
   * `BACKUP_DIR=/var/lib/sharakat/backups`
   * `ATTACHMENT_DIR=/var/lib/sharakat/attachments`
   * the bootstrap admin
   * SMTP settings

   Protected environments refuse to start with SQLite, without Redis or `SECRET_KEY`, with wildcard CORS or
   trusted proxies, or with a non-HTTPS public URL.
4. Copy `deploy/systemd/*` to `/etc/systemd/system/`, then run `systemctl daemon-reload` and
   `systemctl enable sharakat.target`.
5. Copy `deploy/nginx.conf` to `/etc/nginx/conf.d/sharakat.conf`, set `server_name` and the certificate paths,
   then run `nginx -t && systemctl reload nginx`. Keep certificate private keys out of the repository.
   Certificates come either from a managed load balancer or from automated ACME renewal.

## Release

1. Confirm that staging has been validated with this exact release, and that a recent backup has been verified
   by a restore ([database-restore.md](database-restore.md)).
2. Put the release in `/opt/sharakat/releases/<version>`. Use a tagged git checkout or an archive with a
   recorded SHA-256, never an unpinned branch. If `requirements.txt` changed, run
   `/opt/sharakat/venv/bin/pip install -r requirements.txt`.
3. Switch the symlink: `ln -sfn releases/<version> /opt/sharakat/current`.
4. Run the migration: `systemctl restart sharakat-migrate.service`. Stop the rollout if it fails or reports
   more than one Alembic head (`journalctl -u sharakat-migrate`).
5. Restart the services: `systemctl restart sharakat-api sharakat-worker sharakat-beat`. The worker finishes
   its running jobs first (up to 2 minutes).
6. Smoke check:
   * `/health/live` and `/health/ready` through the HTTPS URL
   * login, dashboard, sources and opportunities
   * CSV and XLSX exports

   Don't trigger every source adapter as a deployment test.
7. Check the worker and Beat heartbeats, queue depth, source schedules and the latest backup manifest. Trigger a
   single controlled source sync only when the release plan approves it.
8. Record the release version and archive SHA-256, the migration revision, the smoke results and the operator in
   the deployment log.

## Rollback

Point `current` back to the previous release, then restart `sharakat-api`, `sharakat-worker` and `sharakat-beat`.
Never downgrade the database automatically. If the new migration isn't backward compatible with the old
release, ship a forward fix instead (see [rollback.md](rollback.md)).

## Operations

* Status: `systemctl status 'sharakat-*'`
* Logs: `journalctl -u sharakat-api -u sharakat-worker -u sharakat-beat -f`
* Read-only stack check (staging): `sudo -u sharakat env $(cat /etc/sharakat/platform.env | xargs) /opt/sharakat/venv/bin/python scripts/verify_production_stack.py`,
  run from `/opt/sharakat/current` (see [staging.md](staging.md)).

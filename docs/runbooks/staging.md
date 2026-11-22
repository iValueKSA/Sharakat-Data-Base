# Staging environment

Staging uses the same native topology as production ([deployment.md](deployment.md)) on its own server or VM.
Its `/etc/sharakat/platform.env` comes from the secret manager with `ENVIRONMENT=staging`. Staging must have its
own PostgreSQL database, Redis, bootstrap account, SMTP destination, HTTPS public URL, CORS origin and backup
storage. Set `STAGING_DATABASE_NAME` to the staging database name. Never point staging at production data.
Staging may run controlled public-source reads, but disable automatic sync until the source review and the
operator's live-read window are agreed. Run the migrations and the deployment smoke test before enabling
schedules.

`FORWARDED_ALLOW_IPS` must name the proxy exactly (`127.0.0.1` when nginx runs on the same host). Never trust
forwarded headers from a wildcard.

Once `sharakat-migrate` has succeeded and the API, worker and Beat units are active, run the read-only smoke
check from the release directory:

```bash
cd /opt/sharakat/current
sudo -u sharakat env $(cat /etc/sharakat/platform.env | xargs) /opt/sharakat/venv/bin/python scripts/verify_production_stack.py
```

The script refuses to run unless `ENVIRONMENT=staging`, `DATABASE_URL` is PostgreSQL, and its database name
matches `STAGING_DATABASE_NAME` exactly. It checks:

* the Alembic revision
* PostgreSQL connectivity
* Redis connectivity and a recent Beat tick
* that a Celery worker responds
* the API live and readiness endpoints

It doesn't dispatch source jobs, write database rows or perform destructive operations. Save its output in the
production Phase 1 evidence directory.

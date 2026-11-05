# Staging environment

Use `docker-compose.yml` with a separate `.env.staging` supplied by the secret manager and a distinct Compose project (`alahsa-staging`). Compose prefixes named volumes with the project name, so staging PostgreSQL, Redis, and backup volumes stay separate from production. Set independent DB/Redis URLs, `STAGING_DATABASE_NAME`, bootstrap account, SMTP destination, HTTPS public URL, and CORS origin. Keep staging credentials and backup artifacts separate; never point staging at production data. Staging may run controlled public-source reads, but disable automatic sync until source review and the operator's live-read window are agreed. Run migrations and the deployment smoke test before enabling schedules.

The frontend proxy is pinned to `172.31.240.10` on the default `172.31.240.0/24` Compose network. If `COMPOSE_NETWORK_SUBNET` changes, update `FORWARDED_ALLOW_IPS` to the frontend proxy address. Never use wildcard forwarded-header trust.

After migrations and all containers are healthy, run the read-only smoke check from the API container:

```powershell
docker compose exec api python scripts/verify_production_stack.py
```

The script refuses to run unless `ENVIRONMENT=staging`, `DATABASE_URL` is PostgreSQL, and its database name exactly matches `STAGING_DATABASE_NAME`. It checks the Alembic revision, PostgreSQL connectivity, Redis connectivity and recent Beat tick, Celery worker response, and API live/readiness endpoints. It does not dispatch source jobs, write database rows, or perform destructive operations. Save its output in the production Phase 1 evidence directory.

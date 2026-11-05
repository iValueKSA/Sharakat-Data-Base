# ADR: Production deployment boundary

**Status:** Accepted reference deployment

Run the API, frontend, source workers, scheduler, PostgreSQL, and Redis as separate logical services. Alembic runs in a one-shot migration service and blocks API/worker rollout on failure. The API image is multi-stage and non-root. PostgreSQL and Redis have no published host ports. The frontend binds only to loopback for an external HTTPS reverse proxy or cloud load balancer to terminate TLS. Production startup rejects SQLite, missing Redis/secret configuration, wildcard CORS, and a non-HTTPS public base URL. Production secrets are injected at runtime and excluded from Docker build context.

Compose is a reference deployment. Production TLS certificates, managed PostgreSQL/Redis availability, secret manager integration, encrypted off-host backups, and infrastructure monitoring are operator/platform responsibilities.

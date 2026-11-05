# Deployment

1. Confirm staging validation and a recent verified backup.
2. Pull/build the immutable API and frontend image tags; do not deploy `latest`.
3. Inject staging or production secrets from the platform secret manager. Confirm the environment points to the matching PostgreSQL and Redis instances and that `PUBLIC_BASE_URL` is HTTPS. Set `FORWARDED_ALLOW_IPS` to the exact reverse proxy IPs/CIDRs that connect to the API; wildcard trust is rejected in protected environments. The Compose reference pins its frontend proxy at `172.31.240.10` and uses that as the API trust default.
   Configure TLS at the public reverse proxy/load balancer. Use its managed certificate service (for example, the cloud provider's certificate manager) or automated ACME renewal with Nginx/Traefik; redirect HTTP to HTTPS there and keep certificate private keys outside this repository and container images. The public edge must overwrite incoming `X-Forwarded-Proto` and `X-Forwarded-For`; forward them only from trusted proxy addresses.
4. Run the migration job (`alembic upgrade head`). Stop rollout if it fails or Alembic reports multiple heads.
5. Deploy API, worker, scheduler (one Beat leader), and frontend. Keep PostgreSQL/Redis private; expose only the HTTPS reverse proxy.
6. Check `/health/live`, `/health/ready`, login, dashboard, sources, opportunities, and CSV/XLSX exports. Do not trigger all source adapters as a deployment smoke test.
7. Check worker and scheduler heartbeats, queue depth, source schedules, and latest backup manifest. Trigger a single controlled source sync only when approved by the release plan.
8. Record image digests, migration revision, smoke results, and operator in the deployment log.

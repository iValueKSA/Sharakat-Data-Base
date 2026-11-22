# ADR: Production deployment boundary

**Status:** Accepted. Revised 2026-11-22: native systemd services replace the Docker Compose reference.

Run the API, source workers, scheduler, PostgreSQL and Redis as separate logical services:

* **Application services:** native systemd units (`deploy/systemd`) under a dedicated non-root `sharakat` account,
  with `NoNewPrivileges`, `ProtectSystem=strict` and write access only to `/var/lib/sharakat`.
* **Migrations:** Alembic runs in a one-shot migration unit that the API, worker and Beat units require, so a failed
  migration blocks the rollout.
* **Network exposure:** PostgreSQL and Redis are reachable only on the private network. The API binds to loopback
  behind an nginx HTTPS edge (`deploy/nginx.conf`), which is the only public listener.
* **Startup guards:** production startup rejects SQLite, missing Redis or secret configuration, wildcard CORS or
  trusted proxies, and a non-HTTPS public base URL.
* **Secrets:** injected at runtime through `/etc/sharakat/platform.env` from the secret manager, never committed.

Releases are immutable directories under `/opt/sharakat/releases`. `current` is a symlink, so a rollback is a symlink
switch plus a service restart.

The operator or platform is responsible for production TLS certificates, managed PostgreSQL and Redis availability,
secret manager integration, encrypted off-host backups and infrastructure monitoring.

Docker is no longer part of any supported path. Workstation installs use the native runtime; see
[cross-platform-assessment.md](cross-platform-assessment.md).

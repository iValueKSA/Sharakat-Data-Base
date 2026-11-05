# Local Windows platform

## Architecture

The end-user workstation runs the same PostgreSQL, Redis, FastAPI, static frontend, Celery worker, and Celery Beat services as the production reference through Docker Desktop Compose. All services and storage stay on the local computer. Only the frontend is published, bound to `127.0.0.1:8080`; PostgreSQL and Redis have no host-published ports. The local Compose project is `alahsa-local`.

PostgreSQL and Redis use persistent named volumes (`alahsa-local_postgres_data`, `alahsa-local_redis_data`). Backups are bind-mounted to the project `backups/` directory. `Stop Platform.bat` runs `docker compose stop`; it never removes containers or volumes. Docker Desktop's VM disk holds named volumes, so include Docker Desktop's disk data in the workstation backup plan.

## Start and stop

First time only, double-click `Install Platform Requirements.bat`. It writes a non-secret host diagnostic to `logs/local-requirements-diagnostic.log`, verifies the official Docker Desktop WinGet package, prepares WSL2 (without installing a Linux distribution), and asks for a normal Windows restart when required. After restart, run the installer again; it resumes Docker installation and launches `Start Platform.bat`. Every normal day, double-click `Start Platform.bat`. The PowerShell launcher checks required files, Docker CLI/Compose and Engine, protects local settings, checks port 8080, builds/starts the stack, checks the migration, API/database/Redis/worker health, Beat startup, and frontend response, then opens `http://localhost:8080`. A second click is idempotent and opens the existing healthy platform. Startup details go to `logs/startup.log`.

Double-click `Stop Platform.bat` for a clean Compose stop. It preserves PostgreSQL/Redis volumes and backups. `Restart Platform.bat`, `Platform Status.bat`, and `Create Desktop Shortcuts.bat` are convenience launchers. The shortcut launcher creates Start, Stop, and Status shortcuts on the Windows desktop.

If Docker Desktop is installed but stopped, Start attempts to launch it and waits up to ten minutes for Docker Engine. The first-run installer waits up to fifteen minutes during the initial Docker Engine boot and stops if first-run Docker prompts need attention. No source sync is manually triggered by Start. Celery Beat retains the configured source schedules. Nginx resolves the API service through Docker's embedded DNS so an Engine restart that changes the API container IP does not leave a stale upstream address.

## First run and existing data

The launcher generates `.env.local` with local-only PostgreSQL, Redis, and session credentials; the file is ignored by Git and its Windows ACL is restricted to the current user. A protected copy is kept in `%LOCALAPPDATA%\Sharakat Data Base` so losing the project copy does not silently rotate credentials for an existing database volume. If both copies are missing while the Postgres volume exists, startup stops and does not generate replacements.

The one-shot `local-bootstrap` service runs after Alembic. It requires the target database name to be exactly `sharakat_local`, requires an empty target without an import marker, makes a verified SQLite safety backup under `backups/`, then transactionally imports the source tables from `data/al-ahsa-live.db`, preserving IDs, relationships, JSON, timestamps, job state, and row counts. It advances PostgreSQL sequences and creates a local Admin only if the imported database has no users. Existing users are preserved. The source SQLite file is mounted read-only and never modified. A persisted marker prevents repeat imports. If a partial or non-empty unmarked Postgres database is found, setup refuses to merge or overwrite it.

The current SQLite source was inspected read-only and backed up before setup. Its verified safety copy is [al-ahsa-live.db](../../backups/pre-local-postgres-20261013-101428/al-ahsa-live.db), 55,570,432 bytes, SHA-256 `3e4e99782c8fe7b5368b9dc0c6afdb9e75ab48ebd785a69e4678d7f5953b0364`. It contains 230 opportunities, 2,831 source rows, 7,603 source observations, 10 sources, 200 sync jobs, and no existing users. The manifest records counts and SQLite `integrity_check=ok`.

For the first Admin login, the launcher creates `Local Admin Credentials.txt` with a random local-only password. Keep this file private. Login remains enabled; the launcher does not bypass authentication.

## Ports and local exposure

The frontend URL is `http://localhost:8080`. Compose binds it to loopback only. PostgreSQL and Redis remain on the Compose network and are not available on public or LAN interfaces. The API is reachable through the frontend proxy only. Compose reserves frontend proxy address `172.31.240.10` so the API trusts forwarded headers only from that address; the external network is not used for application infrastructure.

## Troubleshooting

- **Requirements restart pending:** Restart Windows, then double-click `Install Platform Requirements.bat`; the `.local-setup/reboot-required` marker documents the pending step.
- **Docker Desktop missing:** Double-click `Install Platform Requirements.bat` once prerequisites are ready.
- **Engine starting:** Leave the launcher open while it waits; it times out after ten minutes and records the failure in `logs/startup.log`.
- **Port 8080 occupied:** Close the unrelated application using that port, then retry.
- **Saved DB volume but missing `.env.local`:** the launcher restores its per-user settings copy. If both are gone, it refuses to start rather than changing stored database credentials.
- **Migration/bootstrap/service error:** See `logs/startup.log` and `docker compose` service logs using the [Platform Status launcher](../../Platform%20Status.bat). Do not delete volumes to troubleshoot.
- **Admin password lost:** use the existing Admin user-management/reset process; do not recreate or reset the database. The credential file is generated only for the initial account and may no longer match after a password change.

## Backups

The original SQLite file has a verified safety copy before migration. The importer makes another SQLite safety copy immediately before import. PostgreSQL scheduled backups are written to the persistent project `backups/` directory. To verify restore behavior, use a separate local database named `sharakat_local_restore_test`; never restore over `sharakat_local`.

# Live Deployment Target Identification — 2026-11-02

**Scope:** Read-only identification. No service was restarted, no image was built, no backup or migration was run, and no database, flag, or business row was changed. This report is the only requested workspace artifact.

## Decision

**`LIVE_DEPLOYMENT_TARGET = CONFIRMED_ALAHSA_LOCAL`**

The primary user-facing platform is the single-computer Windows installation at `http://localhost:8080`. The launcher, active listener, API, database, persistent volumes, project history, and previously deployed lifecycle images all identify the active target as Compose project `alahsa-local`. No separate external operational deployment was found in configured project evidence.

Use **LIVE USER ENVIRONMENT** or **LIVE LOCAL ENVIRONMENT** for this target going forward. Historical “production” acceptance language in this project refers to the single-computer local installation; the hosted production architecture is a design/reference, not a configured deployment.

## One-click startup trace

`Start Platform.bat` changes to the project directory and runs `scripts/start-platform.ps1`. That script dot-sources `scripts/local-platform.ps1`; no `.installation-state.json` is present, so it selects the standard local mode. The helper sets:

| Setting | Resolved value/evidence |
|---|---|
| Compose project | `alahsa-local` (`-p alahsa-local`) |
| Compose files | `docker-compose.yml`, `docker-compose.local.yml` |
| Environment file | `.env.local` |
| `ENVIRONMENT` | `local_user` |
| Base URL | `http://localhost:8080` |
| Database | `sharakat_local` at the Compose `db` service |
| Docker profile | None selected |
| Startup services | Compose default set, including migrate, API, worker, scheduler/Beat, frontend, PostgreSQL, Redis, and local bootstrap |

The current `.env.local` values for environment, database name, and base URL match those resolved values. Credentials and secret values were not read into this report. Normal Start uses `docker compose up -d --build`, and the standard migration service is configured for `alembic upgrade head`; a future controlled rollout must account for that behavior.

`Stop Platform.bat` calls Compose `stop`; it does not remove volumes. `Restart Platform.bat` calls Stop then Start. The launcher uses a project-prefixed PostgreSQL volume check to refuse unsafe first-run initialization when a prior database volume exists but private settings are missing.

## Port 8080 trace

Docker reports the only published 8080 listener as:

```text
127.0.0.1:8080 -> alahsa-local-frontend-1:8080
```

The frontend container’s Compose labels identify project `alahsa-local`, service `frontend`, the project working directory `C:\Sharakat Data Base`, and `.env.local`. Its image is `alahsa-local-frontend` (`sha256:837868f5ed26ec6fcac9d199b809dafabc47f4d6f43961a467c2e78b1ccbf9b8`). The Nginx configuration proxies API paths to the Compose API service. The active API container has `ENVIRONMENT=local_user` and `PUBLIC_BASE_URL=http://localhost:8080`, and is healthy. This traces the user URL to the same project, not merely to a similarly named container.

## Database and persistence

The API’s SQLAlchemy connection reports `current_database() = sharakat_local`. Its Compose `db` service is PostgreSQL 16 (`postgres:16-alpine`) in project `alahsa-local`. Docker mount inspection shows:

| Data | Persistent storage |
|---|---|
| PostgreSQL | Named volume `alahsa-local_postgres_data` mounted at `/var/lib/postgresql/data` |
| Redis | Named volume `alahsa-local_redis_data` mounted at `/data`; Redis runs with append-only persistence |
| Backup artifacts | Project bind mount `C:\Sharakat Data Base\backups` to `/backups` for API/worker |
| Bootstrap source | `./data` mounted read-only into local bootstrap |

Both PostgreSQL and Redis volumes have Docker Compose labels for project `alahsa-local`. Stopping/restarting through the one-click scripts does not remove those volumes. **`LIVE_DATABASE_PERSISTENT = TRUE`.**

The actual database revision and counts are:

| Measure | Current value |
|---|---:|
| Alembic | `0023_quant_commercial` |
| Masters | 587 |
| Current, unmerged Masters | 566 |
| SourceOpportunity | 3,180 |
| Furas SourceOpportunity | 436 |
| Source observations | 35,626 |
| Qualification reviews | 0 |
| Location reviews | 26 |
| Audit events | 3,764 |
| System events | 19,888 |
| Sources | 11 |
| Sync jobs | 690 |
| Furas jobs | 163 (152 successful); latest Furas job ID 684 is completed successfully |
| Users | 2 (one admin, one viewer; one currently active) |
| Persisted system settings | 1 |

No user identifiers, credentials, session tokens, or secret values were inspected or reported. The dashboard frontend is serving HTTP 200. The current counts match the latest previously reported live-project counts for Masters, current Masters, SourceOpportunities, Furas rows, observations, and location reviews. Job history has naturally advanced from maximum ID 673 in the earlier snapshot to 690 now; recent Furas job history includes scheduled/retry executions. Existing review/audit/job/observation tables and user-role records confirm persisted operational lineage.

**`LIVE_HISTORY_MATCH = TRUE`** for the established project lineage, based on the matching business counts plus existing source registry, review/audit/observation/job history, dashboard setting, RBAC users, and completed Furas history. This task did not perform a row-by-row comparison against an older database dump.

## Runtime environment role

`local_user` is the deliberate mode selected by the official launcher for the user’s operational local installation. It is persistent and user-facing, with PostgreSQL, Redis, API, worker, Beat, Nginx frontend, source schedules, user/session routes, role-aware Admin/Analyst/Viewer authorization, and stored audit/job data. Beat is running, and the Furas job history contains scheduled activity.

The value is not equivalent to the hardened `production` or `staging` modes in application code. Those two modes activate strict HTTPS, trusted-proxy, externally supplied secret, fail-closed Redis-rate-limit, and other protected startup/security behavior. `local_user` uses HTTP loopback and bypasses those protected-mode requirements; non-protected authorization also retains its local admin-token fallback behavior. It is therefore the live operational user environment, but not an internet-hosted production security boundary.

## Compose and deployment target inventory

| Configuration | Classification | Evidence |
|---|---|---|
| `docker-compose.yml` | `ACTIVE_LIVE` base | Used by the launcher; defines API, worker, Beat, frontend, PostgreSQL, Redis, named volumes, and migration service. Its default Compose name is overridden by explicit `-p alahsa-local`. |
| `docker-compose.local.yml` | `ACTIVE_LIVE` | Used by launcher; sets `ENVIRONMENT=local_user` and local bootstrap/settings. |
| `docker-compose.lifecycle-patch.yml` | `ACTIVE_LIVE` runtime override | Running API/worker/Beat labels include this file; overrides their image tags and disables migrations in this patch deployment path. |
| `docker-compose.lifecycle-patch-rollback.yml` | `UNUSED` rollback definition | Not in the active container labels. |
| `docker-compose.portable.yml` | `UNUSED` on this installation | Launcher would select it only if `.installation-state.json` declared portable mode; that file is absent. |
| Compose files in packaged `transfer/` snapshots | `TEST_ONLY` / transfer artifacts | Separate package copies, not the active project working directory. |
| `nwx-ui-*` and `alahsa-transfer-test-*` Compose projects | `ISOLATED_VALIDATION` | Separate named projects/containers; none owns host port 8080. |
| `alahsa-production-reference` | `UNUSED` local reference name | No containers exist for this Compose project. Local Docker volumes with that prefix remain, but there is no attached running service or remote endpoint evidence. |

There is no `.env.staging`, `docker-compose.staging.yml`, or separate production override in the project root. The staging runbook describes an intended separate project, not an active configured target.

## External deployment search

Read-only inspection found:

- Docker contexts are the local Docker Desktop contexts (`desktop-linux` current and the local default pipe); no remote Docker context is configured.
- `.github/workflows/ci.yml` performs CI validation and image builds; it does not deploy to production.
- Deployment documentation describes cloud/hosted production and staging as target architecture/runbooks, while `docs/validation/production-hardening-phase-1.md` explicitly scopes its acceptance to the single-computer Windows deployment and disclaims internet-hosted production.
- No configured production hostname, SSH deployment target, remote PostgreSQL endpoint, remote registry rollout, or CI/CD deployment job was found.

**`SEPARATE_EXTERNAL_PRODUCTION_FOUND = FALSE`.** The unreferenced local `alahsa-production-reference_*` volumes do not establish a separate deployment.

## Lifecycle image lineage

The active containers’ image IDs match the recorded lifecycle patch manifest:

| Service | Tag | Running image ID |
|---|---|---|
| API | `alahsa-api:lifecycle-fix-20261101` | `sha256:ae6560e822c65a3df27dc72576411d712f72816bca726b7e42b979012d933301` |
| Worker | `alahsa-worker:lifecycle-fix-20261101` | `sha256:f87b2d1d7a974f9255304e3b40f3bf0c314417606de54e5dc6e5c521a936a097` |
| Beat | `alahsa-beat:lifecycle-fix-20261101` | `sha256:87db93f8068221f75ea52fd26c29a5e957026bacb35e889a55a1d70b304613b0` |

**`LIFECYCLE_PATCH_PRESENT_IN_LIVE_ENVIRONMENT = TRUE`.** The national checkpoint runtime remains undeployed. No source sync was started by this identification task.

## Required output

```text
LIVE_DEPLOYMENT_TARGET = CONFIRMED_ALAHSA_LOCAL
START_PLATFORM_COMPOSE_PROJECT = alahsa-local
START_PLATFORM_ENVIRONMENT = local_user
START_PLATFORM_URL = http://localhost:8080
START_PLATFORM_DATABASE = sharakat_local
PORT_8080_COMPOSE_PROJECT = alahsa-local
PORT_8080_ENVIRONMENT = local_user
LIVE_DATABASE_ALEMBIC_HEAD = 0023_quant_commercial
LIVE_DATABASE_MASTER_COUNT = 587
LIVE_DATABASE_CURRENT_MASTERS = 566
LIVE_DATABASE_SOURCEOPPORTUNITIES = 3180
LIVE_HISTORY_MATCH = TRUE
LIVE_DATABASE_PERSISTENT = TRUE
LIFECYCLE_PATCH_PRESENT_IN_LIVE_ENVIRONMENT = TRUE
SEPARATE_EXTERNAL_PRODUCTION_FOUND = FALSE
EXTERNAL_PRODUCTION_EVIDENCE = NONE FOUND; HOSTED/CLOUD REFERENCES ARE DESIGN/RUNBOOK ONLY
SAFE_TARGET_FOR_NEXT_FURAS_ROLLOUT = TRUE (IDENTITY ONLY; FUTURE ROLLOUT IS A SEPARATE TASK)
CHANGES_MADE = 0 (LIVE/DATABASE/RUNTIME; THIS REQUESTED REPORT WAS CREATED)
MANUAL_SOURCE_SYNCS = 0
PRODUCTION/LIVE_SCHEMA_CHANGES = 0
```

**Identification ends here.** The LIVE USER ENVIRONMENT is the confirmed target for the separately requested Furas rollout. No backup, migration, deployment, flag change, or sync was performed as part of this identification task.

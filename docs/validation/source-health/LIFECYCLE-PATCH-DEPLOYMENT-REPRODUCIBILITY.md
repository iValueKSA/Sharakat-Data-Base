# Lifecycle Patch Deployment Reproducibility

## Baseline origin

The baseline was recovered from the actual running containers without modifying them. Their complete `/app` trees are stored under `tmp/production-baseline-0023/{api,worker,beat}`. [`production-baseline-manifest.json`](../../../tmp/production-baseline-0023/production-baseline-manifest.json) records container/image IDs, creation timestamps, commands, feature flags, Alembic revision, and SHA-256 hashes for all Python runtime and migration files. Hashes recomputed inside the running containers matched the recovered source.

| Service | Baseline container image ID | Container created |
| --- | --- | --- |
| API | `sha256:3b7e3af3ca632dbd7b5c21df3cd310a05c184784a3206226f5cd00269adfaefc` | 2026-10-28 09:31:04 UTC |
| Worker | `sha256:2eb708e1e2c24b2cc998e2bc86852498fe750abbdb3150b64801d0a5d42978df` | 2026-10-27 07:42:15 UTC |
| Beat | `sha256:4a91e3700eab0ef4168a3e24c1d5e19a9c8cb2f57c41c5c9ceaf41eca4c71f9d` | 2026-10-26 09:07:11 UTC |

The live Alembic head was `0023_quant_commercial`; the nationwide UI, map, and Furas enumeration flags were false. The extracted migration trees contain versions only through 0023.

## Patch source and boundary

`tmp/lifecycle-production-patch/{api,worker,beat}` are copies of the corresponding recovered baseline trees. Only the following app files differ from their matching baseline image:

- API: `app/sync_lifecycle.py`, `app/tasks.py`, `app/service.py`, and `app/main.py`.
- Worker: `app/sync_lifecycle.py`, `app/tasks.py`, and `app/service.py`.
- Beat: `app/sync_lifecycle.py` and `app/tasks.py`.

All changed hunks are lifecycle-only. The API change in `main.py` is the queued-job cancel guard. The workspace versions of nationwide adapters, geographic models/routes/filters/dashboard, related DQ and Celery changes, new geographic modules, and migrations 0024/0025 were excluded. A byte-level comparison confirmed every other app and migration file matches the recovered service baseline.

The exact runtime and test file hashes, excluded changes, image IDs, and validation evidence are in [`LIFECYCLE-PRODUCTION-PATCH-MANIFEST-20261101.json`](LIFECYCLE-PRODUCTION-PATCH-MANIFEST-20261101.json).

## Build reproduction

Local baseline tags point to the original immutable image IDs:

```powershell
docker tag sha256:3b7e3af3ca632dbd7b5c21df3cd310a05c184784a3206226f5cd00269adfaefc alahsa-local-api:baseline-lifecycle-20261101
docker tag sha256:2eb708e1e2c24b2cc998e2bc86852498fe750abbdb3150b64801d0a5d42978df alahsa-local-worker:baseline-lifecycle-20261101
docker tag sha256:4a91e3700eab0ef4168a3e24c1d5e19a9c8cb2f57c41c5c9ceaf41eca4c71f9d alahsa-local-beat:baseline-lifecycle-20261101

Set-Location 'C:\Sharakat Data Base\tmp\lifecycle-production-patch'
docker build --pull=false -f Dockerfile.api -t alahsa-api:lifecycle-fix-20261101 .
docker build --pull=false -f Dockerfile.worker -t alahsa-worker:lifecycle-fix-20261101 .
docker build --pull=false -f Dockerfile.beat -t alahsa-beat:lifecycle-fix-20261101 .
```

Built image digests:

```text
alahsa-api:lifecycle-fix-20261101     sha256:ae6560e822c65a3df27dc72576411d712f72816bca726b7e42b979012d933301
alahsa-worker:lifecycle-fix-20261101  sha256:f87b2d1d7a974f9255304e3b40f3bf0c314417606de54e5dc6e5c521a936a097
alahsa-beat:lifecycle-fix-20261101    sha256:87db93f8068221f75ea52fd26c29a5e957026bacb35e889a55a1d70b304613b0
```

The build Dockerfiles copy only the listed lifecycle files onto each base image. The built image hashes for all Python app and migration files were compared with the patch source tree and passed.

## Validation environment

An isolated PostgreSQL database received a schema-only dump of the live 0023 database; no business rows were copied. Its columns, constraints, and index fingerprints matched production. The test database Alembic version was set to `0023_quant_commercial`; the patch image reported that same current revision. API, worker, and Beat ran with separate isolated Redis endpoints. Beat did not share a queue with the worker. No source job ran.

An earlier isolated attempt to upgrade a brand-new empty PostgreSQL database to 0023 stopped at baseline migration 0022 with `DuplicateColumn: canonical_status`. That isolated container was not production. Validation then switched to the schema-only copy described above. The production deployment path has no migration command and did not run Alembic.

The tested artifact passed 83 applicable lifecycle, DQ, ingestion, and API-cancel tests; API and worker/Beat startup smokes passed. The unchanged DQ consistency gate passed a coherent synthetic terminal history and failed an intentionally inconsistent one at `FAIL` severity. See the patch manifest for detailed results.

## Migration-safe deployment override

[`docker-compose.lifecycle-patch.yml`](../../../docker-compose.lifecycle-patch.yml) pins the API, worker, and scheduler to the unique patch image tags, clears their build contexts, and replaces the migration service with a no-op. The deployment command also uses `--no-build --no-deps`, so it neither builds from the mixed workspace nor starts the migration service or dependencies:

```powershell
docker compose --project-directory 'C:\Sharakat Data Base' --project-name alahsa-local --env-file .env.local `
  -f docker-compose.yml -f docker-compose.local.yml -f docker-compose.lifecycle-patch.yml `
  up -d --no-build --no-deps api worker scheduler
```

The override was parsed and checked: image tags resolve to the patch tags, build entries are cleared, and the migration command contains no Alembic invocation. PostgreSQL, Redis, frontend, and volumes are not targets.

The deployment command was executed on 2026-11-01 at 15:51:59 UTC. Only API, worker, and scheduler containers were recreated. Post-deployment checks passed; production remained on Alembic 0023. No natural post-fix sync job occurred during the observation window.

## Rollback

[`docker-compose.lifecycle-patch-rollback.yml`](../../../docker-compose.lifecycle-patch-rollback.yml) pins affected services to the baseline tags that point to the original image IDs and keeps migrations disabled. Its configuration was validated; rollback was not executed.

```powershell
docker compose --project-directory 'C:\Sharakat Data Base' --project-name alahsa-local --env-file .env.local `
  -f docker-compose.yml -f docker-compose.local.yml -f docker-compose.lifecycle-patch-rollback.yml `
  up -d --no-build --no-deps api worker scheduler
```

This replaces only API, worker, and scheduler containers. It does not alter the database, volumes, job rows, or business data.

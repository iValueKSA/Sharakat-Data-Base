# Furas Job Lifecycle Race Fix — Production Deployment

## Result

The lifecycle-only patch was isolated from the nationwide work, tested against a production-schema-matched PostgreSQL 0023 database, built as three uniquely tagged images, and deployed to API, worker, and Beat. API readiness and worker/Beat health passed after replacement. PostgreSQL, Redis, frontend, and persistent volumes were not restarted.

No post-deployment source job had occurred at the final read-only check, so live lifecycle and Furas verification remain pending natural jobs. No job was triggered to obtain evidence.

## Baseline and patch boundary

The source baseline came from the actual running API, worker, and Beat containers. Each complete `/app` tree was copied without modifying the container. SHA-256 hashes for all Python files under `app` and `migrations` were recomputed inside each running container and matched the recovered files. The baseline and hashes are recorded in [`production-baseline-manifest.json`](../../../tmp/production-baseline-0023/production-baseline-manifest.json).

There was no Git commit available. The exact tested/deployed content is pinned by baseline image IDs, changed-file SHA-256 hashes, and the final image digests in [`LIFECYCLE-PRODUCTION-PATCH-MANIFEST-20261101.json`](LIFECYCLE-PRODUCTION-PATCH-MANIFEST-20261101.json).

| Service image | Lifecycle files deployed |
| --- | --- |
| API | `app/sync_lifecycle.py`, `app/tasks.py`, `app/service.py`, `app/main.py` queued-cancel guard |
| Worker | `app/sync_lifecycle.py`, `app/tasks.py`, `app/service.py` |
| Beat | `app/sync_lifecycle.py`, `app/tasks.py` |

Every changed runtime hunk was reviewed as lifecycle-specific. All other files matched their service baseline byte-for-byte. Nationwide geography modules, routes, filters, dashboard/map changes, current-workspace adapter/model/DQ/Celery changes, and migrations 0024/0025 were excluded. The deployed API OpenAPI document contains no national or geographic-reference paths.

```text
PRODUCTION_BASELINE_SOURCE_RECOVERED = TRUE
BASELINE_HASH_VERIFICATION = PASSED
LIFECYCLE_PATCH_BOUNDARY = VERIFIED
AMBIGUOUS_RUNTIME_HUNKS = 0
NATIONWIDE_RUNTIME_CHANGES_IN_PATCH = 0
```

## Artifact build and validation

The candidate images were built from the recovered service image IDs using copy-only Dockerfiles. Every file under `app`, `migrations`, and `scripts`, plus `alembic.ini`, matched its staged patch tree inside each built image.

| Image | Deployed digest |
| --- | --- |
| `alahsa-api:lifecycle-fix-20261101` | `sha256:ae6560e822c65a3df27dc72576411d712f72816bca726b7e42b979012d933301` |
| `alahsa-worker:lifecycle-fix-20261101` | `sha256:f87b2d1d7a974f9255304e3b40f3bf0c314417606de54e5dc6e5c521a936a097` |
| `alahsa-beat:lifecycle-fix-20261101` | `sha256:87db93f8068221f75ea52fd26c29a5e957026bacb35e889a55a1d70b304613b0` |

The artifact passed **83 applicable tests**: 81 lifecycle/DQ/ingestion tests (24 transition/reliability and 57 DQ/ingestion), plus 2 API cancellation tests. The DQ consistency gate passed for a coherent synthetic terminal job and failed an intentionally inconsistent job with severity `FAIL`. The scheduler/worker overlap cases passed. The earlier workspace regression result was 633 passed; it was not rerun because the deployable patch artifact was validated in its lifecycle-specific scope.

The isolated PostgreSQL test database received a schema-only copy of the live database; no production business rows were copied. Columns, constraints, and index fingerprints matched production. The patch ran with Alembic at `0023_quant_commercial`, and the patch images contain migrations only through 0023. Test environment feature flags were false. API smoke returned `/health = 200`, `/health/ready = 200`; Celery worker `inspect ping` returned `pong`; Beat started successfully. No sync task ran in the isolated environment.

```text
PATCH_IMAGES_BUILT = TRUE
PATCH_STARTUP_CAN_APPLY_0024_OR_0025 = FALSE
PATCH_RUNS_ON_0023 = TRUE
DEPLOYABLE_ARTIFACT_TESTED = TRUE
UNAPPROVED_NATIONAL_RUNTIME_CODE_DEPLOYED = FALSE
```

## Deployment

At 2026-11-01 15:51:59 UTC, the validated Compose override replaced only API, worker, and scheduler/Beat. The command used `--no-build --no-deps`; the override cleared build contexts and made the migration service a no-op. No migration command ran.

```text
API container       0290c823dfafb77cddaef45540c808aac4188d41b591717b832d8eee48625c9b
Worker container    4b5ee7f2119bebb8109671bce1b5a655a395851bf256280d15eb268d108a2df6
Beat container      ab5bbb0ada9290223396761875c9180141606d85b203b377708fe6a0cffee3a6
```

The migration-safe deployment override is [`docker-compose.lifecycle-patch.yml`](../../../docker-compose.lifecycle-patch.yml). The rollback override is [`docker-compose.lifecycle-patch-rollback.yml`](../../../docker-compose.lifecycle-patch-rollback.yml). Both configurations were validated. Rollback was not executed; the baseline image tags still point to the exact previous image IDs.

## Post-deployment checks

- API: running, Docker healthy; `GET /health` 200; `GET /health/ready` 200.
- Worker: running; Celery inspection returned `pong`.
- Beat: running with the expected Celery Beat command.
- PostgreSQL and Redis: running and Docker healthy.
- Frontend: running; it was not restarted.
- Logs: zero matches for import errors, tracebacks, configuration errors, migration errors, or lifecycle exceptions in API, worker, and Beat logs.
- Alembic head: `0023_quant_commercial`.
- Production schema fingerprint after deployment matched its pre-deployment fingerprint: columns `e186f0e941ac5973015eccfa2b471810`, constraints `2dfb86dca578ef9b66ac47fe691263fc`, indexes `1574145b02535bb0c11582c60ab8e650`.
- National UI, map, dashboard, and Furas enumeration flags: all false.
- Active sync jobs: 0 before replacement and 0 after.
- No new sync job appeared after ID 671 during the observation window.
- Historical rows 644, 651, 652, 666, 668, 669, 670, and 671 retained their previously observed statuses. None was edited or retried by this task.
- The API lifespan ran the existing `seed_sources` startup routine. A read-only comparison found zero source-default mismatches afterward. Source, Master Opportunity, SourceOpportunity, qualification-review, and location-review counts matched the pre-deployment snapshot; no source sync, backfill, promotion, or DQ-history rewrite occurred.

There was no new post-deployment DQ result because no natural source job ran. Existing historical DQ evidence was not modified, and the DQ gate code/severity was unchanged.

## Required status

```text
LIFECYCLE_FIX_PRODUCTION_DEPLOYMENT = PASSED
DEPLOYMENT_SCOPE_ISOLATED = TRUE
PRODUCTION_ALEMBIC_HEAD = 0023_quant_commercial
MIGRATION_0024_PRODUCTION_APPLIED = FALSE
MIGRATION_0025_PRODUCTION_APPLIED = FALSE
API_HEALTH = PASSED
WORKER_HEALTH = PASSED
BEAT_HEALTH = PASSED
REDIS_HEALTH = PASSED
POSTGRES_HEALTH = PASSED
NATIONAL_UI_ENABLED = FALSE
NATIONAL_MAP_ENABLED = FALSE
FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE
MANUAL_SOURCE_SYNCS = 0
BACKFILLS = 0
INVEST_SAUDI_PROMOTIONS = 0
HISTORICAL_JOB_ROWS_CHANGED = 0
PRODUCTION_SCHEMA_CHANGES = 0
LIVE_LIFECYCLE_VERIFICATION = PENDING_NATURAL_JOB
FURAS_LIVE_VERIFICATION = PENDING_NATURAL_FURAS_JOB
NEW_POST_FIX_LIFECYCLE_RACE_OBSERVED = FALSE
ROLLBACK_TO_PREVIOUS_IMAGES_READY = TRUE
TEMP_DIAGNOSTIC_SCRIPTS = REMOVED
```

The read-only natural-job observation at 2026-11-01 16:00:32 UTC found no post-cutoff source jobs. See [FURAS-JOB-LIFECYCLE-RACE-LIVE-VERIFICATION-20261101.md](FURAS-JOB-LIFECYCLE-RACE-LIVE-VERIFICATION-20261101.md) for the cutoff query, natural scheduler/worker log evidence, and historical DQ interpretation.

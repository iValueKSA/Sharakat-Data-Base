# KFU Worker-only deployment and corrected Furas test acceptance

**Execution date:** 2026-11-16  
**Decision:** KFU_WORKER_DEPLOYMENT=DEPLOYED_AND_VERIFIED

## Test disposition and corrected tests

The two previously failing assertions expected synthetic, unrecognized national Furas IDs to be inserted as SourceOpportunity rows. That conflicts with the accepted fail-closed quarantine contract. Only the two test expectations in tests/test_nationwide_expansion_safety.py were corrected; production Furas code and the approved candidate image were not changed. The revised assertions verify durable checkpoints, replay progress, zero unauthorized SourceOpportunity/Master/SourceObservation writes, and preservation of the pre-existing local row.

Corrected tests ran against disposable PostgreSQL 16, isolated from production:

- Original production Worker image: Test A passed 3/3; Test B passed 3/3 (6/6 total).
- Approved KFU candidate image: Test A passed 3/3; Test B passed 3/3 (6/6 total).
- Original test failure evidence remains preserved in this directory. Corrected traces: [baseline](baseline-corrected-pg-results.log), [candidate](candidate-corrected-pg-results.log).
- Candidate broader regression suite: 183 passed, 4 skipped. KFU-specific tests: 36 passed. The focused corrected PostgreSQL runs emitted only the existing Starlette/httpx TestClient deprecation warning.

## Release artifact and deployment

- Candidate image digest: sha256:b8191dd075d7fe4cc7ec2542cfefe5bdc46f9a634dfe5c5cf338ed4b4d46c08a
- Candidate KFU parser: 2026.11.16-kfu-2; prior parser: 2026.10.12-kfu-1.
- Candidate manifest and adapter hash were verified before deployment; only KfuAdapter differed from the production Worker implementation. Furas quarantine, shared sync/task code, source identity rules and Celery registration were unchanged.
- The approved candidate image was deployed by recreating only the Compose worker service with --no-deps --no-build --pull never. No build occurred.
- Worker before: container 92891a9762a4ec22cf4be80e3ef7aa95efc8e65218df6ecbe46cb3fbf76a3d45, baseline image sha256:d6d5f9d0dbf912a35250b4865337cae89f3f34ece8bc2727ebc3c8d71df341aa.
- Worker after: container 457ed5db52b876362b66c7295434039a4bc258c144bee335d535003de6b06454, candidate digest above.
- Verified rollback tag: alahsa-local-worker:rollback-kfu-before-20261116T114603Z, resolving to the original baseline digest. Rollback was not executed.
- Worker service configuration, queue names/concurrency and /backups mount were preserved.

## Post-deployment checks

- Celery worker ping: PASS; registered task set intact.
- Active and ETA-scheduled task inspections: empty; expected three queues retained. No manual source collection was started.
- Worker startup logs: no ERROR, traceback or CRITICAL entries in the inspected window.
- API readiness: HTTP 200. Frontend: HTTP 200.
- Other production container IDs unchanged: API d8446bcb65f5a86326b791e03f9b8988868f795ac73fc60d3f69a0336a5c5b4c; frontend 45e1b736f1135c3738e12499d58fd6e5de04b47ccdbbae41d3f50a28c9316553; scheduler 6542eb3a9cc467531ccef8c930daf5c0b81c867705704baadbaabda56eede5df; PostgreSQL 5b5141b2ec4df59a265df1e70113f01cbbe6814c6ee912c0c9917fd36cc2e7c2; Redis 3eb77d941330ba95bf965942caab0b78ab9081f34f60d2f58824efd28688953b.
- Migration head remains 0027_opportunity_documents_mvp; document rows remain 0. Masters remain 6,680 and SourceOpportunity rows 9,470.
- KFU source links remain 2774 -> Master 225 and 2928 -> Master 326; no source identities or Master identities changed.
- Furas national enumeration, Furas removals and RCU scheduled sync remain disabled. No migration, API/frontend deployment, source sync, historical metadata correction or business-data mutation was performed.
- KFU remained enabled on its 720-minute schedule, healthy, with the prior successful run timestamp unchanged and zero active KFU jobs. The deployment window preceded its next due time. Routine scheduler activity skipped national Furas and the RCU bootstrap gate; no KFU collection was triggered.

## Final status

FURAS_TEST_DISPOSITION_ACCEPTED=YES  
BASELINE_CORRECTED_TEST_RESULTS=6/6 PASS  
CANDIDATE_CORRECTED_TEST_RESULTS=6/6 PASS  
ROLLBACK_READY=YES; ROLLBACK_EXECUTED=NO  
SOURCE_IDENTITY_INTEGRITY=PASS  
DOCUMENT_TABLE_ROWS=0  
HISTORICAL_CORRECTION_STATUS=NOT AUTHORIZED; UNCHANGED  
UNAUTHORIZED_BUSINESS_DATA_MUTATIONS=0  
PRODUCTION_DEPLOYMENT_STATUS=DEPLOYED_AND_VERIFIED  
REMAINING_BLOCKERS=NONE FOR THIS WORKER-ONLY RELEASE


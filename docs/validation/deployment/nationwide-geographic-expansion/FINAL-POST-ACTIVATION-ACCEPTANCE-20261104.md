# National Go-Live — Post-Activation Final Acceptance

**Date:** 2026-11-04 (Asia/Amman)  
**Environment:** `alahsa-local` (`http://localhost:8080`)  
**Decision:** `NATIONAL_GO_LIVE = PARTIAL`

## Stop decision

Stage 1 read-only full data-quality evaluation returned one failed gate. The acceptance instructions require stopping when `DQ_FAIL > 0`, so authenticated UI, export, map interaction, and responsive stages were not started in this run.

The failing gate was `CURRENT_MASTER_MAP_PARTITION` (`LOCATION_ELIGIBILITY`): **observed 7,261; expected 6,657; excess 604; sample IDs none**. Its message says exact-mapped, outside-reference, unverified, and missing-coordinate groups must partition the current Master population. The current DQ result was **127 pass, 6 warning, 1 fail** across 134 gates. Full read-only evidence is in [final-dq-read-only.json](evidence/post-activation-20261104/final-dq-read-only.json).

Because the failed gate concerns location eligibility while the national map was enabled, I applied the task’s conditional map-only rollback. The API was recreated with `NATIONAL_MAP_ENABLED=false`; live catalog now reports UI/dashboard enabled, map disabled, and geography reference readiness `READY`. The national UI flag remains enabled because this failure did not demonstrate a UI-specific defect. No browser or computer-use action was made after the DQ failure.

## Stage 1 results

| Check | Result |
|---|---|
| API readiness | HTTP 200, `ready`; database, Redis, and worker checks `ok` |
| PostgreSQL | accepting connections; container healthy |
| Redis | `PONG`; container healthy |
| Worker | Celery ping `pong`; container running |
| Scheduler / Beat | scheduler container running; Beat process not independently verified (`ps` unavailable in container) |
| Live flags after rollback | UI `true`; dashboard `true`; map `false` |
| Geography reference readiness | `READY`; UI enabled; map disabled |
| Current Masters | 6,657 |
| RCU Masters | 6 |
| RCU canonical status incorrect | 0 |
| RCU canonical deadline incorrect | 0 |
| RCU open status reviews | 6 |
| RCU open deadline reviews | 6 |
| Full DQ | 127 pass / 6 warning / 1 fail |
| Regression | 690 passed / 1 skipped / 0 failed (guarded code validation) |

The DQ snapshot contained 6,678 total Master rows, 6,657 current Masters, 21 merged Masters, 9,468 source opportunities, 51,791 observations, and 21 open reviews. The six warning gates were `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY`, `OPEN_REVIEW_BACKLOG`, `HISTORICAL_REVIEW_AUDIT_INCOMPLETE`, `SOURCE_LAST_SUCCESS_TOO_OLD`, `SYNC_RUNTIME_ANOMALY`, and `UNKNOWN_AREA_STORED_AS_ZERO`.

## Acceptance fields

```text
NATIONAL_GO_LIVE = PARTIAL
NATIONAL_UI_ENABLED = TRUE
NATIONAL_MAP_ENABLED = FALSE (rolled back after location-eligibility DQ failure)
NATIONAL_UI_ACCEPTANCE = NOT_COMPLETED
NATIONAL_MAP_ACCEPTANCE = FAILED (CURRENT_MASTER_MAP_PARTITION DQ gate)
AUTHENTICATED_BROWSER = NOT_COMPLETED
API_UI_EXPORT_PARITY = NOT_COMPLETED
MAP_DRILLDOWN = NOT_COMPLETED
RESPONSIVE_VIEWPORTS = NOT_COMPLETED
FINAL_DQ_FAIL = 1
FINAL_REGRESSION_FAILED = 0
UNEXPECTED_JS_ERRORS = NOT_VALIDATED
UNEXPECTED_HTTP_5XX = NOT_VALIDATED
MANUAL_SOURCE_SYNCS = 0
BUSINESS_DATA_CHANGES = 0
```

No source sync was initiated and no business data was changed during this post-activation acceptance run. Browser monitoring, screenshots, and interaction evidence were not collected because the DQ stop condition fired before Stage 2.

## Required follow-up

Investigate why `CURRENT_MASTER_MAP_PARTITION` counts 7,261 members for a 6,657-Master population (604 excess), correct the demonstrated counting/partition defect with a focused regression, then rerun the full DQ gate before re-enabling the map or starting browser acceptance. The map flag remains off pending that gate.

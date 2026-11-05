# Automated Data Quality Gates and Regression Monitoring — Final Review

## Acceptance

`AUTOMATED_DATA_QUALITY_GATES_REGRESSION_MONITORING_DEEP_REVIEW = COMPLETE`

## Focused reconciliation follow-up — 2026-10-21

The later focused closeout is complete and supersedes the earlier warning interpretation below for current acceptance. It reconciles the 308-to-577 review count, classifies the exact 2,537-row legacy source-absence population, and verifies generic Invest Saudi links are hidden from the original-opportunity action. Its live read-only result is 48 gates: 46 PASS, 2 explained WARNING, 0 FAIL. See [the reconciliation report](RECONCILIATION-2026-10-21.md) and [machine-readable results](reconciliation-2026-10-21.json). The earlier snapshot and artifacts below remain the evidence for the original deep review.

This work adds automated read-only data-quality checks and regression monitoring to the existing platform. It does not redo the earlier semantic reviews, alter business data, or start source synchronization. The application services were rebuilt with the implementation and remain running.

## Existing monitoring inventory

The platform already had service liveness/readiness and metrics, admin system/source-health status, validation reports and coverage metadata, sync state/alerts, review queue generation and governance, Celery retry/recovery/locking, regression suites, and the source-link audit index. It did not have an orchestrated DQ gate catalog, bounded cadence runs, severity/alerting model, or DQ-specific admin status view. The new DQ layer complements those checks; it does not conflate service availability with data quality or source coverage.

## Gate model and execution

The evaluator in `app/data_quality.py` is read-only by default. Optional persistence appends a compact `DATA_QUALITY_RUN_COMPLETED` `SystemEvent`; retention is scoped only to those DQ events (365 days, at most 5,000). It does not update Master, SourceOpportunity, observations, review cases, or source mappings. Failures create deduplicated admin alerts; warnings remain visible with evidence and sample IDs. No automatic business-data correction is performed.

- 48 catalogued gates: 31 fail-severity, 12 warning-severity, and 5 informational-severity.
- Fast post-successful-sync cadence: 18 gates.
- Daily full cadence: 27 gates.
- Weekly Furas-completion telemetry: 3 gates; it reads the last successful complete scan and does not enumerate a source or sweep links.
- Daily plus weekly periodic scope: 30 gates.
- A post-sync DQ exception cannot rewrite the completed sync outcome.

Coverage is classified separately from technical health. Pending absence is not treated as confirmed removal; only complete authoritative scans advance absence confirmation. Partial scans cannot trigger unsafe removal conclusions.

## Fixed live snapshot

The final live weekly run completed at `2026-10-21T10:40:19.681079+03:00`, run ID `6c650b8e66f04d50aa571ca1c0262542`, via the admin DQ endpoint against the local PostgreSQL-backed application. The evaluator read business data and recorded only its DQ run audit event.

| Snapshot item | Observed |
|---|---:|
| Master rows / current Masters / merged Masters | 546 / 525 / 21 |
| SourceOpportunity rows | 3,137 |
| Linked SourceOpportunity rows to current Masters | 525 |
| Raw observations | 12,401 |
| Configured / enabled sources | 10 / 10 |
| Open review queue items | 577 |
| Standardization engine | 21 |
| Runtime Alembic head / expected head | `0023_quant_commercial` / `0023_quant_commercial` |
| DQ gates | 48 evaluated; 45 PASS, 3 WARNING, 0 FAIL |

### Current warnings

1. `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION`: 782 Invest Saudi records use the official listing page rather than a per-opportunity detail page. This is surfaced as a warning; the evaluator does not call each link or declare them unavailable.
2. `OPEN_REVIEW_BACKLOG`: 577 valid unresolved review items remain queued. No case was resolved or suppressed by this work.
3. `SOURCE_ABSENCE_CLASSIFICATION`: 27 known historical, 2,537 pending confirmation, and 0 unexplained absences. Pending items are not promoted to confirmed removal.

All other gates passed, including current Master/source linkage, official-reference identity split, source URLs and Furas route, date/deadline provenance, review entity/link integrity and reconciliation, scan/removal safety, source coverage declarations, observation integrity, runtime/version parity, taxonomy invariants, API/dashboard/list/CSV/XLSX count parity, and map partitioning. The live API, dashboard, data dashboard, CSV, and XLSX each returned 525 current Masters.

## Regression and UI verification

`tests/test_data_quality.py` contains 12 chaos cases and 3 positive/safety cases. The full project suite ran after the final implementation against a disposable SQLite database (`DATABASE_URL` overridden to an ephemeral `/tmp` file), not the live PostgreSQL database: **204 passed, 0 failed** (16 existing nonblocking warnings). The suite includes the requested read-only-default and DQ-only-retention safety checks.

The admin status panel displays latest run time, pass/warning/fail totals, and expandable gate details in Arabic RTL. Browser verification covered 1920×1080, 1440×900, 1366×768, 768×900, and 390×844: RTL remained active, document/body width matched each viewport (no horizontal overflow), no page errors were observed, and the latest 45/3/0 DQ status available during capture loaded. The test used a stub admin identity only; DQ content was fetched from the running application. The 1920×1080 capture is included with the validation artifacts.

## Data and sync boundary

No business data, source mappings, review status, or source observations were changed by the DQ implementation or run. No schema migration was added. `system-status` reports 400 sync jobs both in the initial and final review snapshots; no manual source sync was started. Scheduled source synchronization was not invoked as part of this work. The only live write was the DQ audit event (`SystemEvent` ID 498).

## Artifacts

- `dq-gate-catalog.json` — gate keys, domains, invariants, severity, cadence, actions, and live status.
- `dq-live-run.json` — fixed live run, counts, evidence, and warning samples.
- `dq-severity-model.json` — PASS/WARNING/FAIL actions and severity counts.
- `dq-cadence-model.json` — fast, daily, and weekly gate sets.
- `dq-failure-samples.json` — representative warning/failure examples.
- `dq-regression-tests.json` — chaos/safety cases and full suite result.
- `playwright-results.json` and `admin-dq-status-1920x1080.png` — responsive admin panel verification and screenshot.

## Final assertions

```ini
AUTOMATED_DATA_QUALITY_GATES_REGRESSION_MONITORING_DEEP_REVIEW = COMPLETE
TOTAL_DQ_GATES = 48
DQ_FAIL_SEVERITY_GATES = 31
DQ_WARNING_SEVERITY_GATES = 12
DQ_INFO_GATES = 5
POST_SYNC_FAST_GATES = 18
PERIODIC_DAILY_GATES = 27
PERIODIC_WEEKLY_GATES = 3
LIVE_DQ_PASSING_GATES = 45
LIVE_DQ_WARNING_GATES = 3
LIVE_DQ_FAILING_GATES = 0
CURRENT_MASTERS_WITH_ZERO_SOURCES = 0
UNEXPLAINED_SOURCE_ABSENCES = 0
DQ_REVIEW_RECONCILIATION = PASSED
DQ_API_DASHBOARD_EXPORT_RECONCILIATION = PASSED
SERVICE_HEALTH_SEPARATE_FROM_DQ_HEALTH = TRUE
TECHNICAL_HEALTH_SEPARATE_FROM_COVERAGE = TRUE
DQ_AUTO_FIXES_BUSINESS_DATA = FALSE
BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
FULL_REGRESSION_SUITE = 204 passed / 0 failed
BROWSER_DQ_STATUS_VERIFICATION = PASSED
```


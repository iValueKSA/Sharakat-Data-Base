# Pre-RCU Platform Health Remediation — 2026-11-03

## Outcome

**PLATFORM_BASELINE_REMEDIATION = COMPLETE**

The full DQ run returned **128 PASS, 6 WARNING, 0 FAIL** across 134 gates. The full regression suite returned **673 passed, 1 skipped, 0 failed**. No Furas sync was started and no Master was created. One RCJY retry ran independently through the existing scheduled stale-job recovery path; its effects are recorded below.

## Read-only baseline

Captured before repairs with `evaluate_data_quality(scope="full", persist=False)`, so the DQ capture itself made no database writes.

| Measure | Initial | Final |
|---|---:|---:|
| TOTAL_MASTERS | 6,647 | 6,647 |
| CURRENT_MASTERS | 6,626 | 6,626 |
| SOURCEOPPORTUNITIES | 9,293 | 9,293 |
| RCJY_SOURCE_ROWS | 3 | 3 |
| RCJY_MASTERS | 3 | 3 |
| FURAS_ROWS | 6,546 | 6,546 |
| REVIEWS | 10 | 0 |
| JOBS | 720 | 721 |
| ACTIVE_JOBS | 3 | 0 |
| ALEMBIC_HEAD | `0025_source_geographic_coverage` | `0025_source_geographic_coverage` |

Initial read-only full DQ run `338d4dfff9f24757803d55b4bbf763cb`: **118 PASS, 6 WARNING, 10 FAIL**. Final read-only full DQ run `0f5b5cbd8da74cb7a0abba6c4b9c1eb2`: **128 PASS, 6 WARNING, 0 FAIL**. No DQ thresholds or severity definitions were weakened; the fixes correct review actionability and explicitly inactive scheduling scope.

## All 10 initial DQ failures

| # | DQ gate / initial observation | Entity / ID / source; current → expected | Root cause, prior state, safe repair and disposition |
|---:|---|---|---|
| 1 | `STALE_OPEN_REVIEW_CONDITION` — 10 | `OpportunityConflict` 1303–1312 / Invest Saudi; `OPEN` → `RESOLVED_CANONICAL` | **A — actual review-state defect, pre-existing.** Invest Saudi removal was confirmed after 3 successful checks while a newer linked Furas row supported each Master’s canonical `متاحة` status. Safe under the existing field-specific rule; repaired with audit, without changing Master values. |
| 2 | `STALE_OPEN_REVIEWS` — 10 | Same conflicts 1303–1312 / Invest Saudi; same state change | **A — same stale review-state defect, pre-existing.** Duplicate reporting of the same records. The same evidence-backed audited repair applies; no additional writes. |
| 3 | `OPEN_ACTIONABLE_REVIEW_BACKLOG` — 10 | Same 10 conflicts; all open reviews were counted as actionable | **F — DQ semantics defect.** Gate counted all open reviews, despite only stale cases being safely resolvable. Fixed to count affirmative field-specific stale-resolution evidence. Valid human-required open reviews remain warning-only. |
| 4 | `POST_SYNC_ACTIONABLE_REVIEW_BACKLOG` — 10 | Same 10 conflicts; all open reviews were counted as actionable | **F — same pre-existing actionability semantics defect.** Fixed by the same evidence-based count; no separate record repair. |
| 5 | `POST_SYNC_REVIEW_WITHOUT_AUTONOMOUS_RESOLUTION` — 10 | Same 10 conflicts; all open reviews were treated as autonomous | **F — same pre-existing actionability semantics defect.** Fixed by the same evidence-based count; no separate record repair. |
| 6 | `AUTONOMOUS_REVIEW_LEFT_UNRESOLVED` — 10 | Same 10 conflicts; all open reviews were counted as autonomous | **F — pre-existing gate semantics defect.** Gate now checks only the subset proven safely resolvable; `OPEN_REVIEW_BACKLOG` still surfaces human work. |
| 7 | `MULTIPLE_RUNNING_JOBS_SAME_SOURCE` — 1 duplicate group | `SyncJob` 745, 746, 747 / RCJY source 12; `RUNNING` with no live owner → terminal `ABANDONED` | **C — current lifecycle defect, pre-existing.** Stale heartbeats, no finish timestamps, no active/reserved/scheduled task, and no Redis source lock. Scheduled stale-job recovery safely used the atomic transition helper and recorded evidence. |
| 8 | `DB_RUNNING_WITHOUT_LIVE_TASK` — 3 | Same RCJY jobs 745–747; database says `RUNNING`, task absent → terminal `ABANDONED` | **C — same lifecycle defect**, independently reported by reconciliation. Repaired by the same recovery operation; no historical terminal outcome was edited. |
| 9 | `UNEXPLAINED_MISSED_SCHEDULE_EXECUTIONS` — 22 windows | Furas source 1; enumeration feature flag is false → `DISABLED_BY_FEATURE_FLAG` | **D — pre-existing DQ scope error.** Scheduler logs explicitly returned `skipped_national_mode_disabled: ["furas"]`. DQ now recognizes the inactive schedule. Safe fix was scope classification; no Furas job was started. |
| 10 | `SOURCE_LAST_SUCCESS_TOO_OLD` — gate FAIL; Furas caused the failure (Modon/NHC were warnings) | Furas source 1; Job 694 complete at 2026-11-02 07:58:42 UTC, then intentionally disabled → stale-age warning outside active SLA | **D — pre-existing DQ scope error.** National Furas enumeration is deliberately disabled. DQ keeps stale age visible as WARNING and excludes it from the inactive schedule’s SLA; freshness thresholds are unchanged and no sync was run. | 

**Category totals by failing gate:** A actual review-state defect: 2; C scheduler/job lifecycle: 2; D intentionally inactive Furas scope: 2; F DQ review semantics: 4; B historical/audit inconsistency: 0; E valid human-only open review incorrectly auto-resolved: 0; other: 0. The six review gates refer to one set of 10 reviews, not six different review sets.

## Repairs and non-repairs

### Review records

All 10 conflicts (IDs 1303–1312) independently passed `stale_conflict_evidence` under `SOURCE_SCOPED_REMOVAL_WITH_LIVE_LINKED_SUPPORT_V1`. Each changed from `OPEN` to `RESOLVED_CANONICAL` through the locked, evidence-rechecking helper. Audit events 16172–16181 are `REVIEW_STALE_CONDITION_RESOLVED`. Evidence retains the removed Invest Saudi source state and the newer Furas support; source history is preserved. No Master values were modified. No other review was closed.

DQ review-governance logic now counts only proven safe autonomous stale-condition resolutions as actionable. Regression coverage confirms a legitimate open human review remains visible as a warning and does not fail DQ or get auto-resolved.

### RCJY lifecycle and natural scheduler activity

Before this task’s repairs, worker inspection showed no active, reserved, or scheduled Celery sync task for jobs 745–747 and Redis had no RCJY source lock. At 2026-11-03 08:24 UTC the existing five-minute `recover_stale_jobs` task recorded all three as `ABANDONED`, including `finished_at`, heartbeat/task evidence, and `SYNC_JOB_STALE_RECOVERED` events. The same automatic recovery path then retried RCJY as job 750. This was **natural scheduler/recovery activity, not a task-requested or manual source sync**.

Job 750 completed successfully: raw count 3, rejected count 3 as nationally listed/non-local-eligible, `new_count=0`, `update_count=0`, `removed_records_count=0`. It recalculated source standardization fields (33) from the current public records; it created or changed no Master. Provider IDs 265, 266, and 269 remain source rows 9323, 9322, and 9321 linked to Masters 6675, 6676, and 6677. RCJY remains 3 source rows / 3 Masters / 0 duplicate provider keys. No RCJY row was deleted or duplicated.

Furas enumeration was not enabled or invoked. Job 694 remains the successful accepted baseline; historical failed Job 692 remains unchanged and immutable. Furas rows remain 6,546, removals remain disabled, and the 53 deferred rows were not acted on. The lifecycle implementation still uses atomic compare-and-set transitions and forbids terminal-state regression; lifecycle and transition regression tests passed.

### Code corrections

- `/api/data-dashboard` now chooses its timeline date expression from the active request session bind (`db.get_bind().dialect.name`). PostgreSQL still uses `to_char`; SQLite unit sessions use the existing `strftime` branch.
- DQ schedule-window evidence now accepts sources disabled by an explicit feature flag and reports Furas as `DISABLED_BY_FEATURE_FLAG` while `FURAS_NATIONAL_ENUMERATION_ENABLED=false`.
- DQ freshness retains the disabled Furas stale-age evidence as a warning and does not count it against an inactive schedule. No freshness threshold was changed.
- DQ actionable/autonomous review gates no longer classify every human-required open review as an autonomous DQ failure.

No RCU, Ta’adeen, NCP Investors Portal, or new source adapter was integrated.

## Initial SQLite regression failures

Both failures reproduced individually before the fix and were **database-agnostic unit tests**, not PostgreSQL integration tests. Each fixture creates an in-memory SQLite database (`StaticPool`) and patches `main.SessionLocal`; production remains PostgreSQL 16.

| Test | Expected behavior | Failure evidence |
|---|---|---|
| `tests/test_nationwide_expansion_safety.py::test_geographic_filter_and_selectors_work_while_national_ui_flag_stays_off` | Geographic API and dashboard return the same single matching Master; exports remain available | SQLite `OperationalError: no such function: to_char`; SQL: `SELECT to_char(opportunities.first_seen_at, ?) ... GROUP BY to_char(...) ORDER BY to_char(...)`; parameter `YYYY-MM`. |
| `tests/test_reversible_merge.py::test_admin_merge_and_undo_restores_master_and_child_ownership` | Merge and undo leave one current Master and dashboard KPI total 1 | Same SQLite `OperationalError`; same timeline SQL expression. |

The bug was selecting the dialect from the module-global PostgreSQL engine instead of the actual request session. The fix preserves PostgreSQL SQL and runs both tests on their intended SQLite unit backend.

## Final verification

- Full regression: **673 passed, 1 skipped, 0 failed**, 651.62 seconds. The existing skip is `test_postgres_prevents_concurrent_owners_of_same_resume_scope`, documented with `skipif` reason “requires isolated PostgreSQL advisory locks”; `FURAS_CHECKPOINT_TEST_DATABASE_URL` is not configured. It is not skipped to conceal a failure.
- Final full DQ (read-only): **128 pass, 6 warning, 0 fail**, 134 gates evaluated.
- Remaining warnings are: generic source pages (712 rows, 3 exposed as opportunity actions); 120 legacy pre-versioned review audit records; stale source freshness for Furas (feature-gated off), Modon, and NHC; 6 historical runtime anomalies; 15 absence classifications (9 pending confirmation, 6 non-qualified national rows); and 17 unknown areas stored as zero. No historical actor, resolution time, or job outcome was fabricated.
- API `/api/health`: HTTP 200. `/health/ready`: HTTP 200 (`database=ok`, `redis=ok`, `worker=ok`). PostgreSQL and Redis containers report healthy. Celery worker ping returned `pong`. Beat is healthy: Redis `scheduler:last_tick` was current and scheduler logs showed the minute dispatcher; there are no active DB jobs.
- RCJY source filter returns 3. Geographic API filters return: All regions 6,626; Eastern Region 975; Riyadh 800; Makkah 319; Al-Madinah 452; Yanbu Governorate 71. The RCJY-only Al-Madinah/Yanbu intersection returns all 3 RCJY Masters. Their source geography remains Yanbu, parent Al-Madinah.
- MANUAL_SOURCE_SYNCS=0. Natural RCJY recovery job 750 is separately documented above. NEW_MASTERS_CREATED=0. NEW_SOURCE_ADAPTERS=0.

## Final status fields

```text
PLATFORM_BASELINE_REMEDIATION = COMPLETE
INITIAL_DQ_FAIL = 10
REVIEW_STATE_FAILURES = 6 DQ gates / 10 affected review records
FURAS_STATE_FAILURES = 2
SCHEDULER_JOB_STATE_FAILURES = 2 DQ gates / 3 affected jobs
OTHER_DQ_FAILURES = 0
DQ_REPAIRS_APPLIED = 10 audited review transitions + DQ scope/semantics corrections
HISTORICAL_RECORDS_INCORRECTLY_REWRITTEN = 0
FINAL_DQ_PASS = 128
FINAL_DQ_WARNING = 6
FINAL_DQ_FAIL = 0
INITIAL_REGRESSION_FAILURES = 2
POSTGRES_TO_CHAR_TEST_ROOT_CAUSE = Global PostgreSQL engine dialect selected despite SQLite-bound test request sessions
TEST_FIX_APPROACH = Select dialect from active SQLAlchemy session bind; preserve PostgreSQL to_char and SQLite strftime
FINAL_REGRESSION_PASSED = 673
FINAL_REGRESSION_SKIPPED = 1 (isolated PostgreSQL advisory-lock database not configured)
FINAL_REGRESSION_FAILED = 0
LIFECYCLE_FIX_PRESERVED = TRUE
RCJY_SOURCE_ROWS = 3
RCJY_MASTER_COUNT = 3
RCJY_FILTER = PASSED
RCJY_GEOGRAPHY = PASSED
API_HEALTH = 200
API_READINESS = 200
WORKER = HEALTHY
BEAT = HEALTHY
MANUAL_SOURCE_SYNCS = 0
NEW_MASTERS_CREATED = 0
NEW_SOURCE_ADAPTERS = 0
```

**RCU integration was not started.**

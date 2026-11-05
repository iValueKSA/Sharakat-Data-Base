# Source freshness and staleness governance review

**Review result: NOT_COMPLETE.** The source-aware freshness policy, DQ gate, admin display, tests, and evidence bundle are implemented. Closeout is withheld because recent scheduled-job gaps remain unexplained and a natural scheduled sync surfaced an unrelated DQ failure. No manual source sync was run, and no business data was changed by this review.

## Live state

At the final read-only snapshot on 2026-10-21 13:08 UTC, 10 sources were configured and all 10 enabled. Freshness states were: 5 `FRESH`, 2 `AGING`, 2 `STALE`, 1 `LIMITED_SOURCE_OK`, 0 `STATIC_OK`, 0 `MANUAL_REVIEW_DUE`, and 0 `UNKNOWN`.

| Source | Type | Health / coverage | Freshness basis and limits | Current result |
|---|---|---|---|---|
| Furas | A. Dynamic structured API | HEALTHY / COMPLETE_PUBLIC_SOURCE | Complete scan; 120m warning, 360m fail | FRESH |
| Al-Ahsa Opportunities | B. Dynamic web listing | HEALTHY / COMPLETE_PUBLIC_SOURCE | Complete scan; 120m warning, 360m fail | FRESH |
| AHDA | B. Dynamic web listing | HEALTHY / COMPLETE_FOR_DEFINED_SCOPE | Complete scan; 1,440m warning, 4,320m fail | FRESH |
| Invest Saudi | A. Dynamic structured API | HEALTHY / COMPLETE_PUBLIC_SOURCE | Complete scan; 720m warning, 2,880m fail | FRESH |
| KFU | C. Periodic document source | HEALTHY / COMPLETE_FOR_DEFINED_SCOPE | Complete announcement/document scan; 4,320m warning, 20,160m fail | FRESH |
| MODON | F. Limited public coverage | WARNING / PUBLIC_COVERAGE_LIMITED | Successful public-scope verification; 10,080m warning, 43,200m fail | STALE; warning is valid |
| NCP | E. Event-driven source | WARNING / COMPLETE_FOR_DEFINED_SCOPE | Complete public news-archive scan; 1,440m warning, 4,320m fail | AGING; warning is valid |
| NHC | F. Limited public coverage | WARNING / PUBLIC_COVERAGE_LIMITED | Successful public-route scope verification; 10,080m warning, 43,200m fail | STALE; warning is valid |
| PIF | F. Limited public coverage | HEALTHY / PUBLIC_COVERAGE_LIMITED | Successful public-route verification; 10,080m warning, 43,200m fail | LIMITED_SOURCE_OK |
| MWAN | B. Dynamic web listing | WARNING / COMPLETE_FOR_DEFINED_SCOPE | Complete itemized scan; 2,880m warning, 20,160m fail | AGING; warning is valid |

Technical health, source coverage, and freshness remain separate. A successful complete no-change scan resets age; last content change is an informational observation and is never the sole freshness signal. MODON/NHC/PIF limited public scope is not treated as complete opportunity inventory. Their scope verification is bounded and can become overdue.

## Four original freshness warnings

- **MODON — ADAPTER_FAILURE.** Public catalog/product/news and GIS/reference surfaces do not provide a complete current itemized Al-Ahsa opportunity inventory. Its last successful scope verification was 2026-10-12; the 2026-10-21 scheduled attempt failed TLS. Sixteen consecutive unsuccessful scheduled outcomes are recorded. Weekly verification keeps this limited source from inheriting the six-hour dynamic-inventory SLA; the seven-day verification SLA has nevertheless elapsed.
- **NCP — TRUE_STALE_SOURCE.** The 83-page public news archive is enumerable within its declared scope; private PPP pipeline data is excluded. The last complete successful scan was 2026-10-20 06:47 UTC. Job 398, scheduled 2026-10-21 06:01 UTC, failed after that scan. Age was about 30 hours against a 24-hour warning and 72-hour fail boundary. A successful no-change scan is sufficient; a content change is not required.
- **NHC — ADAPTER_FAILURE.** Public investment, qualification, and stimulation routes can be monitored, but do not expose the authenticated item-level inventory. The latest successful scope verification was 2026-10-12; scheduled job 397 on 2026-10-21 remained WARNING. Ten consecutive warning-class outcomes are recorded. Weekly verification is overdue; coverage remains limited.
- **MWAN — ADAPTER_FAILURE.** The public listing and linked details support recurring itemized enumeration within the accepted scope. Its last complete scan was 2026-10-12. Scheduled job 409 on 2026-10-21 failed TLS; eight consecutive failed outcomes are recorded. The 48-hour warning has elapsed, but the 14-day critical age limit has not.

All four original warnings remain valid under the source-specific policy. The freshness gate has 4 warning sources and 0 freshness-failing sources. Its output includes source, status, age, limits, attempt, success, complete scan or scope verification, last failure, content-change evidence, and reason.

## Schedule gaps and escalation

The 14-day schedule report counts scheduled SyncJobs only; expected counts are also normalized to each source's first observed scheduled run. Current Beat heartbeat is healthy. The four most recent estimated missed due windows are still unexplained by durable scheduler/worker uptime evidence:

- MODON: 2026-10-20 18:02 and 2026-10-21 00:02 UTC (2 expected six-hour slots without a job before job 396).
- NCP: 2026-10-20 18:47 UTC (1 expected twelve-hour slot without a job before job 398).
- NHC: 2026-10-20 18:47 UTC (1 expected twelve-hour slot without a job before job 397).

The Oct. 15–18 broader gap overlaps the documented Docker Desktop startup on Oct. 18; the four later windows cannot be attributed confidently to that event. The current scheduler tick does not prove its historical uptime. Therefore `UNEXPLAINED_MISSED_SCHEDULE_EXECUTIONS = 4`, and this criterion is not closed.

`app.tasks.recent_unsuccessful_sync_count` treats failed and warning-class runs as consecutive unsuccessful outcomes. One hard failure raises an informational alert, two raise WARNING, and three or more raise HIGH; warning-class runs raise WARNING and escalate to HIGH after three. Age-based DQ failure is separate and only occurs after each policy's critical limit. Focused tests cover escalation and reset after success.

## Natural scheduled syncs during review

No manual source sync was started. Beat naturally completed:

- Job 416, Furas, SUCCESS, 2026-10-21 13:05:05–13:05:21 UTC: 1 new, 0 updated, 401 unchanged, 13 source records transitioned to the confirmed-removed lifecycle status; 402 reported total. Those 13 `SourceOpportunity` records were retained, not physically deleted.
- Job 417, Al-Ahsa Opportunities, SUCCESS, 2026-10-21 13:05:05–13:05:22 UTC: 0 new, 0 updated, 84 unchanged, 0 removed; 84 reported total.

Compared with the pre-review read-only count snapshot, the natural Furas run added 1 Master row, 1 source-opportunity row, and 14 source-observation rows; it also recorded 13 source lifecycle-status transitions for records confirmed absent. Merge-audit rows stayed at 21. The 13 source records and their provenance were retained. These deltas came from the scheduled job, not a review write. The review and read-only DQ evaluation modified 0 business rows.

The live DQ run after those jobs was 60 PASS, 4 WARNING, 1 FAIL across 65 gates. The source-freshness gate itself remained WARNING with the same four source samples and no failing freshness sources. The newly surfaced unrelated failure is `P2_MEDIUM_INFERENCE_WITH_STRONG_CONTRADICTION` for new Master 577, added by Furas job 416: medium-confidence commercial inference rule `MED_TITLE_CAFE_CONCESSION`, confidence 0.852. That classification was left untouched because it is outside this freshness-only review. The other warning gates were not changed.

## Admin and safety verification

The admin source cards expose technical health, coverage, freshness, last attempt, last success, last complete scan or scope verification, next expected check, policy limits, and consecutive failures separately. The main opportunities dashboard was not changed. Playwright verified the sources page at 1920×1080, 1440×900, 1366×768, 768×900, and 390×844: RTL, no horizontal overflow, and all 10 source freshness panels visible to an admin.

The final live DQ evaluation used a PostgreSQL `READ ONLY` transaction and `persist=False`; protected table counts were identical before and after. Full tests ran against a disposable isolated SQLite database with container networking disabled.

## Required artifacts

- [source-freshness-snapshot.json](source-freshness-snapshot.json)
- [source-operational-types.json](source-operational-types.json)
- [source-freshness-policy.json](source-freshness-policy.json)
- [source-freshness-adjudication.json](source-freshness-adjudication.json)
- [source-schedule-gap-analysis.json](source-schedule-gap-analysis.json)
- [source-failure-escalation.json](source-failure-escalation.json)
- [source-freshness-dq-results.json](source-freshness-dq-results.json)
- [source-freshness-tests.json](source-freshness-tests.json)
- [playwright-results.json](playwright-results.json)
- [Admin source freshness screenshot](admin-source-freshness-1920x1080.png)

## Assertions

```text
SOURCE_FRESHNESS_STALENESS_GOVERNANCE_DEEP_REVIEW = NOT_COMPLETE
CONFIGURED_SOURCES = 10
ENABLED_SOURCES = 10
DQ_FRESHNESS_POLICY_SOURCE_AWARE = TRUE
FRESH_SOURCES = 5
AGING_SOURCES = 2
STALE_SOURCES = 2
STATIC_OK_SOURCES = 0
LIMITED_SOURCE_OK_SOURCES = 1
MANUAL_REVIEW_DUE_SOURCES = 0
UNKNOWN_FRESHNESS_SOURCES = 0
UNEXPLAINED_MISSED_SCHEDULE_EXECUTIONS = 4
SUCCESSFUL_NO_CHANGE_SCAN_COUNTS_AS_FRESH = TRUE
FRESHNESS_USES_CONTENT_CHANGE_AS_SOLE_SIGNAL = FALSE
LIMITED_COVERAGE_NOT_AUTOMATICALLY_STALE = TRUE
TECHNICAL_HEALTH_SEPARATE_FROM_FRESHNESS = TRUE
COVERAGE_STATUS_SEPARATE_FROM_FRESHNESS = TRUE
REPEATED_FAILURE_ESCALATION_DEFINED = TRUE
FALSE_SOURCE_FRESHNESS_WARNINGS = 0
TRUE_STALE_SOURCE_FALSE_PASS = 0
FRESHNESS_DQ_MODIFIES_BUSINESS_DATA = FALSE
LIVE_DQ_FRESHNESS_FAILING_SOURCES = 0
LIVE_DQ_FRESHNESS_WARNING_SOURCES = 4
LIVE_DQ_FAILING_GATES = 1
LIVE_DQ_WARNINGS_ALL_EXPLAINED = TRUE
BUSINESS_DATA_ROWS_MODIFIED_BY_REVIEW = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_IDENTITIES_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
MERGE_LINEAGE_PRESERVED = TRUE
FOCUSED_FRESHNESS_TESTS = 19 passed / 0 failed
FULL_REGRESSION_SUITE = 320 passed / 0 failed
BROWSER_FRESHNESS_ADMIN_VERIFICATION = PASSED
```

Closeout remains open pending attribution of the four missed scheduled due windows. The unrelated DQ failure from Master 577 also needs separate handling; it was deliberately left unchanged here.

## Focused final closeout — 2026-10-21

This addendum addresses the four expected source windows and Master 577 only. The full freshness review, prior semantic reviews, and source synchronization were not rerun.

### Missed source windows

The scheduler does not have a separate Beat entry for each source. The common entry is `enqueue-due-sources-every-minute`, which invokes `app.tasks.enqueue_due_sources` every 60 seconds; that dispatcher uses each enabled source's `polling_frequency_minutes` before creating an `app.tasks.sync_source_task` job. A PostgreSQL backup from 2026-10-20 11:48 UTC, before all four windows, records MODON enabled at 360 minutes and NCP/NHC enabled at 720 minutes. The current values match. Historical configuration is **PARTIAL**, because `sources` has no update timestamp, the admin interval-update route does not emit an audit event, and no Git history is present to rule out a transient change after that backup.

| Source | Expected due time (UTC) | Interval | Expected job/task | Evidence and adjudication |
|---|---|---:|---|---|
| MODON | 2026-10-20 18:02:32Z | 360m | Due-source dispatcher → `sync_source_task` | No `SyncJob`, task ID, or worker receipt found. Prior job 386 was terminal six hours before; valid overlap was not present. **I — log retention prevents full proof.** |
| MODON | 2026-10-21 00:02:32Z | 360m | Due-source dispatcher → `sync_source_task` | No `SyncJob`, task ID, or worker receipt found. No source `SyncJob` for any source was queued within three minutes of the window. **I — log retention prevents full proof.** |
| NCP | 2026-10-20 18:47:32Z | 720m | Due-source dispatcher → `sync_source_task` | No `SyncJob`, task ID, or worker receipt found. Prior job 371 had completed over 12 hours earlier; valid overlap was not present. **I — log retention prevents full proof.** |
| NHC | 2026-10-20 18:47:32Z | 720m | Due-source dispatcher → `sync_source_task` | No `SyncJob`, task ID, or worker receipt found. Prior job 370 had completed over 12 hours earlier; valid overlap was not present. **I — log retention prevents full proof.** |

Beat startup evidence exists for earlier deployments, and the current code still defines the one-minute entry. The current Beat container started at 2026-10-21 07:40:02Z, after these windows; Docker events and task-result retention do not provide the previous Beat process's health or dispatch records at the expected times. The source-job table contains no job from any source near those windows, then shows a batch of eight source jobs (391–398) at 2026-10-21 06:00Z. This supports a shared scheduler/dispatcher interruption, but does not prove whether Beat was down, dispatch failed, or a global pause intervened. No overlap suppression or historical inactive schedule is evidenced.

Therefore the four windows are individually classified, but their cause remains unproven: `TRUE_UNEXPLAINED_MISSED_SCHEDULE_EXECUTIONS = 4`. The zero reported by the new live DQ gate is a **current forward-looking** result and does not erase those historical gaps.

### Future detection and live DQ

A focused `UNEXPLAINED_MISSED_SCHEDULE_EXECUTIONS` DQ gate now compares each scheduled source's due time with job creation. It excludes disabled, explicitly static/manual, and not-yet-baselined sources; global schedule pauses; recent active jobs; and Redis source locks/reservations. It runs read-only and returns per-source due time, interval, common task/Beat entry, classification, and valid-overlap count. Ten focused tests and the full isolated suite passed. The API and worker images were updated to activate the gate; PostgreSQL, Redis, and Beat were not restarted.

At the live read-only DQ evaluation on 2026-10-21 13:30Z, the gate was PASS with 0 current missed windows. The unchanged source-freshness gate remains WARNING for MODON, NCP, NHC, and MWAN, with 0 freshness-failing sources. Overall DQ was 61 PASS, 4 WARNING, 1 FAIL across 66 gates. Protected table counts and `SystemEvent` count were identical before and after the non-persistent DQ evaluation.

### Master 577 and Job 416 safety

Master 577 fails `P2_MEDIUM_INFERENCE_WITH_STRONG_CONTRADICTION` in the TAXONOMY domain. Its stored inference has confidence 0.852, rule `MED_TITLE_CAFE_CONCESSION`, explicit title evidence, no negative-evidence list, and no `confidence_margin` (the gate treats a missing margin as below its minimum of 3). The row was created by successful scheduled Job 416, but the failing invariant is medium-confidence taxonomy inference metadata, not freshness or job lifecycle. It is classified **C — unrelated data-quality issue** and remains unchanged.

Job 416 recorded a complete successful six-page scan (402/402 parsed, 100% complete) and 13 source records transitioned to the retained “removed from source” lifecycle state. All 13 source rows still exist with raw payloads; 13 removal observations were recorded. No Master status/cancellation changes were recorded in the job window. The source rows were not physically deleted and no Master was cancelled solely because of these source removals.

## Focused closeout assertions

```text
HISTORICAL_SCHEDULE_CONFIGURATION_CONFIRMED = PARTIAL
MISSED_SCHEDULE_WINDOWS_REVIEWED = 4
BEAT_OUTAGE_WINDOWS_FOUND = 0 (confirmed outages; historical Beat health remains UNKNOWN)
SOURCE_SPECIFIC_MISS_WINDOWS_FOUND = 0 (none proven from retained evidence)
MODON_MISSED_WINDOWS_REVIEWED = 2
NCP_MISSED_WINDOWS_REVIEWED = 1
NHC_MISSED_WINDOWS_REVIEWED = 1
TRUE_BEAT_SCHEDULING_MISSES_CONFIRMED = 0
VALID_OVERLAP_SUPPRESSIONS = 0
HISTORICAL_SCHEDULE_NOT_ACTIVE = 0
TRUE_UNEXPLAINED_MISSED_SCHEDULE_EXECUTIONS = 4
UNEXPLAINED_SCHEDULE_GAPS = 4
FUTURE_MISSED_SCHEDULE_EXECUTIONS_DETECTABLE = TRUE
DQ_UNEXPLAINED_MISSED_SCHEDULE_EXECUTIONS = 0
MASTER_577_DQ_FAIL_CLASSIFICATION = C. UNRELATED_DATA_QUALITY_ISSUE
MASTER_577_CHANGED = FALSE
MASTER_577_DQ_MESSAGE = "" (empty in the stored live DQ snapshot)
JOB_416_SCAN_COMPLETE = TRUE
JOB_416_SUCCESSFUL = TRUE
JOB_416_SOURCE_RECORDS_MARKED_REMOVED = 13
JOB_416_SOURCE_ROWS_PHYSICALLY_DELETED = 0
JOB_416_MASTER_CANCELLED_SOLELY_FROM_SOURCE_REMOVAL = 0
JOB_416_RAW_HISTORY_PRESERVED = TRUE
JOB_416_OBSERVATION_HISTORY_PRESERVED = TRUE
LIVE_DQ_FAILING_GATES = 1
LIVE_DQ_WARNINGS_ALL_EXPLAINED = TRUE
FALSE_SOURCE_FRESHNESS_WARNINGS = 0
TRUE_STALE_SOURCE_FALSE_PASS = 0
LIVE_DQ_FRESHNESS_FAILING_SOURCES = 0
BUSINESS_DATA_ROWS_MODIFIED_BY_CLOSEOUT = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
FOCUSED_TESTS = 10 passed / 0 failed
FULL_REGRESSION_SUITE = 330 passed / 0 failed
SOURCE_FRESHNESS_FINAL_CLOSEOUT = NOT_COMPLETE
```

The final closeout remains incomplete because durable evidence cannot establish the cause of the four historical windows or confirm the exact schedule configuration through each window. The new gate detects future misses; it does not retroactively explain missing execution records.

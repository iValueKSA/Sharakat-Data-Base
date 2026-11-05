# National source scheduling and freshness — 2026-11-05

Captured: `2026-11-05T07:18:16.340336+00:00`. Environment: `alahsa-local` (`local_user`). This is a live-state report, not a migration or source-discovery exercise.

## Decision

**NATIONAL_SOURCE_SCHEDULING = PARTIAL.** Twelve of 14 configured sources are enabled for the automatic scheduler. Furas national enumeration remains disabled pending identity eligibility reconciliation; Waha Development remains disabled because its adapter is catalogue-only. All source-removal reconciliation remains disabled. No manual non-Furas syncs or production source writes were performed for this review.

## Live baseline

- Current Masters: **6657**; merged Masters: **21**; SourceOpportunity rows: **9468**.
- Sources configured / scheduled: **14 / 12**.
- Technical health HEALTHY: **10**; freshness FRESH: **9**; STALE: **3**; limited public coverage: **4**; BLOCKED: **2**.
- Flags: `{"NATIONAL_UI_ENABLED": "true", "NATIONAL_MAP_ENABLED": "true", "NATIONAL_DASHBOARD_ENABLED": "true", "FURAS_NATIONAL_ENUMERATION_ENABLED": "false", "FURAS_NATIONAL_REMOVAL_RECONCILIATION_ENABLED": "false", "RCU_SCHEDULED_SYNC_ENABLED": "true"}`. Unset Furas flags resolve false in the application.
- API liveness and readiness returned HTTP 200; readiness checks reported PostgreSQL, Redis, and worker healthy. Celery Beat and worker responded; active/reserved sync task inspection was empty. No stuck RUNNING/RETRYING/QUEUED job was found.

## Operating matrix

“Fresh” reflects the per-source freshness model. Limited coverage describes the public scope, independently of endpoint technical health. Zero-change successful scans count as fresh.

| Source | Scheduling readiness | Technical health | Freshness | Coverage | Schedule | Last successful run (UTC) | Next scheduled run (UTC) | Source rows | Current Masters | Open reviews |
|---|---|---|---|---|---:|---|---|---:|---:|---:|
| furas | DISABLED_BY_POLICY | WARNING | STALE | COMPLETE_PUBLIC_SOURCE | 60 minutes | 2026-11-02T07:58:42.277301+00:00 |  | 6546 | 6493 | 0 |
| alahsa-opportunities | READY | HEALTHY | FRESH | COMPLETE_PUBLIC_SOURCE | 60 minutes | 2026-11-05T06:24:49.498186+00:00 | 2026-11-05T07:24:49.656297+00:00 | 123 | 123 | 0 |
| ahda | READY | HEALTHY | FRESH | COMPLETE_FOR_DEFINED_SCOPE | 360 minutes | 2026-11-05T06:25:21.037564+00:00 | 2026-11-05T12:25:21.056968+00:00 | 8 | 8 | 0 |
| invest-saudi | READY | HEALTHY | FRESH | COMPLETE_PUBLIC_SOURCE | 360 minutes | 2026-11-05T06:26:02.149159+00:00 | 2026-11-05T12:26:02.166420+00:00 | 2555 | 106 | 0 |
| kfu | READY | HEALTHY | FRESH | COMPLETE_FOR_DEFINED_SCOPE | 720 minutes | 2026-11-05T06:24:38.171362+00:00 | 2026-11-05T18:24:38.723490+00:00 | 6 | 3 | 0 |
| modon | BLOCKED | WARNING | STALE | PUBLIC_COVERAGE_LIMITED | 360 minutes | 2026-10-12T12:26:46.137294+00:00 | 2026-11-05T12:26:03.353918+00:00 | 0 | 0 | 0 |
| ncp | READY | HEALTHY | FRESH | COMPLETE_FOR_DEFINED_SCOPE | 720 minutes | 2026-11-05T06:26:03.768600+00:00 | 2026-11-05T18:26:03.777377+00:00 | 186 | 26 | 0 |
| nhc | BLOCKED | WARNING | STALE | PUBLIC_COVERAGE_LIMITED | 720 minutes | 2026-10-12T12:35:31.483733+00:00 | 2026-11-05T18:24:39.903888+00:00 | 0 | 0 | 0 |
| pif | READY_WITH_KNOWN_LIMITATIONS | HEALTHY | LIMITED_SOURCE_OK | PUBLIC_COVERAGE_LIMITED | 1440 minutes | 2026-11-04T10:08:22.965026+00:00 | 2026-11-05T10:08:23.011062+00:00 | 0 | 0 | 0 |
| mwan | READY | HEALTHY | FRESH | COMPLETE_FOR_DEFINED_SCOPE | 1440 minutes | 2026-11-04T10:10:22.193448+00:00 | 2026-11-05T10:10:22.201806+00:00 | 7 | 0 | 0 |
| waha-development | DISABLED_BY_POLICY | UNKNOWN | UNKNOWN | PUBLIC_COVERAGE_LIMITED | 1440 minutes |  |  | 0 | 0 | 0 |
| rcjy-investment-opportunities | READY | HEALTHY | FRESH | COMPLETE_FOR_DEFINED_SCOPE | 1440 minutes | 2026-11-04T08:24:23.489212+00:00 | 2026-11-05T08:24:23.560561+00:00 | 3 | 3 | 0 |
| rcu-investment-opportunities | READY | HEALTHY | FRESH | COMPLETE_FOR_DEFINED_SCOPE | 1440 minutes | 2026-11-04T09:29:22.978991+00:00 | 2026-11-05T09:29:23.138665+00:00 | 6 | 6 | 12 |
| taadeen-mining-bids | READY | HEALTHY | FRESH | COMPLETE_FOR_DEFINED_SCOPE | 1440 minutes | 2026-11-04T12:33:22.289922+00:00 | 2026-11-05T12:33:22.383130+00:00 | 28 | 0 | 0 |

Full bilingual names, exact URLs, adapter descriptions, last attempt/job IDs/status/durations/errors, review breakdowns, and computed next runs are in `NATIONAL-SOURCE-OPERATING-MATRIX-20261105.csv`.

## Scheduler and failure recovery

Celery Beat emits the due-source dispatch every 60 seconds and stale-job recovery every 300 seconds. Due checks use each source’s stored `last_attempted_sync` and `polling_frequency_minutes`; source-specific `enqueue_source` reservations and per-source locks prevent overlap. Task retries are bounded (`max_retries=4`); worker task time limits are 1,740 seconds soft / 1,800 seconds hard. Recovery fails closed if Celery active/reserved/scheduled inspection is unavailable and records stale-job transitions instead of overwriting historical jobs. Focused scheduler and checkpoint regression tests passed (79 passed, 1 skipped).

Beat’s local schedule state file exists at `/app/celerybeat-schedule`; it is in the scheduler container writable layer rather than a named volume. Static Beat entries are code-configured and reconstruct on startup; the persistent per-source due state and job history are in PostgreSQL, with duplicate protection in Redis. No scheduler configuration changed, so no restart was applied. A live container replacement/restart test was not performed.

## Freshness and source coverage findings

- **Furas:** national public shadow capture succeeded; the persisted live source remains stale from Nov 2 because national enumeration is off. Current exact ID comparison leaves 641 captured IDs unmatched to SourceOpportunity rows; these identities are not yet reconciled against Master eligibility. No activation or pilot is safe until that work is complete.
- **MODON:** 43 consecutive failed scheduled attempts; latest job 792 failed at TLS certificate verification. Last verified public-scope success was Oct 12. Technical attention is required; TLS verification was not weakened.
- **NHC:** 27 consecutive warning/incomplete attempts; latest job 787 returned a parser warning with no current item rows. Last qualifying public-scope success was Oct 12. Technical attention is required.
- **PIF:** technically healthy and within weekly public-surface review SLA, but source coverage is explicitly limited; the authenticated/private portfolio inventory is not included.
- **Waha Development:** deliberately disabled (`enabled=false`), with no opportunity capture adapter; its public site is catalog/reference evidence only.
- **NCP:** remains under the existing `ncp` identity and includes public UUID-keyed Investors Portal evidence. The latest complete English public scope succeeded; Arabic archive pagination reported a known limitation in its metrics.
- Zero new rows on successful jobs do not count as source failure. Missing records in a time-filtered Furas snapshot are not cancellation evidence.

## Data integrity, UI, and verification

Full read-only DQ returned **128 PASS / 6 WARNING / 0 FAIL**, with no failed gates. Full isolated regression returned **695 passed / 1 skipped / 0 failed**. The focused Furas enumeration/checkpoint/idempotency, scheduler recovery, and source freshness suite returned **79 passed / 1 skipped**. The suite includes map/geography and dashboard paths; no production ingestion was performed to test a new-data refresh. `NATIONAL_UI_ENABLED`, `NATIONAL_DASHBOARD_ENABLED`, and `NATIONAL_MAP_ENABLED` remain true. API/readiness, PostgreSQL, Redis, worker, and Beat were operational.

## Furas activation outcome

The public national enumeration dry run captured **6,511** records using 69 requests over an immutable OBJECTID membership list; 6,511 unique provider IDs and complete pagination were verified. It matched **5,870** existing source IDs and found **641** unmatched IDs. There are **2,245** records missing either a region or city label; all 6,511 contain raw date fields whose deadline semantics remain unverified. The identity-only dry run did not evaluate Master eligibility or content-hash changes for the unmatched/new and matched rows, so potential new Masters and source updates are **NOT EVALUATED**. Possible semantic duplicates are also **NOT EVALUATED**; no title-only matching was used.

**Activation gate: NOT PASSED.** `IDENTITY_SAFETY` is unresolved for 641 identities and the live controlled pilot/post-pilot reconciliation have not run. Accordingly no fresh pilot backup/restore was initiated, no pilot job ID exists, and Furas national scheduling stays false. This avoids turning a safe identity-only shadow result into Master promotions or removals.

## Required outputs and final disposition

- Furas shadow detail: `FURAS-NATIONAL-ENUMERATION-DRY-RUN-20261105.json`.
- Conditional activation decision and exact gate: `FURAS-NATIONAL-SCHEDULING-ACCEPTANCE-20261105.md`.
- 14-source operating matrix: `NATIONAL-SOURCE-OPERATING-MATRIX-20261105.csv`.
- Removals: disabled; automatic removals **0**; manual non-Furas syncs **0**; unexplained duplicate Masters **0** observed by the full DQ gate.

Final state: partial acceptance for the existing automatic schedule framework; Furas national activation withheld until governed identity eligibility reconciliation and pilot gates are complete.

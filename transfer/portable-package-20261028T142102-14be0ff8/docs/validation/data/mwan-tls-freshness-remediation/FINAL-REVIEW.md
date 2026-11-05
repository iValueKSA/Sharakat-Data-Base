# MWAN TLS and source freshness blocker remediation

**Result: COMPLETE — PATH_A (`SOURCE_RESTORED`).** The MWAN adapter now validates the official server certificate with strict hostname and certificate checks. The last-success freshness blocker is cleared. No database recreation, schema change, review decision, Master update, merge, or deletion was performed.

## Before remediation

- MWAN (`source_id=10`) was enabled and scheduled every 1,440 minutes, with coverage `COMPLETE_FOR_DEFINED_SCOPE` and technical health `WARNING`.
- Last complete success: `2026-10-12 12:28:00.933181 UTC`.
- Latest failed run: Job 521, scheduled, `2026-10-26 13:10:24 UTC`, 0 records and 0 removals.
- The live DQ snapshot before the fix had 129 gates: 125 PASS, 3 WARNING, and 1 FAIL (`SOURCE_LAST_SUCCESS_TOO_OLD`, including MWAN).

## Proven TLS cause and safe correction

Job 521 failed while OpenSSL was building the server certificate path, before an HTTP response. The current MWAN leaf certificate is valid through 2026-12-11 and its SAN covers `mwan.gov.sa` and `*.mwan.gov.sa`. It is issued by DigiCert Global G2 TLS RSA SHA256 2020 CA1. Both official MWAN hosts sent only the leaf certificate; strict verification returned `unable to get local issuer certificate` (OpenSSL verify code 20). The system trust bundle is present, contains 148 CA certificates including DigiCert Global Root G2, and the container time is correct. The missing issuer chain—not an expired leaf, hostname mismatch, outdated root store, or changed URL—is the proven cause.

The leaf AIA identifies the official DigiCert CA Issuers URL. Its intermediate certificate has the expected subject/issuer, is valid through 2031, and `openssl verify` validates it to the already trusted DigiCert Global Root G2. The implementation pins that intermediate's PEM fingerprint and adds it only to a dedicated MWAN SSL context. `CERT_REQUIRED` and hostname checking stay enabled. No global CA store, non-MWAN context, TLS bypass, or insecure verification setting changed. The public-source routes remained unchanged.

From both updated API and worker containers, the configured listing and investor-card URLs returned HTTP 200 over verified HTTPS with no redirects. The [official MWAN portal](https://mwared.mwan.gov.sa/en) identifies Investment as a center task and lists investment-opportunity services. The successful MWAN-only scan enumerated six itemized investment opportunities over 11/11 pages. None qualified for Al-Ahsa. One newly observed Asir-region project was retained as a source-only record and not promoted to a Master.

## MWAN-only validation and safety

Job 539 was the only manually queued task and targeted MWAN. It completed `SUCCESS` / `COMPLETED`, refreshed last-success to `2026-10-27 07:43:13.591078 UTC`, and set technical health to `HEALTHY`. The scan received, parsed, and uniquely identified 7 records; 11/11 pages succeeded; pagination and public scope were complete.

The scan added one source-only `SourceOpportunity` (Asir project) and six observations. It created/reused/reevaluated/resolved zero reviews, left zero actionable reviews open, and made zero Master additions, updates, cancellations, merges, or removals. `REMOVAL_ON_INCOMPLETE_SCAN=0`; Job 521 itself removed 0 records. Existing focused ingestion coverage verifies that an incomplete collection does not reconcile missing records.

One automatically persisted **fast post-sync** DQ run occurred during the task's terminal-state transition. Its `SYNC_JOB_STATE_CONSISTENCY` finding sampled only Job 539 because the task had written `status=SUCCESS` while `job_state=RUNNING`; the worker then finalized it as `COMPLETED`. This transient evaluation is retained and disclosed in `mwan-validation-sync.json`. A full live read-only DQ run after terminal completion has 0 FAIL, and the gate no longer identifies MWAN as stale.

## Verification

- Focused tests: **26 passed / 0 failed**.
- Full isolated regression: **588 passed / 0 failed** on disposable SQLite with networking disabled.
- Final live full DQ: **129 gates; 125 PASS, 4 WARNING, 0 FAIL**. The four warnings are `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION`, `HISTORICAL_REVIEW_AUDIT_INCOMPLETE`, `SOURCE_LAST_SUCCESS_TOO_OLD` (MODON and NHC warnings only), and `SYNC_RUNTIME_ANOMALY`. No MWAN freshness failure remains.
- Protected database counts did not change during final read-only DQ evaluation.
- API readiness remained healthy across database, Redis, and worker checks. PostgreSQL, Redis, scheduler, and frontend were not restarted.
- The Change Password implementation and prior security evidence were not rerun or altered. Its report closeout status now reads `IN_APP_CHANGE_PASSWORD = COMPLETE` because the unrelated live DQ blocker is cleared.

## Evidence files

- [Job 521 root-cause record](mwan-job-521-root-cause.json)
- [TLS/container diagnostics](mwan-tls-diagnostics.json)
- [MWAN state before and after](mwan-source-state-before-after.json)
- [Job 539 validation sync](mwan-validation-sync.json)
- [Final full live read-only DQ](mwan-dq-results.json)
- Source-specific CA intermediate: `app/certificates/mwan-digicert-global-g2-tls-rsa-sha256-2020-ca1.pem`
- Implementation and tests: `app/tls.py`, `app/service.py`, `tests/test_source_tls.py`

```ini
MWAN_TLS_FRESHNESS_REMEDIATION = COMPLETE
MWAN_TLS_ROOT_CAUSE = C. MISSING_INTERMEDIATE_CHAIN_FROM_OFFICIAL_SERVER
MWAN_REMEDIATION_PATH = PATH_A_SOURCE_RESTORED
TLS_VERIFICATION_DISABLED = FALSE
MWAN_PUBLIC_SOURCE_AVAILABLE = TRUE
MWAN_ITEMIZED_PUBLIC_COVERAGE = TRUE
MWAN_RELEVANT_TO_ALAHSA = TRUE (source-level relevance; current scan accepted 0 Al-Ahsa items)
MWAN_TECHNICAL_HEALTH = HEALTHY
MWAN_FRESHNESS_STATUS = FRESH
MWAN_LAST_SUCCESS = 2026-10-27T07:43:13.591078Z
MWAN_LAST_JOB_STATUS = SUCCESS
MWAN_VALIDATION_SYNC_STARTED = TRUE (MWAN only)
UNRELATED_MANUAL_SOURCE_SYNC_STARTED = FALSE
REMOVAL_ON_INCOMPLETE_SCAN = 0
MASTER_CANCELLATIONS_FROM_MWAN_TLS_FAILURE = 0
MASTER_DELETIONS_FROM_MWAN_TLS_FAILURE = 0
UNEXPLAINED_CANONICAL_CHANGES = 0
OPEN_ACTIONABLE_REVIEWS = 0
LIVE_DQ_TOTAL = 129
LIVE_DQ_PASS = 125
LIVE_DQ_WARNING = 4
LIVE_DQ_FAIL = 0
FOCUSED_TESTS = 26 passed / 0 failed
FULL_REGRESSION_SUITE = 588 passed / 0 failed
IN_APP_CHANGE_PASSWORD = COMPLETE
```

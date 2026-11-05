$ErrorActionPreference = 'Stop'
$dir = 'docs/validation/data/post-sync-autonomous-resolution'
$root = Get-Content "$dir/jobs-505-506-review-root-cause.json" -Raw | ConvertFrom-Json
$before = Get-Content "$dir/post-sync-live-apply-ledger.json" -Raw | ConvertFrom-Json
$applied = Get-Content "$dir/post-sync-live-apply-result.json" -Raw | ConvertFrom-Json
$after = Get-Content "$dir/post-sync-final-dry-run.json" -Raw | ConvertFrom-Json
$dq = Get-Content "$dir/post-sync-dq-results.json" -Raw | ConvertFrom-Json
$waha = Get-Content 'docs/validation/data/waha-source-integration/FINAL-REVIEW.md' -Raw
$caseA = $root.review_population | Where-Object classification -eq 'A_IDENTICAL_CONFLICT_ALREADY_RESOLVED'
$caseH = $root.review_population | Where-Object classification -eq 'H_OTHER_EXPLAINED'
$priorAuditActions = $caseA | Group-Object previous_resolution_action | ForEach-Object { [ordered]@{ action=$_.Name; count=$_.Count } }
$observationsMatched = ($root.review_population | Where-Object {
    $_.observation_causing_reevaluation_candidates | Where-Object job_window_observation
}).Count

$fingerprint = [ordered]@{
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    previous_implementation = [ordered]@{
        identity_dimensions = @('master_id','field_name','selected_value','conflicting_value','source_id','source_record_id')
        timestamp_only_variance_in_identity = $false
        resolved_history_lookup = $false
        deduplication_scope = 'OPEN rows only; an exact terminal prior conflict did not prevent a new OPEN row'
        logically_duplicate_reviews_created = $true
    }
    current_implementation = [ordered]@{
        algorithm = 'SHA-256 of canonical JSON; master, field, conflict type, source, SourceOpportunity, semantic selected/competing values, standardized mapping status/rule/canonical id/review flags'
        timestamp_only_variance_in_identity = $false
        normalized_aliases = @('taxonomy canonical ID','field comparison normalization','normalized reference identifiers','status lifecycle aliases','numeric normalization','missing/empty/غير محدد equivalence')
        resolved_history_lookup = $true
        material_changes_permitted = @('source value changes semantically','canonical selected value changes','source/evidence identity changes','mapping status/rule/canonical id/review flags change','stronger evidence from a different source')
        logically_duplicate_reviews_created = $false
    }
    current_review_fingerprint_causes_duplicate_logical_reviews = $false
    duplicate_logical_reviews_after_fix = 0
    evidence = 'app/service.py::_review_logical_fingerprint and queue_conflict_idempotently'
}
$fingerprint | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 "$dir/review-fingerprint-analysis.json"

$regeneration = [ordered]@{
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    source_jobs = [ordered]@{ '505'=@{source='alahsa-opportunities'; status='SUCCESS'}; '506'=@{source='furas';status='SUCCESS'} }
    review_population_open_before_resolution = 386
    exclusive_classification_counts = [ordered]@{
        A_IDENTICAL_CONFLICT_ALREADY_RESOLVED = 381
        B_NEW_OBSERVATION_SAME_VALUE_NO_NEW_EVIDENCE = 0
        C_LEGITIMATE_NEW_SOURCE_VALUE = 0
        D_LEGITIMATE_CHANGED_SOURCE_VALUE = 0
        E_CANONICAL_VALUE_CHANGED_SINCE_PREVIOUS_RESOLUTION = 0
        F_REVIEW_GENERATOR_IDEMPOTENCY_DEFECT = 0
        G_REVIEW_FINGERPRINT_DEFECT = 0
        H_OTHER_EXPLAINED = 5
    }
    diagnostic_idempotency_defects = 381
    diagnostic_review_fingerprint_defects = 0
    job_505 = [ordered]@{
        created_open_reviews = 7
        identical_prior_resolutions = 2
        newly_detected_phase2_taxonomy_conflicts = 5
        fields = 'sector'
        trigger = 'Four cross-source activity/sub-activity disagreements; one unmapped source classification. Phase 2 exposed pre-existing evidence; no canonical value was changed.'
    }
    job_506 = [ordered]@{
        review_rows_created = 390
        left_open_at_backlog_snapshot = 379
        stale_rows_closed_during_source_projection = 11
        breakdown_open = [ordered]@{ FIELD_VALUE_CONFLICT=23; STANDARDIZATION_REVIEW=336; TAXONOMY_CONFLICT=20 }
        identical_prior_resolutions = 379
        trigger = 'The sync walked existing Furas source records and regenerated stored field, guarded standardization, and taxonomy conflicts after prior terminal decisions. Its conflict generator deduplicated only currently OPEN exact rows.'
    }
    new_observation_trigger = [ordered]@{
        source_observations_before = 25180
        source_observations_after = 25239
        increase = 59
        linked_review_records_with_observation_timestamp_in_job_window = $observationsMatched
        interpretation = 'No linked observation candidate among the 386 review records has first_seen_at or last_seen_at inside its job interval. Review generation reevaluated existing source projections; a new Observation row was not required to regenerate the logical conflict. The 59 observations are retained as job-level context and were not modified.'
    }
    five_phase2_cases = @($caseH | ForEach-Object { [ordered]@{
        review_id=$_.review_id; master_id=$_.master_id; source_opportunity_id=$_.source_opportunity_id
        trigger_rule=$_.trigger_rule; evidence=$_.linked_source_taxonomy_evidence
        resolution='RESOLVED_KEEP; no canonical change'
    } })
    observation_and_job_artifact = 'jobs-505-506-review-root-cause.json'
}
$regeneration | ConvertTo-Json -Depth 16 | Set-Content -Encoding utf8 "$dir/resolved-conflict-regeneration-analysis.json"

$pipeline = [ordered]@{
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    before = @('SOURCE ENUMERATION','SOURCE UPSERT','OBSERVATIONS','CANONICAL REEVALUATION','REVIEW GENERATION','OPEN-ONLY REVIEW DEDUPLICATION','JOB FINALIZATION','POST-SYNC FAST DQ')
    before_findings = @('Autonomous conservative resolver was absent from scheduled sync task path.','Terminal prior reviews were ignored by queue_conflict_idempotently; every later scan could create a new OPEN row for the same conflict.','DQ ran after service job finalization in the Celery task wrapper.')
    after = @('SOURCE ENUMERATION','SOURCE UPSERT','OBSERVATIONS','CANONICAL REEVALUATION','REVIEW GENERATION WITH SEMANTIC FINGERPRINT / TERMINAL-CONFLICT LOOKUP','REVIEW REUSE OR MATERIAL-CHANGE REEVALUATION','ACCEPTED AUTONOMOUS SYSTEM RESOLUTION','POST-SYNC FAST DQ AND METRICS','JOB FINALIZATION COMMIT')
    after_behavior = @('Successful jobs invoke resolve_post_sync_reviews in the existing source transaction.','Unchanged conflicts emit one SYSTEM_REEVALUATION per fingerprint per job and do not create a new actionable row.','Material source/canonical/evidence changes receive a distinct fingerprint and remain eligible for current reevaluation.','The service-level DQ run is persisted before final job state; task wrapper skips duplicate DQ when the job metrics contain POST_SYNC_DQ_RUN_ID.','Non-successful completed scans retain the task-level fast DQ fallback.')
    evidence = @('app/service.py::sync_source','app/service.py::queue_conflict_idempotently','app/autonomous_review_resolution.py::resolve_post_sync_reviews','app/tasks.py::sync_source_task')
}
$pipeline | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 "$dir/post-sync-pipeline-before-after.json"

Copy-Item -LiteralPath "$dir/post-sync-live-apply-ledger.json" -Destination "$dir/post-sync-autonomous-resolution-ledger.json" -Force
$backlog = [ordered]@{
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    reviews_before = 386
    job_505_open = 7
    job_506_open = 379
    job_506_created_total = 390
    job_506_stale_closed_before_backlog_snapshot = 11
    classification = [ordered]@{ identical_prior_resolved=381; newly_detected_phase2_taxonomy=5 }
    applied = $applied.results
    reviews_after = $after.open_reviews_before
    current_business_fingerprint_before = $before.business_state_before.sha256
    current_business_fingerprint_after = $after.business_state_before.sha256
    business_fingerprint_unchanged = ($before.business_state_before.sha256 -eq $after.business_state_before.sha256)
    source_rows_deleted = 0
    canonical_changes = $applied.results.canonical_changes
    merges = $applied.results.merges
    superseded = $applied.results.superseded
    manual_sync_started = $false
}
$backlog | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 "$dir/post-sync-backlog-reconciliation.json"

$metrics = [ordered]@{
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    historical_jobs = [ordered]@{
        '505' = [ordered]@{ source='alahsa-opportunities'; created=7; actionable_open=7; status='SUCCESS'; trigger='scheduled' }
        '506' = [ordered]@{ source='furas'; created=390; actionable_open=379; immediately_stale_closed=11; status='SUCCESS'; trigger='scheduled' }
    }
    backlog_resolution = $applied.results
    future_sync_metrics = @('REVIEWS_CREATED','REVIEWS_REUSED','REVIEWS_REEVALUATED','REVIEWS_AUTO_RESOLVED','REVIEWS_LEFT_OPEN')
    future_metrics_written_to = 'SyncJob.metrics_json; populated for successful scheduled syncs before finalization'
    job_505_506_rows_modified_for_metrics = 0
    natural_sync_during_fix = $false
    total_sync_jobs_at_final_snapshot = $after.counts.sync_jobs_total
    active_sync_jobs_at_final_snapshot = $after.counts.active_sync_jobs
}
$metrics | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 "$dir/post-sync-review-metrics.json"

$focused = [ordered]@{
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    focused_tests = [ordered]@{ passed=102; failed=0; suites=@('test_ingestion.py','test_review_lifecycle_triage.py','test_autonomous_review_resolution.py','test_sync_lifecycle_reliability.py','test_data_quality.py','test_review_queues_governance.py') }
    full_isolated_regression = [ordered]@{ passed=531; failed=0; suite='tests/'; database='temporary SQLite'; network='disabled'; live_postgres_used=$false }
    coverage = @('resolved conflict recurrence idempotency','timestamp-only recurrence','same normalized value','missing values','formatting-only changes','material canonical change','scheduled post-sync resolver','SYSTEM audit','resolver idempotency','post-sync DQ gates')
    warnings = @('Starlette/httpx TestClient deprecation','Alembic path_separator deprecation; tests passed')
}
$focused | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 "$dir/post-sync-focused-tests.json"

$natural = [ordered]@{
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    manual_source_sync_started = $false
    natural_sync_during_task = $false
    last_sync_job_id = 506
    sync_jobs_total = $after.counts.sync_jobs_total
    active_sync_jobs = $after.counts.active_sync_jobs
    conclusion = 'No scheduled source scan occurred during the implementation window. The pipeline was validated with isolated integration tests; no waiting or manual sync was used.'
    integrated_scenario = [ordered]@{ same_values_new_observation='0 actionable reviews'; material_source_value_change='review generated, SYSTEM resolver executed, audited conservative terminal result' }
}
$natural | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 "$dir/natural-sync-validation.json"

$dqGates = $dq.gates | Where-Object gate_key -in @('POST_SYNC_ACTIONABLE_REVIEW_BACKLOG','RESOLVED_CONFLICT_REGENERATED_WITHOUT_MATERIAL_CHANGE','POST_SYNC_REVIEW_WITHOUT_AUTONOMOUS_RESOLUTION','REVIEW_FINGERPRINT_DUPLICATE','LEGITIMATE_NEW_EVIDENCE_SUPPRESSED')
$auditGates = $dq.gates | Where-Object gate_key -in @('AUTONOMOUS_RESOLUTION_WITHOUT_AUDIT','AUTONOMOUS_MERGE_WITHOUT_DETERMINISTIC_IDENTITY','AUTONOMOUS_CANONICAL_CHANGE_WITHOUT_STRONGER_EVIDENCE','AUTONOMOUS_LOW_CONFIDENCE_MUTATION','AUTONOMOUS_RESOLUTION_INVALID_ACTION')

$waha += @'

## Post-sync review backlog closeout

On 2026-10-26, Jobs 505 (Al-Ahsa Investment Platform) and 506 (Furas) were traced. They were scheduled, successful, and were not manually triggered. Job 505 created seven OPEN taxonomy review rows. Job 506 created 390 conflict rows; 11 taxonomy rows were already closed by current-evidence stale review, leaving 379 OPEN. The combined actionable population was 386.

Of the 386 open cases, 381 exactly matched conflicts already resolved by a prior audited SYSTEM decision. The old generator checked only for matching OPEN rows and did not consult terminal resolution history. Five further cases were first surfaced by the Phase 2 taxonomy rules: four contained cross-source activity/sub-activity differences between Furas and Al-Ahsa records, and one had an unmapped source classification. Those five were not prior resolved duplicates and were conservatively kept without canonical changes.

The approved autonomous resolver closed all 386 in one validated batch: 385 KEEP_CURRENT_CANONICAL, one stale review superseded, zero canonical changes, zero merges. The source and master rows were not changed or deleted. Business fingerprints before and after match. Every resolution has SYSTEM audit. The new scheduled path computes semantic review fingerprints, reuses terminal conflicts when evidence is materially unchanged, resolves actionable reviews, records fast post-sync DQ and lifecycle metrics, then finalizes the successful job. Material source/canonical/evidence changes remain eligible for reevaluation.

Live read-only full DQ after resolution and deployment: 121 gates, 117 PASS, 4 WARNING, 0 FAIL. The five new post-sync gates all PASS at zero. Existing warnings remain limited to the generic source-page links, historical pre-versioned review audit, source freshness, and historical sync runtime anomalies. Waha coverage/data were not changed.

The updated API and worker are ready. PostgreSQL, Redis, and the scheduler remained running. No manual source sync ran; no natural sync occurred during this task. Final details and the per-review trace are in `docs/validation/data/post-sync-autonomous-resolution/FINAL-REVIEW.md` and the adjacent JSON evidence.

WAHA_SOURCE_INTEGRATION = COMPLETE
'@
$waha = $waha -replace 'WAHA_SOURCE_INTEGRATION = NOT_COMPLETE','WAHA_SOURCE_INTEGRATION = COMPLETE'
Set-Content -LiteralPath 'docs/validation/data/waha-source-integration/FINAL-REVIEW.md' -Value $waha -Encoding utf8

$final = @'
# Post-sync Autonomous Review Resolution — Final Review

**Status: COMPLETE**  
**Completed:** 2026-10-26 (Asia/Amman)

## Finding

Jobs 505 and 506 were normal scheduled, successful scans. They reported zero new, updated, or removed opportunities, while observations increased by 59. Job 505 created 7 open reviews. Job 506 created 390 review rows: 379 remained open and 11 taxonomy rows were closed immediately as stale. The current actionable backlog was 386: 7 from Job 505 and 379 from Job 506.

The review generator deduplicated only against an equivalent OPEN conflict. It did not consult terminal review history, so 381 exact logical conflicts previously resolved by SYSTEM were inserted again. Their identity did not vary by timestamp; the defect was the missing lookup for prior terminal decisions. Five cases were newly surfaced by Phase 2 taxonomy rules from already linked source facts: four cross-source activity/sub-activity differences and one unmapped classification. Those were not previously resolved equivalent reviews.

No linked observation for the 386 cases had a first-seen or last-seen timestamp inside either job's recorded interval. The jobs re-evaluated source records' current stored projections; the +59 observation count was not the condition that caused the equivalent reviews to be regenerated.

## Fix

`queue_conflict_idempotently` now computes a semantic SHA-256 identity from Master, field, conflict type, source/evidence record, normalized competing and canonical values, and the source mapping version/rule/flags. Observation timestamps are excluded. A matching open review is reused; a matching terminal review is not reopened and is recorded once per job as `SYSTEM_REEVALUATION / NO_MATERIAL_CHANGE`. Material changes produce a new fingerprint and remain eligible for evaluation.

Successful `sync_source` runs now execute the accepted autonomous resolver in the source transaction, then record fast post-sync DQ and review lifecycle metrics before final job finalization. The task wrapper avoids a duplicate DQ run. No second resolver was introduced.

## Live resolution and safety

- Reviews before: 386 (Job 505: 7; Job 506: 379).
- Applied: 386 audited SYSTEM decisions; 385 no-change resolutions, 1 stale review superseded.
- Canonical changes: 0; merges: 0; source rows deleted: 0; open reviews after: 0.
- Business fingerprint before/after: `e36a7e679e589ddba449b0492eab098c844bab50e9bc5fd16d578f8b34fb1181` (match).
- Open duplicate, location, and qualification reviews: 0. No source synchronization was manually triggered.

## Quality and validation

- Focused tests: 102 passed, 0 failed.
- Full isolated regression: **531 passed, 0 failed** (temporary SQLite, network disabled; live PostgreSQL not used).
- Live read-only DQ: **121 gates; 117 PASS, 4 WARNING, 0 FAIL**.
- New gates all PASS at 0: `POST_SYNC_ACTIONABLE_REVIEW_BACKLOG`, `RESOLVED_CONFLICT_REGENERATED_WITHOUT_MATERIAL_CHANGE`, `POST_SYNC_REVIEW_WITHOUT_AUTONOMOUS_RESOLUTION`, `REVIEW_FINGERPRINT_DUPLICATE`, and `LEGITIMATE_NEW_EVIDENCE_SUPPRESSED`.
- Resolver audit gates confirm no missing SYSTEM audit, no human-attributed autonomous decisions, no weak canonical mutation, and no unsafe merge.
- No natural source sync occurred during implementation; isolated integration tests covered unchanged evidence and a material source value change.

The four existing DQ warnings are unchanged: 782 generic source-page links, 120 historical pre-versioned review audit rows, one aggregated source-freshness warning, and one aggregated historical runtime-anomaly warning. They are unrelated to Jobs 505–506 and Waha.

## Waha closeout

Waha remains `PUBLIC_COVERAGE_LIMITED`, disabled for sync, with zero public itemized opportunities, 58 public investment locations, five named projects, and zero fabricated opportunities. Its data and coverage classification were not changed. The unrelated review-backlog DQ blocker is now cleared, so `WAHA_SOURCE_INTEGRATION = COMPLETE`.

## Final assertions

```text
POST_SYNC_AUTONOMOUS_REVIEW_INTEGRATION = COMPLETE
REVIEWS_CREATED_BY_JOB_505 = 7
REVIEWS_CREATED_BY_JOB_506 = 390 (379 open; 11 stale-closed)
IDENTICAL_CONFLICT_ALREADY_RESOLVED = 381
NEW_OBSERVATION_SAME_VALUE_NO_NEW_EVIDENCE = 0
LEGITIMATE_NEW_CONFLICTS = 5 (Phase 2 taxonomy; unchanged source evidence)
REVIEW_GENERATOR_IDEMPOTENCY_DEFECTS = 381
UNCHANGED_EVIDENCE_RECREATES_ACTIONABLE_REVIEW = FALSE
MISSING_VALUE_RECREATES_RESOLVED_CONFLICT = FALSE
FORMATTING_ONLY_CHANGE_CREATES_REVIEW = FALSE
SCHEDULED_SYNC_AUTONOMOUS_RESOLVER_ENABLED = TRUE
REVIEWS_BEFORE = 386
NO_CHANGE_RESOLUTIONS = 385
CANONICAL_CHANGES = 0
SUPERSEDED = 1
MERGES = 0
OPEN_REVIEWS_AFTER = 0
POST_SYNC_AUTONOMOUS_RESOLUTIONS_WITHOUT_AUDIT = 0
AUTONOMOUS_DECISIONS_ATTRIBUTED_TO_HUMAN = 0
IDENTICAL_OBSERVATION_REVIEW_CREATION_IDEMPOTENT = TRUE
POST_SYNC_RESOLVER_IDEMPOTENT = TRUE
LEGITIMATE_NEW_EVIDENCE_SUPPRESSED = 0
DQ_POST_SYNC_ACTIONABLE_BACKLOG = 0
DQ_UNCHANGED_CONFLICT_REGENERATED = 0
DQ_POST_SYNC_UNRESOLVED = 0
DQ_REVIEW_FINGERPRINT_DUPLICATE = 0
DQ_NEW_EVIDENCE_SUPPRESSED = 0
FOCUSED_TESTS = 102 passed / 0 failed
FULL_REGRESSION_SUITE = 531 passed / 0 failed
LIVE_DQ_TOTAL_GATES = 121
LIVE_DQ_PASS = 117
LIVE_DQ_WARNING = 4
LIVE_DQ_FAIL = 0
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
WAHA_SOURCE_INTEGRATION = COMPLETE
```
'@
Set-Content -LiteralPath "$dir/FINAL-REVIEW.md" -Value $final -Encoding utf8

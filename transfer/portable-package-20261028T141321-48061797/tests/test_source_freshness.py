from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models import SyncJob
from app.source_freshness import POLICIES, evaluate_freshness, evaluate_source_jobs


NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def source(key="ncp", *, coverage="COMPLETE_FOR_DEFINED_SCOPE", health="HEALTHY", enabled=True):
    return SimpleNamespace(id=1, source_key=key, enabled=enabled, technical_health=health,
                           coverage_status=coverage, last_attempted_sync=NOW)


def scan(source_id=1, *, at=None, status="SUCCESS", complete=True, metrics=None):
    return SyncJob(source_id=source_id, started_at=at or NOW-timedelta(hours=1),
        finished_at=NOW, status=status, job_state="COMPLETED" if status=="SUCCESS" else status,
        pagination_complete=complete, metrics_json=metrics or {}, trigger_type="scheduled")


def result(src, jobs, now=NOW):
    return evaluate_source_jobs(src, jobs, now=now)


def test_dynamic_source_fresh_after_complete_successful_scan():
    row=result(source(),[scan()]); assert row["status"]=="FRESH"


def test_dynamic_source_warning_after_source_threshold():
    row=result(source(),[scan(at=NOW-timedelta(hours=30))]); assert row["status"]=="AGING"


def test_dynamic_source_fails_after_critical_threshold():
    row=result(source(),[scan(at=NOW-timedelta(days=4))]); assert row["status"]=="STALE" and row["failing_gate"]


def test_successful_no_change_scan_resets_freshness():
    row=result(source(),[scan()]); assert row["status"]=="FRESH" and row["last_complete_scan"]


def test_unchanged_content_does_not_mean_stale():
    row=result(source(),[scan()]); assert row["status"]=="FRESH" and row["last_content_change"] is None


def test_failed_attempt_does_not_erase_last_success():
    row=result(source(),[scan(at=NOW-timedelta(hours=1)),scan(at=NOW,status="FAILED",complete=None)])
    assert row["last_success"] and row["status"]=="FRESH"


def test_repeated_failures_escalate_explicitly():
    jobs=[scan(at=NOW-timedelta(hours=2),status="FAILED",complete=None),
          scan(at=NOW-timedelta(hours=1),status="FAILED",complete=None),
          scan(at=NOW,status="FAILED",complete=None)]
    row=result(source(),jobs); assert row["consecutive_failures"]==3 and "HIGH" in row["failure_escalation"]


def test_limited_coverage_can_be_fresh_after_scope_verification():
    src=source("modon",coverage="PUBLIC_COVERAGE_LIMITED")
    row=result(src,[scan(metrics={"public_scope_complete":True})])
    assert row["status"]=="LIMITED_SOURCE_OK"


def test_static_source_does_not_use_dynamic_polling_sla():
    src=source("static-reference"); row=evaluate_freshness(src,now=NOW,last_success=NOW-timedelta(days=30))
    assert row["status"]=="STATIC_OK" and row["warning_threshold_minutes"]==129600


def test_manual_source_becomes_review_due_not_sync_stale():
    src=source("manual-review"); row=evaluate_freshness(src,now=NOW,last_success=NOW-timedelta(days=31))
    assert row["status"]=="MANUAL_REVIEW_DUE"


def test_technical_health_is_separate_from_freshness():
    row=result(source(health="WARNING"),[scan()]); assert row["status"]=="FRESH" and row["technical_health"]=="WARNING"


def test_coverage_is_separate_from_freshness():
    row=result(source("modon",coverage="PUBLIC_COVERAGE_LIMITED"),[scan(metrics={"public_scope_complete":True})])
    assert row["status"]=="LIMITED_SOURCE_OK" and row["coverage_status"]=="PUBLIC_COVERAGE_LIMITED"


def test_source_specific_thresholds_differ():
    assert POLICIES["ncp"].warning_after_minutes != POLICIES["mwan"].warning_after_minutes


def test_freshness_evaluation_returns_gate_evidence():
    row=result(source(),[scan()]); assert row["last_complete_scan"] and row["warning_threshold_minutes"] and row["reason"]


def test_fresh_source_has_no_false_warning():
    row=result(source(),[scan()]); assert not row["warning_gate"] and not row["failing_gate"]


def test_true_stale_source_is_not_passed():
    row=result(source(),[scan(at=NOW-timedelta(days=4))]); assert row["status"]=="STALE" and row["failing_gate"]


def test_disabled_source_is_unknown_not_stale():
    row=result(source(enabled=False),[]); assert row["status"]=="UNKNOWN" and not row["warning_gate"]



from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data_quality import _scheduled_sync_window_evidence, evaluate_data_quality
from app.models import Base, Opportunity, Source, SourceObservation, SyncJob, SystemEvent


@pytest.fixture
def dq_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    from app import main
    monkeypatch.setattr(main, "SessionLocal", factory)
    db = factory()
    yield db
    db.close(); engine.dispose()


def source(db, key):
    row = Source(source_key=key, source_name_ar=key, organization_name=key,
                 base_url=f"https://{key}.test", opportunities_url=f"https://{key}.test/opportunities",
                 source_type="scheduled", priority=1, polling_frequency_minutes=360,
                 enabled=True, extraction_method="test", notes="")
    db.add(row); db.flush(); return row


def _evidence(src, now, **kwargs):
    return _scheduled_sync_window_evidence([src], kwargs.pop("jobs", []), now=now, **kwargs)


def test_expected_schedule_with_job_is_not_a_miss(dq_db):
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    src = source(dq_db, "ncp"); src.polling_frequency_minutes = 720
    src.last_attempted_sync = now - timedelta(minutes=20)
    job = SyncJob(source_id=src.id, queued_at=now - timedelta(minutes=20), started_at=now - timedelta(minutes=20),
                  status="SUCCESS", job_state="COMPLETED", trigger_type="scheduled", unchanged_count=84)
    dq_db.add(job); dq_db.flush()
    result = _evidence(src, now, jobs=[job])
    assert result["missed_execution_count"] == 0
    assert result["evidence"][0]["classification"] == "NOT_DUE"


def test_passed_expected_window_without_job_is_detected(dq_db):
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    src = source(dq_db, "ncp"); src.polling_frequency_minutes = 720
    src.last_attempted_sync = now - timedelta(minutes=723)
    result = _evidence(src, now)
    assert result["missed_execution_count"] == 1
    assert result["evidence"][0]["classification"] == "UNEXPLAINED_MISSED_SCHEDULE"


def test_valid_overlap_lock_is_not_counted_as_miss(dq_db):
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    src = source(dq_db, "ncp"); src.polling_frequency_minutes = 720
    src.last_attempted_sync = now - timedelta(minutes=800)
    result = _evidence(src, now, locked_source_ids={src.id})
    assert result["missed_execution_count"] == 0
    assert result["valid_overlap_suppression_count"] == 1


def test_disabled_source_is_not_counted(dq_db):
    now = datetime.now(timezone.utc)
    src = source(dq_db, "ncp"); src.enabled = False
    src.last_attempted_sync = now - timedelta(days=10)
    assert _evidence(src, now)["missed_execution_count"] == 0


def test_static_or_manual_zero_cadence_is_not_counted(dq_db):
    now = datetime.now(timezone.utc)
    src = source(dq_db, "ncp"); src.source_type = "manual_source"; src.polling_frequency_minutes = 0
    src.last_attempted_sync = now - timedelta(days=10)
    assert _evidence(src, now)["missed_execution_count"] == 0


def test_source_without_active_schedule_baseline_is_not_counted(dq_db):
    now = datetime.now(timezone.utc)
    src = source(dq_db, "ncp"); src.last_attempted_sync = None
    result = _evidence(src, now)
    assert result["missed_execution_count"] == 0
    assert result["evidence"][0]["classification"] == "NO_HISTORICAL_BASELINE"


def test_successful_no_change_run_satisfies_schedule_window(dq_db):
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    src = source(dq_db, "ncp"); src.polling_frequency_minutes = 720
    src.last_attempted_sync = now - timedelta(minutes=30)
    job = SyncJob(source_id=src.id, queued_at=now - timedelta(minutes=30), started_at=now - timedelta(minutes=30),
                  status="SUCCESS", job_state="COMPLETED", trigger_type="scheduled", unchanged_count=84)
    result = _evidence(src, now, jobs=[job])
    assert result["missed_execution_count"] == 0


def test_failed_job_is_a_run_not_a_missing_execution(dq_db):
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    src = source(dq_db, "ncp"); src.polling_frequency_minutes = 720
    src.last_attempted_sync = now - timedelta(minutes=45)
    job = SyncJob(source_id=src.id, queued_at=now - timedelta(minutes=45), started_at=now - timedelta(minutes=45),
                  status="FAILED", job_state="FAILED", trigger_type="scheduled")
    assert _evidence(src, now, jobs=[job])["missed_execution_count"] == 0


def test_schedule_arithmetic_is_timezone_aware_and_utc_normalized(dq_db):
    now = datetime(2026, 10, 20, 18, 3, tzinfo=timezone.utc)
    src = source(dq_db, "furas"); src.polling_frequency_minutes = 60
    src.last_attempted_sync = datetime(2026, 10, 20, 20, 0, tzinfo=timezone(timedelta(hours=3)))
    result = _evidence(src, now)
    assert result["missed_execution_count"] == 1
    assert result["evidence"][0]["expected_fire_at"] == "2026-10-20T18:00:00+00:00"


def test_missed_schedule_dq_gate_is_read_only(dq_db, monkeypatch):
    from app import tasks

    class EmptyRedis:
        def scan_iter(self, **kwargs):
            return iter(())

    monkeypatch.setenv("REDIS_URL", "redis://fixture")
    monkeypatch.setattr(tasks, "redis_client", lambda: EmptyRedis())
    src = source(dq_db, "ncp"); src.polling_frequency_minutes = 720
    src.last_attempted_sync = datetime.now(timezone.utc) - timedelta(minutes=723)
    dq_db.flush()
    before = (dq_db.query(Opportunity).count(), dq_db.query(SourceObservation).count(),
              dq_db.query(SyncJob).count(), dq_db.query(SystemEvent).count())
    result = evaluate_data_quality(dq_db, scope="full", persist=False)
    gate = next(row for row in result["gates"] if row["gate_key"] == "UNEXPLAINED_MISSED_SCHEDULE_EXECUTIONS")
    after = (dq_db.query(Opportunity).count(), dq_db.query(SourceObservation).count(),
             dq_db.query(SyncJob).count(), dq_db.query(SystemEvent).count())
    assert gate["status"] == "FAIL"
    assert gate["observed"] == 1
    assert gate["evidence"][0]["source"] == "ncp"
    assert before == after

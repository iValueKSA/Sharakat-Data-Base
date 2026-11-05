from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Source, SyncJob
from app.sync_lifecycle import terminal_sync_job_state, transition_sync_job


@pytest.fixture
def lifecycle_db(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path / 'sync-lifecycle.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source=Source(source_key="fixture",source_name_ar="fixture",organization_name="fixture",
            base_url="https://fixture.invalid",opportunities_url="https://fixture.invalid/list",
            enabled=True,priority=1)
        db.add(source);db.flush()
        now=datetime.now(timezone.utc)
        job=SyncJob(source_id=source.id,started_at=now,status="RUNNING",job_state="RUNNING",
            heartbeat_at=now,removed_records_count=0,pagination_complete=False)
        db.add(job);db.commit()
        yield db,job
    engine.dispose()


def stale_snapshot(job):
    return SimpleNamespace(id=job.id,status="RUNNING",job_state="RUNNING",finished_at=None)


def finish(db,job,status,at=None):
    return transition_sync_job(db,job,target_state=terminal_sync_job_state(status),target_status=status,
        finished_at=at or datetime.now(timezone.utc))


def persisted(db,job_id):
    db.expire_all()
    return db.get(SyncJob,job_id)


def assert_timestamp(actual,expected):
    if actual.tzinfo is None:actual=actual.replace(tzinfo=timezone.utc)
    assert actual==expected


def test_stale_running_writer_cannot_overwrite_succeeded(lifecycle_db):
    db,job=lifecycle_db; stale=stale_snapshot(job); finished=datetime.now(timezone.utc)
    assert finish(db,job,"SUCCESS",finished)
    db.commit()
    assert not transition_sync_job(db,stale,target_state="RUNNING",target_status="RUNNING",finished_at=None)
    current=persisted(db,job.id)
    assert current.status=="SUCCESS" and current.job_state=="COMPLETED";assert_timestamp(current.finished_at,finished)


def test_stale_running_writer_cannot_overwrite_failed(lifecycle_db):
    db,job=lifecycle_db; stale=stale_snapshot(job); finished=datetime.now(timezone.utc)
    assert finish(db,job,"FAILED",finished)
    db.commit()
    assert not transition_sync_job(db,stale,target_state="RUNNING",target_status="RUNNING",finished_at=None)
    current=persisted(db,job.id)
    assert current.status==current.job_state=="FAILED";assert_timestamp(current.finished_at,finished)


def test_competing_finalizers_use_first_successful_compare_and_set(lifecycle_db):
    db,job=lifecycle_db; success_writer=stale_snapshot(job); failure_writer=stale_snapshot(job)
    success_at=datetime.now(timezone.utc);failure_at=success_at+timedelta(seconds=1)
    assert finish(db,success_writer,"SUCCESS",success_at)
    assert not finish(db,failure_writer,"FAILED",failure_at)
    db.commit()
    current=persisted(db,job.id)
    assert current.status=="SUCCESS" and current.job_state=="COMPLETED";assert_timestamp(current.finished_at,success_at)


@pytest.mark.parametrize(("status","target"),[("SUCCESS","COMPLETED"),("FAILED","FAILED")])
def test_repeated_terminal_finalization_is_idempotent(lifecycle_db,status,target):
    db,job=lifecycle_db;finished=datetime.now(timezone.utc)
    assert finish(db,job,status,finished)
    assert finish(db,job,status,finished+timedelta(seconds=30))
    db.commit()
    current=persisted(db,job.id)
    assert current.status==status and current.job_state==target;assert_timestamp(current.finished_at,finished)


def test_failure_then_stale_success_callback_keeps_failure_terminal(lifecycle_db):
    db,job=lifecycle_db;failure_writer=stale_snapshot(job);success_writer=stale_snapshot(job)
    finished=datetime.now(timezone.utc)
    assert finish(db,failure_writer,"FAILED",finished)
    assert not finish(db,success_writer,"SUCCESS",finished+timedelta(seconds=1))
    db.commit()
    current=persisted(db,job.id)
    assert current.status==current.job_state=="FAILED";assert_timestamp(current.finished_at,finished)


@pytest.mark.parametrize("status",["INCOMPLETE_COLLECTION_WARNING","WARNING"])
def test_partial_and_zero_page_outcomes_finalize_without_reconciliation(lifecycle_db,status):
    db,job=lifecycle_db
    job.status=status
    job.pagination_complete=False
    job.pages_scanned=0
    job.removed_records_count=0
    finished=datetime.now(timezone.utc)
    assert transition_sync_job(db,job,target_state="COMPLETED_WITH_WARNINGS",target_status=status,
        finished_at=finished,allowed_from={"RUNNING"})
    db.commit()
    current=persisted(db,job.id)
    assert current.status==status and current.job_state=="COMPLETED_WITH_WARNINGS"
    assert_timestamp(current.finished_at,finished);assert current.removed_records_count==0


def test_deadlock_retry_attempt_remains_nonterminal_until_final_success(lifecycle_db):
    db,job=lifecycle_db;retry_at=datetime.now(timezone.utc)
    assert transition_sync_job(db,job,target_state="RETRYING",target_status="RETRYING",finished_at=None,
        allowed_from={"RUNNING"},values={"error_message":"deadlock retry simulation"})
    db.commit()
    assert job.job_state=="RETRYING" and job.finished_at is None
    assert transition_sync_job(db,job,target_state="RUNNING",target_status="RUNNING",finished_at=None,
        allowed_from={"RETRYING"},values={"started_at":retry_at})
    assert finish(db,job,"SUCCESS",retry_at+timedelta(seconds=1))
    db.commit()
    current=persisted(db,job.id)
    assert current.status=="SUCCESS" and current.job_state=="COMPLETED" and current.finished_at is not None


@pytest.mark.parametrize("first_state,first_status,second_state,second_status",[
    ("ABANDONED","ABANDONED","COMPLETED","SUCCESS"),
    ("COMPLETED","SUCCESS","ABANDONED","ABANDONED"),
])
def test_scheduler_worker_overlap_cannot_regress_terminal_state(
        lifecycle_db,first_state,first_status,second_state,second_status):
    db,job=lifecycle_db;worker=stale_snapshot(job);recovery=stale_snapshot(job)
    at=datetime.now(timezone.utc)
    first=worker if first_status=="SUCCESS" else recovery
    second=recovery if first is worker else worker
    assert transition_sync_job(db,first,target_state=first_state,target_status=first_status,finished_at=at)
    assert not transition_sync_job(db,second,target_state=second_state,target_status=second_status,
        finished_at=at+timedelta(seconds=1))
    db.commit()
    current=persisted(db,job.id)
    assert current.job_state==first_state and current.status==first_status;assert_timestamp(current.finished_at,at)

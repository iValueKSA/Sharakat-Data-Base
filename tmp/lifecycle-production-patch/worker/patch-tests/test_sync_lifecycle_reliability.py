from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from celery.exceptions import Retry

from app import tasks
from app.models import Base, Source, SyncJob, SystemEvent
from app.sync_lifecycle import source_runtime_profiles


class FakeRedis:
    def __init__(self, locks=None):
        self.locks = set(locks or ())
        self.values = {}

    def exists(self, key):
        return key in self.locks

    def eval(self, script, key_count, key, token):
        if self.values.get(key) == token:
            self.values.pop(key, None)
            return 1
        return 0

    def set(self,key,value,nx=False,ex=None):
        if nx and (key in self.locks or key in self.values):return False
        self.values[key]=value
        return True


class FakeInspect:
    def __init__(self, active=None, reserved=None, scheduled=None):
        self._active = active
        self._reserved = reserved
        self._scheduled = scheduled

    def active(self):
        return self._active

    def reserved(self):
        return self._reserved

    def scheduled(self):
        return self._scheduled


def setup_recovery(monkeypatch, *, task_id=None, lock=False, active=None, reserved=None, scheduled=None):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    source_data = __import__("app.service", fromlist=["DEFAULT_SOURCES"]).DEFAULT_SOURCES[0]
    started = datetime.now(timezone.utc) - timedelta(hours=3)
    with sessions() as db:
        source = Source(**source_data, enabled=True)
        db.add(source)
        db.flush()
        job = SyncJob(source_id=source.id, started_at=started, queued_at=started,
                      heartbeat_at=started, status="RUNNING", job_state="RUNNING",
                      celery_task_id=task_id, pagination_complete=None,
                      metrics_json={"reservation_token": "reservation-1"})
        db.add(job)
        db.commit()
        job_id, source_id = job.id, source.id
    redis = FakeRedis({f"source-sync:{source_id}"} if lock else ())
    monkeypatch.setattr(tasks, "SessionLocal", sessions)
    monkeypatch.setattr(tasks, "redis_client", lambda: redis)
    monkeypatch.setattr(tasks.celery_app.control, "inspect", lambda timeout=2: FakeInspect(
        active=active if active is not None else {"worker-1": []},
        reserved=reserved if reserved is not None else {"worker-1": []},
        scheduled=scheduled if scheduled is not None else {"worker-1": []},
    ))
    queued = []
    monkeypatch.setattr(tasks, "enqueue_source", lambda key, trigger_type="manual": queued.append((key, trigger_type)) or {"status": "QUEUED"})
    return engine, sessions, redis, job_id, source_id, queued


def test_dead_stale_job_is_finalized_and_requeued(monkeypatch):
    engine, sessions, redis, job_id, source_id, queued = setup_recovery(monkeypatch, task_id="dead-task")
    try:
        result = tasks.recover_stale_jobs()
        with sessions() as db:
            job = db.get(SyncJob, job_id)
            events = db.scalars(select(SystemEvent).where(SystemEvent.event_type == "SYNC_JOB_STALE_RECOVERED")).all()
            assert job.status == job.job_state == "ABANDONED"
            assert job.finished_at is not None
            assert job.pagination_complete is False
            assert job.celery_task_id == "dead-task"
            assert len(events) == 1
        assert result["abandoned_running"] == 1
        assert queued == [("furas", "retry")]
    finally:
        engine.dispose()


def test_active_task_with_old_heartbeat_is_not_recovered(monkeypatch):
    engine, sessions, redis, job_id, source_id, queued = setup_recovery(
        monkeypatch, task_id="live-task", active={"worker-1": [{"id": "live-task", "name": "app.tasks.sync_source_task"}]})
    try:
        result = tasks.recover_stale_jobs()
        with sessions() as db:
            job = db.get(SyncJob, job_id)
            assert job.status == job.job_state == "RUNNING"
            assert job.finished_at is None
        assert result["abandoned_running"] == 0 and queued == []
    finally:
        engine.dispose()


def test_live_source_lock_prevents_recovery(monkeypatch):
    engine, sessions, redis, job_id, source_id, queued = setup_recovery(monkeypatch, lock=True)
    try:
        result = tasks.recover_stale_jobs()
        with sessions() as db:
            job = db.get(SyncJob, job_id)
            assert job.status == job.job_state == "RUNNING"
        assert result["abandoned_running"] == 0 and queued == []
    finally:
        engine.dispose()


def test_worker_inspection_failure_fails_closed(monkeypatch):
    engine, sessions, redis, job_id, source_id, queued = setup_recovery(monkeypatch)
    monkeypatch.setattr(tasks.celery_app.control, "inspect", lambda timeout=2: FakeInspect(active=None))
    try:
        result = tasks.recover_stale_jobs()
        with sessions() as db:
            job = db.get(SyncJob, job_id)
            assert job.status == job.job_state == "RUNNING"
        assert result["status"] == "INSPECTION_UNAVAILABLE"
        assert queued == []
    finally:
        engine.dispose()


def test_scheduled_or_reserved_sync_task_is_not_recovered(monkeypatch):
    engine, sessions, redis, job_id, source_id, queued = setup_recovery(
        monkeypatch, task_id="waiting-task",
        reserved={"worker-1": [{"id": "waiting-task", "name": "app.tasks.sync_source_task"}]})
    try:
        result = tasks.recover_stale_jobs()
        with sessions() as db:
            job = db.get(SyncJob, job_id)
            assert job.status == job.job_state == "RUNNING"
        assert result["abandoned_running"] == 0 and queued == []
    finally:
        engine.dispose()


def test_lock_and_reservation_ttl_outlive_hard_task_limit(monkeypatch):
    monkeypatch.setenv("SOURCE_JOB_TIMEOUT_SECONDS", "1800")
    assert tasks.sync_lock_ttl() == 2400


def test_retry_policy_retries_transient_failures_but_not_permanent_validation(monkeypatch):
    assert tasks.retryable_result({"status": "FAILED", "error": "Name or service not known"})
    assert tasks.retryable_result({"status": "FAILED", "error": "HTTP 503 temporarily unavailable"})
    assert not tasks.retryable_result({"status": "FAILED", "error": "HTTP 403 forbidden"})
    assert not tasks.retryable_result({"status": "FAILED", "error": "parser structure changed"})
    assert tasks.retryable_exception(TimeoutError("request timed out"))
    assert not tasks.retryable_exception(ValueError("invalid source configuration"))


def test_repeated_warning_runs_escalate_and_success_resets_counter():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine);sessions=sessionmaker(bind=engine,expire_on_commit=False)
    with sessions() as db:
        src=Source(source_key="nhc",source_name_ar="NHC",organization_name="NHC",base_url="https://nhc.test",
            opportunities_url="https://nhc.test/opportunities",enabled=True)
        db.add(src);db.flush();now=datetime.now(timezone.utc)
        db.add_all([SyncJob(source_id=src.id,started_at=now+timedelta(minutes=i),finished_at=now+timedelta(minutes=i),
            status="WARNING",job_state="COMPLETED_WITH_WARNINGS",trigger_type="scheduled") for i in range(3)])
        db.flush()
        assert tasks.recent_unsuccessful_sync_count(db,src.id)==3
        db.add(SyncJob(source_id=src.id,started_at=now+timedelta(minutes=4),finished_at=now+timedelta(minutes=4),
            status="SUCCESS",job_state="COMPLETED",trigger_type="scheduled"));db.flush()
        assert tasks.recent_unsuccessful_sync_count(db,src.id)==0
    engine.dispose()


def test_source_specific_stale_threshold_requires_history_and_covers_long_successes():
    now=datetime.now(timezone.utc)
    short_history=[SimpleNamespace(source_id=1,status="SUCCESS",started_at=now-timedelta(seconds=9000),finished_at=now)]
    profiles=source_runtime_profiles(short_history,1800)
    assert profiles[1]["threshold_basis"]=="conservative_fallback"
    assert profiles[1]["stale_threshold_seconds"]==3600
    history=[SimpleNamespace(source_id=2,status="SUCCESS",started_at=now-timedelta(seconds=duration),finished_at=now)
             for duration in [5,8,10,12,14,15,18,3400]]
    profile=source_runtime_profiles(history,1800)[2]
    assert profile["successful_job_count"]==8
    assert profile["threshold_basis"]=="history"
    assert profile["stale_threshold_seconds"]>=6800


def test_cancelled_queued_task_does_not_enter_sync_or_keep_lock(monkeypatch):
    engine, sessions, redis, job_id, source_id, queued = setup_recovery(monkeypatch)
    with sessions() as db:
        job=db.get(SyncJob,job_id);job.status=job.job_state="CANCELLED";job.finished_at=datetime.now(timezone.utc);db.commit()
    monkeypatch.setattr(tasks,"redis_client",lambda:redis)
    try:
        result=tasks.sync_source_task.run("furas","scheduled","corr",job_id,"reservation-1")
        with sessions() as db:
            job=db.get(SyncJob,job_id)
            assert job.status==job.job_state=="CANCELLED"
        assert result["status"]=="CANCELLED"
        assert f"source-sync:{source_id}" not in redis.values
    finally:
        engine.dispose()


def test_task_redelivery_does_not_lose_running_state_while_prior_lock_lives(monkeypatch):
    engine, sessions, redis, job_id, source_id, queued = setup_recovery(monkeypatch, lock=True)
    try:
        result=tasks.sync_source_task.run("furas","scheduled","corr",job_id,"reservation-1")
        with sessions() as db:
            job=db.get(SyncJob,job_id)
            assert job.status==job.job_state=="RUNNING"
            assert job.finished_at is None
        assert result["status"]=="LOCK_HELD_FOR_PRIOR_ATTEMPT"
    finally:
        engine.dispose()


def test_retryable_sync_failure_stays_nonterminal_until_worker_retries(monkeypatch):
    import app.service as service
    engine, sessions, redis, job_id, source_id, queued = setup_recovery(monkeypatch)
    with sessions() as db:
        job=db.get(SyncJob,job_id);job.status=job.job_state="QUEUED";db.commit()
    async def retryable_failure(source_key,*,queued_job_id,defer_failure_finalization):
        assert defer_failure_finalization is True
        return {"status":"FAILED","error":"HTTP 503 temporarily unavailable","job_id":queued_job_id}
    monkeypatch.setattr(service,"sync_source",retryable_failure)
    monkeypatch.setattr(tasks.sync_source_task,"retry",lambda **kwargs:Retry("isolated retry simulation"))
    try:
        with pytest.raises(Retry):
            tasks.sync_source_task.run("furas","scheduled","corr",job_id,"reservation-1")
        with sessions() as db:
            job=db.get(SyncJob,job_id)
            assert job.status==job.job_state=="RETRYING" and job.finished_at is None
    finally:
        engine.dispose()


def test_stale_retrying_job_is_recovered_after_task_and_lock_disappear(monkeypatch):
    engine, sessions, redis, job_id, source_id, queued = setup_recovery(monkeypatch, task_id="retry-task")
    with sessions() as db:
        job=db.get(SyncJob,job_id);job.status=job.job_state="RETRYING";db.commit()
    try:
        result=tasks.recover_stale_jobs()
        with sessions() as db:
            job=db.get(SyncJob,job_id)
            assert job.status==job.job_state=="ABANDONED"
            assert job.finished_at is not None and job.pagination_complete is False
        assert result["abandoned_running"]==1
        assert queued==[("furas","retry")]
    finally:
        engine.dispose()

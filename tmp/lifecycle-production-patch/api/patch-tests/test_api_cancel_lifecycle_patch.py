from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.celery_app import celery_app
from app.models import Base, Source, SyncJob


@pytest.fixture
def api_db(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(main,"SessionLocal",factory)
    monkeypatch.setattr(celery_app.control,"revoke",lambda *args,**kwargs:None)
    token=main.request_context.set({"user":{"role":"admin"},"path":"/api/admin/jobs/1/cancel","method":"POST"})
    with factory() as db:
        source=Source(source_key="fixture",source_name_ar="fixture",organization_name="fixture",
            base_url="https://fixture.invalid",opportunities_url="https://fixture.invalid/list",
            enabled=True,priority=1)
        db.add(source);db.flush()
        job=SyncJob(source_id=source.id,queued_at=datetime.now(timezone.utc),started_at=datetime.now(timezone.utc),
            status="QUEUED",job_state="QUEUED",celery_task_id="fixture-task",pagination_complete=False)
        db.add(job);db.commit()
        yield factory,job.id
    main.request_context.reset(token)
    engine.dispose()


def test_api_cancel_endpoint_uses_guarded_terminal_transition(api_db):
    factory,job_id=api_db
    result=main.cancel_queued_job(job_id,"unused")
    assert result=={"ok":True,"status":"CANCELLED"}
    with factory() as db:
        job=db.get(SyncJob,job_id)
        assert job.status==job.job_state=="CANCELLED"
        assert job.finished_at is not None


def test_api_cancel_rejects_already_terminal_job_without_regression(api_db):
    factory,job_id=api_db
    with factory() as db:
        job=db.get(SyncJob,job_id)
        job.status="SUCCESS";job.job_state="COMPLETED";job.finished_at=datetime.now(timezone.utc)
        db.commit()
    with pytest.raises(HTTPException) as exc:
        main.cancel_queued_job(job_id,"unused")
    assert exc.value.status_code==409
    with factory() as db:
        job=db.get(SyncJob,job_id)
        assert job.status=="SUCCESS" and job.job_state=="COMPLETED"

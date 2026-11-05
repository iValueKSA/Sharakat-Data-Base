from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app import main, security
from app.models import Base, User
from app.security import hash_password, verify_password
from app import tasks
from app.models import Source, SyncJob
from types import SimpleNamespace


def client_with_users(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(main,"SessionLocal",sessions)
    monkeypatch.setattr(security,"SessionLocal",sessions)
    with sessions() as db:
        for role in ("admin","analyst","viewer"):
            db.add(User(email=f"{role}@example.test",display_name=role,role=role,password_hash=hash_password("Correct-Horse-Battery-7!"),is_active=True))
        db.commit()
    monkeypatch.setenv("ENVIRONMENT","test")
    return TestClient(main.app),engine


def test_scrypt_password_hash_is_salted_and_verified():
    first=hash_password("Correct-Horse-Battery-7!")
    second=hash_password("Correct-Horse-Battery-7!")
    assert first.startswith("scrypt$") and first!=second
    assert verify_password("Correct-Horse-Battery-7!",first)
    assert not verify_password("wrong",first)


def test_production_proxy_trust_requires_explicit_addresses():
    assert main.validate_forwarded_allow_ips(" 172.31.240.10, 10.0.0.5/32 ")=="172.31.240.10,10.0.0.5/32"
    import pytest
    with pytest.raises(RuntimeError,match="explicit trusted proxy"):
        main.validate_forwarded_allow_ips("*")
    with pytest.raises(RuntimeError,match="explicit trusted proxy"):
        main.validate_forwarded_allow_ips("  ")


def test_login_cookie_and_role_authorization(monkeypatch):
    client,engine=client_with_users(monkeypatch)
    try:
        login=client.post("/api/auth/login",json={"email":"viewer@example.test","password":"Correct-Horse-Battery-7!"})
        assert login.status_code==200
        assert login.cookies.get("alahsa_session")
        assert login.headers.get("set-cookie").lower().find("httponly")>=0
        assert client.get("/api/auth/me").json()["user"]["role"]=="viewer"
        assert client.get("/api/admin/users").status_code==403
        assert client.post("/api/admin/conflicts/999/keep",json={"note":"This viewer decision should be denied."}).status_code==403
        assert client.post("/api/auth/logout").status_code==200
        assert client.get("/api/auth/me").status_code==401
    finally:
        client.close();engine.dispose()


def test_analyst_can_review_but_cannot_manage_users(monkeypatch):
    client,engine=client_with_users(monkeypatch)
    try:
        assert client.post("/api/auth/login",json={"email":"analyst@example.test","password":"Correct-Horse-Battery-7!"}).status_code==200
        assert client.get("/api/admin/duplicates").status_code==200
        assert client.get("/api/admin/users").status_code==403
    finally:
        client.close();engine.dispose()


def test_login_rejects_unexpected_fields(monkeypatch):
    client,engine=client_with_users(monkeypatch)
    try:
        response=client.post("/api/auth/login",json={"email":"admin@example.test","password":"Correct-Horse-Battery-7!","role":"admin"})
        assert response.status_code==422
    finally:
        client.close();engine.dispose()


def test_redis_reservation_skips_duplicate_source_sync(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(tasks,"SessionLocal",sessions)
    source_data=__import__("app.service",fromlist=["DEFAULT_SOURCES"]).DEFAULT_SOURCES[0]
    with sessions() as db:
        db.add(Source(**source_data,enabled=True));db.commit()
    class FakeRedis:
        occupied=set()
        def set(self,key,value,nx=False,ex=None):
            if nx and key in self.occupied:return False
            self.occupied.add(key);return True
    fake=FakeRedis();sent=[]
    monkeypatch.setattr(tasks,"redis_client",lambda:fake)
    monkeypatch.setattr(tasks.celery_app,"send_task",lambda *args,**kwargs:(sent.append((args,kwargs)) or SimpleNamespace(id="task-1")))
    try:
        first=tasks.enqueue_source("furas","manual","corr-1")
        second=tasks.enqueue_source("furas","manual","corr-2")
        assert first["status"]=="QUEUED" and first["job_id"]
        assert second["status"]=="SKIPPED_ALREADY_RUNNING"
        assert len(sent)==1
        with sessions() as db:
            job=db.get(SyncJob,first["job_id"])
            assert job.job_state=="QUEUED" and job.trigger_type=="manual" and job.correlation_id=="corr-1"
    finally:
        engine.dispose()


def test_retry_backoff_is_bounded_and_jittered(monkeypatch):
    monkeypatch.setattr(tasks.random,"randint",lambda low,high:high)
    assert [tasks.retry_delay(i) for i in range(4)]==[90,330,930,3630]


def test_deadline_alerts_are_configurable_deduplicated_and_skip_expired(monkeypatch):
    from datetime import date, datetime, timedelta, timezone
    from app.models import Opportunity, AlertEvent

    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(tasks,"SessionLocal",sessions)
    monkeypatch.setenv("DEADLINE_ALERT_DAYS","14,3")
    now=datetime.now(timezone.utc)

    def opportunity(identifier, deadline, status="متاحة"):
        return Opportunity(canonical_id=identifier,title_ar=identifier,normalized_title=identifier,
            primary_publication_platform="Test",submission_deadline=deadline,status=status,
            first_seen_at=now,last_seen_at=now,last_updated_at=now,created_at=now,updated_at=now)

    with sessions() as db:
        db.add_all([
            opportunity("two-weeks",(date.today()+timedelta(days=14)).isoformat()),
            opportunity("three-days",(date.today()+timedelta(days=3)).isoformat()),
            opportunity("expired",(date.today()-timedelta(days=1)).isoformat()),
            opportunity("cancelled",(date.today()+timedelta(days=14)).isoformat(),"CANCELLED"),
        ])
        db.commit()

    try:
        assert tasks.check_deadlines()=={"created":2,"thresholds":[3,14]}
        assert tasks.check_deadlines()=={"created":0,"thresholds":[3,14]}
        with sessions() as db:
            alerts=db.query(AlertEvent).all()
            assert len(alerts)==2
            assert {alert.payload["days_remaining"] for alert in alerts}=={3,14}
    finally:
        engine.dispose()


def test_date_only_deadline_remaining_days_keeps_today_actionable():
    from datetime import date, timedelta
    from app.tasks import deadline_days_left
    today = date(2026, 10, 21)
    assert deadline_days_left(today.isoformat(), today) == 0
    assert deadline_days_left((today - timedelta(days=1)).isoformat(), today) is None
    assert deadline_days_left((today + timedelta(days=1)).isoformat(), today) == 1
    assert deadline_days_left("2026-10-20T22:30:00Z", today) == 0
    assert deadline_days_left("2026-10-21T00:30:00", today) is None


def test_health_metrics_and_streamed_exports(monkeypatch):
    client,engine=client_with_users(monkeypatch)
    try:
        assert client.get("/health/live").json()["status"]=="ok"
        assert client.get("/health/ready").json()["status"]=="ready"
        assert "api_requests_total" in client.get("/metrics").text
        assert client.get("/api/export.csv").status_code==200
        assert client.get("/api/export.xlsx").status_code==200
        assert main.spreadsheet_safe("=1+1")=="'=1+1"
        assert main.spreadsheet_safe(-125)==-125
    finally:
        client.close();engine.dispose()

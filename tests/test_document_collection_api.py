from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main, security
from app.models import Base, Source, User


@pytest.fixture
def api_client(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(main,"SessionLocal",factory)
    monkeypatch.setattr(security,"SessionLocal",factory)
    monkeypatch.setenv("ENVIRONMENT","local_user")
    with factory.begin() as db:
        db.add(Source(source_key="furas",source_name_ar="فرص",organization_name="جهة رسمية",
            base_url="https://furas.momah.gov.sa",opportunities_url="https://furas.momah.gov.sa/ar/list-opportunities",
            source_type="official",enabled=True,technical_health="UNKNOWN",coverage_status="UNKNOWN_COVERAGE"))
    client=TestClient(main.app)
    try:
        yield client,factory
    finally:
        client.close();engine.dispose()


def _session_cookie(factory,role):
    now=datetime.now(timezone.utc)
    with factory.begin() as db:
        user=User(email=f"{role}@example.test",display_name=role,role=role,password_hash="fixture",
            is_active=True,created_at=now)
        db.add(user);db.flush()
        token=security.new_session(db,user)
    return token


def test_collection_admin_api_requires_session_and_uses_existing_rbac(api_client):
    client,factory=api_client
    path="/api/admin/document-collection/candidates"
    assert client.get(path).status_code==401
    viewer=_session_cookie(factory,"viewer")
    response=client.get(path,cookies={security.SESSION_COOKIE:viewer})
    assert response.status_code==200 and response.json()["items"]==[]
    denied=client.post(path+"/1/approve",json={"reason":"Reviewed evidence"},
        cookies={security.SESSION_COOKIE:viewer})
    assert denied.status_code==403,denied.text
    admin=_session_cookie(factory,"admin")
    capabilities=client.get("/api/admin/document-collection/capabilities",cookies={security.SESSION_COOKIE:admin})
    assert capabilities.status_code==200
    result={row["source_key"]:row["status"] for row in capabilities.json()["capabilities"]}
    assert result=={"furas":"IMPLEMENTED"}
    assert capabilities.json()["scheduling_configured"] is False
    assert capabilities.json()["flags"]=={
        "engine":False,"manual_collection":False,"scheduled_collection":False,
        "candidate_staging":False,"automatic_approval":False,"automatic_publication":False}


from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.models import AuditEvent, Base, Opportunity, OpportunityConflict, Source, SourceOpportunity, SystemEvent


def test_field_review_requires_actor_and_records_atomic_complete_decision(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(main,"SessionLocal",factory)
    monkeypatch.setenv("ADMIN_TOKEN","review-test-token")
    now=datetime.now(timezone.utc)
    with factory() as db:
        source=Source(source_key="fixture",source_name_ar="مصدر تجريبي",organization_name="fixture",
            base_url="https://example.test",opportunities_url="https://example.test",priority=1)
        db.add(source);db.flush()
        master=Opportunity(canonical_id="REVIEW-1",title_ar="فرصة اختبار",normalized_title="فرصة اختبار",
            opportunity_owner="جهة أ",primary_publication_platform="مصدر تجريبي",city="الأحساء",sector="تجاري",
            status="منشورة",location_confidence_score=.9,location_detection_method="fixture",location_evidence="fixture",
            data_quality_score=.9,manual_review_required=False,first_seen_at=now,last_seen_at=now,last_updated_at=now,
            created_at=now,updated_at=now)
        db.add(master);db.flush()
        record=SourceOpportunity(source_id=source.id,master_opportunity_id=master.id,source_opportunity_id="fixture-1",
            source_title="فرصة اختبار",normalized_source_title="فرصة اختبار",source_url="https://example.test/1",
            source_owner="جهة أ",raw_location="الأحساء",raw_status="منشورة",canonical_status="منشورة",
            raw_data_json={"immutable":"original"},raw_dates={},first_seen_at=now,last_seen_at=now,
            content_hash="a"*64,parser_version="fixture")
        db.add(record);db.flush()
        conflict=OpportunityConflict(opportunity_id=master.id,field_name="sector",conflict_type="TAXONOMY_CONFLICT",
            selected_value="تجاري",conflicting_value="صناعي",source_id=source.id,source_record_id=record.id,
            detected_at=now,status="OPEN")
        db.add(conflict);db.commit();conflict_id=conflict.id;record_id=record.id
        duration_review=OpportunityConflict(opportunity_id=master.id,field_name="contract_duration_years",conflict_type="STANDARDIZATION_REVIEW",
            selected_value="",conflicting_value="TemporaryRental",source_id=source.id,source_record_id=record.id,
            detected_at=now,status="OPEN")
        db.add(duration_review);db.flush();duration_id=duration_review.id
        value_review=OpportunityConflict(opportunity_id=master.id,field_name="investment_value",conflict_type="STANDARDIZATION_REVIEW",
            selected_value="",conflicting_value="0",source_id=source.id,source_record_id=record.id,
            detected_at=now,status="OPEN")
        db.add(value_review);db.commit();value_id=value_review.id
    client=TestClient(main.app)
    note={"note":"Reviewed the attached source evidence and selected its canonical value."}
    path=f"/api/admin/conflicts/{conflict_id}/use_source"
    assert client.post(path,json=note).status_code==401
    headers={"X-Admin-Token":"review-test-token"}
    queue=client.get("/api/admin/review-queue?domain=taxonomy_conflict&status=OPEN",headers=headers)
    assert queue.status_code==200 and len(queue.json())==1
    assert queue.json()[0]["priority"]=="P2" and queue.json()[0]["age_days"]>=0
    duration_queue=client.get("/api/admin/review-queue?domain=field_conflict&status=OPEN",headers=headers)
    duration_item=next(item for item in duration_queue.json() if item["id"]==duration_id)
    assert duration_item["reason_key"]=="DURATION_UNIT_OR_SEMANTICS_UNVERIFIED"
    assert duration_item["reason_label"]=="وحدة أو دلالة مدة المصدر غير موثقة"
    value_item=next(item for item in duration_queue.json() if item["id"]==value_id)
    assert value_item["reason_key"]=="INVESTMENT_VALUE_ZERO_WITHOUT_UNIT_OR_MEANING"
    blocked_promotion=client.post(f"/api/admin/conflicts/{duration_id}/use_source",headers=headers,json=note)
    assert blocked_promotion.status_code==409
    assert client.post(f"/api/admin/conflicts/{value_id}/use_source",headers=headers,json=note).status_code==409
    assert client.post(f"/api/admin/conflicts/{duration_id}/keep",headers=headers,json=note).status_code==200
    assert client.post(f"/api/admin/conflicts/{value_id}/keep",headers=headers,json=note).status_code==200
    assert client.post(path,headers=headers,json={"note":"short"}).status_code==422
    response=client.post(path,headers=headers,json=note)
    assert response.status_code==200
    assert client.post(path,headers=headers,json=note).status_code==409
    resolved=client.get("/api/admin/review-queue?domain=taxonomy_conflict&status=RESOLVED",headers=headers)
    assert resolved.status_code==200 and len(resolved.json())==1
    assert resolved.json()[0]["status"]=="RESOLVED"
    with factory() as db:
        master=db.scalar(select(Opportunity).where(Opportunity.canonical_id=="REVIEW-1"))
        record=db.get(SourceOpportunity,record_id)
        conflict=db.get(OpportunityConflict,conflict_id)
        event=db.scalar(select(AuditEvent).where(AuditEvent.entity_type=="opportunity_conflict",AuditEvent.entity_id==str(conflict_id)))
        assert master.sector=="صناعي" and conflict.status=="RESOLVED_SOURCE"
        assert record.raw_data_json=={"immutable":"original"} and record.content_hash=="a"*64
        assert event.before_json["value"]=="تجاري" and event.after_json["value"]=="صناعي"
        assert event.after_json["reason"]==note["note"]
        assert event.after_json["evidence"]["source_record_id"]==record_id
        duration_event=db.scalar(select(AuditEvent).where(AuditEvent.entity_type=="opportunity_conflict",AuditEvent.entity_id==str(duration_id)))
        assert db.get(Opportunity,master.id).contract_duration_years is None
        assert db.get(OpportunityConflict,duration_id).status=="RESOLVED_KEEP"
        assert duration_event.before_json["value"] is None and duration_event.after_json["value"] is None
        value_event=db.scalar(select(AuditEvent).where(AuditEvent.entity_type=="opportunity_conflict",AuditEvent.entity_id==str(value_id)))
        assert db.get(Opportunity,master.id).investment_value is None
        assert db.get(OpportunityConflict,value_id).status=="RESOLVED_KEEP"
        assert value_event.before_json["value"] is None and value_event.after_json["value"] is None
        from app.service import canonical_duplicate_pair, queue_conflict_idempotently
        assert canonical_duplicate_pair(9,4)==canonical_duplicate_pair(4,9)==(4,9)
        second=OpportunityConflict(opportunity_id=master.id,field_name="sector",conflict_type="TAXONOMY_CONFLICT",
            selected_value="صناعي",conflicting_value="خدمي",source_id=record.source_id,source_record_id=record.id,
            detected_at=now,status="OPEN")
        db.add(second);db.commit();second_id=second.id
        reopened=queue_conflict_idempotently(db,opportunity_id=master.id,field_name="sector",conflict_type="TAXONOMY_CONFLICT",
            selected_value="تجاري",conflicting_value="صناعي",source_id=record.source_id,source_record_id=record.id,detected_at=now)
        assert reopened is not None
        assert queue_conflict_idempotently(db,opportunity_id=master.id,field_name="sector",conflict_type="TAXONOMY_CONFLICT",
            selected_value="تجاري",conflicting_value="صناعي",source_id=record.source_id,source_record_id=record.id,detected_at=now) is None
        db.flush()
        assert reopened.status=="OPEN"
        assert db.scalar(select(SystemEvent).where(SystemEvent.event_type=="REVIEW_REOPENED")) is not None

    original_audit=main._review_audit
    def fail_audit(*args,**kwargs):raise RuntimeError("fixture audit failure")
    monkeypatch.setattr(main,"_review_audit",fail_audit)
    atomic_client=TestClient(main.app,raise_server_exceptions=False)
    failed=atomic_client.post(f"/api/admin/conflicts/{second_id}/use_source",headers=headers,json={"note":"Attempting source value to test rollback behavior."})
    assert failed.status_code==500
    with factory() as db:
        master=db.scalar(select(Opportunity).where(Opportunity.canonical_id=="REVIEW-1"))
        assert master.sector=="صناعي" and db.get(OpportunityConflict,second_id).status=="OPEN"
    monkeypatch.setattr(main,"_review_audit",original_audit)

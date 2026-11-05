from datetime import datetime, timezone
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.models import AuditEvent, Base, DuplicateCandidate, FieldProvenance, LocationReview, Opportunity, OpportunityConflict, QualificationReview, Source, SourceObservation, SourceOpportunity, SystemEvent


def workbench_fixture(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "allow_rate", lambda *args, **kwargs: True)
    monkeypatch.setenv("ADMIN_TOKEN", "workbench-test-token")
    now = datetime.now(timezone.utc)
    with factory() as db:
        source = Source(source_key="fixture", source_name_ar="مصدر تجريبي", organization_name="fixture",
            base_url="https://example.test", opportunities_url="https://example.test/opportunities", priority=1)
        db.add(source); db.flush()
        master = Opportunity(canonical_id="WB-1", title_ar="فرصة عمل تجريبية", normalized_title="فرصة عمل تجريبية",
            opportunity_owner="المالك", primary_publication_platform="الناشر", city="الأحساء", district="الهفوف",
            sector="تجاري", activity="تجزئة", status="منشورة", location_confidence_score=.9,
            location_detection_method="fixture", location_evidence="source", data_quality_score=.9,
            manual_review_required=False, first_seen_at=now, last_seen_at=now, last_updated_at=now,
            created_at=now, updated_at=now)
        db.add(master); db.flush()
        record = SourceOpportunity(source_id=source.id, master_opportunity_id=master.id, source_opportunity_id="wb-1",
            source_title="فرصة عمل تجريبية", normalized_source_title="فرصة عمل تجريبية", source_url="https://example.test/item/1",
            source_owner="المالك", raw_location="الهفوف", raw_status="منشورة", canonical_status="منشورة",
            raw_data_json={"sector": "صناعي", "description": "وصف موثق", "attributes": {"AREA": 100}},
            standardized_data_json={"fields": {"sector": {"value": "صناعي", "rule": "EXACT_TEST"}}}, raw_dates={},
            first_seen_at=now, last_seen_at=now, content_hash="a" * 64, parser_version="fixture")
        db.add(record); db.flush()
        conflict = OpportunityConflict(opportunity_id=master.id, field_name="sector", conflict_type="TAXONOMY_CONFLICT",
            selected_value="تجاري", conflicting_value="صناعي", source_id=source.id, source_record_id=record.id,
            detected_at=now, status="OPEN")
        db.add(conflict); db.flush()
        db.add(FieldProvenance(opportunity_id=master.id, field_name="sector", selected_value="تجاري", source_id=source.id,
            source_record_id=record.id, captured_at=now, confidence=.9))
        observation = SourceObservation(source_opportunity_id=record.id, dataset_name="fixture", endpoint="fixture",
            official_source_id_original="wb-1", official_source_id_normalized="wb-1", raw_data_json={"sector": "صناعي"},
            source_updated_at=now.isoformat(), content_hash="b" * 64, first_seen_at=now, last_seen_at=now)
        db.add(observation); db.commit()
        conflict_id, master_id, record_id = conflict.id, master.id, record.id
        db.add(SourceOpportunity(source_id=source.id, master_opportunity_id=master.id, source_opportunity_id="wb-2",
            source_title="فرصة عمل تجريبية نسخة مصدرية", normalized_source_title="فرصة عمل تجريبية", source_url="https://example.test/item/2",
            source_owner=None, raw_location=None, raw_status=None, canonical_status="غير محددة", raw_data_json={},
            standardized_data_json={}, raw_dates={}, first_seen_at=now, last_seen_at=now, content_hash="c" * 64, parser_version="fixture"))
        db.commit()
        return factory, engine, conflict_id, master_id, record_id


def test_review_workbench_detail_returns_comparison_sources_history_and_version(monkeypatch):
    factory, engine, review_id, master_id, record_id = workbench_fixture(monkeypatch)
    try:
        response = TestClient(main.app).get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",
            headers={"X-Admin-Token": "workbench-test-token"})
        assert response.status_code == 200
        detail = response.json()
        assert detail["comparison"]["current_value"] == "تجاري"
        assert detail["comparison"]["competing_values"][0]["value"] == "صناعي"
        assert detail["linked_source_count"] == 2
        assert detail["sources"][0]["source_record_id"] == record_id
        assert detail["sources"][0]["source_opportunity_id"] == "wb-1"
        assert detail["sources"][0]["mapping_rule"] == "EXACT_TEST"
        assert len(detail["history"]) == 1
        assert len(detail["version_token"]) == 64
        assert {item["key"] for item in detail["allowed_actions"]} == {"keep", "use_source"}
    finally:
        engine.dispose()


def test_review_workbench_decision_preview_is_read_only_and_rejects_stale_version(monkeypatch):
    factory, engine, review_id, master_id, record_id = workbench_fixture(monkeypatch)
    try:
        client = TestClient(main.app)
        headers = {"X-Admin-Token": "workbench-test-token"}
        detail = client.get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}", headers=headers).json()
        preview = client.post(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}/preview?action=use_source&version_token={detail['version_token']}", headers=headers)
        assert preview.status_code == 200
        assert preview.json()["impacts"][0]["before"] == "تجاري"
        assert preview.json()["impacts"][0]["after"] == "صناعي"
        with factory() as db:
            assert db.get(Opportunity, master_id).sector == "تجاري"
            assert db.get(OpportunityConflict, review_id).status == "OPEN"
        stale = client.post(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}/preview?action=keep&version_token={'0' * 64}", headers=headers)
        assert stale.status_code == 409
        missing_token = client.post(f"/api/admin/conflicts/{review_id}/keep", headers=headers,
            json={"note":"Attempted decision without a current review version."})
        assert missing_token.status_code == 409
        stale_commit = client.post(f"/api/admin/conflicts/{review_id}/keep", headers=headers,
            json={"note":"Attempted decision with an outdated review version.","version_token":"0" * 64})
        assert stale_commit.status_code == 409
        response = client.post(f"/api/admin/conflicts/{review_id}/keep", headers=headers,
            json={"note": "Reviewed this source evidence and retained the current canonical value.", "version_token": detail["version_token"]})
        assert response.status_code == 200
        with factory() as db:
            assert db.get(OpportunityConflict, review_id).status == "RESOLVED_KEEP"
            event = db.scalar(select(AuditEvent).where(AuditEvent.entity_type == "opportunity_conflict", AuditEvent.entity_id == str(review_id)))
            assert event is not None and event.after_json["evidence"]["source_record_id"] == record_id
    finally:
        engine.dispose()


def test_reviewer_action_contract_disallows_viewer_and_ambiguous_recommendation(monkeypatch):
    factory, engine, review_id, master_id, record_id = workbench_fixture(monkeypatch)
    try:
        with factory() as db:
            item = main.review_queue("workbench-test-token", "taxonomy_conflict", "OPEN", 10)[0]
            detail = main._workbench_detail(db, item)
            assert main._workbench_allowed_actions(detail, "viewer") == []
            assert detail["recommendation"]["action"] is None
            assert detail["recommendation"]["confidence"] == "NONE"
            assert detail["recommendation"]["reason"]
    finally:
        engine.dispose()


def test_pilot_mode_serves_fixed_cohort_and_records_keep_open_feedback_without_business_change(monkeypatch,tmp_path):
    factory,engine,review_id,master_id,record_id=workbench_fixture(monkeypatch)
    pilot_file=tmp_path/"pilot.json"
    pilot_file.write_text(json.dumps({"pilot_id":"fixture-pilot","metrics_purpose":"WORKFLOW_CALIBRATION_ONLY",
        "phase_counts":{"A":1,"B":0},"cases":[{"review_id":review_id,"review_id_key":f"taxonomy_conflict:{review_id}",
        "phase":"A","pilot_sequence":1,"type":"taxonomy_conflict","subtype":"sector"}]}),encoding="utf-8")
    monkeypatch.setattr(main,"PILOT_COHORT_PATH",pilot_file)
    client=TestClient(main.app); headers={"X-Admin-Token":"workbench-test-token"}
    try:
        current=client.get("/api/admin/review-workbench/pilot",headers=headers)
        assert current.status_code==200
        assert current.json()["started"] is False
        assert current.json()["cases"][0]["review_id_key"]==f"taxonomy_conflict:{review_id}"
        assert current.json()["cases"][0]["available"] is True
        assert client.post("/api/admin/review-workbench/pilot/events",headers=headers,json={
            "pilot_id":"fixture-pilot","event_kind":"PILOT_STARTED"}).status_code==200
        blocked=client.post("/api/admin/review-workbench/pilot/events",headers=headers,json={
            "pilot_id":"fixture-pilot","event_kind":"PHASE_A_REVIEWED","reason":"premature phase review"})
        assert blocked.status_code==409
        feedback={"evidence_sufficiency":"PARTIAL","decision_clarity":"YES","recommendation_helpfulness":"NONE",
            "actions_appropriate":"YES","missing_evidence_note":""}
        saved=client.post("/api/admin/review-workbench/pilot/events",headers=headers,json={
            "pilot_id":"fixture-pilot","event_kind":"CASE_OUTCOME","review_id_key":f"taxonomy_conflict:{review_id}",
            "phase":"A","outcome":"KEPT_OPEN","feedback":feedback,
            "metrics":{"recommendation_available":False,"handling_time_seconds":12.0}})
        assert saved.status_code==200
        assert client.post("/api/admin/review-workbench/pilot/events",headers=headers,json={
            "pilot_id":"fixture-pilot","event_kind":"CASE_OUTCOME","review_id_key":f"taxonomy_conflict:{review_id}",
            "phase":"A","outcome":"KEPT_OPEN","feedback":feedback,"metrics":{}}).status_code==409
        phase_review=client.post("/api/admin/review-workbench/pilot/events",headers=headers,json={
            "pilot_id":"fixture-pilot","event_kind":"PHASE_A_REVIEWED","reason":"Reviewed evidence and workflow findings."})
        assert phase_review.status_code==200
        assert client.get("/api/admin/review-workbench/pilot",headers=headers).json()["active_phase"]=="B"
        with factory() as db:
            assert db.get(OpportunityConflict,review_id).status=="OPEN"
            assert db.get(Opportunity,master_id).sector=="تجاري"
            events=db.scalars(select(SystemEvent).where(SystemEvent.event_type=="HUMAN_REVIEW_PILOT_EVENT")).all()
            case_event=next(event for event in events if (event.payload or {}).get("event_kind")=="CASE_OUTCOME")
            assert case_event.payload["metrics_purpose"]=="WORKFLOW_CALIBRATION_ONLY"
            assert case_event.payload["feedback"]["evidence_sufficiency"]=="PARTIAL"
            assert not db.scalars(select(AuditEvent).where(AuditEvent.entity_type=="opportunity_conflict",
                AuditEvent.entity_id==str(review_id),AuditEvent.event_type.in_(("REVIEW_FIELD_KEEP","REVIEW_FIELD_USE_SOURCE")))).all()
    finally:
        engine.dispose()


def test_pilot_resolution_requires_human_audit_and_source_recheck_is_audited_and_non_resolving(monkeypatch,tmp_path):
    factory,engine,review_id,master_id,record_id=workbench_fixture(monkeypatch)
    pilot_file=tmp_path/"pilot.json"
    pilot_file.write_text(json.dumps({"pilot_id":"fixture-pilot","metrics_purpose":"WORKFLOW_CALIBRATION_ONLY",
        "phase_counts":{"A":1,"B":0},"cases":[{"review_id":review_id,"review_id_key":f"taxonomy_conflict:{review_id}",
        "phase":"A","pilot_sequence":1,"type":"taxonomy_conflict","subtype":"sector"}]}),encoding="utf-8")
    monkeypatch.setattr(main,"PILOT_COHORT_PATH",pilot_file)
    client=TestClient(main.app); headers={"X-Admin-Token":"workbench-test-token"}
    feedback={"evidence_sufficiency":"NO","decision_clarity":"NO","recommendation_helpfulness":"NONE",
        "actions_appropriate":"YES","missing_evidence_note":"The source context was insufficient."}
    try:
        assert client.post("/api/admin/review-workbench/pilot/events",headers=headers,json={
            "pilot_id":"fixture-pilot","event_kind":"PILOT_STARTED"}).status_code==200
        denied=client.post("/api/admin/review-workbench/pilot/events",headers=headers,json={
            "pilot_id":"fixture-pilot","event_kind":"CASE_OUTCOME","review_id_key":f"taxonomy_conflict:{review_id}",
            "phase":"A","outcome":"RESOLVED","feedback":feedback,"metrics":{}})
        assert denied.status_code==409
        with factory() as db:
            assert db.get(OpportunityConflict,review_id).status=="OPEN"
        requested=client.post("/api/admin/review-workbench/pilot/events",headers=headers,json={
            "pilot_id":"fixture-pilot","event_kind":"CASE_OUTCOME","review_id_key":f"taxonomy_conflict:{review_id}",
            "phase":"A","outcome":"SOURCE_RECHECK_REQUIRED","reason":"Verify the project value with the publisher.",
            "feedback":feedback,"metrics":{}})
        assert requested.status_code==200
        queue=main.review_queue("workbench-test-token","taxonomy_conflict","OPEN",10)
        assert queue[0]["disposition"]=="SOURCE_RECHECK_REQUIRED"
        with factory() as db:
            assert db.get(OpportunityConflict,review_id).status=="OPEN"
            recheck=db.scalar(select(AuditEvent).where(AuditEvent.event_type=="REVIEW_SOURCE_RECHECK_REQUESTED",
                AuditEvent.entity_id==str(review_id)))
            assert recheck and recheck.request_metadata["decision_kind"]=="HUMAN"
    finally:
        engine.dispose()


def test_source_recheck_evidence_is_not_actionable_and_missing_source_value_is_not_conflict(monkeypatch):
    factory, engine, review_id, master_id, record_id = workbench_fixture(monkeypatch)
    try:
        now = datetime.now(timezone.utc)
        with factory() as db:
            db.add(AuditEvent(user_id=None, event_type="REVIEW_EVIDENCE_ENRICHED", entity_type="review_evidence",
                entity_id=f"opportunity_conflict:{review_id}", before_json=None, after_json={"review_type": "OPPORTUNITY_CONFLICT",
                "review_id": review_id, "classification": "SOURCE_RECHECK_REQUIRED", "evidence": []},
                request_metadata={"actor": "SYSTEM"}, created_at=now))
            db.commit()
            # Missing values are represented by the assessment as missing, not conflict.
            row = main.review_queue("workbench-test-token", "taxonomy_conflict", "OPEN", 10)[0]
            assert row["disposition"] == "SOURCE_RECHECK_REQUIRED"
            assert main.review_queue("workbench-test-token", "taxonomy_conflict", "OPEN", 10, exclude_source_recheck=True) == []
            comparison = main._workbench_detail(db, row)["comparison"]
            assert comparison["assessment"] == "MISSING_VALUE"
            detail_response = TestClient(main.app).get(
                f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",
                headers={"X-Admin-Token": "workbench-test-token"})
            assert detail_response.status_code == 200
            assert detail_response.json()["disposition"] == "SOURCE_RECHECK_REQUIRED"
            blocked_decision = TestClient(main.app).post(
                f"/api/admin/conflicts/{review_id}/keep", headers={"X-Admin-Token": "workbench-test-token"},
                json={"note":"Cannot resolve before source recheck is complete.",
                      "version_token":detail_response.json()["version_token"]})
            assert blocked_decision.status_code == 409
            assert db.get(OpportunityConflict, review_id).status == "OPEN"
    finally:
        engine.dispose()


def test_unlinked_location_review_keeps_its_source_evidence_visible(monkeypatch):
    factory, engine, conflict_id, master_id, record_id = workbench_fixture(monkeypatch)
    now = datetime.now(timezone.utc)
    try:
        with factory() as db:
            record = db.get(SourceOpportunity, record_id)
            record.master_opportunity_id = None
            review = LocationReview(source_id=record.source_id, source_record_id=record.id,
                external_id=record.source_opportunity_id, title=record.source_title, sector="تجاري",
                source_location="الهفوف", description="وصف موثق", evidence="حقل الموقع", confidence_score=.7,
                reason="تحقق من الموقع", status="PENDING", created_at=now)
            db.add(review); db.commit(); review_id = review.id
        response = TestClient(main.app).get(
            f"/api/admin/review-workbench/location/{review_id}",
            headers={"X-Admin-Token": "workbench-test-token"})
        assert response.status_code == 200
        detail = response.json()
        assert detail["master_ids"] == []
        assert detail["linked_source_count"] == 1
        assert detail["sources"][0]["source_record_id"] == record_id
        assert detail["sources"][0]["source_opportunity_id"] == "wb-1"
    finally:
        engine.dispose()


def test_legacy_resolved_review_timeline_marks_missing_audit_without_fabrication(monkeypatch):
    factory, engine, review_id, _master_id, _record_id = workbench_fixture(monkeypatch)
    try:
        with factory() as db:
            review = db.get(OpportunityConflict, review_id)
            review.status = "RESOLVED_KEEP"
            db.commit()
        response = TestClient(main.app).get(
            f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",
            headers={"X-Admin-Token": "workbench-test-token"})
        assert response.status_code == 200
        timeline = response.json()["timeline"]
        legacy = next(event for event in timeline if event["event_type"] == "LEGACY_DECISION_INCOMPLETE")
        assert legacy["label"] == "قرار تاريخي — بعض بيانات التدقيق غير متوفرة"
        assert legacy["legacy_incomplete"] is True
        assert legacy["actor"] == "غير متوفر" and legacy["timestamp"] is None
        assert "لا تتوفر هوية المنفذ أو وقت القرار" in legacy["description"]
        assert legacy["historical_unknown_time"] is True and legacy["timeline_group"]=="HISTORICAL_UNKNOWN_TIME"
        assert timeline[-1]["event_type"]=="LEGACY_DECISION_INCOMPLETE"
        assert legacy.get("reason") is None
        preview=TestClient(main.app).post(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}/reopen/preview?version_token={response.json()['version_token']}",
            headers={"X-Admin-Token":"workbench-test-token"})
        assert preview.status_code==200 and preview.json()["historical_decision_incomplete"] is True
        assert preview.json()["historical_notice"]=="قرار تاريخي — بعض بيانات التدقيق غير متوفرة"
        assert preview.json()["original_actor"] is None and preview.json()["original_timestamp"] is None and preview.json()["original_reason"] is None
    finally:
        engine.dispose()


def test_unified_timeline_uses_stable_event_ids_for_equal_timestamps(monkeypatch):
    factory,engine,review_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        same_time=datetime(2026,10,22,12,0,tzinfo=timezone.utc)
        with factory() as db:
            db.add_all([
                AuditEvent(user_id=None,event_type="REVIEW_FIELD_KEEP",entity_type="opportunity_conflict",entity_id=str(review_id),
                    before_json={"status":"OPEN"},after_json={"status":"RESOLVED_KEEP","decision":"FIELD_KEEP","reason":"Kept after evidence review."},
                    request_metadata={"actor":"Analyst","actor_role":"analyst"},created_at=same_time),
                AuditEvent(user_id=None,event_type="REVIEW_REOPENED",entity_type="opportunity_conflict",entity_id=str(review_id),
                    before_json={"status":"RESOLVED_KEEP"},after_json={"status":"OPEN","reopen_reason":"ظهور دليل جديد"},
                    request_metadata={"actor":"Analyst","actor_role":"analyst"},created_at=same_time),
            ]);db.flush()
            item=main.review_queue("workbench-test-token","taxonomy_conflict","OPEN",10)[0]
            timeline=main._workbench_timeline(db,item,"opportunity_conflict",review_id)
            tied=[event for event in timeline if event["timestamp"]==main.dt(same_time)]
            assert [int(event["event_id"].split(":")[1]) for event in tied]==sorted(int(event["event_id"].split(":")[1]) for event in tied)
            assert all(event["timeline_group"]=="CHRONOLOGICAL" for event in tied)
    finally: engine.dispose()


def _upgrade_fixture_authority(factory, master_id, source_id):
    now = datetime.now(timezone.utc)
    with factory() as db:
        authoritative = db.get(Source, source_id); authoritative.priority=1
        authoritative_record=db.get(SourceOpportunity,db.scalar(select(OpportunityConflict.source_record_id).where(OpportunityConflict.opportunity_id==master_id)))
        authoritative_record.standardized_data_json={"fields":{"sector":{"value":"صناعي","mapping_status":"MAPPED","rule":"EXACT_SOURCE_TAXONOMY_V1"}}}
        lower = Source(source_key="fixture-lower", source_name_ar="مصدر أقل موثوقية", organization_name="lower",
            base_url="https://lower.test", opportunities_url="https://lower.test/opportunities", priority=5)
        db.add(lower); db.flush()
        record=SourceOpportunity(source_id=lower.id,master_opportunity_id=master_id,source_opportunity_id="wb-lower",
            source_title="فرصة مصدر أقل",normalized_source_title="فرصة مصدر أقل",source_url="https://lower.test/item/1",
            source_owner="المالك",raw_location="الهفوف",raw_status="منشورة",canonical_status="منشورة",
            raw_data_json={"sector":"تجاري"},standardized_data_json={"fields":{"sector":{"value":"تجاري","rule":"EXACT_TEST"}}},
            raw_dates={},first_seen_at=now,last_seen_at=now,content_hash="e"*64,parser_version="fixture")
        db.add(record);db.flush()
        provenance=db.scalar(select(FieldProvenance).where(FieldProvenance.opportunity_id==master_id,FieldProvenance.field_name=="sector"))
        provenance.source_id=lower.id;provenance.source_record_id=record.id;provenance.captured_at=now;provenance.confidence=.99
        db.commit()


def _add_matching_conflict(factory, source_id):
    now = datetime.now(timezone.utc)
    with factory() as db:
        source = db.get(Source, source_id)
        master = Opportunity(canonical_id="WB-2", title_ar="فرصة ثانية", normalized_title="فرصة ثانية",
            opportunity_owner="المالك", primary_publication_platform="الناشر", city="الأحساء", sector="تجاري",
            activity="تجزئة", status="منشورة", location_confidence_score=.9, location_detection_method="fixture",
            location_evidence="source", data_quality_score=.9, manual_review_required=False, first_seen_at=now,
            last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
        db.add(master); db.flush()
        record = SourceOpportunity(source_id=source.id, master_opportunity_id=master.id, source_opportunity_id=f"wb-batch-{master.id}",
            source_title="فرصة ثانية", normalized_source_title="فرصة ثانية", source_url="https://example.test/item/2",
            source_owner="المالك", raw_location="الهفوف", raw_status="منشورة", canonical_status="منشورة",
            raw_data_json={"sector":"صناعي"}, standardized_data_json={"fields":{"sector":{"value":"صناعي","rule":"EXACT_TEST"}}},
            raw_dates={}, first_seen_at=now, last_seen_at=now, content_hash="d"*64, parser_version="fixture")
        db.add(record); db.flush()
        conflict=OpportunityConflict(opportunity_id=master.id,field_name="sector",conflict_type="FIELD_VALUE_CONFLICT",
            selected_value="تجاري",conflicting_value="صناعي",source_id=source.id,source_record_id=record.id,
            detected_at=now,status="OPEN")
        db.add(conflict); db.add(FieldProvenance(opportunity_id=master.id,field_name="sector",selected_value="تجاري",
            source_id=source.id,source_record_id=record.id,captured_at=now,confidence=.9)); db.commit()
        return conflict.id, master.id, record.id


def test_authoritative_source_recommendation_snapshot_and_follow_audit(monkeypatch):
    factory, engine, review_id, master_id, record_id = workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id
        _upgrade_fixture_authority(factory,master_id,source_id)
        client=TestClient(main.app); headers={"X-Admin-Token":"workbench-test-token"}
        detail=client.get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",headers=headers).json()
        assert detail["recommendation"]["action"]=="use_source"
        assert detail["recommendation"]["confidence"]=="HIGH"
        shown=client.post(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}/recommendation-shown?version_token={detail['version_token']}",headers=headers)
        assert shown.status_code==200
        response=client.post(f"/api/admin/conflicts/{review_id}/use_source",headers=headers,json={"note":"Approved the explicit higher-authority source value.","version_token":detail["version_token"],"recommendation_version":detail["recommendation_version"]})
        assert response.status_code==200
        with factory() as db:
            decision=db.scalar(select(AuditEvent).where(AuditEvent.event_type=="REVIEW_FIELD_USE_SOURCE",AuditEvent.entity_id==str(review_id)))
            assert decision.after_json["evidence"]["recommendation"]["disposition"]=="FOLLOWED_RECOMMENDATION"
            assert decision.after_json["evidence"]["recommendation"]["version"]==detail["recommendation_version"]
            assert decision.after_json["evidence"]["recommendation"]["supporting_evidence"][0]["source_record_id"]==record_id
    finally: engine.dispose()


def test_recommendation_override_requires_reason_and_is_audited(monkeypatch):
    factory, engine, review_id, master_id, record_id = workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id
        _upgrade_fixture_authority(factory,master_id,source_id)
        client=TestClient(main.app); headers={"X-Admin-Token":"workbench-test-token"}
        detail=client.get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",headers=headers).json()
        rejected=client.post(f"/api/admin/conflicts/{review_id}/keep",headers=headers,json={"note":"Kept the current canonical value after review.","version_token":detail["version_token"],"recommendation_version":detail["recommendation_version"]})
        assert rejected.status_code==422
        accepted=client.post(f"/api/admin/conflicts/{review_id}/keep",headers=headers,json={"note":"Kept the current canonical value after review.","version_token":detail["version_token"],"recommendation_version":detail["recommendation_version"],"recommendation_override_reason":"تعارض في الأدلة","analyst_note":"Manual review supports the current value."})
        assert accepted.status_code==200
        with factory() as db:
            event=db.scalar(select(AuditEvent).where(AuditEvent.event_type=="REVIEW_FIELD_KEEP",AuditEvent.entity_id==str(review_id)))
            recommendation=event.after_json["evidence"]["recommendation"]
            assert recommendation["disposition"]=="OVERRIDDEN_RECOMMENDATION"
            assert recommendation["override_reason"]=="تعارض في الأدلة"
    finally: engine.dispose()


def test_reopen_preview_and_governed_reopen_preserve_resolution_history(monkeypatch):
    factory, engine, review_id, master_id, record_id = workbench_fixture(monkeypatch)
    try:
        client=TestClient(main.app); headers={"X-Admin-Token":"workbench-test-token"}
        detail=client.get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",headers=headers).json()
        decided=client.post(f"/api/admin/conflicts/{review_id}/keep",headers=headers,json={"note":"Keep the canonical value after evidence review.","version_token":detail["version_token"]})
        assert decided.status_code==200
        with factory() as db:
            source_record=db.get(SourceOpportunity,record_id);source_record.content_hash="f"*64;source_record.last_seen_at=datetime.now(timezone.utc);db.commit()
        resolved=client.get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",headers=headers).json()
        preview=client.post(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}/reopen/preview?version_token={resolved['version_token']}",headers=headers)
        assert preview.status_code==200 and preview.json()["original_decision"]=="FIELD_KEEP"
        assert preview.json()["evidence_change_comparison_available"] is True
        assert preview.json()["current_evidence_changes"][0]["source_record_id"]==record_id
        payload={"reason":"ظهور دليل جديد","note":"A new source observation is available.","version_token":resolved["version_token"]}
        reopened=client.post(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}/reopen",headers=headers,json=payload)
        assert reopened.status_code==200 and reopened.json()["status"]=="OPEN"
        with factory() as db:
            events=db.scalars(select(AuditEvent).where(AuditEvent.entity_id==str(review_id)).order_by(AuditEvent.id)).all()
            decision=next(event for event in events if event.event_type=="REVIEW_FIELD_KEEP")
            reopen=next(event for event in events if event.event_type=="REVIEW_REOPENED")
            assert decision.after_json["status"]=="RESOLVED_KEEP"
            assert reopen.before_json["previous_resolution_event_id"]==decision.id
            assert reopen.after_json["reopen_reason"]==payload["reason"]
            assert reopen.after_json["review_id"]==review_id
            assert reopen.after_json["previous_status"]=="RESOLVED_KEEP" and reopen.after_json["new_status"]=="OPEN"
            assert reopen.after_json["review_version"]==resolved["version_token"]
            assert reopen.after_json["previous_resolution_reference"]==decision.id
            assert reopen.after_json["actor_role"]=="admin_token" and reopen.after_json["timestamp"]
            timeline=main._workbench_timeline(db,main.review_queue("workbench-test-token","taxonomy_conflict","OPEN",10)[0],"opportunity_conflict",review_id)
            assert {event["event_type"] for event in timeline}>={"CREATED","RESOLVED","REOPENED"}
    finally: engine.dispose()


def test_reopen_requires_authorized_role_valid_status_reason_and_current_version(monkeypatch):
    factory, engine, review_id, master_id, record_id = workbench_fixture(monkeypatch)
    try:
        client=TestClient(main.app); headers={"X-Admin-Token":"workbench-test-token"}
        detail=client.get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",headers=headers).json()
        open_preview=client.post(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}/reopen/preview?version_token={detail['version_token']}",headers=headers)
        assert open_preview.status_code==409
        with factory() as db: db.get(OpportunityConflict,review_id).status="RESOLVED_KEEP";db.commit()
        resolved=client.get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",headers=headers).json()
        missing=client.post(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}/reopen",headers=headers,json={"reason":" ","version_token":resolved["version_token"]})
        assert missing.status_code==422
        stale=client.post(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}/reopen",headers=headers,json={"reason":"تعارض جديد","version_token":"0"*64})
        assert stale.status_code==409
        monkeypatch.setattr(main,"review_write_auth",lambda token: (_ for _ in ()).throw(main.HTTPException(403,"Insufficient permissions")))
        denied=client.post(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}/reopen/preview?version_token={resolved['version_token']}",headers=headers)
        assert denied.status_code==403
    finally: engine.dispose()


def test_deterministic_batch_preview_commit_has_individual_audits_and_is_idempotent(monkeypatch):
    factory, engine, first_id, master_id, record_id = workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id
        with factory() as db: db.get(OpportunityConflict,first_id).conflict_type="FIELD_VALUE_CONFLICT";db.commit()
        second_id,_,_= _add_matching_conflict(factory,source_id)
        client=TestClient(main.app); headers={"X-Admin-Token":"workbench-test-token"}
        first=client.get(f"/api/admin/review-workbench/field_conflict/{first_id}",headers=headers).json()
        second=client.get(f"/api/admin/review-workbench/field_conflict/{second_id}",headers=headers).json()
        payload={"items":[{"domain":"field_conflict","review_id":first_id,"version_token":first["version_token"],"recommendation_version":first["recommendation_version"]},{"domain":"field_conflict","review_id":second_id,"version_token":second["version_token"],"recommendation_version":second["recommendation_version"]}],"action":"keep","reason":"نمط أدلة متماثل","batch_operation_id":"workbench-batch-test-01","confirm":False}
        preview=client.post("/api/admin/review-workbench/batch/preview",headers=headers,json=payload)
        assert preview.status_code==200 and preview.json()["eligible"] is True
        payload["items"]=preview.json()["items"]
        payload["batch_operation_id"]=preview.json()["batch_operation_id"]
        payload["batch_signature"]=preview.json()["signature"]
        payload["confirm"]=True
        committed=client.post("/api/admin/review-workbench/batch/commit",headers=headers,json=payload)
        assert committed.status_code==200 and committed.json()["policy"]=="ATOMIC_ALL_OR_NONE"
        assert committed.json()["resolved_review_ids"]==[first_id,second_id],(first_id,second_id,preview.json(),committed.json())
        repeated=client.post("/api/admin/review-workbench/batch/commit",headers=headers,json=payload)
        assert repeated.status_code==409
        with factory() as db:
            statuses=[db.get(OpportunityConflict,rid).status for rid in (first_id,second_id)]
            assert statuses==["RESOLVED_KEEP","RESOLVED_KEEP"],statuses
            for rid in (first_id,second_id):
                audit=db.scalar(select(AuditEvent).where(AuditEvent.entity_type=="opportunity_conflict",AuditEvent.entity_id==str(rid),AuditEvent.event_type=="REVIEW_FIELD_KEEP"))
                assert audit.after_json["evidence"]["batch_operation_id"]==payload["batch_operation_id"]
    finally: engine.dispose()


def test_mixed_signature_stale_source_recheck_and_duplicate_batch_are_rejected(monkeypatch):
    factory, engine, first_id, master_id, record_id = workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id
        with factory() as db: db.get(OpportunityConflict,first_id).conflict_type="FIELD_VALUE_CONFLICT";db.commit()
        second_id,_,second_record_id=_add_matching_conflict(factory,source_id)
        client=TestClient(main.app); headers={"X-Admin-Token":"workbench-test-token"}
        first=client.get(f"/api/admin/review-workbench/field_conflict/{first_id}",headers=headers).json()
        second=client.get(f"/api/admin/review-workbench/field_conflict/{second_id}",headers=headers).json()
        with factory() as db: db.get(OpportunityConflict,second_id).conflicting_value="زراعي";db.commit()
        stale_payload={"items":[{"domain":"field_conflict","review_id":first_id,"version_token":first["version_token"]},{"domain":"field_conflict","review_id":second_id,"version_token":second["version_token"]}],"action":"keep","reason":"نمط أدلة متماثل","batch_operation_id":"workbench-batch-mixed-01","confirm":False}
        mixed=client.post("/api/admin/review-workbench/batch/preview",headers=headers,json=stale_payload)
        assert mixed.status_code==409
        fresh=client.get(f"/api/admin/review-workbench/field_conflict/{second_id}",headers=headers).json()
        stale_payload["items"][1]["version_token"]=fresh["version_token"]
        rejected=client.post("/api/admin/review-workbench/batch/preview",headers=headers,json=stale_payload)
        assert rejected.status_code==200 and rejected.json()["eligible"] is False
        with factory() as db:
            db.add(AuditEvent(user_id=None,event_type="REVIEW_EVIDENCE_ENRICHED",entity_type="review_evidence",entity_id=f"opportunity_conflict:{first_id}",before_json=None,after_json={"review_type":"OPPORTUNITY_CONFLICT","review_id":first_id,"classification":"SOURCE_RECHECK_REQUIRED","evidence":[]},request_metadata={"actor":"SYSTEM"},created_at=datetime.now(timezone.utc)));db.commit()
        first=client.get(f"/api/admin/review-workbench/field_conflict/{first_id}",headers=headers).json()
        second=client.get(f"/api/admin/review-workbench/field_conflict/{second_id}",headers=headers).json()
        source_recheck={**stale_payload,"items":[{"domain":"field_conflict","review_id":first_id,"version_token":first["version_token"]},{"domain":"field_conflict","review_id":second_id,"version_token":second["version_token"]}],"batch_operation_id":"workbench-batch-recheck-01"}
        blocked=client.post("/api/admin/review-workbench/batch/preview",headers=headers,json=source_recheck)
        assert blocked.status_code==200 and blocked.json()["eligible"] is False
        duplicate=client.post("/api/admin/review-workbench/batch/preview",headers=headers,json={**source_recheck,"action":"merge","items":[{"domain":"duplicate","review_id":1,"version_token":"0"*64},{"domain":"duplicate","review_id":2,"version_token":"0"*64}],"batch_operation_id":"workbench-batch-duplicate-01"})
        assert duplicate.status_code==422
        with factory() as db: assert db.get(OpportunityConflict,first_id).status=="OPEN" and db.get(OpportunityConflict,second_id).status=="OPEN"
    finally: engine.dispose()


@pytest.mark.parametrize("reason",["", "قرار سابق", "تغيير غير محدد"])
def test_reopen_rejects_missing_or_unapproved_reason_without_mutating_status(monkeypatch,reason):
    factory,engine,review_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db: db.get(OpportunityConflict,review_id).status="RESOLVED_KEEP";db.commit()
        client=TestClient(main.app);headers={"X-Admin-Token":"workbench-test-token"}
        detail=client.get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",headers=headers).json()
        response=client.post(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}/reopen",headers=headers,
            json={"reason":reason,"version_token":detail["version_token"]})
        assert response.status_code==422
        with factory() as db: assert db.get(OpportunityConflict,review_id).status=="RESOLVED_KEEP"
    finally: engine.dispose()


@pytest.mark.parametrize("domain",["field_conflict","taxonomy_conflict","duplicate","location","qualification"])
def test_reopen_preview_is_available_for_each_governed_resolved_domain(monkeypatch,domain):
    factory,engine,conflict_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db:
            now=datetime.now(timezone.utc);record=db.get(SourceOpportunity,record_id);source_id=record.source_id
            if domain in ("field_conflict","taxonomy_conflict"):
                conflict=db.get(OpportunityConflict,conflict_id);conflict.conflict_type="FIELD_VALUE_CONFLICT" if domain=="field_conflict" else "TAXONOMY_CONFLICT";conflict.status="RESOLVED_KEEP";review_id=conflict.id
            elif domain=="duplicate":
                other=Opportunity(canonical_id="WB-DUP",title_ar="مرشح مكرر",normalized_title="مرشح مكرر",opportunity_owner="المالك",primary_publication_platform="الناشر",city="الأحساء",sector="تجاري",activity="تجزئة",status="منشورة",location_confidence_score=.9,location_detection_method="fixture",location_evidence="source",data_quality_score=.9,manual_review_required=False,first_seen_at=now,last_seen_at=now,last_updated_at=now,created_at=now,updated_at=now);db.add(other);db.flush()
                duplicate=DuplicateCandidate(left_opportunity_id=master_id,right_opportunity_id=other.id,confidence_score=.8,status="REJECTED",created_at=now,explanation_json={});db.add(duplicate);db.flush();review_id=duplicate.id
            elif domain=="location":
                location=LocationReview(source_id=source_id,source_record_id=record_id,external_id="wb-location",title="فرصة تجريبية",sector="تجاري",source_location="الهفوف",description="وصف",latitude=None,longitude=None,evidence="دليل",confidence_score=.8,reason="مراجعة",status="REJECTED",created_at=now);db.add(location);db.flush();review_id=location.id
            else:
                qualification=QualificationReview(source_id=source_id,source_record_id=record_id,external_id="wb-qualification",title="فرصة تجريبية",source_url="https://example.test/item/1",proposed_type="investment",reason="مراجعة",status="REJECTED",created_at=now);db.add(qualification);db.flush();review_id=qualification.id
            db.commit()
        client=TestClient(main.app);headers={"X-Admin-Token":"workbench-test-token"}
        detail=client.get(f"/api/admin/review-workbench/{domain}/{review_id}",headers=headers)
        assert detail.status_code==200 and detail.json()["reopen_allowed"] is True
        preview=client.post(f"/api/admin/review-workbench/{domain}/{review_id}/reopen/preview?version_token={detail.json()['version_token']}",headers=headers)
        assert preview.status_code==200 and preview.json()["current_status"] in {"RESOLVED_KEEP","REJECTED"}
    finally: engine.dispose()


@pytest.mark.parametrize("condition",["mapping_missing","mapped_value_disagrees","authority_tie","source_recheck"])
def test_recommendation_returns_none_when_evidence_does_not_resolve_conflict(monkeypatch,condition):
    factory,engine,review_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id
        _upgrade_fixture_authority(factory,master_id,source_id)
        with factory() as db:
            record=db.get(SourceOpportunity,record_id)
            if condition=="mapping_missing":record.standardized_data_json={"fields":{"sector":{"value":None,"mapping_status":"MISSING"}}}
            elif condition=="mapped_value_disagrees":record.standardized_data_json={"fields":{"sector":{"value":"تجاري","mapping_status":"MAPPED","rule":"EXACT_TEST"}}}
            elif condition=="authority_tie":
                provenance=db.scalar(select(FieldProvenance).where(FieldProvenance.opportunity_id==master_id,FieldProvenance.field_name=="sector"))
                provenance.source_id=source_id;provenance.source_record_id=record_id;db.get(Source,source_id).priority=1
            elif condition=="source_recheck":
                db.add(AuditEvent(user_id=None,event_type="REVIEW_EVIDENCE_ENRICHED",entity_type="review_evidence",entity_id=f"opportunity_conflict:{review_id}",before_json=None,after_json={"review_type":"OPPORTUNITY_CONFLICT","review_id":review_id,"classification":"SOURCE_RECHECK_REQUIRED","evidence":[]},request_metadata={"actor":"SYSTEM"},created_at=datetime.now(timezone.utc)))
            db.commit()
        detail=TestClient(main.app).get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",headers={"X-Admin-Token":"workbench-test-token"}).json()
        assert detail["recommendation"]["action"] is None and detail["recommendation"]["confidence"]=="NONE"
        assert detail["recommendation"]["reason"] and detail["recommendation"]["confidence_levels_available"]==["HIGH","MEDIUM","NONE"]
    finally: engine.dispose()


def test_medium_confidence_recommendation_follows_canonical_source_evidence(monkeypatch):
    factory,engine,review_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id
        _upgrade_fixture_authority(factory,master_id,source_id)
        with factory() as db:
            db.get(Source,source_id).priority=2
            db.query(Source).filter_by(source_key="fixture-lower").one().priority=1
            db.commit()
        client=TestClient(main.app);headers={"X-Admin-Token":"workbench-test-token"}
        detail=client.get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",headers=headers).json()
        assert detail["recommendation"]["action"]=="keep" and detail["recommendation"]["confidence"]=="MEDIUM"
        assert detail["recommendation"]["supporting_evidence"][0]["value"]=="تجاري"
        assert detail["recommendation"]["contradictory_evidence"][0]["source_record_id"]==record_id
        response=client.post(f"/api/admin/conflicts/{review_id}/keep",headers=headers,json={"note":"Retained value backed by higher source authority.","version_token":detail["version_token"],"recommendation_version":detail["recommendation_version"]})
        assert response.status_code==200
        with factory() as db:
            event=db.scalar(select(AuditEvent).where(AuditEvent.event_type=="REVIEW_FIELD_KEEP",AuditEvent.entity_id==str(review_id)))
            assert event.after_json["evidence"]["recommendation"]["disposition"]=="FOLLOWED_RECOMMENDATION"
            assert event.after_json["evidence"]["recommendation"]["confidence"]=="MEDIUM"
    finally: engine.dispose()


@pytest.mark.parametrize("override_reason",["غير معتمد","سبب يدوي غير معروف"," "])
def test_recommendation_override_rejects_unapproved_reason(monkeypatch,override_reason):
    factory,engine,review_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id
        _upgrade_fixture_authority(factory,master_id,source_id)
        client=TestClient(main.app);headers={"X-Admin-Token":"workbench-test-token"}
        detail=client.get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",headers=headers).json()
        response=client.post(f"/api/admin/conflicts/{review_id}/keep",headers=headers,json={"note":"Retained canonical value after review.","version_token":detail["version_token"],"recommendation_version":detail["recommendation_version"],"recommendation_override_reason":override_reason})
        assert response.status_code==422
        with factory() as db: assert db.get(OpportunityConflict,review_id).status=="OPEN"
    finally: engine.dispose()


def test_recommendation_version_rejects_changed_rule_inputs_before_decision(monkeypatch):
    factory,engine,review_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id
        _upgrade_fixture_authority(factory,master_id,source_id)
        client=TestClient(main.app);headers={"X-Admin-Token":"workbench-test-token"}
        detail=client.get(f"/api/admin/review-workbench/taxonomy_conflict/{review_id}",headers=headers).json()
        assert detail["recommendation"]["action"]=="use_source"
        with factory() as db: db.get(Source,source_id).priority=5;db.commit()
        response=client.post(f"/api/admin/conflicts/{review_id}/use_source",headers=headers,json={
            "note":"Apply the displayed recommendation after checking its current authority evidence.",
            "version_token":detail["version_token"],"recommendation_version":detail["recommendation_version"]})
        assert response.status_code==409
        with factory() as db:
            assert db.get(OpportunityConflict,review_id).status=="OPEN"
            assert db.scalar(select(AuditEvent.id).where(AuditEvent.entity_type=="opportunity_conflict",
                AuditEvent.entity_id==str(review_id),AuditEvent.event_type=="REVIEW_FIELD_USE_SOURCE")) is None
    finally: engine.dispose()


def test_batch_commit_rejects_changed_preview_signature_without_partial_writes(monkeypatch):
    factory,engine,first_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id;db.get(OpportunityConflict,first_id).conflict_type="FIELD_VALUE_CONFLICT";db.commit()
        second_id,_,_=_add_matching_conflict(factory,source_id)
        client=TestClient(main.app);headers={"X-Admin-Token":"workbench-test-token"}
        first=client.get(f"/api/admin/review-workbench/field_conflict/{first_id}",headers=headers).json()
        second=client.get(f"/api/admin/review-workbench/field_conflict/{second_id}",headers=headers).json()
        payload={"items":[{"domain":"field_conflict","review_id":first_id,"version_token":first["version_token"],"recommendation_version":first["recommendation_version"]},
            {"domain":"field_conflict","review_id":second_id,"version_token":second["version_token"],"recommendation_version":second["recommendation_version"]}],
            "action":"keep","reason":"قرار موحد بعد مراجعة الأدلة","batch_operation_id":"workbench-batch-signature-01"}
        preview=client.post("/api/admin/review-workbench/batch/preview",headers=headers,json=payload).json()
        payload.update(items=preview["items"],batch_signature="0"*64,confirm=True)
        rejected=client.post("/api/admin/review-workbench/batch/commit",headers=headers,json=payload)
        assert rejected.status_code==409
        with factory() as db:
            assert db.get(OpportunityConflict,first_id).status=="OPEN" and db.get(OpportunityConflict,second_id).status=="OPEN"
            assert db.scalar(select(AuditEvent.id).where(AuditEvent.event_type=="REVIEW_BATCH_DECISION")) is None
    finally: engine.dispose()


def test_batch_override_requires_and_audits_an_explicit_reason(monkeypatch):
    factory,engine,first_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id;db.get(OpportunityConflict,first_id).conflict_type="FIELD_VALUE_CONFLICT";db.commit()
        _upgrade_fixture_authority(factory,master_id,source_id)
        second_id,second_master_id,second_record_id=_add_matching_conflict(factory,source_id)
        with factory() as db:
            lower_source_id=db.scalar(select(Source.id).where(Source.source_key=="fixture-lower"))
            for rid,mid,source_record_id in ((first_id,master_id,record_id),(second_id,second_master_id,second_record_id)):
                db.get(Opportunity,mid).sector="تجاري"
                db.get(SourceOpportunity,source_record_id).standardized_data_json={"fields":{"sector":{"value":"صناعي","mapping_status":"MAPPED","rule":"EXACT_SOURCE_TAXONOMY_V1"}}}
                conflict=db.get(OpportunityConflict,rid);conflict.field_name="sector";conflict.conflicting_value="صناعي";conflict.conflict_type="FIELD_VALUE_CONFLICT"
                provenance=db.scalar(select(FieldProvenance).where(FieldProvenance.opportunity_id==mid,FieldProvenance.field_name=="sector"))
                if provenance:
                    provenance.source_id=lower_source_id;provenance.source_record_id=source_record_id
                else:
                    db.add(FieldProvenance(opportunity_id=mid,field_name="sector",selected_value="تجاري",source_id=lower_source_id,
                        source_record_id=source_record_id,captured_at=datetime.now(timezone.utc),confidence=.9))
            db.commit()
        client=TestClient(main.app);headers={"X-Admin-Token":"workbench-test-token"}
        details=[client.get(f"/api/admin/review-workbench/field_conflict/{rid}",headers=headers).json() for rid in (first_id,second_id)]
        items=[{"domain":"field_conflict","review_id":rid,"version_token":detail["version_token"],"recommendation_version":detail["recommendation_version"]} for rid,detail in zip((first_id,second_id),details)]
        missing=client.post("/api/admin/review-workbench/batch/preview",headers=headers,json={"items":items,"action":"keep","reason":"تم الحفاظ على القيمة الحالية بعد التحقق","batch_operation_id":"batch-override-missing-01"}).json()
        assert missing["override_required"] is True and missing["eligible"] is False
        payload={"items":items,"action":"keep","reason":"تم الحفاظ على القيمة الحالية بعد التحقق","batch_operation_id":"batch-override-valid-01","override_reason":"تعارض في الأدلة"}
        preview=client.post("/api/admin/review-workbench/batch/preview",headers=headers,json=payload).json()
        assert preview["eligible"] is True
        payload.update(items=preview["items"],batch_signature=preview["signature"],confirm=True)
        committed=client.post("/api/admin/review-workbench/batch/commit",headers=headers,json=payload)
        assert committed.status_code==200
        with factory() as db:
            for rid in (first_id,second_id):
                event=db.scalar(select(AuditEvent).where(AuditEvent.entity_type=="opportunity_conflict",AuditEvent.entity_id==str(rid),AuditEvent.event_type=="REVIEW_FIELD_KEEP"))
                assert event.after_json["evidence"]["recommendation"]["disposition"]=="OVERRIDDEN_RECOMMENDATION"
                assert event.after_json["evidence"]["recommendation"]["override_reason"]=="تعارض في الأدلة"
    finally: engine.dispose()


def test_batch_commit_requires_confirmation_and_stale_member_is_atomic(monkeypatch):
    factory,engine,first_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id;db.get(OpportunityConflict,first_id).conflict_type="FIELD_VALUE_CONFLICT";db.commit()
        second_id,_,second_record_id=_add_matching_conflict(factory,source_id)
        client=TestClient(main.app);headers={"X-Admin-Token":"workbench-test-token"}
        first=client.get(f"/api/admin/review-workbench/field_conflict/{first_id}",headers=headers).json()
        second=client.get(f"/api/admin/review-workbench/field_conflict/{second_id}",headers=headers).json()
        payload={"items":[{"domain":"field_conflict","review_id":first_id,"version_token":first["version_token"]},{"domain":"field_conflict","review_id":second_id,"version_token":second["version_token"]}],"action":"keep","reason":"نمط أدلة متماثل","batch_operation_id":"batch-atomic-stale-0001","confirm":False}
        preview=client.post("/api/admin/review-workbench/batch/preview",headers=headers,json=payload)
        assert preview.status_code==200 and preview.json()["eligible"] is True
        payload["items"]=preview.json()["items"]
        unconfirmed=client.post("/api/admin/review-workbench/batch/commit",headers=headers,json=payload)
        assert unconfirmed.status_code==422
        with factory() as db: db.get(SourceOpportunity,second_record_id).content_hash="f"*64;db.commit()
        payload["confirm"]=True
        stale=client.post("/api/admin/review-workbench/batch/commit",headers=headers,json=payload)
        assert stale.status_code==409
        with factory() as db:
            assert db.get(OpportunityConflict,first_id).status=="OPEN" and db.get(OpportunityConflict,second_id).status=="OPEN"
            assert not db.scalar(select(AuditEvent.id).where(AuditEvent.event_type=="REVIEW_BATCH_DECISION"))
    finally: engine.dispose()


def test_viewer_cannot_preview_or_commit_batch_decisions(monkeypatch):
    factory,engine,review_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db: db.get(OpportunityConflict,review_id).conflict_type="FIELD_VALUE_CONFLICT";source_id=db.get(SourceOpportunity,record_id).source_id;db.commit()
        second_id,_,_=_add_matching_conflict(factory,source_id)
        client=TestClient(main.app);headers={"X-Admin-Token":"workbench-test-token"}
        first=client.get(f"/api/admin/review-workbench/field_conflict/{review_id}",headers=headers).json()
        second=client.get(f"/api/admin/review-workbench/field_conflict/{second_id}",headers=headers).json()
        payload={"items":[{"domain":"field_conflict","review_id":review_id,"version_token":first["version_token"]},{"domain":"field_conflict","review_id":second_id,"version_token":second["version_token"]}],"action":"keep","reason":"نمط أدلة متماثل","batch_operation_id":"batch-viewer-check-001","confirm":True}
        def deny_viewer(token): raise main.HTTPException(403,"Insufficient permissions")
        monkeypatch.setattr(main,"review_write_auth",deny_viewer)
        assert client.post("/api/admin/review-workbench/batch/preview",headers=headers,json=payload).status_code==403
        assert client.post("/api/admin/review-workbench/batch/commit",headers=headers,json=payload).status_code==403
        with factory() as db: assert db.get(OpportunityConflict,review_id).status=="OPEN" and db.get(OpportunityConflict,second_id).status=="OPEN"
    finally: engine.dispose()


@pytest.mark.parametrize("difference",["field","canonical_value","mapping_rule","source_priority","review_subtype","conflicting_value","mapping_status","source_authority"])
def test_batch_signature_rejects_each_material_decision_difference(monkeypatch,difference):
    factory,engine,first_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db: source_id=db.get(SourceOpportunity,record_id).source_id;db.get(OpportunityConflict,first_id).conflict_type="FIELD_VALUE_CONFLICT";db.commit()
        second_id,second_master_id,second_record_id=_add_matching_conflict(factory,source_id)
        with factory() as db:
            second=db.get(OpportunityConflict,second_id);record=db.get(SourceOpportunity,second_record_id);source=db.get(Source,source_id)
            if difference=="field":second.field_name="activity"
            elif difference=="canonical_value":db.get(Opportunity,second_master_id).sector="زراعي"
            elif difference=="mapping_rule":record.standardized_data_json={"fields":{"sector":{"value":"صناعي","rule":"DIFFERENT_RULE"}}}
            elif difference=="source_priority":
                alternate=Source(source_key="fixture-priority-two",source_name_ar="مصدر بديل",organization_name="alternate",base_url="https://alternate.test",opportunities_url="https://alternate.test/opportunities",priority=2);db.add(alternate);db.flush();record.source_id=alternate.id;second.source_id=alternate.id
            elif difference=="review_subtype":second.conflict_type="STANDARDIZATION_REVIEW"
            elif difference=="conflicting_value":second.conflicting_value="زراعي"
            elif difference=="mapping_status":record.standardized_data_json={"fields":{"sector":{"value":"صناعي","rule":"EXACT_TEST","mapping_status":"AMBIGUOUS"}}}
            elif difference=="source_authority":
                authoritative=Source(source_key="fixture-priority-zero",source_name_ar="مصدر أعلى",organization_name="authority",base_url="https://authority.test",opportunities_url="https://authority.test/opportunities",priority=0);db.add(authoritative);db.flush();db.scalar(select(FieldProvenance).where(FieldProvenance.opportunity_id==second_master_id,FieldProvenance.field_name=="sector")).source_id=authoritative.id
            db.commit()
        client=TestClient(main.app);headers={"X-Admin-Token":"workbench-test-token"}
        first=client.get(f"/api/admin/review-workbench/field_conflict/{first_id}",headers=headers).json()
        second=client.get(f"/api/admin/review-workbench/field_conflict/{second_id}",headers=headers).json()
        payload={"items":[{"domain":"field_conflict","review_id":first_id,"version_token":first["version_token"]},{"domain":"field_conflict","review_id":second_id,"version_token":second["version_token"]}],"action":"keep","reason":"حالات متشابهة للمقارنة","batch_operation_id":f"signature-{difference}-001","confirm":False}
        result=client.post("/api/admin/review-workbench/batch/preview",headers=headers,json=payload)
        assert result.status_code==200 and result.json()["eligible"] is False and result.json()["signature_count"]==2
    finally: engine.dispose()


@pytest.mark.parametrize("action",["use_source","reject","accept"])
def test_batch_preview_excludes_unsupported_actions_without_writes(monkeypatch,action):
    factory,engine,review_id,master_id,record_id=workbench_fixture(monkeypatch)
    try:
        with factory() as db: db.get(OpportunityConflict,review_id).conflict_type="FIELD_VALUE_CONFLICT";source_id=db.get(SourceOpportunity,record_id).source_id;db.commit()
        second_id,_,_=_add_matching_conflict(factory,source_id)
        client=TestClient(main.app);headers={"X-Admin-Token":"workbench-test-token"}
        first=client.get(f"/api/admin/review-workbench/field_conflict/{review_id}",headers=headers).json()
        second=client.get(f"/api/admin/review-workbench/field_conflict/{second_id}",headers=headers).json()
        payload={"items":[{"domain":"field_conflict","review_id":review_id,"version_token":first["version_token"]},{"domain":"field_conflict","review_id":second_id,"version_token":second["version_token"]}],"action":action,"reason":"قرار غير مؤهل للدفعة","batch_operation_id":f"batch-action-{action}-01","confirm":False}
        result=client.post("/api/admin/review-workbench/batch/preview",headers=headers,json=payload)
        assert result.status_code==200 and result.json()["eligible"] is False
        with factory() as db: assert db.get(OpportunityConflict,review_id).status=="OPEN" and db.get(OpportunityConflict,second_id).status=="OPEN"
    finally: engine.dispose()

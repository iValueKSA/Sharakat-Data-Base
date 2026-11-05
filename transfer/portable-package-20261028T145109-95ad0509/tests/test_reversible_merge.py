from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (AuditEvent, Base, ChangeHistory, DuplicateCandidate, FieldProvenance, Opportunity,
                        OpportunityConflict, Source, SourceOpportunity, SystemEvent)
from app.merge import merge_candidate


def test_admin_merge_and_undo_restores_master_and_child_ownership(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with factory() as db:
        sources = [Source(source_key=key, source_name_ar=key, organization_name=key,
            base_url="https://example.test", opportunities_url="https://example.test", priority=i)
            for i, key in enumerate(("alahsa-opportunities", "furas"), 1)]
        db.add_all(sources); db.flush()
        common = dict(city="الأحساء", status="متاحة", primary_publication_platform="Al-Ahsa",
            location_confidence_score=.9, location_detection_method="fixture", location_evidence="fixture",
            data_quality_score=.8, manual_review_required=False, first_seen_at=now, last_seen_at=now,
            last_updated_at=now, created_at=now, updated_at=now)
        target = Opportunity(canonical_id="A-1", title_ar="فرصة أصلية", normalized_title="فرصة اصلية",
            opportunity_owner="أمانة الأحساء", submission_deadline="2026-10-21", **common)
        merged = Opportunity(canonical_id="F-1", title_ar="فرصة ثانية", normalized_title="فرصة ثانية",
            opportunity_owner="أمانة الأحساء", submission_deadline="2026-10-21", **common)
        db.add_all([target, merged]); db.flush()
        target_record = SourceOpportunity(source_id=sources[0].id, master_opportunity_id=target.id,
            source_opportunity_id="A-1", source_title="فرصة أصلية", normalized_source_title="فرصة اصلية",
            source_url="https://example.test/A-1", raw_status="متاحة", raw_data_json={}, raw_dates={},
            first_seen_at=now, last_seen_at=now, content_hash="b"*64, parser_version="test")
        record = SourceOpportunity(source_id=sources[1].id, master_opportunity_id=merged.id,
            source_opportunity_id="F-1", source_title="فرصة ثانية", normalized_source_title="فرصة ثانية",
            source_url="https://example.test/F-1", raw_status="Announced", raw_data_json={"keep": True},
            raw_dates={}, first_seen_at=now, last_seen_at=now, content_hash="a"*64, parser_version="test")
        db.add_all([target_record,record]); db.flush()
        target_record_id, source_record_id = target_record.id, record.id
        history = ChangeHistory(opportunity_id=merged.id, changed_field="title_ar", previous_value="old",
            new_value="فرصة ثانية", source_id=sources[1].id, detected_at=now)
        provenance = FieldProvenance(opportunity_id=merged.id, field_name="title_ar", selected_value="فرصة ثانية",
            source_id=sources[1].id, source_record_id=record.id, captured_at=now, confidence=.9)
        conflict = OpportunityConflict(opportunity_id=merged.id, field_name="deadline", selected_value="a",
            conflicting_value="b", source_id=sources[1].id, source_record_id=record.id, detected_at=now, status="OPEN")
        db.add_all([history, provenance, conflict])
        db.flush()
        history_id, provenance_id, conflict_id = history.id, provenance.id, conflict.id
        candidate = DuplicateCandidate(left_opportunity_id=target.id, right_opportunity_id=merged.id,
            confidence_score=.99, status="PENDING", created_at=now,
            explanation_json={"positive_evidence": ["same site"]})
        db.add(candidate); db.commit(); candidate_id = candidate.id
        target_updated_at = target.updated_at

    from app import main
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setenv("ADMIN_TOKEN", "fixture-review-token")
    client = TestClient(main.app)
    denied = client.post(f"/api/admin/duplicates/{candidate_id}/merge", json={"note":"Reviewed fixture evidence"})
    assert denied.status_code == 401
    headers={"X-Admin-Token":"fixture-review-token"}
    detail=client.get(f"/api/admin/review-workbench/duplicate/{candidate_id}",headers=headers).json()
    decision={"note":"Reviewed official source evidence and confirmed the same opportunity.","version_token":detail["version_token"]}
    merged_response = client.post(f"/api/admin/duplicates/{candidate_id}/merge",headers=headers,json=decision)
    assert merged_response.status_code == 200
    assert client.post(f"/api/admin/duplicates/{candidate_id}/merge",headers=headers,json=decision).status_code == 409
    live_list = client.get("/api/opportunities?limit=500").json()
    assert live_list["total"] == 1
    assert [item["id"] for item in live_list["items"]] == [target.id]
    listed = live_list["items"][0]
    assert listed["source_count"] == 2
    dashboard = client.get("/api/data-dashboard").json()
    assert dashboard["kpis"]["total"] == 1
    detail = client.get(f"/api/opportunities/{listed['id']}").json()
    assert detail["source_count"] == 2
    csv_response = client.get("/api/export.csv")
    assert csv_response.status_code == 200
    csv_lines = [line for line in csv_response.text.splitlines() if line.strip()]
    assert len(csv_lines) == 2
    xlsx_response = client.get("/api/export.xlsx")
    assert xlsx_response.status_code == 200
    from io import BytesIO
    from openpyxl import load_workbook
    workbook = load_workbook(BytesIO(xlsx_response.content), read_only=True, data_only=True)
    export_rows = list(workbook.active.iter_rows(values_only=True))
    assert sum(row[0] == target.title_ar for row in export_rows) == 1
    workbook.close()
    with factory() as db:
        candidate = db.get(DuplicateCandidate, candidate_id)
        target, merged = db.get(Opportunity, candidate.left_opportunity_id), db.get(Opportunity, candidate.right_opportunity_id)
        assert candidate.status == "MERGED"
        assert merged.merged_into_id == target.id
        assert db.scalar(select(func.count(SourceOpportunity.id)).where(SourceOpportunity.master_opportunity_id == target.id)) == 2
        assert db.scalar(select(ChangeHistory.opportunity_id).where(ChangeHistory.changed_field == "title_ar")) == target.id
        assert db.scalar(select(FieldProvenance.opportunity_id)) == target.id
        assert db.scalar(select(OpportunityConflict.opportunity_id)) == target.id
        assert db.scalar(select(SystemEvent.event_type).where(SystemEvent.event_type == "MASTER_DUPLICATE_MERGED"))
        review_audit=db.scalar(select(AuditEvent).where(AuditEvent.entity_type=="duplicate_candidate",AuditEvent.entity_id==str(candidate_id)))
        assert review_audit and review_audit.after_json["reason"]==decision["note"]
        assert review_audit.before_json["status"]=="PENDING" and review_audit.after_json["status"]=="MERGED"
        merge_history_ids = {row.id for row in db.scalars(select(ChangeHistory).where(ChangeHistory.opportunity_id == target.id)).all()} - {history_id}

    detail=client.get(f"/api/admin/review-workbench/duplicate/{candidate_id}",headers=headers).json()
    undo_response = client.post(f"/api/admin/duplicates/{candidate_id}/undo",headers=headers,json={"note":"Restoring fixture after reversible merge test.","version_token":detail["version_token"]})
    assert undo_response.status_code == 200
    with factory() as db:
        candidate = db.get(DuplicateCandidate, candidate_id)
        target, merged = db.get(Opportunity, candidate.left_opportunity_id), db.get(Opportunity, candidate.right_opportunity_id)
        assert candidate.status == "UNDONE"
        assert target.title_ar == "فرصة أصلية"
        assert target.updated_at == target_updated_at.replace(tzinfo=None)
        assert merged.merged_into_id is None
        assert db.get(SourceOpportunity, target_record_id).master_opportunity_id == target.id
        assert db.get(SourceOpportunity, source_record_id).master_opportunity_id == merged.id
        assert db.get(ChangeHistory, history_id).opportunity_id == merged.id
        assert db.get(FieldProvenance, provenance_id).opportunity_id == merged.id
        assert db.get(OpportunityConflict, conflict_id).opportunity_id == merged.id
        assert all(db.get(ChangeHistory, row_id) is None for row_id in merge_history_ids)
        assert db.scalar(select(SystemEvent.event_type).where(SystemEvent.event_type == "MASTER_DUPLICATE_MERGE_UNDONE"))


def test_exact_same_source_article_alias_can_merge_duplicate_masters():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with factory() as db:
        source = Source(source_key="ncp", source_name_ar="NCP", organization_name="NCP",
            base_url="https://ncp.gov.sa", opportunities_url="https://ncp.gov.sa/news", priority=1)
        db.add(source); db.flush()
        shared = dict(opportunity_owner="NCP", primary_publication_platform="NCP", city="الأحساء",
            status="EXPIRED", first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
        left = Opportunity(canonical_id="ncp-old", title_ar="Food Safety Labs EOI", normalized_title="food safety labs eoi", **shared)
        right = Opportunity(canonical_id="ncp-new", title_ar="Food Safety Labs EOI", normalized_title="food safety labs eoi", **shared)
        db.add_all([left,right]); db.flush()
        article = dict(source_id=source.id, source_title="Food Safety Labs EOI", normalized_source_title="food safety labs eoi",
            source_url="https://ncp.gov.sa/en/MediaCenter/News/Pages/FoodSafetyLabs.aspx", raw_status="EXPIRED",
            raw_data_json={}, raw_dates={}, first_seen_at=now, last_seen_at=now, parser_version="test")
        db.add_all([SourceOpportunity(master_opportunity_id=left.id, source_opportunity_id="ncp:foodsafetylabs", content_hash="a"*64, **article),
                    SourceOpportunity(master_opportunity_id=right.id, source_opportunity_id="ncp-project:legacy-hash", content_hash="b"*64, **article)])
        db.flush()
        candidate=DuplicateCandidate(left_opportunity_id=left.id,right_opportunity_id=right.id,confidence_score=1.0,
            status="PENDING",created_at=now,explanation_json={"evidence":"same official URL and normalized title"})
        db.add(candidate); db.flush()
        audit=merge_candidate(db,candidate,performed_by="system:exact-same-source-article")
        assert right.merged_into_id == left.id
        assert db.scalar(select(func.count(SourceOpportunity.id)).where(SourceOpportunity.master_opportunity_id == left.id)) == 2
        assert candidate.status == "MERGED"
        assert audit.merge_reason
        db.rollback()

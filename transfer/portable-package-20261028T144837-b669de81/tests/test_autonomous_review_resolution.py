from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.autonomous_review_resolution import apply_ledger, classify_review, exact_duplicate_identity, resolve_post_sync_reviews
from app.models import (AuditEvent, Base, DuplicateCandidate, FieldProvenance, LocationReview, MergeAudit,
                        Opportunity, OpportunityConflict, Source, SourceOpportunity,
                        SourceObservation, SyncJob)


def fixture(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "allow_rate", lambda *args, **kwargs: True)
    monkeypatch.setenv("ADMIN_TOKEN", "autonomous-test-token")
    now = datetime.now(timezone.utc)
    with factory() as db:
        source = Source(source_key="fixture", source_name_ar="مصدر تجريبي", organization_name="fixture",
                        base_url="https://example.test", opportunities_url="https://example.test/opportunities", priority=1)
        db.add(source); db.flush()
        master = Opportunity(canonical_id="AR-1", title_ar="فرصة تجريبية", normalized_title="فرصة تجريبية",
            opportunity_owner="مالك موثق", primary_publication_platform="الناشر", city="الأحساء", district="الهفوف",
            sector="تجاري", activity="تجزئة", status="منشورة", location_confidence_score=.9,
            location_detection_method="fixture", location_evidence="source", data_quality_score=.9,
            manual_review_required=False, first_seen_at=now, last_seen_at=now, last_updated_at=now,
            created_at=now, updated_at=now)
        db.add(master); db.flush()
        record = SourceOpportunity(source_id=source.id, master_opportunity_id=master.id, source_opportunity_id="ar-1",
            official_source_id_original="OFF-1", official_source_id_normalized="OFF1",
            source_title="فرصة تجريبية", normalized_source_title="فرصة تجريبية", source_url="https://example.test/item/1",
            source_owner=None, raw_location=None, raw_status="DELETED_FROM_SOURCE", canonical_status="غير محددة",
            raw_data_json={"publisher": "الجهة الناشرة", "source_scope": "SOURCE_SCOPE_NATIONAL"},
            standardized_data_json={"fields": {}}, raw_dates={}, first_seen_at=now, last_seen_at=now,
            content_hash="a" * 64, parser_version="fixture")
        db.add(record); db.flush()
        conflict = OpportunityConflict(opportunity_id=master.id, field_name="activity", conflict_type="FIELD_VALUE_CONFLICT",
            selected_value="تجزئة", conflicting_value="بيع", source_id=source.id, source_record_id=record.id,
            detected_at=now, status="OPEN")
        db.add(conflict)
        db.add(FieldProvenance(opportunity_id=master.id, field_name="activity", selected_value="تجزئة",
            source_id=source.id, source_record_id=record.id, captured_at=now, confidence=.9))
        db.add(SourceObservation(source_opportunity_id=record.id, dataset_name="fixture", endpoint="fixture",
            official_source_id_original="OFF-1", official_source_id_normalized="OFF1", raw_data_json={},
            source_updated_at=now.isoformat(), content_hash="b" * 64, first_seen_at=now, last_seen_at=now))
        db.commit()
        return factory, engine, source.id, master.id, record.id, conflict.id


def queue_item(factory, domain="field_conflict", review_id=1, disposition="HUMAN_REVIEW_REQUIRED", evidence=None):
    with factory() as db:
        row = main.review_queue("autonomous-test-token", domain, "OPEN", 1000, disposition="ALL")
        item = next((x for x in row if int(x["id"]) == review_id), None)
        if item is None:
            raise AssertionError(f"missing {domain}:{review_id}")
        if disposition:
            item["disposition"] = disposition
        if evidence is not None:
            item["evidence"].update(evidence)
        return item


def classify(factory, item, recommendation=None):
    with factory() as db:
        return classify_review(db, item, recommendation)


def test_stronger_authoritative_source_wins_when_governed_recommendation_is_high(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        item = queue_item(factory)
        result = classify(factory, item, {"action": "use_source", "confidence": "HIGH", "rule": "SOURCE_PRIORITY",
                                         "supporting_evidence": [{"source_record_id": 1}]})
        assert result["resolution_class"] == "A_STRONGER_SOURCE_VALUE_WINS"
        assert result["business_change"] == "CANONICAL_FIELD_CHANGE"
    finally:
        engine.dispose()


def test_ambiguous_field_conflict_keeps_current_canonical_value(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        result = classify(factory, queue_item(factory), None)
        assert result["resolution_class"] == "B_KEEP_CURRENT_CANONICAL"
        assert result["action"] == "keep"
        assert result["business_change"] == "NO_BUSINESS_CHANGE"
    finally:
        engine.dispose()


def test_duplicate_with_same_source_official_id_has_deterministic_proof(monkeypatch):
    factory, engine, source_id, master_id, record_id, _ = fixture(monkeypatch)
    try:
        with factory() as db:
            now = datetime.now(timezone.utc)
            other = Opportunity(canonical_id="AR-2", title_ar="عنوان مختلف", normalized_title="عنوان مختلف",
                opportunity_owner="مالك", primary_publication_platform="الناشر", city="الأحساء", sector="تجاري",
                activity="تجزئة", status="منشورة", location_confidence_score=.9, location_detection_method="fixture",
                location_evidence="source", data_quality_score=.9, manual_review_required=False, first_seen_at=now,
                last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
            db.add(other); db.flush()
            db.add(SourceOpportunity(source_id=source_id, master_opportunity_id=other.id, source_opportunity_id="ar-2",
                official_source_id_original="OFF-1", official_source_id_normalized="OFF1", source_title="غير متطابق",
                normalized_source_title="غير متطابق", source_url="https://example.test/item/2", source_owner="مالك",
                raw_location=None, raw_status="PUBLISHED", canonical_status="متاح", raw_data_json={},
                standardized_data_json={}, raw_dates={}, first_seen_at=now, last_seen_at=now,
                content_hash="c" * 64, parser_version="fixture")); db.flush()
            candidate = DuplicateCandidate(left_opportunity_id=master_id, right_opportunity_id=other.id,
                confidence_score=.5, status="PENDING", created_at=now, explanation_json={})
            db.add(candidate); db.commit(); proof = exact_duplicate_identity(db, candidate)
            assert proof["kind"] == "SAME_SOURCE_OFFICIAL_ID"
            item = main.review_queue("autonomous-test-token", "duplicate", "OPEN", 1000)[0]
            result = classify_review(db, item)
            assert result["action"] == "merge"
            version = main._review_version_token(db, "duplicate", candidate.id)
            applied = apply_ledger(db, [result], expected_versions={f"duplicate:{candidate.id}": version})
            assert applied["merges"] == 1
            assert db.get(DuplicateCandidate, candidate.id).status == "MERGED"
            audit = db.scalar(select(MergeAudit).where(MergeAudit.merged_opportunity_id == other.id))
            assert audit is not None and audit.performed_by == "SYSTEM"
    finally:
        engine.dispose()


def test_uncertain_duplicate_defaults_to_keep_separate(monkeypatch):
    factory, engine, source_id, master_id, *_ = fixture(monkeypatch)
    try:
        with factory() as db:
            now = datetime.now(timezone.utc)
            other = Opportunity(canonical_id="AR-3", title_ar="فرصة تجريبية", normalized_title="فرصة تجريبية",
                opportunity_owner="مالك موثق", primary_publication_platform="الناشر", city="الأحساء", sector="تجاري",
                activity="تجزئة", status="منشورة", location_confidence_score=.9, location_detection_method="fixture",
                location_evidence="source", data_quality_score=.9, manual_review_required=False, first_seen_at=now,
                last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
            db.add(other); db.flush()
            db.add(SourceOpportunity(source_id=source_id, master_opportunity_id=other.id, source_opportunity_id="ar-3",
                official_source_id_original="OTHER", official_source_id_normalized="OTHER", source_title="فرصة تجريبية",
                normalized_source_title="فرصة تجريبية", source_url="https://example.test/item/3", source_owner="مالك",
                raw_location="الهفوف", raw_status="PUBLISHED", canonical_status="متاح", raw_data_json={},
                standardized_data_json={}, raw_dates={}, first_seen_at=now, last_seen_at=now,
                content_hash="d" * 64, parser_version="fixture")); db.flush()
            candidate = DuplicateCandidate(left_opportunity_id=master_id, right_opportunity_id=other.id,
                confidence_score=.99, status="PENDING", created_at=now, explanation_json={})
            db.add(candidate); db.commit()
            item = main.review_queue("autonomous-test-token", "duplicate", "OPEN", 1000)[0]
            result = classify_review(db, item)
            assert result["resolution_class"] == "D_CONSERVATIVE_NOT_DUPLICATE"
            assert result["action"] == "reject"
    finally:
        engine.dispose()


def test_same_source_different_official_ids_never_merge(monkeypatch):
    factory, engine, source_id, master_id, *_ = fixture(monkeypatch)
    try:
        with factory() as db:
            now = datetime.now(timezone.utc)
            other = Opportunity(canonical_id="AR-4", title_ar="عنوان مطابق", normalized_title="عنوان مطابق",
                opportunity_owner="مالك", primary_publication_platform="الناشر", city="الأحساء", sector="تجاري",
                activity="تجزئة", status="منشورة", location_confidence_score=.9, location_detection_method="fixture",
                location_evidence="source", data_quality_score=.9, manual_review_required=False, first_seen_at=now,
                last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
            db.add(other); db.flush()
            db.add(SourceOpportunity(source_id=source_id, master_opportunity_id=other.id, source_opportunity_id="ar-4",
                official_source_id_original="OFF-OTHER", official_source_id_normalized="OFFOTHER", source_title="عنوان مطابق",
                normalized_source_title="عنوان مطابق", source_url="https://example.test/item/4", source_owner="مالك",
                raw_location="الهفوف", raw_status="PUBLISHED", canonical_status="متاح", raw_data_json={},
                standardized_data_json={}, raw_dates={}, first_seen_at=now, last_seen_at=now,
                content_hash="e" * 64, parser_version="fixture")); db.flush()
            candidate = DuplicateCandidate(left_opportunity_id=master_id, right_opportunity_id=other.id,
                confidence_score=1.0, status="PENDING", created_at=now, explanation_json={"auto_merge_safe": True})
            db.add(candidate); db.commit()
            assert exact_duplicate_identity(db, candidate) is None
    finally:
        engine.dispose()


def test_publisher_is_not_promoted_to_opportunity_owner(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        with factory() as db:
            conflict=db.get(OpportunityConflict,1); conflict.field_name="opportunity_owner"
            conflict.selected_value="مالك موثق"; conflict.conflicting_value="الجهة الناشرة"; db.commit()
        result = classify(factory, queue_item(factory),
            {"action": "use_source", "confidence": "HIGH", "rule": "SOURCE_PRIORITY", "supporting_evidence": [1]})
        assert result["resolution_class"] == "B_KEEP_CURRENT_CANONICAL"
        assert result["business_change"] == "NO_BUSINESS_CHANGE"
    finally:
        engine.dispose()


def test_missing_location_is_not_fabricated(monkeypatch):
    factory, engine, source_id, master_id, record_id, _ = fixture(monkeypatch)
    try:
        with factory() as db:
            now = datetime.now(timezone.utc)
            review = LocationReview(source_id=source_id, external_id="loc-1", source_record_id=record_id,
                title="فرصة", sector="تجاري", source_location=None, description="", latitude=None, longitude=None,
                evidence="no project site", confidence_score=0, reason="LOCATION_UNSPECIFIED", status="PENDING", created_at=now)
            db.add(review); db.commit()
            item = main.review_queue("autonomous-test-token", "location", "OPEN", 1000, disposition="ALL")[0]
            result = classify_review(db, item)
            assert result["action"] == "reject"
            assert result["business_change"] == "NO_BUSINESS_CHANGE"
    finally:
        engine.dispose()


def test_national_listing_is_not_promoted_to_al_ahsa(monkeypatch):
    factory, engine, source_id, master_id, record_id, _ = fixture(monkeypatch)
    try:
        with factory() as db:
            now = datetime.now(timezone.utc)
            review = LocationReview(source_id=source_id, external_id="loc-national", source_record_id=record_id,
                title="فرصة وطنية", sector="تجاري", source_location=None, description="", latitude=None, longitude=None,
                evidence="national listing", confidence_score=.8, reason="scope only", status="PENDING", created_at=now)
            db.add(review); db.commit()
            item = main.review_queue("autonomous-test-token", "location", "OPEN", 1000, disposition="ALL")[0]
            assert classify_review(db, item)["action"] == "reject"
    finally:
        engine.dispose()


def test_deleted_from_source_does_not_infer_cancelled(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        with factory() as db:
            review=db.get(OpportunityConflict,1); review.field_name="status"
            review.selected_value="منشورة"; review.conflicting_value="DELETED_FROM_SOURCE"; db.commit()
        item = queue_item(factory)
        result = classify(factory, item)
        assert result["action"] == "keep"
        with factory() as db:
            assert db.get(Opportunity, 1).status == "منشورة"
    finally:
        engine.dispose()


def test_published_alias_matching_current_status_supersedes_conflict(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        with factory() as db:
            review=db.get(OpportunityConflict,1); review.field_name="status"
            review.selected_value="متاحة"; review.conflicting_value="PUBLISHED"
            db.get(Opportunity,1).status="منشورة"; db.commit()
        result=classify(factory,queue_item(factory))
        assert result["resolution_class"]=="K_SUPERSEDED_OR_STALE_REVIEW"
        assert result["business_change"]=="NO_BUSINESS_CHANGE"
    finally:
        engine.dispose()


def test_unknown_status_values_do_not_collapse_removed_into_expired(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        with factory() as db:
            review=db.get(OpportunityConflict,1); review.field_name="status"
            review.selected_value="منتهية"; review.conflicting_value="'منتهية'; deadline='2026-10-21'"
            db.get(Opportunity,1).status="أزيلت من المصدر"; db.commit()
        result=classify(factory,queue_item(factory))
        assert result["resolution_class"]=="B_KEEP_CURRENT_CANONICAL"
        assert result["action"]=="keep"
    finally:
        engine.dispose()


def test_unknown_currency_is_not_inferred(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        with factory() as db:
            review=db.get(OpportunityConflict,1); review.field_name="investment_value"
            review.selected_value="100"; review.conflicting_value="200"
            db.get(Opportunity,1).investment_value=100
            record=db.get(SourceOpportunity,1); record.raw_data_json={"investmentSize":"200"}; db.commit()
        item = queue_item(factory)
        result = classify(factory, item)
        assert result["action"] == "keep"
        with factory() as db:
            assert db.get(Opportunity, 1).currency is None
    finally:
        engine.dispose()


def test_conflicting_quantitative_values_retain_safer_state(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        with factory() as db:
            review=db.get(OpportunityConflict,1); review.field_name="contract_duration_years"
            review.selected_value="10"; review.conflicting_value="15"
            db.get(Opportunity,1).contract_duration_years=10
            record=db.get(SourceOpportunity,1); record.raw_data_json={"duration":"15"}; db.commit()
        item = queue_item(factory)
        result = classify(factory, item)
        assert result["action"] == "keep"
        assert result["business_change"] == "NO_BUSINESS_CHANGE"
    finally:
        engine.dispose()


def test_missing_evidence_closes_with_no_change(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        result = classify(factory, queue_item(factory, evidence={"source_record_id": None}), None)
        assert result["reason"] == "INSUFFICIENT_EVIDENCE_NO_CHANGE"
        assert result["action"] == "keep"
    finally:
        engine.dispose()


def test_merged_master_conflict_is_superseded(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        with factory() as db:
            master = db.get(Opportunity, 1); master.merged_into_id = 999; db.commit()
        result = classify(factory, queue_item(factory))
        assert result["resolution_class"] == "K_SUPERSEDED_OR_STALE_REVIEW"
    finally:
        engine.dispose()


def test_system_actor_audit_is_recorded_atomically(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        item = queue_item(factory)
        decision = classify(factory, item)
        with factory() as db:
            token = main._review_version_token(db, "field_conflict", item["id"])
            applied = apply_ledger(db, [decision], expected_versions={f"field_conflict:{item['id']}": token})
        assert applied["resolved"] == 1
        with factory() as db:
            review = db.get(OpportunityConflict, item["id"])
            event = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == str(item["id"]),
                AuditEvent.event_type == "REVIEW_FIELD_KEEP"))
            assert review.status == "RESOLVED_KEEP"
            assert event.request_metadata["actor"] == "SYSTEM"
            assert event.request_metadata["decision_kind"] == "AUTONOMOUS"
    finally:
        engine.dispose()


def test_resolution_batch_rolls_back_on_stale_version(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        with factory() as db:
            now = datetime.now(timezone.utc)
            extra = OpportunityConflict(opportunity_id=1, field_name="activity", conflict_type="FIELD_VALUE_CONFLICT",
                selected_value="تجزئة", conflicting_value="جملة", source_id=1, source_record_id=1,
                detected_at=now, status="OPEN")
            db.add(extra); db.commit(); extra_id = extra.id
        decisions=[{"review_type":"field_conflict","review_id":1,"action":"keep","resolution_class":"B_KEEP_CURRENT_CANONICAL",
                    "confidence":"CONSERVATIVE","business_change":"NO_BUSINESS_CHANGE","reason":"INSUFFICIENT_EVIDENCE_NO_CHANGE","evidence":{}},
                   {"review_type":"field_conflict","review_id":extra_id,"action":"keep","resolution_class":"B_KEEP_CURRENT_CANONICAL",
                    "confidence":"CONSERVATIVE","business_change":"NO_BUSINESS_CHANGE","reason":"INSUFFICIENT_EVIDENCE_NO_CHANGE","evidence":{}}]
        with factory() as db:
            v1=main._review_version_token(db,"field_conflict",1)
            with pytest.raises(RuntimeError, match="evidence changed"):
                apply_ledger(db,decisions,expected_versions={"field_conflict:1":v1,"field_conflict:%s"%extra_id:"bad"})
        with factory() as db:
            assert db.get(OpportunityConflict,1).status == "OPEN"
            assert db.get(OpportunityConflict,extra_id).status == "OPEN"
    finally:
        engine.dispose()


def test_resolver_is_idempotent_after_terminal_resolution(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        item = queue_item(factory); decision = classify(factory, item)
        with factory() as db:
            token = main._review_version_token(db, "field_conflict", item["id"])
            apply_ledger(db, [decision], expected_versions={f"field_conflict:{item['id']}": token})
        with factory() as db:
            assert apply_ledger(db, [], expected_versions={})["resolved"] == 0
            assert db.get(OpportunityConflict, item["id"]).status == "RESOLVED_KEEP"
    finally:
        engine.dispose()


def test_post_sync_resolver_closes_source_backlog_with_system_audit_and_is_idempotent(monkeypatch):
    factory, engine, source_id, _, _, review_id = fixture(monkeypatch)
    try:
        with factory() as db:
            started=datetime.now(timezone.utc)+timedelta(seconds=1)
            job=SyncJob(source_id=source_id,started_at=started,status="RUNNING",job_state="RUNNING")
            db.add(job);db.commit();job_id=job.id
        with factory() as db:
            result=resolve_post_sync_reviews(db,source_id=source_id,job_id=job_id)
            assert result["reviews_auto_resolved"]==1
            assert result["reviews_left_open"]==0
            db.commit()
        with factory() as db:
            audit=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==str(review_id),
                AuditEvent.event_type=="REVIEW_FIELD_KEEP"))
            assert db.get(OpportunityConflict,review_id).status=="RESOLVED_KEEP"
            assert audit and audit.request_metadata["actor"]=="SYSTEM"
            prior_audits=db.query(AuditEvent).filter_by(entity_id=str(review_id),event_type="REVIEW_FIELD_KEEP").count()
            repeated=resolve_post_sync_reviews(db,source_id=source_id,job_id=job_id)
            assert repeated["reviews_auto_resolved"]==0 and repeated["reviews_left_open"]==0
            db.commit()
        with factory() as db:
            assert db.query(AuditEvent).filter_by(entity_id=str(review_id),event_type="REVIEW_FIELD_KEEP").count()==prior_audits
    finally:
        engine.dispose()


def test_source_recheck_closes_conservatively_without_mutation(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        result = classify(factory, queue_item(factory, disposition="SOURCE_RECHECK_REQUIRED"))
        assert result["resolution_class"] == "J_SOURCE_RECHECK_CONSERVATIVE_NO_CHANGE"
        assert result["action"] == "keep"
        assert result["business_change"] == "NO_BUSINESS_CHANGE"
    finally:
        engine.dispose()


def test_fuzzy_same_source_match_is_not_identity_proof(monkeypatch):
    factory, engine, source_id, master_id, *_ = fixture(monkeypatch)
    try:
        with factory() as db:
            now = datetime.now(timezone.utc)
            other = Opportunity(canonical_id="AR-FUZZY", title_ar="عنوان قريب", normalized_title="عنوان قريب",
                opportunity_owner="مالك", primary_publication_platform="الناشر", city="الأحساء", sector="تجاري",
                activity="تجزئة", status="منشورة", location_confidence_score=.9, location_detection_method="fixture",
                location_evidence="source", data_quality_score=.9, manual_review_required=False, first_seen_at=now,
                last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
            db.add(other); db.flush()
            db.add(SourceOpportunity(source_id=source_id, master_opportunity_id=other.id, source_opportunity_id="fuzzy",
                official_source_id_original="OFF-FUZZY", official_source_id_normalized="OFFFUZZY", source_title="عنوان قريب",
                normalized_source_title="عنوان قريب", source_url="https://example.test/item/fuzzy", source_owner="مالك",
                raw_location="الهفوف", raw_status="PUBLISHED", canonical_status="متاح", raw_data_json={},
                standardized_data_json={}, raw_dates={}, first_seen_at=now, last_seen_at=now,
                content_hash="f" * 64, parser_version="fixture")); db.flush()
            candidate = DuplicateCandidate(left_opportunity_id=master_id, right_opportunity_id=other.id,
                confidence_score=.999, status="PENDING", created_at=now, explanation_json={"auto_merge_safe": True})
            db.add(candidate); db.commit()
            assert exact_duplicate_identity(db, candidate) is None
    finally:
        engine.dispose()


def test_low_confidence_recommendation_cannot_mutate_canonical(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        result = classify(factory, queue_item(factory), {"action": "use_source", "confidence": "MEDIUM",
            "rule": "SOURCE_PRIORITY", "supporting_evidence": [1]})
        assert result["action"] == "keep"
        assert result["business_change"] == "NO_BUSINESS_CHANGE"
    finally:
        engine.dispose()


def test_fully_classified_backlog_can_close_without_open_reviews(monkeypatch):
    factory, engine, *_ = fixture(monkeypatch)
    try:
        item = queue_item(factory); decision = classify(factory, item)
        with factory() as db:
            token = main._review_version_token(db, "field_conflict", item["id"])
            apply_ledger(db, [decision], expected_versions={f"field_conflict:{item['id']}": token})
        with factory() as db:
            assert db.scalar(select(OpportunityConflict).where(OpportunityConflict.status.in_(("OPEN", "PENDING")))) is None
    finally:
        engine.dispose()

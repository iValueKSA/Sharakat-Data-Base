from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import AuditEvent, Base, DuplicateCandidate, OpportunityConflict, SourceOpportunity
from app.review_lifecycle import reevaluate_open_conflicts, stale_conflict_evidence
from app.data_quality import evaluate_data_quality


def _db_fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, factory


def _entities(db, *, source_key="fixture", master_id="M-1", field="sector", projection=None,
              source_sector=None, source_owner=None, raw_location=None, source_field_value="old"):
    from app.models import Opportunity, Source, SourceOpportunity

    now = datetime.now(timezone.utc)
    source = Source(source_key=source_key, source_name_ar=source_key, organization_name=source_key,
        base_url="https://fixture.test", opportunities_url="https://fixture.test/opportunities", priority=1)
    db.add(source); db.flush()
    master = Opportunity(canonical_id=master_id, title_ar="فرصة", normalized_title="title",
        primary_publication_platform=source_key, city="الأحساء", status="متاحة", sector="صناعي",
        activity="تجاري", opportunity_type=None, contract_duration_years=None,
        first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
    db.add(master); db.flush()
    fields = {field: projection or {"raw": source_field_value, "canonical_label": source_field_value,
                                   "mapping_status": "MAPPED", "rule": "fixture"}}
    record = SourceOpportunity(source_id=source.id, master_opportunity_id=master.id,
        source_opportunity_id=f"{master_id}-source", source_title="فرصة", normalized_source_title="title",
        source_url="https://fixture.test/1", source_owner=source_owner, raw_location=raw_location,
        source_sector=source_sector, raw_dates={}, raw_data_json={}, standardized_data_json={"fields": fields},
        first_seen_at=now, last_seen_at=now, content_hash="a" * 64, parser_version="fixture")
    db.add(record); db.flush()
    return source, master, record


def _conflict(db, source, master, record, *, field="sector", kind="TAXONOMY_CONFLICT",
              selected="صناعي", conflicting="أخرى"):
    row = OpportunityConflict(opportunity_id=master.id, field_name=field, conflict_type=kind,
        selected_value=selected, conflicting_value=conflicting, source_id=source.id,
        source_record_id=record.id, detected_at=datetime.now(timezone.utc), status="OPEN")
    db.add(row); db.flush()
    return row


def test_missing_sector_conflict_is_audited_without_changing_master():
    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, master, record = _entities(db, source_key="furas", field="sector",
                projection={"raw": None, "canonical_label": "غير محدد", "mapping_status": "MISSING", "rule": "preserve_missing"})
            record.source_sector = None
            conflict = _conflict(db, source, master, record)
            assert stale_conflict_evidence(db, conflict)["rule"] == "CURRENT_SOURCE_SECTOR_MISSING_NOT_CONFLICT_V1"
            assert reevaluate_open_conflicts(db, source_record_id=record.id, master_id=master.id) == [conflict.id]
            db.flush()
            assert conflict.status == "RESOLVED_CANONICAL"
            assert master.sector == "صناعي"
            event = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == str(conflict.id)))
            assert event and event.request_metadata["actor"] == "SYSTEM"
            assert event.after_json["evidence"]["rule"] == "CURRENT_SOURCE_SECTOR_MISSING_NOT_CONFLICT_V1"
    finally:
        engine.dispose()


def test_explicit_activity_contradiction_stays_open():
    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, master, record = _entities(db, field="activity",
                projection={"raw": "تجاري", "canonical_label": "تجاري", "mapping_status": "MAPPED", "rule": "fixture"})
            conflict = _conflict(db, source, master, record, field="activity", kind="TAXONOMY_CONFLICT",
                                 selected="صناعي", conflicting="تجاري")
            assert stale_conflict_evidence(db, conflict) is None
            assert reevaluate_open_conflicts(db, source_record_id=record.id) == []
            assert conflict.status == "OPEN"
    finally:
        engine.dispose()


def test_valid_changed_duration_resolves_only_targeted_review():
    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, master, record = _entities(db, source_key="furas", field="contract_duration_years",
                projection={"raw": "5 سنة", "canonical_label": 5.0, "mapping_status": "VALID", "rule": "validated_numeric_v1"})
            conflict = _conflict(db, source, master, record, field="contract_duration_years",
                kind="STANDARDIZATION_REVIEW", selected="", conflicting="60")
            assert reevaluate_open_conflicts(db, source_record_id=record.id) == [conflict.id]
            assert conflict.status == "RESOLVED_CANONICAL"
            assert master.contract_duration_years is None
    finally:
        engine.dispose()


def test_auto_resolved_logical_issue_reopens_idempotently_when_recreated():
    from app.models import SystemEvent
    from app.service import queue_conflict_idempotently

    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, master, record = _entities(db, source_key="furas", field="sector",
                projection={"raw": None, "canonical_label": "غير محدد", "mapping_status": "MISSING", "rule": "preserve_missing"})
            record.source_sector = None
            conflict = _conflict(db, source, master, record)
            resolved_ids = reevaluate_open_conflicts(db, source_record_id=record.id)
            assert resolved_ids == [conflict.id]
            reopened = queue_conflict_idempotently(db, opportunity_id=master.id, field_name="sector",
                conflict_type="TAXONOMY_CONFLICT", selected_value="صناعي", conflicting_value="أخرى",
                source_id=source.id, source_record_id=record.id, detected_at=datetime.now(timezone.utc))
            assert reopened is not None and reopened.status == "OPEN"
            assert queue_conflict_idempotently(db, opportunity_id=master.id, field_name="sector",
                conflict_type="TAXONOMY_CONFLICT", selected_value="صناعي", conflicting_value="أخرى",
                source_id=source.id, source_record_id=record.id, detected_at=datetime.now(timezone.utc)) is None
            assert db.query(OpportunityConflict).filter_by(status="OPEN").count() == 1
            assert db.query(SystemEvent).filter_by(event_type="REVIEW_REOPENED").count() == 1
    finally:
        engine.dispose()


def test_master_merge_transfers_then_reevaluates_only_survivor_conflicts():
    from app.merge import merge_candidate

    engine, factory = _db_fixture()
    try:
        with factory() as db:
            left_source, left, left_record = _entities(db, source_key="alahsa-opportunities",
                master_id="M-LEFT", field="sector", projection={"raw": "صناعي", "canonical_label": "صناعي", "mapping_status": "MAPPED", "rule": "fixture"})
            right_source, right, right_record = _entities(db, source_key="furas", master_id="M-RIGHT",
                field="sector", projection={"raw": None, "canonical_label": "غير محدد", "mapping_status": "MISSING", "rule": "preserve_missing"})
            right_record.source_sector = None
            conflict = _conflict(db, right_source, right, right_record)
            candidate = DuplicateCandidate(left_opportunity_id=left.id, right_opportunity_id=right.id,
                confidence_score=.99, status="PENDING", created_at=datetime.now(timezone.utc), explanation_json={})
            db.add(candidate); db.flush()
            merge_candidate(db, candidate, performed_by="system:test")
            db.flush()
            assert right.merged_into_id == left.id
            assert right_record.master_opportunity_id == left.id
            assert conflict.opportunity_id == left.id
            assert conflict.status == "RESOLVED_CANONICAL"
            event = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == str(conflict.id)))
            assert event and event.request_metadata["actor"] == "SYSTEM"
    finally:
        engine.dispose()


def test_exact_current_location_projection_is_stale_but_nonexact_text_is_not():
    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, master, record = _entities(db, field="location_description",
                projection={"raw": "الهفوف", "canonical_label": "الهفوف", "mapping_status": "NORMALIZED", "rule": "fixture"})
            master.location_description = "الهفوف"
            conflict = _conflict(db, source, master, record, field="location_description",
                kind="FIELD_VALUE_CONFLICT", selected="الهفوف", conflicting="الهفوف")
            assert stale_conflict_evidence(db, conflict)["rule"] == "CURRENT_CANONICAL_FIELD_AGREEMENT_V1"
            record.standardized_data_json["fields"]["location_description"]["canonical_label"] = "العيون الصناعية"
            assert stale_conflict_evidence(db, conflict) is None
    finally:
        engine.dispose()


def test_dq_stale_and_automatic_audit_gates_reconcile():
    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, master, record = _entities(db, source_key="furas", field="sector",
                projection={"raw": None, "canonical_label": "غير محدد", "mapping_status": "MISSING", "rule": "preserve_missing"})
            record.source_sector = None
            conflict = _conflict(db, source, master, record)
            gates = {item["gate_key"]: item for item in evaluate_data_quality(db, scope="full", persist=False)["gates"]}
            assert gates["STALE_OPEN_REVIEW_CONDITION"]["status"] == "FAIL"
            assert gates["STALE_OPEN_REVIEWS"]["status"] == "FAIL"
            assert gates["STALE_OPEN_REVIEW_CONDITION"]["observed"] == 1
            assert reevaluate_open_conflicts(db, source_record_id=record.id) == [conflict.id]
            gates = {item["gate_key"]: item for item in evaluate_data_quality(db, scope="full", persist=False)["gates"]}
            assert gates["STALE_OPEN_REVIEW_CONDITION"]["status"] == "PASS"
            assert gates["STALE_OPEN_REVIEWS"]["status"] == "PASS"
            assert gates["AUTO_RESOLUTION_WITHOUT_EVIDENCE"]["status"] == "PASS"
            assert gates["REVIEW_RESOLUTION_WITHOUT_AUDIT"]["status"] == "PASS"
            assert gates["REVIEW_REOPEN_IDEMPOTENCY"]["status"] == "PASS"
    finally:
        engine.dispose()

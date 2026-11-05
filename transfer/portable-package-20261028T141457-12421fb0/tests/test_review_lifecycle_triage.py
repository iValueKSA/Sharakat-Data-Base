from datetime import datetime, timedelta, timezone

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


def test_auto_resolved_logical_issue_is_reused_when_unchanged_evidence_repeats():
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
            first_seen=datetime.now(timezone.utc)
            repeated = queue_conflict_idempotently(db, opportunity_id=master.id, field_name="sector",
                conflict_type="TAXONOMY_CONFLICT", selected_value="صناعي", conflicting_value="أخرى",
                source_id=source.id, source_record_id=record.id, detected_at=first_seen)
            assert repeated is None
            assert queue_conflict_idempotently(db, opportunity_id=master.id, field_name="sector",
                conflict_type="TAXONOMY_CONFLICT", selected_value="صناعي", conflicting_value="أخرى",
                source_id=source.id, source_record_id=record.id, detected_at=first_seen+timedelta(days=2)) is None
            assert db.query(OpportunityConflict).filter_by(status="OPEN").count() == 0
            reevaluation=db.query(SystemEvent).filter_by(event_type="SYSTEM_REEVALUATION").one()
            assert reevaluation.payload["result"]=="NO_MATERIAL_CHANGE"
            assert reevaluation.payload["prior_review_id"]==conflict.id
    finally:
        engine.dispose()


def test_material_source_value_change_creates_a_new_review_and_records_reevaluation():
    from app.service import queue_conflict_idempotently

    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, master, record = _entities(db, source_field_value="أخرى")
            prior = _conflict(db, source, master, record, selected="صناعي", conflicting="أخرى")
            prior.status = "RESOLVED_KEEP"
            changed = queue_conflict_idempotently(db, opportunity_id=master.id, field_name="sector",
                conflict_type="TAXONOMY_CONFLICT", selected_value="صناعي", conflicting_value="تجاري",
                source_id=source.id, source_record_id=record.id, detected_at=datetime.now(timezone.utc))
            assert changed is not None and changed.status == "OPEN"
            event=db.scalar(select(__import__("app.models",fromlist=["SystemEvent"]).SystemEvent).where(
                __import__("app.models",fromlist=["SystemEvent"]).SystemEvent.event_type=="REVIEW_REEVALUATED_MATERIAL_CHANGE"))
            assert event and event.payload["result"]=="MATERIAL_CHANGE_REEVALUATED"
    finally:
        engine.dispose()


def test_new_source_identity_is_not_suppressed_as_old_review():
    from app.models import Opportunity, Source, SourceOpportunity
    from app.service import queue_conflict_idempotently

    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, master, record = _entities(db)
            prior=_conflict(db,source,master,record);prior.status="RESOLVED_KEEP"
            stronger=Source(source_key="stronger-fixture",source_name_ar="مصدر أقوى",organization_name="fixture",
                base_url="https://stronger.test",opportunities_url="https://stronger.test/opportunities",priority=1)
            db.add(stronger);db.flush()
            second=SourceOpportunity(source_id=stronger.id,master_opportunity_id=master.id,source_opportunity_id="new-evidence",
                source_title="فرصة",normalized_source_title="title",source_url="https://stronger.test/1",raw_dates={},
                raw_data_json={},standardized_data_json={"fields":{"sector":{"raw":"أخرى","rule":"stronger-v1","mapping_status":"MAPPED"}}},
                first_seen_at=datetime.now(timezone.utc),last_seen_at=datetime.now(timezone.utc),content_hash="c"*64,parser_version="fixture")
            db.add(second);db.flush()
            reevaluated=queue_conflict_idempotently(db,opportunity_id=master.id,field_name="sector",
                conflict_type="TAXONOMY_CONFLICT",selected_value="صناعي",conflicting_value="أخرى",
                source_id=stronger.id,source_record_id=second.id,detected_at=datetime.now(timezone.utc))
            assert reevaluated is not None and reevaluated.status=="OPEN"
    finally:
        engine.dispose()


def _assert_unchanged_batch_is_idempotent(source_key, case_count):
    from app.models import Opportunity, SourceOpportunity, SystemEvent
    from app.service import queue_conflict_idempotently
    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, _, _ = _entities(db, source_key=source_key)
            now=datetime.now(timezone.utc)
            for index in range(case_count):
                master=Opportunity(canonical_id=f"{source_key}-{index}",title_ar="فرصة",normalized_title="title",
                    primary_publication_platform=source_key,city="الأحساء",status="متاحة",sector="صناعي",
                    first_seen_at=now,last_seen_at=now,last_updated_at=now,created_at=now,updated_at=now)
                db.add(master);db.flush()
                record=SourceOpportunity(source_id=source.id,master_opportunity_id=master.id,
                    source_opportunity_id=f"{source_key}-record-{index}",source_title="فرصة",normalized_source_title="title",
                    source_url=f"https://fixture.test/{index}",raw_dates={},raw_data_json={},
                    standardized_data_json={"fields":{"sector":{"raw":"أخرى","rule":"fixture","mapping_status":"MAPPED"}}},
                    first_seen_at=now,last_seen_at=now,content_hash=(f"{index:064x}"[-64:]),parser_version="fixture")
                db.add(record);db.flush()
                prior=_conflict(db,source,master,record)
                prior.status="RESOLVED_KEEP"
            db.flush()
            for prior in db.scalars(select(OpportunityConflict).where(OpportunityConflict.status=="RESOLVED_KEEP")).all():
                assert queue_conflict_idempotently(db,opportunity_id=prior.opportunity_id,field_name=prior.field_name,
                    conflict_type=prior.conflict_type,selected_value=prior.selected_value,conflicting_value=prior.conflicting_value,
                    source_id=prior.source_id,source_record_id=prior.source_record_id,detected_at=now+timedelta(days=1)) is None
            assert db.query(OpportunityConflict).filter_by(status="OPEN").count()==0
            assert db.query(SystemEvent).filter_by(event_type="SYSTEM_REEVALUATION").count()==case_count
    finally:
        engine.dispose()


def test_furas_high_volume_unchanged_scan_does_not_recreate_reviews():
    _assert_unchanged_batch_is_idempotent("furas",120)


def test_al_ahsa_unchanged_scan_does_not_recreate_reviews():
    _assert_unchanged_batch_is_idempotent("alahsa-opportunities",7)


def test_material_canonical_change_allows_conflict_reevaluation():
    from app.service import queue_conflict_idempotently

    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, master, record = _entities(db, source_field_value="أخرى")
            conflict = _conflict(db, source, master, record, selected="صناعي", conflicting="أخرى")
            conflict.status = "RESOLVED_KEEP"
            changed = queue_conflict_idempotently(db, opportunity_id=master.id, field_name="sector",
                conflict_type="TAXONOMY_CONFLICT", selected_value="تجاري", conflicting_value="أخرى",
                source_id=source.id, source_record_id=record.id, detected_at=datetime.now(timezone.utc))
            assert changed is not None and changed.status == "OPEN"
    finally:
        engine.dispose()


def test_mapping_evidence_version_change_after_resolved_review_allows_reevaluation():
    from app.models import SystemEvent
    from app.service import queue_conflict_idempotently

    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, master, record = _entities(db, source_field_value="أخرى")
            first = queue_conflict_idempotently(db, opportunity_id=master.id, field_name="sector",
                conflict_type="TAXONOMY_CONFLICT", selected_value="صناعي", conflicting_value="أخرى",
                source_id=source.id, source_record_id=record.id, detected_at=datetime.now(timezone.utc))
            assert first is not None and first.status == "OPEN"
            captured = db.scalar(select(SystemEvent).where(
                SystemEvent.event_type == "REVIEW_FINGERPRINT_CAPTURED"))
            assert captured and captured.payload["review_id"] == first.id

            first.status = "RESOLVED_KEEP"
            changed_projection = dict(record.standardized_data_json)
            changed_fields = dict(changed_projection["fields"])
            changed_sector = dict(changed_fields["sector"])
            changed_sector["rule"] = "fixture-mapping-v2"
            changed_fields["sector"] = changed_sector
            changed_projection["fields"] = changed_fields
            record.standardized_data_json = changed_projection

            reevaluated = queue_conflict_idempotently(db, opportunity_id=master.id, field_name="sector",
                conflict_type="TAXONOMY_CONFLICT", selected_value="صناعي", conflicting_value="أخرى",
                source_id=source.id, source_record_id=record.id, detected_at=datetime.now(timezone.utc))
            assert reevaluated is not None and reevaluated.status == "OPEN"
            material_event = db.scalar(select(SystemEvent).where(
                SystemEvent.event_type == "REVIEW_REEVALUATED_MATERIAL_CHANGE"))
            assert material_event and material_event.payload["result"] == "MATERIAL_CHANGE_REEVALUATED"
            assert material_event.payload["prior_fingerprint"] != material_event.payload["new_fingerprint"]
    finally:
        engine.dispose()


def test_formatting_and_missing_value_variants_reuse_resolved_conflict():
    from app.service import queue_conflict_idempotently

    engine, factory = _db_fixture()
    try:
        with factory() as db:
            source, master, record = _entities(db, source_field_value="أخرى")
            conflict = _conflict(db, source, master, record, selected="غير محدد", conflicting="أخرى")
            conflict.status = "RESOLVED_KEEP"
            formatted = queue_conflict_idempotently(db, opportunity_id=master.id, field_name="sector",
                conflict_type="TAXONOMY_CONFLICT", selected_value="", conflicting_value=" أُخرى ",
                source_id=source.id, source_record_id=record.id, detected_at=datetime.now(timezone.utc))
            assert formatted is None
            assert db.query(OpportunityConflict).filter_by(status="OPEN").count() == 0
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

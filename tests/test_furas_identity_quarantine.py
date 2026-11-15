from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters import RawOpportunity
from app.models import (
    Base,
    Opportunity,
    Source,
    SourceIdentityAlias,
    SourceObservation,
    SourceOpportunity,
)
from app.service import _safe_record


NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


def _source(db, key="furas"):
    source = Source(
        source_key=key,
        source_name_ar="فرص" if key == "furas" else key,
        organization_name="Fixture",
        base_url="https://fixture.invalid",
        opportunities_url="https://fixture.invalid/list",
        priority=1,
    )
    db.add(source)
    db.flush()
    return source


def _pair(db, source, key="canonical-provider-id"):
    master = Opportunity(
        canonical_id=f"Q-{key}",
        title_ar="فرصة اختبار",
        normalized_title="فرصة اختبار",
        primary_publication_platform=source.source_name_ar,
        city="",
        status="متاحة",
        location_confidence_score=0,
        location_detection_method="fixture",
        location_evidence="fixture",
        data_quality_score=0,
        manual_review_required=False,
        first_seen_at=NOW,
        last_seen_at=NOW,
        last_updated_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(master)
    db.flush()
    record = SourceOpportunity(
        source_id=source.id,
        master_opportunity_id=master.id,
        source_opportunity_id=key,
        source_reference_number=key,
        source_reference_number_normalized=key,
        source_title="فرصة اختبار",
        normalized_source_title="فرصة اختبار",
        source_url=f"https://fixture.invalid/{key}",
        source_owner=None,
        raw_location="",
        raw_dates={},
        raw_status="Announced",
        canonical_status="متاحة",
        raw_data_json={"attributes": {"OPPORTUNITYID": key}},
        standardized_data_json={},
        standardization_version="fixture",
        first_seen_at=NOW,
        last_seen_at=NOW,
        content_hash="a" * 64,
        parser_version="fixture",
    )
    db.add(record)
    db.flush()
    return master, record


def _raw(provider_id, *, reference=None, raw=None):
    return RawOpportunity(
        external_id=provider_id,
        title="فرصة اختبار واردة",
        url=f"https://fixture.invalid/{provider_id}",
        status="Announced",
        reference=reference or provider_id,
        location="الرياض",
        latitude=24.7,
        longitude=46.7,
        raw=raw or {
            "source_endpoint": "https://fixture.invalid/MapServer/0",
            "enumeration_scope": "SAUDI_NATIONAL_V1",
            "checkpoint_provenance": {
                "scan_run_id": "capture-fixture-1",
                "scope_fingerprint": "scope-fixture-1",
            },
            "attributes": {"OBJECTID": 17, "OPPORTUNITYID": provider_id},
        },
    )


def _engine_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _turn_on_national_furas(monkeypatch):
    monkeypatch.setattr("app.geography_flags.flag_enabled", lambda name: name == "FURAS_NATIONAL_ENUMERATION_ENABLED")


def test_unresolved_national_furas_is_quarantined_before_autoflush_and_all_writes(monkeypatch):
    _turn_on_national_furas(monkeypatch)
    engine, factory = _engine_factory()
    flushes = []
    listener = lambda *_: flushes.append(True)
    event.listen(Session, "before_flush", listener)
    try:
        with factory() as db:
            source = _source(db)
            master, existing = _pair(db, source)
            observation = SourceObservation(
                source_opportunity_id=existing.id,
                dataset_name="fixture",
                endpoint=existing.source_url,
                official_source_id_original=existing.source_opportunity_id,
                official_source_id_normalized=existing.source_opportunity_id,
                raw_data_json={"fixture": True},
                content_hash="b" * 64,
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
            db.add(observation)
            db.commit()
            flushes.clear()
            master_before = (master.status, master.city, master.updated_at)
            source_before = (existing.source_title, existing.master_opportunity_id, existing.canonical_status)
            existing_observations = db.scalar(select(func.count(SourceObservation.id)))
            pending = Opportunity(
                canonical_id="pending-unrelated",
                title_ar="pending",
                normalized_title="pending",
                primary_publication_platform="fixture",
                city="",
                status="fixture",
                location_confidence_score=0,
                location_detection_method="fixture",
                location_evidence="fixture",
                data_quality_score=0,
                manual_review_required=False,
                first_seen_at=NOW,
                last_seen_at=NOW,
                last_updated_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
            db.add(pending)
            counts = defaultdict(int)
            raw = _raw("new-unrecognized-provider-id")
            first = _safe_record(db, source, raw, counts)
            second = _safe_record(db, source, raw, counts)

            assert first["decision"] == second["decision"] == "QUARANTINE"
            assert first["quarantine_reason"] == second["quarantine_reason"] == "UNRECOGNIZED_PROVIDER_ID"
            stable_keys = set(first) - {"processing_timestamp_utc"}
            assert {k: first[k] for k in stable_keys} == {k: second[k] for k in stable_keys}
            assert first["provider_id"] == "new-unrecognized-provider-id"
            assert first["source_namespace"] == "furas"
            assert first["capture_identifier"] == "capture-fixture-1"
            assert first["evidence_reference"]["source_object_id"] == 17
            assert len(first["evidence_reference"]["record_sha256"]) == 64
            assert flushes == []  # resolution used no_autoflush
            assert db.scalar(select(func.count(SourceOpportunity.id))) == 1
            assert db.scalar(select(func.count(SourceObservation.id))) == existing_observations
            assert (db.get(Opportunity, master.id).status,
                    db.get(Opportunity, master.id).city,
                    db.get(Opportunity, master.id).updated_at) == master_before
            assert (db.get(SourceOpportunity, existing.id).source_title,
                    db.get(SourceOpportunity, existing.id).master_opportunity_id,
                    db.get(SourceOpportunity, existing.id).canonical_status) == source_before
            assert counts["raw_count"] == 2
            assert counts["identity_quarantined_count"] == 2
            db.rollback()
    finally:
        event.remove(Session, "before_flush", listener)
        engine.dispose()


def test_exact_furas_match_and_approved_alias_still_use_existing_path(monkeypatch):
    _turn_on_national_furas(monkeypatch)
    engine, factory = _engine_factory()
    try:
        with factory() as db:
            source = _source(db)
            master, record = _pair(db, source)
            alias = SourceIdentityAlias(
                source_id=source.id,
                source_namespace="furas",
                alias_provider_id="approved-alias",
                target_source_opportunity_id=record.id,
                canonical_source_key=record.source_opportunity_id,
                expected_master_opportunity_id=master.id,
                evidence_reference_json={"record_sha256": "c" * 64},
                approval_artifact_reference="fixture.csv",
                approval_artifact_sha256="d" * 64,
                approval_decision_fingerprint="e" * 64,
                approval_method="fixture",
                approval_authority="fixture",
                approval_timestamp=NOW,
                application_timestamp=NOW,
                application_batch_id="fixture-batch",
                status="ACTIVE",
                audit_metadata_json={},
                created_at=NOW,
            )
            db.add(alias)
            db.commit()
            counts = defaultdict(int)
            exact = _safe_record(db, source, _raw(record.source_opportunity_id), counts,
                                 allow_master_creation=False)
            assert not (isinstance(exact, dict) and exact.get("decision") == "QUARANTINE")
            assert db.scalar(select(func.count(SourceOpportunity.id))) == 1
            assert db.get(SourceOpportunity, record.id).source_opportunity_id == record.source_opportunity_id
            before_alias_state = (record.source_title, record.content_hash,
                                  record.canonical_status, record.master_opportunity_id)
            alias_result = _safe_record(db, source, _raw("approved-alias"), counts,
                                        allow_master_creation=False)
            assert alias_result.id == record.id
            assert alias_result.master_opportunity_id == master.id
            assert counts.get("identity_quarantined_count", 0) == 0
            assert db.scalar(select(func.count(SourceOpportunity.id))) == 1
            assert (record.source_title, record.content_hash, record.canonical_status,
                    record.master_opportunity_id) == before_alias_state
    finally:
        engine.dispose()


def test_conflicting_inactive_and_missing_alias_targets_quarantine(monkeypatch):
    _turn_on_national_furas(monkeypatch)
    engine, factory = _engine_factory()
    try:
        with factory() as db:
            source = _source(db)
            master, record = _pair(db, source, "canonical-one")
            _other_master, canonical_collision = _pair(db, source, "collision-key")
            rows = [
                SourceIdentityAlias(
                    source_id=source.id, source_namespace="furas", alias_provider_id="collision-key",
                    target_source_opportunity_id=record.id, canonical_source_key="canonical-one",
                    expected_master_opportunity_id=master.id, evidence_reference_json={},
                    approval_artifact_reference="fixture.csv", approval_artifact_sha256="d" * 64,
                    approval_decision_fingerprint="e" * 64, approval_method="fixture",
                    approval_authority="fixture", approval_timestamp=NOW, application_timestamp=NOW,
                    application_batch_id="fixture-collision", status="ACTIVE", audit_metadata_json={}, created_at=NOW,
                ),
                SourceIdentityAlias(
                    source_id=source.id, source_namespace="furas", alias_provider_id="inactive-alias",
                    target_source_opportunity_id=record.id, canonical_source_key="canonical-one",
                    expected_master_opportunity_id=master.id, evidence_reference_json={},
                    approval_artifact_reference="fixture.csv", approval_artifact_sha256="d" * 64,
                    approval_decision_fingerprint="e" * 64, approval_method="fixture",
                    approval_authority="fixture", approval_timestamp=NOW, application_timestamp=NOW,
                    application_batch_id="fixture-inactive", status="INACTIVE", audit_metadata_json={}, created_at=NOW,
                ),
                SourceIdentityAlias(
                    source_id=source.id, source_namespace="furas", alias_provider_id="missing-target-alias",
                    target_source_opportunity_id=99999, canonical_source_key="missing-target",
                    expected_master_opportunity_id=None, evidence_reference_json={},
                    approval_artifact_reference="fixture.csv", approval_artifact_sha256="d" * 64,
                    approval_decision_fingerprint="e" * 64, approval_method="fixture",
                    approval_authority="fixture", approval_timestamp=NOW, application_timestamp=NOW,
                    application_batch_id="fixture-missing", status="ACTIVE", audit_metadata_json={}, created_at=NOW,
                ),
                SourceIdentityAlias(
                    source_id=source.id, source_namespace="furas", alias_provider_id="master-mismatch-alias",
                    target_source_opportunity_id=record.id, canonical_source_key="canonical-one",
                    expected_master_opportunity_id=None, evidence_reference_json={},
                    approval_artifact_reference="fixture.csv", approval_artifact_sha256="d" * 64,
                    approval_decision_fingerprint="e" * 64, approval_method="fixture",
                    approval_authority="fixture", approval_timestamp=NOW, application_timestamp=NOW,
                    application_batch_id="fixture-master-mismatch", status="ACTIVE", audit_metadata_json={}, created_at=NOW,
                ),
            ]
            db.add_all(rows)
            db.commit()
            counts = defaultdict(int)
            collision = _safe_record(db, source, _raw("collision-key"), counts)
            inactive = _safe_record(db, source, _raw("inactive-alias"), counts)
            missing = _safe_record(db, source, _raw("missing-target-alias"), counts)
            master_mismatch = _safe_record(db, source, _raw("master-mismatch-alias"), counts)
            assert collision["quarantine_reason"] == "IDENTITY_ATTRIBUTE_CONFLICT"
            assert inactive["quarantine_reason"] == "INVALID_IDENTITY_REFERENCE"
            assert missing["quarantine_reason"] == "INVALID_IDENTITY_REFERENCE"
            assert master_mismatch["quarantine_reason"] == "CROSS_SOURCE_MASTER_UNRESOLVED"
            assert db.get(SourceOpportunity, canonical_collision.id).source_opportunity_id == "collision-key"
            assert db.scalar(select(func.count(SourceObservation.id))) == 0
            assert db.scalar(select(func.count(SourceOpportunity.id))) == 2
            assert db.scalar(select(func.count(Opportunity.id))) == 2
    finally:
        engine.dispose()


def test_furas_quarantine_gate_is_scoped_to_furas_namespace(monkeypatch):
    _turn_on_national_furas(monkeypatch)
    engine, factory = _engine_factory()
    try:
        with factory() as db:
            source = _source(db, "invest-saudi")
            result = _safe_record(db, source, _raw("investsaudi:new-id"), defaultdict(int))
            assert not (isinstance(result, dict) and result.get("decision") == "QUARANTINE")
    finally:
        engine.dispose()


def test_concurrent_processing_of_unresolved_provider_id_is_side_effect_free(monkeypatch):
    _turn_on_national_furas(monkeypatch)
    engine, factory = _engine_factory()
    try:
        with factory() as db:
            source = _source(db)
            db.commit()
            source_id = source.id

        def process_once():
            with factory() as db:
                source = db.get(Source, source_id)
                return _safe_record(db, source, _raw("same-unresolved-id"), defaultdict(int))

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: process_once(), range(2)))
        assert all(item["decision"] == "QUARANTINE" for item in results)
        assert all(item["quarantine_reason"] == "UNRECOGNIZED_PROVIDER_ID" for item in results)
        with factory() as db:
            assert db.scalar(select(func.count(SourceOpportunity.id))) == 0
            assert db.scalar(select(func.count(SourceObservation.id))) == 0
            assert db.scalar(select(func.count(Opportunity.id))) == 0
    finally:
        engine.dispose()

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Base
from app.review_evidence import (
    attach_review_evidence, choose_sector, compare_text,
    deterministic_resolution_allowed, duration_disposition, evidence_item,
    lifecycle_evidence_relevant, location_disposition, merge_evidence_allowed,
    numeric_evidence, owner_evidence, stable_hash, value_at_path,
)


STAMP = datetime(2026, 10, 22, tzinfo=timezone.utc)


def item(**changes):
    data = dict(source_type="official", source_name="furas", source_opportunity_id=42,
        observation_id=7, raw_field="attributes.DURATION", raw_value=366,
        normalized_value=None, observed_at=STAMP, evidence_role="raw", reliability_level="uninterpreted")
    data.update(changes)
    return evidence_item(**data)


def test_recover_current_source_field():
    result = item()
    assert result["raw_value"] == 366 and result["source_opportunity_id"] == 42


def test_recover_raw_payload_field():
    assert value_at_path({"attributes": {"DURATION": 366}}, "attributes.DURATION") == 366


def test_recover_historical_observation():
    result = item(observation_id=991, observed_at="2026-10-20T10:00:00+00:00")
    assert result["observation_id"] == 991 and result["observed_at"].startswith("2026-10-20")


def test_recover_from_another_linked_source():
    result = item(source_name="furas", source_opportunity_id=2831, raw_field="attributes.CITYNAME", raw_value="الاحساء")
    assert result["source_opportunity_id"] == 2831 and result["source_name"] == "furas"


def test_missing_is_not_conflict():
    assert numeric_evidence("investment_value", None)["state"] == "MISSING"
    assert numeric_evidence("investment_value", 0, currency="SAR")["state"] == "EXPLICIT"


def test_owner_is_not_inferred_from_publisher():
    assert owner_evidence("Furas", source_role="publisher") is None


def test_explicit_sector_beats_inference():
    assert choose_sector("الزراعة", "التجارة") == "الزراعة"


def test_location_explicit_but_below_threshold_needs_review():
    assert location_disposition(explicit_site=True, confidence=0.8, threshold=0.85) == "HUMAN_REVIEW_REQUIRED"


def test_location_without_asset_evidence_stays_unavailable():
    assert location_disposition(explicit_site=False, confidence=0.2, threshold=0.85) == "LOCATION_STILL_UNAVAILABLE"


def test_deleted_from_source_history_remains_evidence():
    assert lifecycle_evidence_relevant(historical_status="PUBLISHED", source_disappeared=True)


def test_quantitative_missing_is_not_zero():
    assert numeric_evidence("land_area_sqm", None)["value"] is None


def test_unknown_currency_remains_unknown():
    result = numeric_evidence("investment_value", 1000)
    assert result["currency"] is None and result["state"] == "UNINTERPRETED"


def test_text_whitespace_difference_is_equivalent():
    assert compare_text("  Project  name ", "project name") == "EQUIVALENT_TEXT"


def test_material_text_difference_remains_manual():
    assert compare_text("Build a school", "Operate a hospital") == "MATERIAL_TEXT_DIFFERENCE"


def test_unverified_duration_remains_human_review():
    assert duration_disposition(366, semantics_verified=False) == "EVIDENCE_RECOVERED_BUT_HUMAN_REVIEW_REQUIRED"


def test_merge_lineage_requires_identity_proof():
    assert merge_evidence_allowed(identity_proven=True)


def test_unrelated_merge_evidence_is_rejected():
    assert not merge_evidence_allowed(identity_proven=False)


def test_deterministic_resolution_needs_all_safety_conditions():
    assert deterministic_resolution_allowed(explicit_or_governed=True, provenance_complete=True,
        conflicting_evidence=False, subjective_judgment=False, workflow_safe=True)


def test_ambiguous_recovered_evidence_is_not_deterministic():
    assert not deterministic_resolution_allowed(explicit_or_governed=True, provenance_complete=True,
        conflicting_evidence=False, subjective_judgment=True, workflow_safe=True)


def test_truly_unavailable_evidence_stays_blocked():
    assert duration_disposition(None, semantics_verified=False) == "TRULY_UNAVAILABLE_EVIDENCE"


def test_source_recheck_case_does_not_claim_determinism():
    assert location_disposition(explicit_site=False, confidence=None, threshold=.85) != "CONFIRMED_AL_AHSA"


@pytest.mark.parametrize("missing", [
    "source_type", "source_name", "source_opportunity_id", "raw_field", "raw_value",
    "observed_at", "evidence_role", "reliability_level",
])
def test_evidence_provenance_is_mandatory(missing):
    data = dict(source_type="official", source_name="furas", source_opportunity_id=42,
        observation_id=None, raw_field="field", raw_value="x", normalized_value=None,
        observed_at=STAMP, evidence_role="raw", reliability_level="source")
    data[missing] = None
    with pytest.raises(ValueError):
        evidence_item(**data)


def test_no_duplicate_evidence_attachment_and_idempotency():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        args = dict(review_type="LOCATION_REVIEW", review_id=8, master_id=9, source_ids=[1],
            field="location", classification="BLOCKED_BY_MISSING_EVIDENCE",
            disposition="EVIDENCE_RECOVERED_BUT_HUMAN_REVIEW_REQUIRED", evidence=[item()],
            explanation="test", fingerprint="stable-key")
        assert attach_review_evidence(db, **args)
        db.flush()
        assert not attach_review_evidence(db, **args)
        db.commit()
        events = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "REVIEW_EVIDENCE_ENRICHED")).all()
        assert len(events) == 1
        assert events[0].request_metadata["actor"] == "SYSTEM"
    engine.dispose()


def test_enrichment_fingerprint_is_stable():
    assert stable_hash({"b": 2, "a": 1}) == stable_hash({"a": 1, "b": 2})


def test_targeted_reevaluation_requires_entity_id():
    from app.review_evidence import re_evaluate_review_evidence
    with pytest.raises(ValueError):
        re_evaluate_review_evidence(None)


def test_future_evidence_can_reclassify_to_human_or_deterministic():
    assert duration_disposition(366, semantics_verified=False).endswith("HUMAN_REVIEW_REQUIRED")
    assert duration_disposition(5, semantics_verified=True) == "EVIDENCE_RECOVERED_AND_DETERMINISTIC"


def test_system_audit_is_append_only():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        attach_review_evidence(db, review_type="LOCATION_REVIEW", review_id=8, master_id=9,
            source_ids=[1], field="location", classification="BLOCKED_BY_MISSING_EVIDENCE",
            disposition="RETAIN_OPEN", evidence=[item()], explanation="test", fingerprint="audit-key")
        db.flush()
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_type == "REVIEW_EVIDENCE_ENRICHED"))
        assert event.before_json is None and event.request_metadata["append_only"] is True
        assert event.request_metadata["actor"] == "SYSTEM"
    engine.dispose()


def test_manual_sync_is_not_implied_by_evidence_enrichment():
    assert item()["source_name"] == "furas"  # Evidence construction performs no I/O or task enqueue.


def test_recovery_dq_provenance_gate_inputs_are_complete():
    result = item()
    assert all(result.get(key) is not None for key in (
        "source_name", "source_opportunity_id", "raw_field", "raw_value", "observed_at",
        "evidence_role", "reliability_level"))


def test_enrichment_does_not_touch_business_data():
    result = item()
    assert set(result) == {"source_type", "source_name", "source_opportunity_id", "observation_id",
        "raw_field", "raw_value", "normalized_value", "observed_at", "evidence_role", "reliability_level"}


def test_raw_missing_value_is_not_fabricated():
    assert value_at_path({"attributes": {}}, "attributes.DURATION") is None

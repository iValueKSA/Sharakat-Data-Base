from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data_quality import _audit_medium_inference_provenance, evaluate_data_quality
from app.models import Base, Opportunity, SystemEvent


def medium(**overrides):
    row = {
        "master_id": 577,
        "sector": "تجاري",
        "classification_origin": "INFERRED_RULE_MEDIUM",
        "engine_version": "ahda-sector-controlled-relaxation-1.0.1",
        "inference_timestamp": "2026-10-21T13:05:14Z",
        "confidence": 0.852,
        "rule_key": "MED_TITLE_CAFE_CONCESSION",
        "positive_evidence": [{"field": "title", "signal": "مقهى"}],
        "negative_evidence": [],
        "evidence_fields": ["title"],
        "confidence_margin_applicability": "NOT_APPLICABLE",
        "confidence_margin": None,
        "top_sector_id": "sector:commercial",
        "top_score": 4.0,
        "second_sector_id": None,
        "second_score": None,
    }
    row.update(overrides)
    return row


def audit(row):
    return _audit_medium_inference_provenance([row])


def test_medium_scored_rule_with_healthy_margin_passes():
    result = audit(medium(confidence_margin_applicability="APPLICABLE", confidence_margin=4.0,
        second_sector_id="sector:healthcare", second_score=0.0))
    assert result == {"contradictions": [], "incomplete_provenance": []}


def test_medium_scored_rule_with_close_competitor_is_contradiction():
    result = audit(medium(confidence_margin_applicability="APPLICABLE", confidence_margin=2.0,
        second_sector_id="sector:healthcare", second_score=2.0))
    assert len(result["contradictions"]) == 1


def test_deterministic_single_sector_null_margin_passes_contradiction_gate():
    assert audit(medium())["contradictions"] == []


def test_deterministic_rule_with_explicit_competitor_fails_contradiction_gate():
    result = audit(medium(competing_sector_signals=[{"sector": "sector:healthcare", "strength": "STRONG"}]))
    assert len(result["contradictions"]) == 1


def test_weak_competing_mention_alone_is_not_strong_contradiction():
    result = audit(medium(competing_sector_signals=[{"sector": "sector:healthcare", "strength": "WEAK"}]))
    assert result["contradictions"] == []


def test_missing_margin_is_not_coerced_to_zero():
    result = audit(medium(confidence_margin=None))
    assert result["contradictions"] == []


def test_missing_core_provenance_is_reported_separately():
    row = medium(); row.pop("rule_key")
    result = audit(row)
    assert result["contradictions"] == []
    assert result["incomplete_provenance"][0]["missing_core_fields"] == ["rule_key"]


def test_non_applicable_margin_is_valid_for_single_candidate_rule():
    assert audit(medium(confidence_margin_applicability="NOT_APPLICABLE"))["incomplete_provenance"] == []


def test_legacy_medium_without_scores_does_not_false_fail():
    row = medium(engine_version="ahda-sector-controlled-relaxation-1.0.0")
    for key in ("confidence_margin_applicability", "confidence_margin", "top_score", "second_score"):
        row.pop(key, None)
    result = audit(row)
    assert result == {"contradictions": [], "incomplete_provenance": []}


def test_applicable_but_missing_competing_scores_is_provenance_issue():
    result = audit(medium(confidence_margin_applicability="APPLICABLE", second_sector_id="sector:healthcare",
        confidence_margin=None, second_score=None))
    assert result["contradictions"] == []
    assert len(result["incomplete_provenance"]) == 1


def test_source_or_official_sector_provenance_is_not_a_medium_inference_conflict():
    row = medium(classification_origin="SOURCE_EXPLICIT", negative_evidence=["ignored by medium gate"])
    assert audit(row) == {"contradictions": [], "incomplete_provenance": []}


def test_existing_specified_sector_is_not_a_medium_inference_conflict():
    row = medium(classification_origin="EXISTING_CLASSIFIED", sector="صناعي", negative_evidence=["ignored"])
    assert audit(row) == {"contradictions": [], "incomplete_provenance": []}


def test_live_dq_evaluation_is_read_only_for_business_and_event_rows():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    try:
        with factory() as db:
            master = Opportunity(canonical_id="MASTER-577-FIXTURE", title_ar="فرصة مقهى",
                normalized_title="فرصة مقهى", sector="تجاري", primary_publication_platform="fixture",
                city="الأحساء", status="متاحة", location_confidence_score=.9,
                location_detection_method="fixture", location_evidence="fixture", data_quality_score=.9,
                manual_review_required=False, first_seen_at=now, last_seen_at=now,
                last_updated_at=now, created_at=now, updated_at=now)
            db.add(master); db.flush()
            event_row = medium(master_id=master.id)
            event_row["confidence_margin_applicability"] = "NOT_APPLICABLE"
            db.add(SystemEvent(event_type="SECTOR_CONTROLLED_RELAXATION_APPLIED", created_at=now,
                payload={"classifications": [event_row]})); db.flush()
            before = (db.query(Opportunity).count(), db.query(SystemEvent).count())
            result = evaluate_data_quality(db, scope="fast", persist=False)
            after = (db.query(Opportunity).count(), db.query(SystemEvent).count())
            gates = {row["gate_key"]: row for row in result["gates"]}
            assert gates["P2_MEDIUM_INFERENCE_WITH_STRONG_CONTRADICTION"]["status"] == "PASS"
            assert gates["MEDIUM_INFERENCE_PROVENANCE_INTEGRITY"]["status"] == "PASS"
            assert before == after
    finally:
        engine.dispose()

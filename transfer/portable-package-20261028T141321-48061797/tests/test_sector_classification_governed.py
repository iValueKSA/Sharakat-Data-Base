from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, ChangeHistory, Opportunity, Source, SourceOpportunity, SystemEvent
from app.sector_classification import ENGINE_VERSION, classify_governed, evidence_fingerprint
from app.standardization import canonical_id


def rec(**overrides):
    base = {
        "id": 1, "sector": "غير محدد", "activity": None, "sub_activity": None,
        "subsector": None, "title_ar": "فرصة استثمارية بموقع", "normalized_title": "فرصة استثمارية بموقع",
        "short_description": None, "full_description": None, "opportunity_type": "تأجير مؤقت",
        "investment_model": None, "asset_facility_type": None, "sources": [],
    }
    base.update(overrides)
    return base


def test_explicit_source_sector_is_preserved_as_high_confidence():
    result = classify_governed(rec(sources=[{"source_key": "test", "source_sector": "Tourism"}]))
    assert result["sector_id"] == "sector:tourism"
    assert result["classification"] == "HIGH_CONFIDENCE"


def test_activity_based_classification():
    result = classify_governed(rec(activity="الأنشطة المالية", title_ar="خدمات مالية"))
    assert result["sector_id"] == "sector:financial_services"


def test_subactivity_based_classification():
    result = classify_governed(rec(sub_activity="خدمات الصرافة"))
    assert result["sector_id"] == "sector:financial_services"


def test_title_classification():
    result = classify_governed(rec(title_ar="إنشاء مصنع للمنتجات المعدنية"))
    assert result["sector_id"] == "sector:industrial"


def test_description_classification():
    result = classify_governed(rec(title_ar="فرصة بموقع", full_description="إنشاء وتشغيل فندق سياحي"))
    assert result["sector_id"] == "sector:tourism"


def test_asset_facility_classification():
    result = classify_governed(rec(asset_facility_type="مستشفى", title_ar="إنشاء مستشفى تخصصي"))
    assert result["sector_id"] == "sector:healthcare"


def test_multisource_evidence_is_aggregated():
    result = classify_governed(rec(sources=[
        {"source_key": "one", "source_activity": "الأنشطة التجارية"},
        {"source_key": "two", "source_title": "مزاولة البيع في كشك"},
    ]))
    assert result["sector_id"] == "sector:commercial"
    assert len(result["positive_evidence"]) >= 2


def test_conflicting_official_evidence_still_returns_auditable_best_fit():
    result = classify_governed(rec(activity="الأنشطة التجارية", sources=[
        {"source_key": "one", "source_sector": "Tourism"},
        {"source_key": "two", "source_sector": "Healthcare"},
    ]))
    assert result["sector_id"] in {"sector:tourism", "sector:healthcare", "sector:commercial"}
    assert result["classification"] == "FORCED_BEST_FIT"


def test_owner_or_location_context_alone_does_not_mean_healthcare():
    result = classify_governed(rec(title_ar="فرصة استثمارية بموقع", opportunity_owner="مستشفى الأحساء",
                                   location_description="بالقرب من المستشفى"))
    assert result["sector_id"] == "sector:commercial"
    assert all("healthcare" not in str(item) for item in result["positive_evidence"])


def test_hospital_cafe_is_commercial():
    result = classify_governed(rec(title_ar="كشك مقهى بالقرب من مستشفى الأمير"))
    assert result["sector_id"] == "sector:commercial"


def test_tourism_is_independent():
    assert classify_governed(rec(title_ar="إنشاء وتشغيل فندق سياحي"))["sector_id"] == "sector:tourism"


def test_agriculture_is_independent():
    assert classify_governed(rec(title_ar="إنشاء مزرعة لإنتاج المحاصيل الزراعية"))["sector_id"] == "sector:agriculture"


def test_healthcare_activity():
    assert classify_governed(rec(title_ar="إنشاء مركز طبي متكامل"))["sector_id"] == "sector:healthcare"


def test_commercial_activity():
    assert classify_governed(rec(title_ar="كشك لبيع الأغذية والمشروبات"))["sector_id"] == "sector:commercial"


def test_other_requires_positive_entertainment_evidence():
    result = classify_governed(rec(title_ar="تشغيل قطار ترفيهي للأطفال"))
    assert result["sector_id"] == "sector:other"
    assert result["positive_evidence"]


def test_insufficient_evidence_gets_forced_best_fit_not_unspecified():
    result = classify_governed(rec(title_ar="فرصة استثمارية بموقع"))
    assert result["classification"] == "FORCED_BEST_FIT"
    assert result["sector_id"] != "sector:unspecified"


def test_forced_best_fit_never_uses_other_as_missing_value():
    result = classify_governed(rec(title_ar="فرصة استثمارية بموقع"))
    assert result["sector_id"] != "sector:other"
    assert not any(item["rule_key"].startswith("FORCED_BEST_FIT") and item["sector_id"] == "sector:other"
                   and item["weight"] > 0 for item in result["positive_evidence"])


def test_low_confidence_has_reason_alternative_and_evidence():
    result = classify_governed(rec(title_ar="فرصة استثمارية بموقع"))
    assert result["confidence_label"] == "LOW"
    assert result["method"] == "FORCED_BEST_FIT"
    assert result["reason"] and result["positive_evidence"]
    assert result["top_score"] is not None and result["second_score"] is not None


def test_same_input_is_deterministic():
    row = rec(title_ar="فرصة استثمارية بموقع")
    assert classify_governed(row) == classify_governed(row)


def test_new_master_has_governed_auto_classification():
    result = classify_governed(rec(id=9001, title_ar="عربة أطعمة متنقلة"))
    assert result["sector"] and result["engine_version"] == ENGINE_VERSION


def test_material_evidence_change_changes_fingerprint():
    row = rec(title_ar="فرصة استثمارية بموقع")
    first = classify_governed(row)
    changed = {**row, "title_ar": "كشك لبيع الأغذية والمشروبات"}
    second = classify_governed(changed)
    assert evidence_fingerprint(row, first) != evidence_fingerprint(changed, second)


def test_unchanged_evidence_keeps_fingerprint():
    row = rec(title_ar="فرصة استثمارية بموقع")
    assert evidence_fingerprint(row, classify_governed(row)) == evidence_fingerprint(row, classify_governed(row))


def test_classifier_never_creates_review_decision():
    result = classify_governed(rec(title_ar="فرصة استثمارية بموقع"))
    assert result["classification"] != "REVIEW_REQUIRED"


def test_governed_ingestion_writes_history_and_provenance():
    from app.service import apply_sector_phase2_after_ingestion

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    try:
        with factory() as db:
            source = Source(source_key="governed-test", source_name_ar="مصدر تجريبي", organization_name="جهة",
                base_url="https://example.test", opportunities_url="https://example.test/opportunities")
            master = Opportunity(canonical_id="GOV-1", title_ar="موقع استثماري", normalized_title="موقع استثماري",
                opportunity_owner="جهة", primary_publication_platform="fixture", sector="غير محدد",
                city="الأحساء", status="متاحة", location_confidence_score=0.9, location_detection_method="fixture",
                location_evidence="fixture", data_quality_score=0.9, manual_review_required=False,
                first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
            db.add_all([source, master]); db.flush()
            source_record = SourceOpportunity(source_id=source.id, master_opportunity_id=master.id,
                source_opportunity_id="GOV-SRC-1", source_title="موقع استثماري", normalized_source_title="موقع استثماري",
                source_url="https://example.test/1", first_seen_at=now, last_seen_at=now,
                content_hash="a"*64, parser_version="test", raw_data_json={"attributes":{"LOCATIONTYPE":"\"العربات المتنقلة\""}})
            db.add(source_record); db.flush()
            apply_sector_phase2_after_ingestion(db, master, source=source, source_record=source_record, detected_at=now)
            db.flush()
            assert canonical_id("sector", master.sector) == "sector:commercial"
            assert db.scalar(select(ChangeHistory.id).where(ChangeHistory.opportunity_id==master.id,
                ChangeHistory.changed_field=="sector")) is not None
            event = db.scalar(select(SystemEvent).where(SystemEvent.event_type=="SECTOR_GOVERNED_CLASSIFICATION_APPLIED"))
            assert event and event.payload["classifications"][0]["evidence_fingerprint"]
            assert event.payload["classifications"][0]["reason"]
    finally:
        engine.dispose()


@pytest.mark.parametrize("title", [
    "تأجير موقع لبيع الألعاب والهدايا والتحف", "تأجير موقع لمقهى", "كشك بيع أغذية",
    "سيارة آيسكريم في حديقة", "عربة أطعمة متنقلة", "فود ترك في الساحة", "مبسط غذائي",
    "بسطة لبيع التسالي والشاي", "مزاولة البيع في فعالية", "مقطورة ترويجية",
    "مزايدة تأجير موقع مقهى في كلية", "خدمات غذائية في الكلية",
])
def test_clear_retail_concessions_map_to_commercial(title):
    assert classify_governed(rec(title_ar=title))["sector_id"] == "sector:commercial"


@pytest.mark.parametrize("title", [
    "تشغيل قطار ترفيهي للأطفال", "نشاط ألعاب مائية", "نشاط ألعاب هوائية", "تأجير دبابات",
    "تشغيل سكوتر", "زحليقة ملونة", "عربات خيل حناطير", "عربات مضيئة في منتزه",
])
def test_explicit_amusement_concessions_map_to_positive_other(title):
    result = classify_governed(rec(title_ar=title))
    assert result["sector_id"] == "sector:other"
    assert result["positive_evidence"]


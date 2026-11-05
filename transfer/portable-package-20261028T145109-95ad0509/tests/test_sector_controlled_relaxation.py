from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.sector_inference_relaxed import ENGINE_VERSION, classify_relaxed
from app.standardization import canonical_id


def record(**overrides):
    row = {
        "id": 1, "sector": "غير محدد", "activity": None, "sub_activity": None,
        "title_ar": "فرصة استثمارية بموقع", "normalized_title": "فرصة استثمارية بموقع",
        "short_description": "فرصة استثمارية بموقع", "full_description": "فرصة استثمارية بموقع",
        "asset_facility_type": None, "sources": [],
    }
    row.update(overrides)
    return row


def test_official_sector_is_never_overridden():
    result = classify_relaxed(record(sources=[{"source_key": "fixture", "source_sector": "Tourism"}],
                                     title_ar="مصنع للأغذية"))
    assert result["classification"] == "HIGH_CONFIDENCE"
    assert result["sector_id"] == "sector:tourism"


def test_existing_specified_sector_is_preserved():
    result = classify_relaxed(record(sector="صناعي", title_ar="فندق سياحي"))
    assert result["classification"] == "EXISTING_CLASSIFIED"
    assert result["sector_id"] == "sector:industrial"


def test_strong_single_title_signal_is_medium():
    result = classify_relaxed(record(title_ar="إنشاء وتشغيل فندق سياحي"))
    assert result["classification"] == "MEDIUM_CONFIDENCE"
    assert result["sector_id"] == "sector:tourism"
    assert result["top_sector_id"] == "sector:tourism"
    assert result["second_sector_id"] is None
    assert result["second_score"] is None
    assert result["confidence_margin"] is None
    assert result["confidence_margin_applicability"] == "NOT_APPLICABLE"


def test_title_aliases_do_not_double_count_confidence():
    result = classify_relaxed(record(title_ar="عربة آيسكريم متنقلة"))
    assert result["sector_id"] == "sector:commercial"
    assert result["top_score"] == 4.0
    assert result["confidence"] == 0.852


def test_generic_title_uses_clear_full_description_fallback():
    result = classify_relaxed(record(title_ar="موقع استثماري", short_description="موقع استثماري",
        full_description="إنشاء وتشغيل فندق سياحي متكامل"))
    assert result["classification"] == "MEDIUM_CONFIDENCE"
    assert result["sector_id"] == "sector:tourism"
    assert any(item["field"] == "full_description" for item in result["positive_evidence"])


def test_generic_title_does_not_classify():
    assert classify_relaxed(record(title_ar="استثمار موقع للتطوير والتشغيل"))["classification"] == "INSUFFICIENT_EVIDENCE"


def test_clear_title_classifies_when_activity_is_missing():
    result = classify_relaxed(record(title_ar="إنشاء مصنع للمنتجات البلاستيكية", activity=None))
    assert result["sector_id"] == "sector:industrial"


def test_activity_and_title_agreement_is_medium():
    result = classify_relaxed(record(activity="الأنشطة المالية", title_ar="إنشاء خدمات مالية رقمية"))
    assert result["classification"] == "MEDIUM_CONFIDENCE"
    assert result["sector_id"] == "sector:financial_services"


def test_specific_asset_and_title_agreement_is_medium():
    result = classify_relaxed(record(title_ar="إنشاء وتشغيل مستشفى تخصصي", asset_facility_type="مستشفى"))
    assert result["classification"] == "MEDIUM_CONFIDENCE"
    assert "asset_facility_type" in result["evidence_fields"]


def test_source_category_and_title_agreement_is_medium():
    result = classify_relaxed(record(title_ar="خدمات صرافة وتحويل أموال", sources=[
        {"source_key": "fixture", "source_sub_activity": "خدمات الصرافة"}]))
    assert result["classification"] == "MEDIUM_CONFIDENCE"
    assert result["sector_id"] == "sector:financial_services"


def test_strong_contradiction_requires_review():
    result = classify_relaxed(record(activity="الأنشطة الزراعية والحيوانية",
        sub_activity="أنشطة وخدمات انتاج المواد غير الغذائية", title_ar="إنشاء مصنع للمنتجات الثانوية للنخيل"))
    assert result["classification"] == "REVIEW_REQUIRED"


def test_close_competing_sector_signals_require_review():
    result = classify_relaxed(record(title_ar="إنشاء مستشفى ومدرسة متكاملة"))
    assert result["classification"] == "REVIEW_REQUIRED"
    assert set(result["candidates"]) == {"sector:healthcare", "sector:education"}
    assert result["top_score"] == result["second_score"]
    assert result["confidence_margin"] == 0
    assert result["confidence_margin_applicability"] == "APPLICABLE"


def test_tourism_strong_hotel_phrase_is_accepted():
    result = classify_relaxed(record(title_ar="إنشاء وتشغيل فندق بالأحساء"))
    assert result["sector_id"] == "sector:tourism"


def test_restaurant_is_not_tourism():
    result = classify_relaxed(record(title_ar="تشغيل مطعم سياحي ومقهى"))
    assert result["sector_id"] != "sector:tourism"


def test_agriculture_strong_farm_phrase_is_accepted():
    result = classify_relaxed(record(title_ar="إنشاء مزرعة لإنتاج المحاصيل الزراعية"))
    assert result["sector_id"] == "sector:agriculture"


def test_food_retail_is_not_agriculture():
    result = classify_relaxed(record(title_ar="كشك لبيع الأغذية والمشروبات"))
    assert result["sector_id"] == "sector:commercial"


def test_industrial_factory_purpose_is_accepted():
    result = classify_relaxed(record(title_ar="إنشاء مصنع للمنتجات المعدنية"))
    assert result["sector_id"] == "sector:industrial"


def test_health_facility_purpose_is_accepted():
    result = classify_relaxed(record(title_ar="إنشاء وتشغيل مركز طبي"))
    assert result["sector_id"] == "sector:healthcare"


def test_education_facility_purpose_is_accepted():
    result = classify_relaxed(record(title_ar="إنشاء مدرسة أهلية للبنين"))
    assert result["sector_id"] == "sector:education"


def test_clear_commercial_retail_purpose_is_accepted():
    result = classify_relaxed(record(title_ar="كشك لبيع الأغذية والمشروبات"))
    assert result["sector_id"] == "sector:commercial"


def test_logistics_requires_logistics_context():
    result = classify_relaxed(record(title_ar="إنشاء مستودع لوجستي ومركز توزيع"))
    assert result["sector_id"] == "sector:logistics"


def test_sports_facility_is_accepted():
    result = classify_relaxed(record(title_ar="إنشاء نادي رياضي وملاعب"))
    assert result["sector_id"] == "sector:sports"


def test_explicit_family_entertainment_maps_to_positive_other():
    result = classify_relaxed(record(title_ar="إنشاء ركن ترفيهي يشمل ألعاب أطفال كهربائية"))
    assert result["sector_id"] == "sector:other"
    assert result["positive_evidence"]


def test_generic_land_is_not_real_estate():
    result = classify_relaxed(record(title_ar="تأجير أرض تجارية للتطوير"))
    assert result["classification"] == "INSUFFICIENT_EVIDENCE"


def test_financial_services_are_accepted():
    result = classify_relaxed(record(title_ar="إنشاء خدمات مصرفية وتمويلية"))
    assert result["sector_id"] == "sector:financial_services"


def test_other_is_distinct_from_unspecified():
    result = classify_relaxed(record(title_ar="تشغيل قطار ترفيهي للأطفال"))
    assert canonical_id("sector", "أخرى") == "sector:other"
    assert result["sector_id"] == "sector:other"
    assert result["sector_id"] != "sector:unspecified"


def test_medium_decision_has_traceable_provenance():
    result = classify_relaxed(record(title_ar="إنشاء وتشغيل فندق سياحي"))
    assert result["classification_origin"] == "INFERRED_RULE_MEDIUM"
    assert result["engine_version"] == ENGINE_VERSION
    assert result["rule_key"] and result["positive_evidence"] and result["evidence_fields"]


def test_future_official_evidence_supersedes_medium_inference():
    from app.service import apply_sector_phase2_after_ingestion
    from app.models import ChangeHistory

    master = SimpleNamespace(id=5, sector="تجاري", updated_at=None, last_updated_at=None)
    linked = SimpleNamespace(source=SimpleNamespace(source_key="alahsa-opportunities"), source_id=1,
        id=11, source_sector="Tourism", normalized_sector="السياحة", source_activity=None, source_sub_activity=None)
    previous = SimpleNamespace(payload={"classifications":[{"master_id":5,"sector":"تجاري",
        "classification_origin":"INFERRED_RULE_MEDIUM"}]})
    class ScalarRows:
        def __init__(self, rows): self.rows = rows
        def all(self): return self.rows
    class FakeDB:
        def __init__(self): self.calls = 0; self.added = []
        def scalars(self, _statement):
            self.calls += 1
            return ScalarRows([linked] if self.calls == 1 else [previous])
        def scalar(self, _statement): return None
        def add(self, value): self.added.append(value)
    db = FakeDB()
    apply_sector_phase2_after_ingestion(db, master, source=SimpleNamespace(id=1), source_record=linked,
                                        detected_at=datetime.now(timezone.utc))
    assert master.sector == "السياحة"
    assert any(isinstance(item, ChangeHistory) and item.changed_field == "sector" for item in db.added)


def test_duplicate_sector_review_is_not_created_when_open_review_exists():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.models import Base, OpportunityConflict, Source
    from app.service import queue_conflict_idempotently

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with factory() as db:
        source = Source(source_key="review-test", source_name_ar="مصدر", organization_name="جهة",
            base_url="https://review.test", opportunities_url="https://review.test/opportunities")
        db.add(source); db.flush()
        kwargs = dict(opportunity_id=1, field_name="sector", conflict_type="TAXONOMY_CONFLICT",
            selected_value="غير محدد", conflicting_value="MED_COMPETING", source_id=source.id,
            source_record_id=1, detected_at=now)
        db.add(OpportunityConflict(**kwargs, status="OPEN")); db.flush()
        assert queue_conflict_idempotently(db, **kwargs) is None
        assert db.scalar(select(__import__("sqlalchemy").func.count(OpportunityConflict.id))) == 1
    engine.dispose()


def test_classifier_repeated_run_is_idempotent():
    row = record(title_ar="كشك لبيع الأغذية والمشروبات")
    assert classify_relaxed(row) == classify_relaxed(row)


def test_dashboard_sector_counts_reconcile_with_sector_filter(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app import main
    from app.models import Base, Opportunity

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory); monkeypatch.setattr(main, "engine", engine)
    now = datetime.now(timezone.utc)
    common = dict(opportunity_owner="جهة", primary_publication_platform="fixture", city="الأحساء", status="متاحة",
        location_confidence_score=.9, location_detection_method="fixture", location_evidence="fixture",
        data_quality_score=.9, manual_review_required=False, first_seen_at=now, last_seen_at=now,
        last_updated_at=now, created_at=now, updated_at=now)
    with factory() as db:
        db.add_all([Opportunity(canonical_id="REL-DASH-1", title_ar="كشك", normalized_title="كشك", sector="تجاري", **common),
                    Opportunity(canonical_id="REL-DASH-2", title_ar="مطعم", normalized_title="مطعم", sector="تجاري", **common)])
        db.commit()
    client = TestClient(main.app)
    try:
        dashboard = client.get("/api/data-dashboard").json()
        assert next(x["count"] for x in dashboard["by_sector"] if x["canonical_id"] == "sector:commercial") == 2
        rows = client.get("/api/opportunities", params={"sector": "sector:commercial", "limit": 20}).json()
        assert rows["total"] == 2 and all(x["sector"] == "تجاري" for x in rows["items"])
    finally:
        client.close(); engine.dispose()


def test_csv_and_xlsx_sector_exports_reconcile(monkeypatch):
    from openpyxl import load_workbook
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app import main
    from app.models import Base, Opportunity

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory); monkeypatch.setattr(main, "engine", engine)
    now = datetime.now(timezone.utc)
    row = Opportunity(canonical_id="REL-EXPORT", title_ar="كشك تجاري", normalized_title="كشك تجاري", sector="تجاري",
        opportunity_owner="جهة", primary_publication_platform="fixture", city="الأحساء", status="متاحة",
        location_confidence_score=.9, location_detection_method="fixture", location_evidence="fixture",
        data_quality_score=.9, manual_review_required=False, first_seen_at=now, last_seen_at=now,
        last_updated_at=now, created_at=now, updated_at=now)
    with factory() as db: db.add(row); db.commit()
    client = TestClient(main.app)
    try:
        params = {"sector": "sector:commercial"}
        csv_response = client.get("/api/export.csv", params=params)
        csv_rows = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
        xlsx_response = client.get("/api/export.xlsx", params=params)
        book = load_workbook(io.BytesIO(xlsx_response.content), read_only=True)
        try:
            sheet = book["الفرص الاستثمارية"]
            assert len(csv_rows) == 2 and sheet.max_row == 7
            assert "تجاري" in " ".join(map(str, csv_rows[1]))
        finally: book.close()
    finally:
        client.close(); engine.dispose()

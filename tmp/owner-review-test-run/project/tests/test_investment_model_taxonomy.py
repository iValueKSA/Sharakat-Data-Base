import csv
import io
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.models import Base, Opportunity
from app.standardization import (
    STANDARDIZATION_VERSION,
    canonical_id,
    canonical_value,
    standardize_field,
    standardize_opportunity,
)


def test_investment_model_registry_is_dimension_and_source_scoped():
    assert STANDARDIZATION_VERSION == "16"
    assert standardize_field("investment_model", "EOMT", source_key="ncp") == {
        "raw": "EOMT", "normalized": "eomt", "canonical_id": "investment_model:eomt",
        "canonical_label": "التجهيز والتشغيل والصيانة والنقل", "mapping_status": "MAPPED",
        "rule": "source_scoped_investment_model_v15",
    }
    assert standardize_field("investment_model", "BTO", source_key="ncp")["canonical_id"] == "investment_model:bto"
    assert standardize_field("investment_model", "DBFOMT", source_key="ncp")["canonical_id"] == "investment_model:dbfomt"
    assert standardize_field("investment_model", "PPP", source_key="other")["mapping_status"] == "UNMAPPED"
    assert standardize_field("investment_model", "BOO", source_key="ncp")["mapping_status"] == "UNMAPPED"
    assert standardize_field("investment_model", "DBFO", source_key="ncp")["mapping_status"] == "UNMAPPED"
    assert standardize_field("investment_model", "BOT", source_key="invest-saudi")["canonical_id"] == "investment_model:bot"
    assert standardize_field("investment_model", "Joint Venture", source_key="invest-saudi")["canonical_id"] == "investment_model:joint_venture"
    assert standardize_field("investment_model", "مشاركة إيرادات", source_key="ahda")["canonical_id"] == "investment_model:revenue_share"
    assert standardize_field("investment_model", "PPP_PROJECT", source_key="ncp")["mapping_status"] == "DIMENSION_REDIRECT"
    assert canonical_id("investment_model", None) == "investment_model:missing"
    assert canonical_value("investment_model", None) == "غير محدد"
    assert canonical_id("investment_model", "أخرى") == "investment_model:other"
    assert canonical_id("investment_model", "أخرى") != canonical_id("investment_model", None)
    assert standardize_field("investment_model", "LEASE_OPPORTUNITY", source_key="kfu")["canonical_id"] == "investment_model:lease"
    assert standardize_field("investment_model", "LEASE_OPPORTUNITY", source_key="furas")["mapping_status"] == "DIMENSION_REDIRECT"


def test_source_evidence_separates_furas_type_kfu_lease_and_kfu_facility():
    furas = standardize_opportunity(
        {"title_ar": "تأجير مؤقت لموقع", "opportunity_type": "TemporaryRental", "investment_model": None},
        source_key="furas", source_record={"raw": {"attributes": {"OPPORTUNITYTYPE": "TemporaryRental"}}, "title": "تأجير مؤقت لموقع"},
    )
    assert furas["values"]["opportunity_type"] == "تأجير مؤقت"
    assert furas["values"]["investment_model"] is None
    assert furas["metadata"]["fields"]["investment_model"]["canonical_id"] == "investment_model:missing"

    kfu = standardize_opportunity(
        {"title_ar": "فرصة تأجير مواقع مؤقتة", "opportunity_type": "LEASE_OPPORTUNITY", "investment_model": None},
        source_key="kfu", source_record={"raw": {"content_type": "LEASE_OPPORTUNITY"}, "title": "فرصة تأجير مواقع مؤقتة"},
    )
    assert kfu["values"]["investment_model"] == "التأجير"
    assert kfu["metadata"]["fields"]["investment_model"]["rule"] == "explicit_source_lease_text_v12"

    facility = standardize_opportunity(
        {"title_ar": "مزايدة خدمات", "opportunity_type": "COMMERCIAL_FACILITY_OPPORTUNITY", "investment_model": None},
        source_key="kfu", source_record={"raw": {"content_type": "COMMERCIAL_FACILITY_OPPORTUNITY"}, "title": "مزايدة خدمات"},
    )
    assert facility["values"]["investment_model"] is None
    assert facility["metadata"]["fields"]["investment_model_evidence"]["mapping_status"] == "REVIEW_REQUIRED"
    assert "INVESTMENT_MODEL_REVIEW_REQUIRED" in {issue["code"] for issue in facility["issues"]}


def test_ahda_explicit_multiple_investment_options_are_queued_for_review():
    raw_text = "مواصفات المشروع. نموذج الاستثمار: خيارات متعددة (تأجير، مشاركة إيرادات، أو ملكية كاملة)."
    result = standardize_opportunity(
        {"title_ar": "تطوير فندق", "investment_model": None},
        source_key="ahda", source_record={"raw": {"raw_text": raw_text}, "title": "تطوير فندق"},
    )
    evidence = result["metadata"]["fields"]["investment_model_evidence"]
    assert result["values"]["investment_model"] is None
    assert evidence["mapping_status"] == "REVIEW_REQUIRED"
    assert evidence["normalized"] == ["تأجير", "مشاركة إيرادات", "ملكية كاملة"]
    assert evidence["rule"] == "explicit_multiple_model_options_v15"
    assert "INVESTMENT_MODEL_REVIEW_REQUIRED" in {issue["code"] for issue in result["issues"]}


def test_investment_model_filter_dashboard_csv_xlsx_are_reconciled(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", engine)
    now = datetime.now(timezone.utc)
    common = dict(primary_publication_platform="fixture", opportunity_owner="جهة", city="الأحساء", status="متاحة",
                  location_confidence_score=.9, location_detection_method="fixture", location_evidence="fixture",
                  data_quality_score=.8, manual_review_required=False, first_seen_at=now, last_seen_at=now,
                  last_updated_at=now, created_at=now, updated_at=now)
    with factory() as db:
        db.add_all([
            Opportunity(canonical_id="MODEL-1", title_ar="فرصة تأجير", normalized_title="فرصة تأجير", investment_model="التأجير", **common),
            Opportunity(canonical_id="MODEL-2", title_ar="فرصة EOMT", normalized_title="فرصة eomt", investment_model="التجهيز والتشغيل والصيانة والنقل", **common),
            Opportunity(canonical_id="MODEL-3", title_ar="نموذج غير محدد", normalized_title="نموذج غير محدد", investment_model=None, **common),
        ])
        db.commit()
    client = TestClient(main.app)
    try:
        filters = client.get("/api/filters").json()
        assert filters["investment_models"] == ["التأجير", "التجهيز والتشغيل والصيانة والنقل", "غير محدد"]
        ids = filters["option_ids"]["investment_models"]
        counts = filters["option_counts"]["investment_models"]
        expected = {"investment_model:lease": 1, "investment_model:eomt": 1, "investment_model:missing": 1}
        assert {ids[label]: counts[label] for label in ids} == expected
        for label, identity in ids.items():
            query = client.get("/api/opportunities", params={"investment_model": identity, "limit": 1}).json()
            assert counts[label] == query["total"]
        dashboard = client.get("/api/data-dashboard").json()
        assert {row["canonical_id"]: row["count"] for row in dashboard["by_investment_model"]} == expected
        assert dashboard["investment_model_coverage"] == {"total": 3, "canonical": 2, "unspecified": 1, "review": 0, "canonical_percent": 66.7}
        csv_response = client.get("/api/export.csv", params={"investment_model": "investment_model:eomt"})
        csv_rows = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
        col = csv_rows[0].index("نموذج الاستثمار")
        assert len(csv_rows) == 2 and csv_rows[1][col] == "التجهيز والتشغيل والصيانة والنقل"
        workbook = load_workbook(io.BytesIO(client.get("/api/export.xlsx", params={"investment_model": "investment_model:lease"}).content), read_only=True)
        sheet = workbook["الفرص الاستثمارية"]
        headers = [cell.value for cell in next(sheet.iter_rows(min_row=6, max_row=6))]
        model_col = headers.index("نموذج الاستثمار") + 1
        assert sheet.max_row == 7 and sheet.cell(7, model_col).value == "التأجير"
        workbook.close()
    finally:
        client.close()
        engine.dispose()

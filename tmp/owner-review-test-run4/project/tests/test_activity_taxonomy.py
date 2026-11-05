from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main
from app.adapters import RawOpportunity, normalized_record
from app.models import Base, Opportunity, Source, SourceOpportunity
from app.standardization import canonical_id, canonical_identity, canonical_value, standardize_opportunity


def test_activity_and_sector_identities_are_separate_and_missing_is_not_other():
    assert canonical_id("activity", "صناعي") == "activity:industrial"
    assert canonical_id("sector", "صناعي") == "sector:industrial"
    assert canonical_id("activity", "صناعي") != canonical_id("sector", "صناعي")
    assert canonical_id("activity", "أخرى") != canonical_id("activity", None)
    assert canonical_value("activity", "أخرى") == "أخرى"
    assert canonical_value("activity", None) != canonical_value("activity", "أخرى")
    assert canonical_identity("activity", "الأنشطة الرياضية والترفيهية") == {
        "id": "activity:sports_recreation", "label": "الأنشطة الرياضية والترفيهية"
    }
    assert canonical_id("activity", "الأنشطة الرياضية و الترفيهية") == "activity:sports_recreation"
    assert canonical_value("activity", None) == "غير محدد"


def test_activity_sub_activity_alias_and_future_ingestion_are_dimension_safe():
    assert canonical_identity("sub_activity", "انشطة التجارة العامة") == canonical_identity("sub_activity", "أنشطة التجارة العامة")
    raw = RawOpportunity("future-1", "فرصة تجارة", "https://example.test/1", activity="الأنشطة التجارية",
        sub_activity="انشطة التجارة العامة", raw={"attributes":{"ACTIVITYTYPE":"الأنشطة التجارية","SUBACTIVITYTYPE":"انشطة التجارة العامة"}})
    values = normalized_record(raw)
    standardized = standardize_opportunity(values, source_key="furas", source_record=raw)["values"]
    assert standardized["activity"] == "الأنشطة التجارية"
    assert standardized["sub_activity"] == "أنشطة التجارة العامة"
    assert standardized["sector"] is None

    technical = RawOpportunity("future-enum", "إعلان شراكة", "https://example.test/2", activity="PPP_PROJECT",
        raw={"opportunity_type":"PPP_PROJECT"})
    values = normalized_record(technical)
    result = standardize_opportunity(values, source_key="ncp", source_record=technical)
    standardized = result["values"]
    assert standardized["activity"] is None
    assert standardized["opportunity_type"] is None
    assert standardized["investment_model"] is None
    assert result["metadata"]["fields"]["opportunity_type"]["canonical_id"] == "opportunity_type:missing"


def test_activity_sub_activity_filter_details_and_exports(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread":False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", engine)
    now = datetime.now(timezone.utc)
    common = dict(primary_publication_platform="fixture", city="الأحساء", status="متاحة", location_confidence_score=.95,
        location_detection_method="fixture", location_evidence="fixture", data_quality_score=.8, manual_review_required=False,
        first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
    with factory() as db:
        source = Source(source_key="furas", source_name_ar="فرص", organization_name="وزارة", base_url="https://example.test",
            opportunities_url="https://example.test", priority=1, polling_frequency_minutes=60, enabled=True, extraction_method="test", notes="")
        row = Opportunity(canonical_id="ACT-1", title_ar="فرصة تجارة", normalized_title="فرصة تجارة", sector="تجاري",
            activity="الأنشطة التجارية", sub_activity="أنشطة التجارة العامة", opportunity_type="فرصة استثمارية", **common)
        other = Opportunity(canonical_id="ACT-2", title_ar="فرصة أخرى", normalized_title="فرصة أخرى", sector="تجاري",
            activity="تجاري", opportunity_type="فرصة استثمارية", **common)
        sports = Opportunity(canonical_id="ACT-3", title_ar="فرصة رياضية", normalized_title="فرصة رياضية", sector="الرياضة",
            activity="الأنشطة الرياضية و الترفيهية", opportunity_type="فرصة استثمارية", **common)
        activity_other = Opportunity(canonical_id="ACT-6", title_ar="فرصة بنشاط أخرى", normalized_title="فرصة بنشاط أخرى", sector="تجاري",
            activity="أخرى", opportunity_type="فرصة استثمارية", **common)
        unspecified = Opportunity(canonical_id="ACT-4", title_ar="فرصة بلا نشاط", normalized_title="فرصة بلا نشاط", sector="تجاري",
            activity=None, sub_activity="أخرى", opportunity_type="فرصة استثمارية", **common)
        unknown = Opportunity(canonical_id="ACT-5", title_ar="فرصة تصنيف تجريبي", normalized_title="فرصة تصنيف تجريبي", sector="تجاري",
            activity="نشاط غير معروف للاختبار", sub_activity="نشاط فرعي غير معروف للاختبار", opportunity_type="فرصة استثمارية", **common)
        db.add_all([source,row,other,sports,activity_other,unspecified,unknown]); db.flush()
        db.add(SourceOpportunity(source_id=source.id, master_opportunity_id=row.id, source_opportunity_id="furas-1",
            source_title=row.title_ar, normalized_source_title=row.normalized_title, source_url="https://example.test/furas-1",
            source_activity="الأنشطة التجارية", source_sub_activity="أنشطة التجارة العامة", raw_data_json={"attributes":{"ACTIVITYTYPE":"الأنشطة التجارية","SUBACTIVITYTYPE":"أنشطة التجارة العامة"}},
            raw_dates={}, first_seen_at=now, last_seen_at=now, content_hash="a"*64, parser_version="test"))
        db.commit()

    client = TestClient(main.app)
    filters = client.get("/api/filters").json()
    assert "أنشطة التجارة العامة" in filters["sub_activities"]
    chosen = filters["option_ids"]["sub_activities"]["أنشطة التجارة العامة"]
    assert chosen == "sub_activity:general_trade"
    result = client.get("/api/opportunities", params={"sub_activity":chosen}).json()
    assert result["total"] == 1
    item = result["items"][0]
    assert item["activity"] == "الأنشطة التجارية"
    assert item["sub_activity"] == "أنشطة التجارة العامة"
    detail = client.get(f"/api/opportunities/{item['id']}").json()
    assert detail["sub_activity"] == "أنشطة التجارة العامة"
    assert detail["type"] == "غير محدد"

    csv_response = client.get("/api/export.csv", params={"sub_activity":chosen})
    assert csv_response.status_code == 200
    assert "النشاط الفرعي" in csv_response.text
    assert "أنشطة التجارة العامة" in csv_response.text
    xlsx_response = client.get("/api/export.xlsx", params={"sub_activity":chosen})
    assert xlsx_response.status_code == 200
    from io import BytesIO
    workbook = load_workbook(BytesIO(xlsx_response.content), read_only=True, data_only=True)
    sheet = workbook["الفرص الاستثمارية"]
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=6, max_row=6))]
    assert "النشاط الفرعي" in headers
    assert "أنشطة التجارة العامة" in [cell.value for cell in next(sheet.iter_rows(min_row=7, max_row=7))]
    workbook.close()

    sports_label = "الأنشطة الرياضية والترفيهية"
    sports_id = filters["option_ids"]["activities"][sports_label]
    assert sports_id == "activity:sports_recreation"
    assert filters["option_counts"]["activities"][sports_label] == 1
    assert client.get("/api/opportunities", params={"activity":sports_id}).json()["total"] == 1

    missing_id = filters["option_ids"]["activities"]["غير محدد"]
    assert missing_id == "activity:missing"
    assert filters["option_counts"]["activities"]["غير محدد"] == 1
    missing_result = client.get("/api/opportunities", params={"activity":missing_id}).json()
    assert missing_result["total"] == 1
    assert missing_result["items"][0]["activity"] == "غير محدد"
    missing_detail = client.get(f"/api/opportunities/{missing_result['items'][0]['id']}").json()
    assert missing_detail["activity"] == "غير محدد"
    assert client.get("/api/export.csv", params={"activity":missing_id}).text.count("غير محدد") >= 1
    missing_xlsx = client.get("/api/export.xlsx", params={"activity":missing_id})
    workbook = load_workbook(BytesIO(missing_xlsx.content), read_only=True, data_only=True)
    sheet = workbook["الفرص الاستثمارية"]
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=6, max_row=6))]
    activity_column = headers.index("النشاط")
    assert next(sheet.iter_rows(min_row=7, max_row=7, values_only=True))[activity_column] == "غير محدد"
    workbook.close()

    activity_other = filters["option_ids"]["activities"]["أخرى"]
    sub_activity_other = filters["option_ids"]["sub_activities"]["أخرى"]
    assert activity_other == "activity:other"
    assert sub_activity_other == "sub_activity:other"
    assert activity_other != missing_id
    assert activity_other != sub_activity_other
    assert canonical_value("activity", "أخرى") != canonical_value("activity", None)
    assert canonical_id("activity", "نشاط غير معروف للاختبار").startswith("unmapped:activity:")
    assert canonical_id("sub_activity", "نشاط فرعي غير معروف للاختبار").startswith("unmapped:sub_activity:")

    for dimension, field in (("activities", "activity"), ("sub_activities", "sub_activity")):
        for label, option_id in filters["option_ids"][dimension].items():
            displayed_count = filters["option_counts"][dimension][label]
            query_count = client.get("/api/opportunities", params={field:option_id, "limit":500}).json()["total"]
            assert query_count == displayed_count, (dimension, label, option_id, displayed_count, query_count)

    dashboard = client.get("/api/data-dashboard").json()
    assert dashboard["option_ids"]["activities"][sports_label] == "activity:sports_recreation"
    assert dashboard["option_ids"]["activities"]["غير محدد"] == "activity:missing"
    assert {row["canonical_id"]:row["count"] for row in dashboard["by_activity"]}["activity:sports_recreation"] == 1
    engine.dispose()

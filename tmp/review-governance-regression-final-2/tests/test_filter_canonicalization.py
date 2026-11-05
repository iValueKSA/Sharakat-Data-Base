from datetime import datetime, timezone
import csv
import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.filter_canonicalization import canonical_id, canonical_value, comparison_key, matching_values, group_counts
from app.models import Base, Opportunity, Source, SourceOpportunity


def test_comparison_key_and_dimension_safety():
    assert comparison_key("  أمانة\u00a0الأحساء ـ  ") == comparison_key("امانة الاحساء")
    assert comparison_key("أمانة الأحساء") != comparison_key("امانة الاحسه")
    assert comparison_key("هدى") != comparison_key("هدي")
    assert canonical_value("sector", "اخرى") == "أخرى"
    assert canonical_value("opportunity_type", "Others") == "غير محدد"
    assert canonical_value("opportunity_type", "غير محدد") != canonical_value("opportunity_type", "أخرى")
    assert canonical_id("opportunity_type", "أخرى") == "opportunity_type:other"
    assert canonical_value("owner", "امانة الاحساء") == "أمانة الأحساء"
    assert canonical_value("owner", "أمانة محافظة الأحساء") == "أمانة الأحساء"


def test_legacy_technical_taxonomy_enums_are_redacted_from_business_history():
    for value in ("PPP_PROJECT", "LEASE_OPPORTUNITY", "INVESTMENT_OPPORTUNITY", "TemporaryRental"):
        assert main._business_history_value(value) == "قيمة غير معتمدة"
    assert main._business_history_value("صناعي") == "صناعي"
    assert canonical_value("owner", "محافظة الأحساء") == "محافظة الأحساء"
    assert canonical_value("owner", "the Ministry of Municipalities") == "وزارة البلديات والإسكان"
    assert canonical_value("owner", "هيئة تطوير الأحساء") != canonical_value("owner", "أمانة الأحساء")
    assert canonical_value("location", "Al-Ahsa") == "الأحساء"
    assert canonical_value("location", "الهفوف") == "الهفوف"
    assert canonical_value("sector", "بقية القطاعات") == "أخرى"
    assert canonical_value("sector", None) == canonical_value("sector", "") == canonical_value("sector", "قيمة مفقودة") == "غير محدد"
    assert canonical_value("sector", "غير محدد") != canonical_value("sector", "أخرى")
    rows = group_counts("sector", [("أخرى", 2), ("بقية القطاعات", 3), (None, 4), ("قيمة مفقودة", 1)])
    assert {row["name"]: row["count"] for row in rows} == {"أخرى": 5, "غير محدد": 5}
    assert matching_values("sector", "أخرى", ["أخرى", "بقية القطاعات", "صناعي"]) == ["أخرى", "بقية القطاعات"]


def test_filter_canonicalization_api_dashboard_and_filtered_exports(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", engine)
    now = datetime.now(timezone.utc)
    common = dict(primary_publication_platform="fixture", location_confidence_score=.9,
        location_detection_method="fixture", location_evidence="fixture", data_quality_score=.8,
        manual_review_required=False, first_seen_at=now, last_seen_at=now,
        last_updated_at=now, created_at=now, updated_at=now)
    with factory() as db:
        values = [
            ("أخرى", "أخرى", "أمانة الأحساء", "الأحساء", "متاحة"),
            ("اخرى", "اخرى", "امانة الاحساء", "الاحساء", "UNKNOWN"),
            ("بقية القطاعات", "Others", "أمانة  الأحساء ", "Al-Ahsa", "غير محددة"),
            ("غير محدد", "غير محدد", "أمانة محافظة الأحساء", "الهفوف", "Announced"),
            ("صناعي", "صناعي", "هيئة تطوير الأحساء", "الهفوف", "متاحة"),
            ("Industrial", "Industrial", "هيئة تطوير الأحساء", "الأحساء", "متاحة"),
            ("تجاري", "تجاري", "وزارة البلديات والإسكان", "الهفوف", "Announced"),
            ("تجاري", "تجاري", "the Ministry of Municipalities", "الهفوف", "Announced"),
        ]
        masters = []
        for index, (sector, kind, owner, city, status) in enumerate(values, 1):
            masters.append(Opportunity(canonical_id=f"CAN-{index}", title_ar=f"فرصة {index}", normalized_title=f"فرصة {index}", sector=sector, activity="نشاط اختبار" if index == 1 else None, opportunity_type=kind, opportunity_owner=owner, city=city, status=status, **common))
        db.add_all(masters)
        source = Source(source_key="fixture", source_name_ar="المصدر التجريبي", organization_name="جهة", base_url="https://example.test", opportunities_url="https://example.test/list", technical_health="HEALTHY", coverage_status="COMPLETE_PUBLIC_SOURCE", enabled=True, priority=1)
        db.add(source); db.flush()
        raw_row = SourceOpportunity(source_id=source.id, master_opportunity_id=masters[1].id, source_opportunity_id="raw-1", source_title="فرصة 2", normalized_source_title="فرصة 2", source_url="https://example.test/1", source_owner="امانة الاحساء", raw_location="الاحساء", raw_dates={}, raw_status="UNKNOWN", raw_data_json={"original": "preserved"}, first_seen_at=now, last_seen_at=now, content_hash="raw-hash", parser_version="test")
        db.add(raw_row); db.commit()

    before_counts = None
    with factory() as db:
        before_counts = (db.scalar(select(func.count(Opportunity.id))), db.scalar(select(func.count(SourceOpportunity.id))), db.get(SourceOpportunity, raw_row.id).source_owner)
    client = TestClient(main.app)
    try:
        filters = client.get("/api/filters").json()
        for key, dimension in (("sectors", "sector"), ("activities", "activity"), ("owners", "owner"), ("types", "opportunity_type"), ("locations", "location"), ("statuses", "status")):
            labels = filters[key]
            assert len(labels) == len({canonical_value(dimension, label) for label in labels})
            assert all(label and label == label.strip() for label in labels)
        assert filters["sectors"].count("أخرى") == 1
        assert filters["owners"].count("أمانة الأحساء") == 1
        assert filters["owners"].count("هيئة تطوير الأحساء") == 1
        assert filters["types"] == ["غير محدد", "أخرى"]
        assert filters["option_counts"]["sectors"]["أخرى"] == 3
        assert filters["option_counts"]["owners"]["أمانة الأحساء"] == 4
        assert filters["option_counts"]["owners"]["وزارة البلديات والإسكان"] == 2
        assert filters["option_counts"]["types"]["أخرى"] == 2
        assert filters["option_counts"]["types"]["غير محدد"] == 6
        assert filters["option_ids"]["sectors"]["أخرى"] == "sector:other"
        assert filters["option_ids"]["sectors"]["غير محدد"] == "sector:unspecified"
        assert filters["option_counts"]["sectors"]["غير محدد"] == 1
        assert "نشاط اختبار" in filters["activities"]
        assert filters["option_ids"]["owners"]["أمانة الأحساء"] == "al_ahsa_municipality"
        assert filters["option_ids"]["types"]["أخرى"] == "opportunity_type:other"
        assert filters["option_ids"]["types"]["غير محدد"] == "opportunity_type:missing"

        for params, expected in [({"sector": "أخرى"}, 3), ({"owner": "أمانة الأحساء"}, 4), ({"opportunity_type": "غير محدد"}, 6), ({"opportunity_type": "أخرى"}, 2), ({"sector": "صناعي"}, 2)]:
            response = client.get("/api/opportunities", params=params)
            assert response.status_code == 200
            assert response.json()["total"] == expected
        assert client.get("/api/opportunities", params={"activity": filters["option_ids"]["activities"]["نشاط اختبار"]}).json()["total"] == 1
        assert client.get("/api/opportunities", params={"owner": "وزارة البلديات والإسكان"}).json()["total"] == 2
        searched = client.get("/api/opportunities", params={"q": "فرصة", "sector": "أخرى", "limit": 2, "offset": 2}).json()
        assert searched["total"] == 3 and len(searched["items"]) == 1
        assert searched["items"][0]["sector"] == "أخرى"

        dash = client.get("/api/data-dashboard").json()
        assert next(row["count"] for row in dash["by_sector"] if row["name"] == "أخرى") == 3
        assert next(row["count"] for row in dash["by_owner"] if row["name"] == "أمانة الأحساء") == 4
        assert next(row["count"] for row in dash["by_activity"] if row["name"] == "نشاط اختبار") == 1
        filtered_dash = client.get("/api/data-dashboard", params={"opportunity_type": "غير محدد"}).json()
        assert filtered_dash["kpis"]["total"] == 6

        csv_response = client.get("/api/export.csv", params={"owner": "أمانة الأحساء"})
        csv_rows = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
        assert len(csv_rows) == 5
        assert {row[1] for row in csv_rows[1:]} == {"أمانة الأحساء"}
        xlsx_response = client.get("/api/export.xlsx", params={"sector": "أخرى"})
        workbook = load_workbook(io.BytesIO(xlsx_response.content), read_only=True)
        sheet = workbook["الفرص الاستثمارية"]
        assert sheet.max_row == 9
        assert {sheet.cell(row, 3).value for row in range(7, sheet.max_row + 1)} == {"أخرى"}
        workbook.close()

        type_params = {"opportunity_type": filters["option_ids"]["types"]["غير محدد"]}
        type_csv = client.get("/api/export.csv", params=type_params)
        type_csv_rows = list(csv.reader(io.StringIO(type_csv.content.decode("utf-8-sig"))))
        type_header = type_csv_rows[0]
        assert len(type_csv_rows) - 1 == filters["option_counts"]["types"]["غير محدد"] == 6
        type_column = type_header.index("نوع الفرصة")
        assert {row[type_column] for row in type_csv_rows[1:]} == {"غير محدد"}
        type_xlsx = load_workbook(io.BytesIO(client.get("/api/export.xlsx", params=type_params).content), read_only=True)
        type_sheet = type_xlsx["الفرص الاستثمارية"]
        type_sheet_header = [cell.value for cell in next(type_sheet.iter_rows(min_row=6, max_row=6))]
        type_column = type_sheet_header.index("نوع الفرصة") + 1
        assert type_sheet.max_row == 12
        assert {type_sheet.cell(row, type_column).value for row in range(7, type_sheet.max_row + 1)} == {"غير محدد"}
        type_xlsx.close()
    finally:
        client.close()
    with factory() as db:
        after_counts = (db.scalar(select(func.count(Opportunity.id))), db.scalar(select(func.count(SourceOpportunity.id))), db.get(SourceOpportunity, raw_row.id).source_owner)
    assert after_counts == before_counts
    engine.dispose()


def test_sector_alias_missing_invalid_filter_dashboard_and_export_consistency(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"engine",engine)
    now=datetime.now(timezone.utc)
    common=dict(primary_publication_platform="fixture",opportunity_owner="جهة",city="الأحساء",status="متاحة",
        location_confidence_score=.9,location_detection_method="fixture",location_evidence="fixture",data_quality_score=.8,
        manual_review_required=False,first_seen_at=now,last_seen_at=now,last_updated_at=now,created_at=now,updated_at=now)
    with factory() as db:
        sectors=["أخرى","بقية القطاعات",None,"","قيمة مفقودة","فرصة استثمارية"]
        db.add_all([Opportunity(canonical_id=f"TAX-{i}",title_ar=f"حالة {i}",normalized_title=f"حالة {i}",sector=sector,**common) for i,sector in enumerate(sectors)])
        db.commit()
    client=TestClient(main.app)
    try:
        filters=client.get("/api/filters").json()
        assert filters["sectors"].count("أخرى")==1
        assert filters["sectors"].count("غير محدد")==1
        assert not ({"قيمة مفقودة","بقية القطاعات","فرصة استثمارية"}&set(filters["sectors"]))
        assert filters["option_counts"]["sectors"]["أخرى"]==2
        assert filters["option_counts"]["sectors"]["غير محدد"]==4
        assert client.get("/api/opportunities",params={"sector":"أخرى"}).json()["total"]==2
        assert client.get("/api/opportunities",params={"sector":"غير محدد"}).json()["total"]==4
        dashboard=client.get("/api/data-dashboard").json()
        assert sum(row["count"] for row in dashboard["by_sector"])==dashboard["kpis"]["total"]==6
        assert not ({"قيمة مفقودة","بقية القطاعات","فرصة استثمارية"}&{row["name"] for row in dashboard["by_sector"]})
        csv_response=client.get("/api/export.csv",params={"sector":"أخرى"})
        csv_rows=list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
        assert csv_rows[0][2:7]==["القطاع","النشاط","النشاط الفرعي","القطاع الفرعي","نوع الفرصة"]
        assert len(csv_rows)==3 and {row[2] for row in csv_rows[1:]}=={"أخرى"}
        xlsx=load_workbook(io.BytesIO(client.get("/api/export.xlsx",params={"sector":"أخرى"}).content),read_only=True)
        sheet=xlsx["الفرص الاستثمارية"]
        assert sheet.cell(6,3).value=="القطاع" and sheet.cell(6,4).value=="النشاط"
        assert {sheet.cell(row,3).value for row in range(7,9)}=={"أخرى"}
        xlsx.close()
    finally:
        client.close();engine.dispose()

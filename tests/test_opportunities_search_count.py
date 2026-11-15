from datetime import datetime, timezone
import io
import csv
import pytest

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import export_storage, main
from app.excel_export import HEADERS
from app.models import Base, GeographicReferenceDataset, GeographicReferenceUnit, Opportunity, OpportunityConflict, OpportunityLocation, Source, SourceObservation, SourceOpportunity


def test_opportunity_search_count_uses_filters_and_page_limit(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    now = datetime.now(timezone.utc)
    common = dict(
        primary_publication_platform="fixture",
        location_confidence_score=0.9,
        location_detection_method="fixture",
        location_evidence="fixture",
        data_quality_score=0.8,
        manual_review_required=False,
        first_seen_at=now,
        last_seen_at=now,
        last_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    with factory() as db:
        db.add_all([
            Opportunity(canonical_id="A-1", title_ar="مستودع صناعي أول", normalized_title="مستودع صناعي اول", sector="صناعي", status="متاحة", investment_value=1250000.5, currency="USD", **common),
            Opportunity(canonical_id="A-2", title_ar="مستودع صناعي ثان", normalized_title="مستودع صناعي ثان", sector="صناعي", status="منشورة", **common),
            Opportunity(canonical_id="A-3", title_ar="حديقة عامة", normalized_title="حديقة عامة", sector="تجاري", status="متاحة", **common),
        ])
        db.commit()

    client = TestClient(main.app)
    try:
        response = client.get("/api/opportunities", params={"q": "مستودع", "limit": 1, "offset": 0})
        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert len(response.json()["items"]) == 1

        filtered = client.get("/api/opportunities", params={"q": "مستودع", "sector": "صناعي", "status": "متاحة"})
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 2
        assert {item["canonical_id"] for item in filtered.json()["items"]} == {"A-1", "A-2"}
        assert all(item["status"] == "متاحة" for item in filtered.json()["items"])
        valued_item = next(item for item in filtered.json()["items"] if item["canonical_id"] == "A-1")
        assert valued_item["investment_value"] == 1250000.5
        assert valued_item["currency"] == "USD"
        detail = client.get("/api/opportunities/1")
        assert detail.status_code == 200
        assert detail.json()["investment_value"] == 1250000.5
        assert detail.json()["currency"] == "USD"

        export = client.get("/api/export.xlsx")
        assert export.status_code == 200
        workbook = load_workbook(io.BytesIO(export.content), read_only=False)
        sheet = workbook["الفرص الاستثمارية"]
        assert workbook.sheetnames == ["الفرص الاستثمارية", "معلومات التقرير"]
        assert sheet.max_row == 9
        assert sheet.sheet_view.rightToLeft is True
        assert sheet.freeze_panes == "A7"
        assert sheet.auto_filter.ref == "A6:AF9"
        fixture_row = next(row for row in range(7, sheet.max_row + 1) if sheet.cell(row, 1).value == "مستودع صناعي أول")
        assert sheet.cell(fixture_row, 14).value == 1250000.5
        assert sheet.cell(fixture_row, 15).value == "USD"
        csv_response = client.get("/api/export.csv")
        assert csv_response.status_code == 200
        csv_rows = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
        assert len(csv_rows) == 4
        assert len(csv_rows[0]) == 32
        csv_fixture = next(row for row in csv_rows[1:] if row[0] == "مستودع صناعي أول")
        assert csv_fixture[14] == "1250000.5"
        assert csv_fixture[15] == "USD"
    finally:
        client.close()
        engine.dispose()


def test_current_master_list_pagination_filters_and_exports_ignore_source_review_multiplicity(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    now = datetime.now(timezone.utc)
    common = dict(primary_publication_platform="fixture", location_confidence_score=.9,
        location_detection_method="fixture", location_evidence="fixture", data_quality_score=.8,
        manual_review_required=False, first_seen_at=now, last_seen_at=now,
        last_updated_at=now, created_at=now, updated_at=now)
    with factory() as db:
        masters = [Opportunity(canonical_id=f"PAGE-{i}", title_ar=f"فرصة صفحة {i}",
            normalized_title=f"فرصة صفحة {i}", sector="تجاري", status="متاحة", **common) for i in range(4)]
        merged = Opportunity(canonical_id="PAGE-MERGED", title_ar="سجل مدمج", normalized_title="سجل مدمج",
            sector="تجاري", status="متاحة", merged_into_id=None, **common)
        db.add_all(masters + [merged]); db.flush()
        merged.merged_into_id = masters[0].id
        sources = [Source(source_key=f"page-source-{i}", source_name_ar=f"مصدر {i}",
            organization_name=f"جهة {i}", base_url=f"https://s{i}.test", opportunities_url=f"https://s{i}.test/list",
            technical_health="HEALTHY", coverage_status="COMPLETE_PUBLIC_SOURCE", enabled=True, priority=i) for i in range(2)]
        db.add_all(sources); db.flush()
        source_rows=[]
        for i, src in enumerate(sources):
            source_rows.append(SourceOpportunity(source_id=src.id, master_opportunity_id=masters[0].id,
                source_opportunity_id=f"master-0-source-{i}", source_title="فرصة صفحة 0", normalized_source_title="فرصة صفحة 0",
                source_url=f"https://s{i}.test/item", source_owner="جهة", raw_dates={}, raw_status="متاحة",
                canonical_status="متاحة", raw_data_json={"source":i}, standardized_data_json={}, standardization_version="1",
                first_seen_at=now, last_seen_at=now, content_hash=f"{i}".ljust(64,"0"), parser_version="test"))
        db.add_all(source_rows); db.flush()
        db.add_all([SourceObservation(source_opportunity_id=row.id, dataset_name="fixture", endpoint=f"/item/{i}",
            official_source_id_original=f"raw-{i}", official_source_id_normalized=f"raw-{i}", raw_data_json={"version":i},
            content_hash=f"observation-{i}".ljust(64,"0"), first_seen_at=now, last_seen_at=now) for i,row in enumerate(source_rows)])
        db.add_all([OpportunityConflict(opportunity_id=masters[0].id, field_name=f"field-{i}",
            conflict_type="FIELD_VALUE_CONFLICT", selected_value="a", conflicting_value="b", source_id=sources[i].id,
            source_record_id=source_rows[i].id, detected_at=now, status="OPEN") for i in range(2)])
        db.commit()

    client = TestClient(main.app)
    try:
        first = client.get("/api/opportunities", params={"limit":2,"offset":0}).json()
        second = client.get("/api/opportunities", params={"limit":2,"offset":2}).json()
        ids=[item["id"] for item in first["items"]+second["items"]]
        assert first["total"]==second["total"]==4
        assert len(ids)==len(set(ids))==4
        assert ids==sorted(ids,reverse=True)
        assert client.get("/api/opportunities",params={"source":"page-source-0"}).json()["total"]==1
        assert client.get("/api/opportunities",params={"source":"page-source-1"}).json()["total"]==1
        assert {item["canonical_id"] for item in client.get("/api/opportunities",params={"source":"page-source-0"}).json()["items"]}=={"PAGE-0"}
        csv_rows=list(csv.reader(io.StringIO(client.get("/api/export.csv").content.decode("utf-8-sig"))))
        assert len(csv_rows)-1==4
        workbook=load_workbook(io.BytesIO(client.get("/api/export.xlsx").content),read_only=True)
        assert workbook["الفرص الاستثمارية"].max_row-6==4
        workbook.close()
    finally:
        client.close()
        engine.dispose()


def test_exports_batch_geography_and_source_locations_without_changing_export_values(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    now = datetime.now(timezone.utc)
    common = dict(primary_publication_platform="fixture", location_confidence_score=.9,
        location_detection_method="fixture", location_evidence="fixture", data_quality_score=.8,
        manual_review_required=False, first_seen_at=now, last_seen_at=now,
        last_updated_at=now, created_at=now, updated_at=now)
    with factory() as db:
        dataset = GeographicReferenceDataset(dataset_key="fixture", version="1", operator="fixture",
            source_url="https://fixture.test", coverage_json={}, provenance_json={},
            content_sha256="0" * 64, import_status="IMPORTED", is_current=False, created_at=now)
        source = Source(source_key="fixture", source_name_ar="مصدر اختباري", organization_name="جهة",
            base_url="https://fixture.test", opportunities_url="https://fixture.test/list")
        db.add_all([dataset, source]); db.flush()
        unit = GeographicReferenceUnit(dataset_id=dataset.id, level="governorate", external_id="fixture",
            name_ar="محافظة الأحساء")
        db.add(unit); db.flush()
        masters = [Opportunity(canonical_id=f"BATCH-{i}", title_ar=f"فرصة دفعة {i}",
            normalized_title=f"فرصة دفعة {i}", sector="صناعي", status="متاحة",
            geography_reference_unit_id=unit.id, **common) for i in range(25)]
        db.add_all(masters); db.flush()
        records = [SourceOpportunity(source_id=source.id, master_opportunity_id=master.id,
            source_opportunity_id=f"item-{i}", source_title=master.title_ar,
            normalized_source_title=master.title_ar, source_url="https://fixture.test/item",
            raw_dates={}, raw_status="متاحة", raw_data_json={}, standardized_data_json={},
            standardization_version="1", first_seen_at=now, last_seen_at=now,
            content_hash=f"{i:064d}", parser_version="fixture") for i, master in enumerate(masters)]
        db.add_all(records); db.flush()
        db.add_all([OpportunityLocation(source_opportunity_id=record.id, location_name="الأحساء")
            for record in records]); db.commit()

    query_count = [0]
    def count_query(*args, **kwargs):
        query_count[0] += 1
    event.listen(engine, "before_cursor_execute", count_query)
    client = TestClient(main.app)
    try:
        xlsx = client.get("/api/export.xlsx")
        assert xlsx.status_code == 200
        assert query_count[0] < 25
        workbook = load_workbook(io.BytesIO(xlsx.content), read_only=True)
        sheet = workbook["الفرص الاستثمارية"]
        assert sheet.max_row == 31
        assert sheet.max_column == 32
        assert [sheet.cell(6, column).value for column in range(1, 33)] == HEADERS
        assert workbook["معلومات التقرير"]["B8"].value == 25
        assert sheet["A7"].value == "فرصة دفعة 0"
        assert sheet["J7"].value == "الأحساء"

        query_count[0] = 0
        csv_response = client.get("/api/export.csv")
        assert csv_response.status_code == 200
        assert query_count[0] < 25
        csv_rows = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
        assert len(csv_rows) == 26
        assert len(csv_rows[0]) == 32
        assert csv_rows[0] == ["اسم الفرصة", "الجهة المالكة", "القطاع", "النشاط", "النشاط الفرعي",
            "القطاع الفرعي", "نوع الفرصة", "المدينة", "الحي / الموقع", "المواقع التفصيلية",
            "مرحلة المشروع", "نموذج الاستثمار", "نوع الأصل أو الموقع", "المساحة (م²)",
            "القيمة الاستثمارية", "العملة", "مدة العقد (سنة)", "تاريخ النشر", "آخر موعد للتقديم",
            "الحالة", "الرقم المرجعي الرسمي", "معرّفات المصدر التقنية", "المصدر الرئيسي", "عدد المصادر",
            "المصادر", "رابط الفرصة", "الدولة", "المنطقة", "المحافظة", "المدينة / الموقع", "الحي",
            "حالة الموقع الجغرافي"]
        assert csv_rows[1][0] == "فرصة دفعة 0"
        assert csv_rows[1][9] == "الأحساء"

        export_root = export_storage.EXPORT_TEMP_ROOT
        assert list(export_root.glob("request-*")) == []

        def fail_workbook_generation(*_args, **_kwargs):
            raise RuntimeError("simulated workbook generation failure")
        monkeypatch.setattr(main, "build_opportunities_workbook_write_only", fail_workbook_generation)
        with pytest.raises(RuntimeError, match="simulated workbook generation failure"):
            client.get("/api/export.xlsx")
        assert list(export_root.glob("request-*")) == []
        main.acquire_export_slot()
        main.release_export_slot()
    finally:
        client.close()
        engine.dispose()

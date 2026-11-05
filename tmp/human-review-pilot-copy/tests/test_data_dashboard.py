from datetime import datetime, timedelta, timezone
import io
import json

from openpyxl import load_workbook

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.models import Base, DuplicateCandidate, LocationReview, Opportunity, OpportunityConflict, Source, SourceOpportunity


def test_data_dashboard_aggregates_distinct_masters_and_exposes_scoped_filters(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", test_engine)
    now = datetime.now(timezone.utc)
    common = dict(
        primary_publication_platform="fixture", location_confidence_score=0.9,
        location_detection_method="fixture", location_evidence="Al Ahsa",
        data_quality_score=0.8, manual_review_required=False, first_seen_at=now,
        last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now,
    )
    with factory() as db:
        source_a = Source(source_key="fixture-a", source_name_ar="المصدر أ", organization_name="جهة أ", base_url="https://a.test", opportunities_url="https://a.test/opportunities", technical_health="HEALTHY", coverage_status="COMPLETE_PUBLIC_SOURCE", enabled=True, priority=1)
        source_b = Source(source_key="fixture-b", source_name_ar="المصدر ب", organization_name="جهة ب", base_url="https://b.test", opportunities_url="https://b.test/opportunities", technical_health="WARNING", coverage_status="PUBLIC_COVERAGE_LIMITED", enabled=True, priority=2)
        db.add_all([source_a, source_b]); db.flush()
        first = Opportunity(canonical_id="DASH-1", title_ar="فرصة صناعية أولى", normalized_title="فرصة صناعية اولى", opportunity_owner="هيئة أ", sector="صناعي", activity="تصنيع", subsector="تجزئة", opportunity_type="تأجير", city="الأحساء", district="الهفوف", location_description="الهفوف", land_area_sqm=1200, submission_deadline=(now.date() + timedelta(days=5)).isoformat(), status="Announced", **common)
        second = Opportunity(canonical_id="DASH-2", title_ar="فرصة سياحية ثانية", normalized_title="فرصة سياحية ثانية", opportunity_owner="هيئة ب", sector=None, subsector=None, opportunity_type="شراكة", city="الأحساء", district="المبرز", status="EXPIRED", first_seen_at=now - timedelta(days=50), last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now, primary_publication_platform="fixture", location_confidence_score=0.8, location_detection_method="fixture", location_evidence="Al Ahsa", data_quality_score=0.7, manual_review_required=False)
        merged = Opportunity(canonical_id="DASH-MERGED", title_ar="سجل مدمج", normalized_title="سجل مدمج", merged_into_id=1, **common)
        db.add_all([first, second, merged]); db.flush()
        def source_row(source, master, external):
            return SourceOpportunity(source_id=source.id, master_opportunity_id=master.id, source_opportunity_id=external, source_title=master.title_ar, normalized_source_title=master.normalized_title, source_url=f"https://{external}.test", raw_dates={}, raw_data_json={}, first_seen_at=now, last_seen_at=now, content_hash=external, parser_version="test")
        db.add_all([source_row(source_a, first, "a-1"), source_row(source_b, first, "b-1"), source_row(source_a, second, "a-2")]); db.flush()
        db.add(DuplicateCandidate(left_opportunity_id=first.id, right_opportunity_id=second.id, confidence_score=.8, status="PENDING", created_at=now))
        db.add(LocationReview(source_id=source_a.id, external_id="pending-1", title="موقع قيد المراجعة", confidence_score=.7, created_at=now))
        db.add_all([
            OpportunityConflict(opportunity_id=first.id, field_name="sector", conflict_type="TAXONOMY_CONFLICT", selected_value="صناعي", conflicting_value="تجاري", source_id=source_b.id, source_record_id=2, detected_at=now, status="OPEN"),
            OpportunityConflict(opportunity_id=first.id, field_name="owner", conflict_type="FIELD_VALUE_CONFLICT", selected_value="هيئة أ", conflicting_value="هيئة ج", source_id=source_b.id, source_record_id=2, detected_at=now, status="OPEN"),
        ])
        db.commit()

    client = TestClient(main.app)
    try:
        response = client.get("/api/data-dashboard")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["kpis"]["total"] == 2
        assert data["global_total"] == 2
        assert data["kpis"]["active"] == 1
        assert data["kpis"]["historical"] == 1
        assert data["kpis"]["multi_source"] == 1
        assert data["kpis"]["sources"] == 2
        assert data["kpis"]["enabled_sources"] == 2
        assert data["kpis"]["deadline_30d"] == 1
        trend_row = data["deadline_trend"][0]
        assert trend_row["month"] == (now.date() + timedelta(days=5)).strftime("%Y-%m")
        assert trend_row["count"] == 1 and trend_row["start_date"].endswith("-01")
        assert trend_row["end_date"].startswith(trend_row["month"])
        assert next(bucket["count"] for bucket in data["deadline_buckets"] if bucket["key"] == "7d") == 1
        assert {row["key"]: row["count"] for row in data["by_source"]} == {"fixture-a": 2, "fixture-b": 1}
        assert {row["key"]: row["share_percent"] for row in data["by_source"]} == {"fixture-a": 100.0, "fixture-b": 50.0}
        assert {row["name"]: row["count"] for row in data["by_activity"]} == {"تصنيع": 1, "غير محدد": 1}
        assert {row["name"]: row["count"] for row in data["by_type"]} == {"غير محدد": 2}
        assert all(row["canonical_id"] for row in data["by_sector"])
        assert len({row["canonical_id"] for row in data["by_sector"]}) == len(data["by_sector"])
        assert data["data_quality"] == {"pending_duplicates": 1, "pending_locations": 1, "open_taxonomy_conflicts": 1, "open_field_conflicts": 1}
        assert data["completeness"][0]["count"] == 2
        assert {row["status"] for row in data["source_health"]} == {"HEALTHY", "WARNING"}
        assert {row["status"] for row in data["source_coverage"]} == {"COMPLETE_PUBLIC_SOURCE", "PUBLIC_COVERAGE_LIMITED"}

        filtered = client.get("/api/data-dashboard", params={"sector": "صناعي", "source": "fixture-b"})
        assert filtered.status_code == 200
        assert filtered.json()["kpis"]["total"] == 1
        assert filtered.json()["global_total"] == 2
        assert filtered.json()["kpis"]["multi_source"] == 1
        assert {row["key"]: row["count"] for row in filtered.json()["by_source"]} == {"fixture-a": 1, "fixture-b": 1}

        options = client.get("/api/filters").json()
        sector_id = options["option_ids"]["sectors"]["صناعي"]
        activity_id = options["option_ids"]["activities"]["تصنيع"]
        subsector_id = options["option_ids"]["subsectors"]["تجزئة"]
        assert options["option_ids"]["sectors"]["غير محدد"] == "sector:unspecified"
        assert options["option_ids"]["subsectors"]["قيمة مفقودة"] == "subsector:missing"
        by_ids = client.get("/api/data-dashboard", params={"sector": sector_id, "subsector": subsector_id})
        assert by_ids.status_code == 200
        assert by_ids.json()["kpis"]["total"] == 1
        missing_sector = client.get("/api/data-dashboard", params={"sector": "sector:unspecified"})
        missing_activity = client.get("/api/opportunities", params={"subsector": "subsector:missing"})
        assert missing_sector.json()["kpis"]["total"] == 1
        assert missing_activity.json()["total"] == 1
        missing_sector_list = client.get("/api/opportunities", params={"sector": options["option_ids"]["sectors"]["غير محدد"]})
        assert missing_sector_list.json()["total"] == 1
        aggregated_sectors = [options["option_ids"]["sectors"]["صناعي"], options["option_ids"]["sectors"]["غير محدد"]]
        grouped_filter = {"sector_values": json.dumps(aggregated_sectors, ensure_ascii=False)}
        grouped_list = client.get("/api/opportunities", params=grouped_filter)
        assert grouped_list.status_code == 200 and grouped_list.json()["total"] == 2
        assert {item["sector"] for item in grouped_list.json()["items"]} == {"صناعي", "غير محدد"}
        grouped_csv = client.get("/api/export.csv", params=grouped_filter)
        assert grouped_csv.status_code == 200 and len(grouped_csv.content.decode("utf-8-sig").splitlines()) == 3
        grouped_xlsx = client.get("/api/export.xlsx", params=grouped_filter)
        grouped_workbook = load_workbook(io.BytesIO(grouped_xlsx.content), read_only=True)
        assert grouped_workbook["الفرص الاستثمارية"].max_row == 8
        grouped_filter_description = grouped_workbook["معلومات التقرير"]["B12"].value
        assert "صناعي" in grouped_filter_description and "غير محدد" in grouped_filter_description
        grouped_workbook.close()
        assert client.get("/api/opportunities", params={"sector_values": "not-json"}).status_code == 422

        recent = client.get("/api/data-dashboard", params={"period": "30d"})
        assert recent.status_code == 200
        assert recent.json()["kpis"]["total"] == 1

        opportunities = client.get("/api/opportunities", params={"source": "fixture-b", "deadline_after": (now.date() + timedelta(days=1)).isoformat()})
        assert opportunities.status_code == 200
        assert opportunities.json()["total"] == 1
        active_scope = client.get("/api/opportunities", params={"lifecycle": "active"})
        historical_scope = client.get("/api/opportunities", params={"lifecycle": "historical"})
        assert active_scope.json()["total"] == 1
        assert historical_scope.json()["total"] == 1
        assert client.get("/api/data-dashboard", params={"lifecycle": "active"}).json()["kpis"]["total"] == 1
        activity_filter = client.get("/api/opportunities", params={"activity": activity_id})
        assert activity_filter.json()["total"] == 1
        assert client.get("/api/opportunities", params={"subsector": subsector_id}).json()["total"] == 1
        csv_export = client.get("/api/export.csv", params={"lifecycle": "active", "subsector": subsector_id, "period": "30d"})
        assert csv_export.status_code == 200
        assert len(csv_export.content.decode("utf-8-sig").splitlines()) == 2
        xlsx_export = client.get("/api/export.xlsx", params={"lifecycle": "active", "subsector": subsector_id, "period": "30d"})
        assert xlsx_export.status_code == 200
        workbook = load_workbook(io.BytesIO(xlsx_export.content), read_only=True)
        assert workbook["الفرص الاستثمارية"].max_row == 7
        workbook.close()
        location_filtered = client.get("/api/opportunities", params={"location": "الهفوف"})
        assert location_filtered.status_code == 200
        assert location_filtered.json()["total"] == 1
        options_response = client.get("/api/filters")
        assert options_response.status_code == 200
        assert "الهفوف" in options_response.json()["locations"]
        assert "هيئة أ" in options_response.json()["owners"]
    finally:
        client.close()
        test_engine.dispose()


def test_data_dashboard_rejects_unknown_period(monkeypatch):
    client = TestClient(main.app)
    try:
        response = client.get("/api/data-dashboard", params={"period": "all-time-ish"})
        assert response.status_code == 422
    finally:
        client.close()


def test_geography_maps_only_source_verified_points_inside_local_boundary(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", test_engine)
    now = datetime.now(timezone.utc)
    common = dict(primary_publication_platform="Furas", first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now,
                  location_confidence_score=.9, location_detection_method="FURAS_ARCGIS", location_evidence="source geometry", data_quality_score=.8, manual_review_required=False)
    with factory() as db:
        source = Source(source_key="furas", source_name_ar="فرص", organization_name="جهة", base_url="https://furas.sa", opportunities_url="https://furas.sa/opportunities", enabled=True, priority=1)
        db.add(source); db.flush()
        inside = Opportunity(canonical_id="MAP-IN", title_ar="داخل الحد", normalized_title="داخل الحد", sector="صناعي", opportunity_owner="جهة", city="الأحساء", latitude=25.38, longitude=49.6, status="Announced", **common)
        outside = Opportunity(canonical_id="MAP-OUT", title_ar="خارج الحد", normalized_title="خارج الحد", sector="تجاري", opportunity_owner="جهة", city="الأحساء", latitude=24.767819999999972, longitude=50.745813999999996, status="Announced", **common)
        no_coords = Opportunity(canonical_id="MAP-NOCOORD", title_ar="دون إحداثيات", normalized_title="دون إحداثيات", sector="صناعي", opportunity_owner="جهة", city="الأحساء", latitude=None, longitude=None, status="Announced", **common)
        mismatch = Opportunity(canonical_id="MAP-MISMATCH", title_ar="إحداثيات غير مطابقة", normalized_title="إحداثيات غير مطابقة", sector="صناعي", opportunity_owner="جهة", city="الأحساء", latitude=25.38, longitude=49.6, status="Announced", **common)
        db.add_all([inside, outside, no_coords, mismatch]); db.flush()
        for item, longitude, latitude in [(inside,49.6,25.38),(outside,50.745813999999996,24.767819999999972),(mismatch,49.7,25.4)]:
            db.add(SourceOpportunity(source_id=source.id, master_opportunity_id=item.id, source_opportunity_id=item.canonical_id, source_title=item.title_ar,
                normalized_source_title=item.normalized_title, source_url="https://furas.sa/opportunity", raw_dates={}, raw_data_json={"geometry":{"x":longitude,"y":latitude}},
                first_seen_at=now,last_seen_at=now,content_hash=item.canonical_id,parser_version="test"))
        db.commit()
        inside_id, outside_id = inside.id, outside.id
    client = TestClient(main.app)
    try:
        response = client.get("/api/data-dashboard/geography")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["counts"] == {"total":4,"coordinate_records":3,"exact_mapped":1,"locality_mapped":0,"missing_coordinates":1,"outside_boundary":1,"unverified_coordinates":1,"unmapped":3}
        assert data["points"][0]["ids"] == [inside_id]
        assert outside_id not in data["points"][0]["ids"]
        filtered = client.get("/api/data-dashboard/geography", params={"sector":"sector:missing"})
        assert filtered.status_code == 200 and filtered.json()["counts"]["total"] == 0
        drilldown = client.get("/api/opportunities", params={"map_ids":str(inside_id)})
        assert drilldown.status_code == 200 and drilldown.json()["total"] == 1
        map_export = client.get("/api/export.csv", params={"map_ids":str(inside_id)})
        assert map_export.status_code == 200 and len(map_export.content.decode("utf-8-sig").splitlines()) == 2
        assert client.get("/api/opportunities", params={"map_ids":"invalid"}).status_code == 422
    finally:
        client.close(); test_engine.dispose()


def test_tourism_and_agriculture_remain_distinct_filterable_sector_buckets(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", test_engine)
    now = datetime.now(timezone.utc)
    common = dict(primary_publication_platform="fixture", opportunity_owner="جهة", city="الأحساء",
        status="متاحة", location_confidence_score=.9, location_detection_method="fixture",
        location_evidence="fixture", data_quality_score=.9, manual_review_required=False,
        first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
    with factory() as db:
        db.add_all([
            Opportunity(canonical_id="SECTOR-TOURISM", title_ar="فندق سياحي", normalized_title="فندق سياحي", sector="السياحة", **common),
            Opportunity(canonical_id="SECTOR-AGRI", title_ar="مزرعة نخيل", normalized_title="مزرعة نخيل", sector="الزراعة", **common),
            Opportunity(canonical_id="SECTOR-OTHER", title_ar="فرصة أخرى", normalized_title="فرصة أخرى", sector="أخرى", **common),
            Opportunity(canonical_id="SECTOR-UNSPEC", title_ar="فرصة غير محددة", normalized_title="فرصة غير محددة", sector=None, **common),
        ])
        db.commit()
    client = TestClient(main.app)
    try:
        dashboard = client.get("/api/data-dashboard").json()
        sectors = {row["canonical_id"]: row["count"] for row in dashboard["by_sector"]}
        assert sectors["sector:tourism"] == 1
        assert sectors["sector:agriculture"] == 1
        assert sectors["sector:other"] == 1
        assert sectors["sector:unspecified"] == 1
        for sector_id, canonical in (("sector:tourism", "SECTOR-TOURISM"), ("sector:agriculture", "SECTOR-AGRI")):
            response = client.get("/api/opportunities", params={"sector": sector_id, "limit": 100})
            assert response.status_code == 200 and response.json()["total"] == 1
            assert response.json()["items"][0]["canonical_id"] == canonical
    finally:
        client.close(); test_engine.dispose()

import csv
import io
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.geography import canonical_geography_identity, resolve_master_geography
from app.models import Base, LocationReview, Opportunity, OpportunityLocation, Source, SourceOpportunity
from app.normalization import classify_location
from app.standardization import canonical_id, canonical_value


def _fixture(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", engine)
    now = datetime.now(timezone.utc)
    common = dict(
        primary_publication_platform="fixture", opportunity_owner="جهة رسمية", sector="خدمي",
        status="متاحة", location_confidence_score=.95, location_detection_method="explicit_location",
        location_evidence="حقل موقع رسمي", data_quality_score=.9, manual_review_required=False,
        first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now,
    )
    with factory() as db:
        source = Source(source_key="fixture", source_name_ar="مصدر تجريبي", organization_name="جهة رسمية",
            base_url="https://example.test", opportunities_url="https://example.test/list",
            technical_health="HEALTHY", coverage_status="COMPLETE_FOR_DEFINED_SCOPE", enabled=True, priority=1)
        db.add(source)
        db.flush()
        records = []
        for index, (city, district) in enumerate([
            ("الأحساء", None), ("الهفوف", None), ("Al-Hofuf", None), ("المبرز", None),
            ("Tabuk", None), ("الأحساء", None), ("الأحساء", None), ("Salwa", None),
        ], start=1):
            opportunity = Opportunity(canonical_id=f"GEO-{index}", title_ar=f"فرصة جغرافية {index}",
                normalized_title=f"فرصة جغرافية {index}", city=city, district=district,
                location_description="موقع منشور" if index <= 5 else "نطاق جهة النشر (الأحساء)", **common)
            db.add(opportunity)
            records.append(opportunity)
        db.flush()
        for master_index, external_id, reason in [
            (6, "unspecified", "LOCATION_UNSPECIFIED: لم يحدد المصدر موقع المشروع."),
            (7, "region-only", "REGION_ONLY: المنطقة الشرقية فقط؛ لا يوجد موقع مشروع محدد."),
            (8, "conflict", "COORDINATE_TEXT_CONFLICT: نص الموقع والإحداثيات متعارضان."),
        ]:
            master = records[master_index - 1]
            source_row = SourceOpportunity(source_id=source.id, master_opportunity_id=master.id,
                source_opportunity_id=external_id, source_title=master.title_ar,
                normalized_source_title=master.normalized_title, source_url="https://example.test/item",
                raw_location=None if master_index == 5 else master.city, raw_dates={}, raw_status="UNKNOWN",
                raw_data_json={"raw_location_retained": True}, first_seen_at=now, last_seen_at=now,
                content_hash=f"hash-{external_id}", parser_version="fixture")
            db.add(source_row)
            db.flush()
            db.add(LocationReview(source_id=source.id, external_id=external_id, source_record_id=source_row.id,
                title=master.title_ar, source_location=source_row.raw_location, description="دليل المصدر",
                confidence_score=.3, reason=reason, status="PENDING", created_at=now))
        confirmed = records[0]
        candidate_row = SourceOpportunity(source_id=source.id, master_opportunity_id=confirmed.id,
            source_opportunity_id="candidate-review", source_title=confirmed.title_ar,
            normalized_source_title=confirmed.normalized_title, source_url="https://example.test/candidate",
            raw_location="Al-Ahsa", raw_dates={}, raw_status="Announced",
            raw_data_json={"raw_location_retained": True}, first_seen_at=now, last_seen_at=now,
            content_hash="hash-candidate-review", parser_version="fixture")
        db.add(candidate_row)
        db.flush()
        db.add(LocationReview(source_id=source.id, external_id="candidate-review", source_record_id=candidate_row.id,
            title=confirmed.title_ar, source_location="Al-Ahsa", description="دليل صريح في مصدر آخر",
            confidence_score=.8, reason="Explicit Al-Ahsa evidence appears in descriptive text; verify candidate identity.",
            status="PENDING", created_at=now))
        # Keep all five source places, including Al-Ahsa, attached to one Master.
        multi = records[4]
        multi_source = SourceOpportunity(source_id=source.id, master_opportunity_id=multi.id,
            source_opportunity_id="multi-city", source_title=multi.title_ar, normalized_source_title=multi.normalized_title,
            source_url="https://example.test/multi", raw_location="Al-Ahsa; Tabuk; Qassim; Hafr Al Batin; Northern Borders",
            raw_dates={}, raw_status="Announced", raw_data_json={"opportunity_locations":["Al-Ahsa","Tabuk","Qassim","Hafr Al Batin","Northern Borders"]},
            first_seen_at=now, last_seen_at=now, content_hash="hash-multi", parser_version="fixture")
        db.add(multi_source)
        db.flush()
        db.add_all([OpportunityLocation(source_opportunity_id=multi_source.id, location_name=place,
            location_scope="MULTI_LOCATION", is_al_ahsa=(place == "Al-Ahsa"), source_location_text=multi_source.raw_location)
            for place in ["Al-Ahsa", "Tabuk", "Qassim", "Hafr Al Batin", "Northern Borders"]])
        db.commit()
        ids = {"governorate": records[0].id, "arabic_hofuf": records[1].id, "english_hofuf": records[2].id,
            "mubarraz": records[3].id, "multi": records[4].id, "unspecified": records[5].id,
            "region_only": records[6].id, "conflict": records[7].id}
    return engine, factory, ids


def test_locality_aliases_keep_locality_and_roll_up_to_governorate():
    for alias, locality in [("الهفوف", "الهفوف"), ("Hofuf", "الهفوف"), ("Al-Hofuf", "الهفوف"),
                            ("المبرز", "المبرز"), ("Al-Mubarraz", "المبرز"), ("Al Mubarraz", "المبرز")]:
        identity = canonical_geography_identity(alias)
        assert identity["label"] == locality
        assert identity["id"].startswith("al_ahsa_locality:")
        assert canonical_value("location", alias) == locality
        assert resolve_master_geography(alias)["governorate"] == "الأحساء"
        assert classify_location(alias)[0] is True
    hierarchy = resolve_master_geography("Al-Mubarraz")
    assert hierarchy["locality"] == "المبرز"
    assert hierarchy["governorate"] == "الأحساء"
    assert hierarchy["region"] == "المنطقة الشرقية"
    assert hierarchy["country_code"] == "SA"
    assert canonical_id("location", "Al-Hofuf") == canonical_id("location", "الهفوف")


def test_governorate_filter_rolls_up_localities_and_excludes_open_location_reviews(monkeypatch):
    engine, factory, ids = _fixture(monkeypatch)
    client = TestClient(main.app)
    try:
        filters = client.get("/api/filters").json()
        ahsa_id = filters["option_ids"]["locations"]["الأحساء"]
        assert ahsa_id == "al_ahsa_governorate"
        assert filters["option_counts"]["locations"]["الأحساء"] == 5
        assert {row["id"] for row in filters["location_hierarchy"] if row["level"] == "locality"} >= {
            canonical_geography_identity("الهفوف")["id"], canonical_geography_identity("المبرز")["id"]
        }
        response = client.get("/api/opportunities", params={"location": ahsa_id, "limit": 100})
        assert response.status_code == 200
        returned = {item["id"] for item in response.json()["items"]}
        expected = {ids["governorate"], ids["arabic_hofuf"], ids["english_hofuf"], ids["mubarraz"], ids["multi"]}
        assert response.json()["total"] == 5
        assert returned == expected
        assert ids["unspecified"] not in returned
        assert ids["region_only"] not in returned
        assert ids["conflict"] not in returned
        # The general Master universe is retained and communicates review status.
        general = client.get("/api/opportunities", params={"limit": 100}).json()
        assert general["total"] == 8
        by_id = {item["id"]: item for item in general["items"]}
        assert by_id[ids["unspecified"]]["geography"]["status"] == "LOCATION_UNSPECIFIED"
        assert by_id[ids["unspecified"]]["geography"]["confirmed"] is False
        assert by_id[ids["unspecified"]]["city"] == "غير محدد"
        assert by_id[ids["unspecified"]]["location"] is None
        assert by_id[ids["region_only"]]["geography"]["status"] == "LOCATION_REVIEW_REQUIRED"
        assert by_id[ids["region_only"]]["geography"]["region"] == "المنطقة الشرقية"
        assert by_id[ids["conflict"]]["geography"]["confirmed"] is False
    finally:
        client.close()
        engine.dispose()


def test_dashboard_map_and_exports_use_the_same_governorate_set(monkeypatch):
    engine, factory, ids = _fixture(monkeypatch)
    client = TestClient(main.app)
    try:
        params = {"location": "الأحساء"}
        listing = client.get("/api/opportunities", params={**params, "limit": 100}).json()
        dashboard = client.get("/api/data-dashboard", params=params).json()
        geography = client.get("/api/data-dashboard/geography", params=params).json()
        csv_rows = list(csv.reader(io.StringIO(client.get("/api/export.csv", params=params).content.decode("utf-8-sig"))))
        workbook = load_workbook(io.BytesIO(client.get("/api/export.xlsx", params=params).content), read_only=True)
        sheet = workbook["الفرص الاستثمارية"]
        assert listing["total"] == dashboard["kpis"]["total"] == geography["counts"]["total"] == 5
        assert len(csv_rows) - 1 == 5
        assert sheet.max_row == 11
        headers = [cell.value for cell in next(sheet.iter_rows(min_row=6, max_row=6))]
        assert headers[-6:] == ["الدولة", "المنطقة", "المحافظة", "المدينة / الموقع", "الحي", "حالة الموقع الجغرافي"]
        assert sheet.cell(7, headers.index("المحافظة") + 1).value == "الأحساء"
        workbook.close()
        detail = client.get(f"/api/opportunities/{ids['multi']}").json()
        assert detail["geography"]["locality"] is None
        assert detail["geography"]["governorate"] == "الأحساء"
        assert detail["geography"]["confirmed"] is True
        assert detail["city"] == "Tabuk"
        assert len(detail["sources"][0]["opportunity_locations"]) == 5
        # The export adds a normalized hierarchy while retaining the source's multi-city text.
        export = csv.DictReader(io.StringIO(client.get("/api/export.csv", params=params).content.decode("utf-8-sig")))
        multi_export = next(row for row in export if row["اسم الفرصة"] == detail["title"])
        assert multi_export["المحافظة"] == "الأحساء"
        assert set(multi_export["المواقع التفصيلية"].split(" | ")) == {"Al-Ahsa", "Tabuk", "Qassim", "Hafr Al Batin", "Northern Borders"}
    finally:
        client.close()
        engine.dispose()

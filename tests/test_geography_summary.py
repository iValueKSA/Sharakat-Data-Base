from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from starlette.requests import Request
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.models import (Base, GeographicReferenceDataset, GeographicReferenceUnit,
    Opportunity, OpportunityLocation, Source, SourceOpportunity)


def test_geography_summary_batches_source_memberships_and_keeps_unique_masters(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", test_engine)
    now = datetime.now(timezone.utc)
    dataset = GeographicReferenceDataset(dataset_key="saudi_administrative_units", version="summary-test",
        operator="test", source_url="https://example.test/geography", content_sha256="a" * 64,
        is_current=True, created_at=now, imported_at=now, coverage_json={"country": True, "region": True,
        "governorate": True, "city": False})
    with factory() as db:
        db.add(dataset); db.flush()
        regions = [GeographicReferenceUnit(dataset_id=dataset.id, level="region", external_id=str(i),
            name_ar=f"منطقة اختبار {i}") for i in range(1, 14)]
        riyadh, eastern = regions[0], regions[4]
        db.add_all(regions); db.flush()
        ahsa = GeographicReferenceUnit(dataset_id=dataset.id, level="governorate", external_id="501",
            parent_id=eastern.id, parent_external_id="5", name_ar="الأحساء")
        db.add(ahsa); db.flush()
        source = Source(source_key="ncp", source_name_ar="NCP", organization_name="NCP",
            base_url="https://ncp.test", opportunities_url="https://ncp.test/opportunities", enabled=True, priority=1)
        db.add(source); db.flush()
        common = dict(primary_publication_platform="fixture", opportunity_owner="جهة", status="متاحة",
            first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now,
            location_confidence_score=.9, location_detection_method="fixture", location_evidence="fixture",
            data_quality_score=.9, manual_review_required=False)
        masters = [Opportunity(canonical_id=f"SUMMARY-{i}", title_ar=f"فرصة {i}", normalized_title=f"فرصة {i}",
            geography_reference_unit_id=(None if i == 6656 else ahsa.id if i == 0 else riyadh.id),
            geographic_scope=("MULTIPLE_VERIFIED_LOCATIONS" if i == 0 else "UNSPECIFIED" if i == 6656 else "REGION_WIDE"),
            **common) for i in range(6657)]
        db.add_all(masters); db.flush()
        source_rows = [SourceOpportunity(source_id=source.id, master_opportunity_id=masters[0].id,
            source_opportunity_id=f"ncp-{i}", source_title="فرصة متعددة المواقع", normalized_source_title="فرصة متعددة المواقع",
            source_url="https://ncp.test/1", raw_dates={}, raw_data_json={}, first_seen_at=now,
            last_seen_at=now, content_hash=f"ncp-{i}", parser_version="test") for i in range(2)]
        db.add_all(source_rows); db.flush()
        db.add_all([
            OpportunityLocation(source_opportunity_id=source_rows[0].id, location_name="الرياض", location_scope="MULTIPLE_LOCATIONS",
                geography_reference_unit_id=riyadh.id),
            OpportunityLocation(source_opportunity_id=source_rows[1].id, location_name="الأحساء", location_scope="MULTIPLE_LOCATIONS",
                geography_reference_unit_id=ahsa.id),
        ])
        point_record = source_rows[0]
        masters[0].latitude = 24.7
        masters[0].longitude = 46.7
        masters[0].coordinate_provenance_json = {"verified": True,
            "verification_method": "DIRECT_SOURCE_COORDINATE", "source_record_identity_matches": True,
            "source_record_id": point_record.id, "source_opportunity_id": point_record.source_opportunity_id,
            "source_url": point_record.source_url, "source_latitude": 24.7, "source_longitude": 46.7,
            "boundary_validation": {"status": "VERIFIED_IN_SAUDI", "method": "POINT_IN_OFFICIAL_REGION_POLYGON"},
            "test_only": True}
        db.commit()
        dataset_id = dataset.id

    monkeypatch.setattr(main, "_geographic_reference_readiness", lambda db: (db.get(GeographicReferenceDataset, dataset_id),
        {"ready": True, "dataset_version": "summary-test", "counts_by_level": {"region": 13, "governorate": 1, "city": 0}}))
    monkeypatch.setattr(main, "geographic_feature_state", lambda ready: {"national_dashboard_enabled": True})
    statements = []
    event.listen(test_engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    client = TestClient(main.app)
    try:
        response = client.get("/api/data-dashboard/geography-summary")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["unique_master_total"] == 6657
        assert data["mapped_unique_masters"] == 1
        assert data["unspecified_unique_masters"] == 1
        assert data["membership_counts_are_non_additive"] is True
        assert {row["id"]: row["unique_masters"] for row in data["by_region"]} == {
            **{str(i): 0 for i in range(1, 14)}, "1": 6656, "5": 1}
        assert {row["id"]: row["unique_masters"] for row in data["by_governorate"]} == {"501": 1}
        # The N+1 lookup is replaced by one joined, distinct membership query.
        assert len(statements) <= 4

        expected_by_region = {str(i): (6656 if i == 1 else 1 if i == 5 else 0) for i in range(1, 14)}
        for region_id, expected in expected_by_region.items():
            filtered_region = client.get("/api/data-dashboard/geography-summary", params={"region_id": region_id})
            assert filtered_region.status_code == 200
            assert filtered_region.json()["unique_master_total"] == expected

        filtered_governorate = client.get("/api/data-dashboard/geography-summary", params={"governorate_id": "501"})
        assert filtered_governorate.status_code == 200
        assert filtered_governorate.json()["unique_master_total"] == 1

        statements.clear()
        filtered = client.get("/api/data-dashboard/geography-summary", params={"source": "ncp"})
        assert filtered.status_code == 200
        assert filtered.json()["unique_master_total"] == 1
        assert len(statements) <= 5

        # Empty filtered sets return a valid empty summary and skip memberships.
        empty = client.get("/api/data-dashboard/geography-summary", params={"q": "no matching title"})
        assert empty.status_code == 200 and empty.json()["unique_master_total"] == 0
    finally:
        client.close()
        test_engine.dispose()


def test_geography_summary_handles_concurrent_reads(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path / 'summary-concurrency.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(test_engine)
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    now = datetime.now(timezone.utc)
    with factory() as db:
        dataset = GeographicReferenceDataset(dataset_key="saudi_administrative_units", version="concurrent-test",
            operator="test", source_url="https://example.test/geography", content_sha256="b" * 64,
            is_current=True, created_at=now, imported_at=now, coverage_json={"region": True, "governorate": True})
        db.add(dataset); db.flush()
        region = GeographicReferenceUnit(dataset_id=dataset.id, level="region", external_id="1", name_ar="الرياض")
        db.add(region); db.flush()
        common = dict(primary_publication_platform="fixture", opportunity_owner="جهة", status="متاحة",
            first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now,
            location_confidence_score=.9, location_detection_method="fixture", location_evidence="fixture",
            data_quality_score=.9, manual_review_required=False)
        db.add_all([Opportunity(canonical_id=f"CONCURRENT-{i}", title_ar=f"فرصة {i}", normalized_title=f"فرصة {i}",
            geography_reference_unit_id=region.id, geographic_scope="REGION_WIDE", **common) for i in range(100)])
        db.commit()
        dataset_id = dataset.id
    monkeypatch.setattr(main, "_geographic_reference_readiness", lambda db: (db.get(GeographicReferenceDataset, dataset_id),
        {"ready": True, "dataset_version": "concurrent-test", "counts_by_level": {"region": 1, "governorate": 0, "city": 0}}))
    monkeypatch.setattr(main, "geographic_feature_state", lambda ready: {"national_dashboard_enabled": True})

    def fetch(_):
        request = Request({"type": "http", "method": "GET", "path": "/api/data-dashboard/geography-summary",
            "query_string": b"", "headers": [], "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 12345), "scheme": "http"})
        return 200, main.data_dashboard_geography_summary(request).get("unique_master_total")

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(fetch, range(4)))
        assert results == [(200, 100)] * 4
    finally:
        test_engine.dispose()

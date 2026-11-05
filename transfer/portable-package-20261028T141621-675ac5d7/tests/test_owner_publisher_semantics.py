from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.main import source_json, source_publishing_entity
from app.models import Base, Opportunity, Source
from app.standardization import STANDARDIZATION_VERSION, canonical_id, canonical_value


def test_source_api_separates_platform_from_source_operator():
    source = Source(
        id=1,
        source_key="invest-saudi",
        source_name_ar="استثمر في السعودية",
        organization_name="وزارة الاستثمار",
        opportunities_url="https://example.test/opportunities",
        source_type="national_opportunity_platform",
        priority=1,
        polling_frequency_minutes=360,
        enabled=True,
        sync_status="READY",
        technical_health="HEALTHY",
        coverage_status="PUBLIC_COVERAGE_LIMITED",
        coverage_notes="",
        extraction_method="public API",
        last_attempted_sync=None,
        last_successful_sync=None,
        last_record_count=0,
        last_source_total_reported=None,
        last_collection_completeness_percent=None,
        last_pagination_complete=None,
        notes="",
    )

    result = source_json(source, count=0)

    assert result["publication_platform"] == "استثمر في السعودية"
    assert result["source_operator"] == "وزارة الاستثمار"
    assert "owner" not in result


def test_item_publisher_uses_explicit_source_field_and_stays_separate_from_owner():
    furas_record = SimpleNamespace(
        source=SimpleNamespace(source_key="furas"),
        raw_data_json={"attributes": {"AMANA": "أمانة الأحساء", "ENTITIESNAME": "وزارة البلديات والإسكان"}},
    )
    assert source_publishing_entity(furas_record) == "وزارة البلديات والإسكان"

    explicit_record = SimpleNamespace(
        source=SimpleNamespace(source_key="example"),
        raw_data_json={"publisher": "ناشر مسجل"},
    )
    assert source_publishing_entity(explicit_record) == "ناشر مسجل"

    missing_record = SimpleNamespace(source=SimpleNamespace(source_key="example"), raw_data_json={})
    assert source_publishing_entity(missing_record) is None


def test_missing_owner_uses_the_approved_unspecified_bucket_without_collapsing_other():
    assert canonical_value("owner", None) == "غير محدد"
    assert canonical_value("owner", "قيمة مفقودة") == "غير محدد"
    assert canonical_id("owner", None) == canonical_id("owner", "غير محدد") == "owner:missing"
    assert canonical_value("owner", "أخرى") == "أخرى"
    assert canonical_id("owner", "أخرى") != "owner:missing"
    assert STANDARDIZATION_VERSION == "21"


def test_missing_owner_is_available_and_filterable_as_non_business_value(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", engine)
    now = datetime.now(timezone.utc)
    with factory() as db:
        db.add(Opportunity(
            canonical_id="OWNER-MISSING-1",
            title_ar="فرصة بلا جهة مالكة مؤكدة",
            normalized_title="فرصة بلا جهة مالكة مؤكدة",
            primary_publication_platform="منصة اختبار",
            opportunity_owner=None,
            city="الأحساء",
            status="متاحة",
            first_seen_at=now,
            last_seen_at=now,
            last_updated_at=now,
            created_at=now,
            updated_at=now,
        ))
        db.commit()

    client = TestClient(main.app)
    try:
        filters = client.get("/api/filters").json()
        assert "غير محدد" in filters["owners"]
        assert filters["option_counts"]["owners"]["غير محدد"] == 1
        assert filters["option_ids"]["owners"]["غير محدد"] == "owner:missing"
        filtered = client.get("/api/opportunities", params={"owner": "owner:missing"}).json()
        assert filtered["total"] == 1
        assert filtered["items"][0]["owner"] == "غير محدد"
    finally:
        client.close()


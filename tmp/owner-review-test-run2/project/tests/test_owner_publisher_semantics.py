from types import SimpleNamespace

from app.main import source_json, source_publishing_entity
from app.models import Source
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
    assert STANDARDIZATION_VERSION == "17"


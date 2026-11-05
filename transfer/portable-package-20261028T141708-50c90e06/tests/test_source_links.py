from types import SimpleNamespace
from datetime import datetime, timezone

from app.source_links import (
    REDIRECTED_VALID,
    TEMPORARILY_UNVERIFIABLE,
    UNAVAILABLE_CONFIRMED,
    VALID,
    classify_http_result,
    furas_detail_url,
    resolve_preferred_source_link,
    resolve_source_link,
    source_url_history_observation,
)


def source_record(*, status="منشورة", misses=0, url="https://furas.momah.gov.sa/ar/opportunity/02-26-017001-58001?type=TemporaryRental"):
    source = SimpleNamespace(source_key="furas", missing_confirmation_threshold=3)
    record = SimpleNamespace(
        id=2926,
        source=source,
        source_url=url,
        source_opportunity_id="02-26-017001-58001",
        official_source_id_original=None,
        source_reference_number="02-26-017001-58001",
        raw_data_json={"attributes": {"OPPORTUNITYID": "02-26-017001-58001", "OPPORTUNITYTYPE": "TemporaryRental"}},
        canonical_status=status,
        missing_successful_checks=misses,
    )
    return record, source


def test_legacy_furas_temporary_rental_route_is_rebuilt_from_official_reference():
    record, source = source_record()
    resolution = resolve_source_link(record, source, audited_health=VALID)
    assert resolution["url"] == "https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-58001?type=TempRental"
    assert resolution["historical_url"] == record.source_url
    assert resolution["url_repaired"] is True
    assert furas_detail_url("02-26-017001-58001", "Investment").endswith("?type=Investment")


def test_invalid_or_missing_furas_identifiers_never_fall_back_to_a_homepage():
    assert furas_detail_url(None, "Investment") is None
    assert furas_detail_url("https://evil.example/", "Investment") is None
    assert furas_detail_url("02-26-017001-58001", None) is None


def test_link_http_health_states_are_distinct_and_never_change_business_status():
    assert classify_http_result(status=200, identity_match=True) == VALID
    assert classify_http_result(status=200, identity_match=True, redirected=True) == REDIRECTED_VALID
    assert classify_http_result(status=404) == UNAVAILABLE_CONFIRMED
    assert classify_http_result(status=410) == UNAVAILABLE_CONFIRMED
    assert classify_http_result(status=403) == TEMPORARILY_UNVERIFIABLE
    assert classify_http_result(status=500) == TEMPORARILY_UNVERIFIABLE
    assert classify_http_result(status=None, network_error=True) == TEMPORARILY_UNVERIFIABLE
    assert classify_http_result(status=200, identity_match=False) == TEMPORARILY_UNVERIFIABLE
    assert classify_http_result(status=200, identity_match=True, error_page=True) == TEMPORARILY_UNVERIFIABLE
    record, source = source_record(status="منشورة", misses=0)
    assert classify_http_result(status=404) == UNAVAILABLE_CONFIRMED
    assert record.canonical_status == "منشورة"  # Link health does not imply cancellation/removal.
    assert resolve_source_link(record, source)["url"].endswith("?type=TempRental")


def test_confirmed_unavailable_source_is_disabled_and_keeps_historical_url():
    record, source = source_record(status="أزيلت من المصدر", misses=9)
    previous = record.source_url
    resolution = resolve_source_link(record, source, audited_health=UNAVAILABLE_CONFIRMED)
    assert resolution["url"] is None
    assert resolution["link_health"] == UNAVAILABLE_CONFIRMED
    assert resolution["historical_url"] == record.source_url
    assert resolution["checked_url"].endswith("?type=TempRental")
    assert record.source_url == previous
    assert record.canonical_status == "أزيلت من المصدر"


def test_generic_invest_saudi_listing_page_is_not_exposed_as_original_opportunity_action():
    source = SimpleNamespace(source_key="invest-saudi", base_url="https://investsaudi.sa/",
        opportunities_url="https://investsaudi.sa/investment-opportunities")
    record = SimpleNamespace(id=782, source=source, source_url=source.opportunities_url,
        raw_data_json={"qualified_location": False}, source_opportunity_id="investsaudi:generic-1",
        source_reference_number=None, official_source_id_original=None)
    resolution = resolve_source_link(record, source)
    assert resolution["url"] is None
    assert resolution["link_health"] == "GENERIC_SOURCE_PAGE"
    assert resolution["historical_url"] == source.opportunities_url


def test_each_source_link_is_resolved_independently_for_a_multi_source_master():
    unavailable, source_a = source_record(status="أزيلت من المصدر", misses=9)
    other_source = SimpleNamespace(source_key="ahda", missing_confirmation_threshold=3)
    healthy = SimpleNamespace(id=44, source_url="https://ahda.gov.sa/official/44", raw_data_json={},
                              source_opportunity_id="44", source_reference_number="44",
                              official_source_id_original="44", canonical_status="منشورة",
                              missing_successful_checks=0, source=other_source)
    first = resolve_source_link(unavailable, source_a, audited_health=UNAVAILABLE_CONFIRMED)
    second = resolve_source_link(healthy, other_source, audited_health=VALID)
    assert first["url"] is None
    assert second["url"] == healthy.source_url


def test_single_url_export_prefers_a_healthy_link_from_a_multi_source_master(monkeypatch):
    import app.source_links as source_links

    unavailable, source_a = source_record(status="أزيلت من المصدر", misses=9)
    source_a.priority = 1
    healthy_source = SimpleNamespace(source_key="ahda", priority=2)
    healthy = SimpleNamespace(id=45, source=healthy_source, source_url="https://ahda.gov.sa/official/45")
    monkeypatch.setattr(source_links, "resolve_source_link", lambda record, source=None: (
        {"url": None, "link_health": UNAVAILABLE_CONFIRMED} if record.id == unavailable.id
        else {"url": record.source_url, "link_health": VALID}
    ))

    selected = resolve_preferred_source_link([unavailable, healthy])
    assert selected["url"] == healthy.source_url


def test_bad_http_200_content_is_not_accepted_as_an_opportunity_link():
    assert classify_http_result(status=200, identity_match=False, error_page=True) == TEMPORARILY_UNVERIFIABLE


def test_source_url_provenance_is_not_overwritten_by_link_resolution():
    record, source = source_record()
    old_url = record.source_url
    _ = resolve_source_link(record, source, audited_health=VALID)
    assert record.source_url == old_url


def test_future_ingestion_url_replacement_creates_immutable_old_url_evidence():
    record, _source = source_record()
    old_url = record.source_url
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    observation = source_url_history_observation(
        record, "https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-58001?type=TempRental", now
    )
    assert observation["dataset_name"] == "source-url-history"
    assert observation["raw_data_json"]["previous_url"] == old_url
    assert observation["raw_data_json"]["replacement_url"].endswith("?type=TempRental")
    assert record.source_url == old_url
    assert source_url_history_observation(record, old_url, now) is None


def test_future_ingestion_to_no_detail_url_still_preserves_the_old_listing_url():
    record, _source = source_record(url="https://investsaudi.sa/investment-opportunities")
    observation = source_url_history_observation(
        record, "", datetime(2026, 10, 19, tzinfo=timezone.utc)
    )
    assert observation["endpoint"] == record.source_url
    assert observation["raw_data_json"]["previous_url"] == record.source_url
    assert observation["raw_data_json"]["replacement_url"] is None
    assert record.source_url == "https://investsaudi.sa/investment-opportunities"

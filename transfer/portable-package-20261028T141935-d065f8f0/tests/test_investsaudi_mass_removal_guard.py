from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.adapters import ADAPTERS, InvestSaudiAdapter
from app.models import Base, Opportunity, Source, SourceOpportunity, SourceOpportunityDatasetMembership, SyncJob, SourceObservation, SystemEvent
from app.service import assess_investsaudi_reconciliation_scope, reconcile_missing_records, source_presence_ids


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    source = Source(source_key="invest-saudi", source_name_ar="استثمر في السعودية",
        organization_name="وزارة الاستثمار", base_url="https://investsaudi.sa",
        opportunities_url="https://investsaudi.sa/investment-opportunities",
        source_type="national_opportunity_platform", priority=4, polling_frequency_minutes=360,
        enabled=True, extraction_method="test", notes="", sync_status="HEALTHY", last_record_count=0,
        missing_confirmation_threshold=3)
    db.add(source)
    db.flush()
    return engine, db, source


def _endpoints(counts=None):
    adapter = InvestSaudiAdapter()
    counts = counts or {}
    return [
        {"dataset_name": name, "endpoint": url, "method": "GET", "page_size": 100,
         "request_params": {"page": "1..totalPages", "per_page": 100}, "total": counts.get(url, 300),
         "pages": 3, "pages_succeeded": 3, "failed_pages": 0, "empty_unexpected_pages": 0,
         "complete": True}
        for name, url in (("Opportunities", adapter.api), ("Investment projects", adapter.projects_api),
                          ("PIF opportunities", adapter.pif_api), ("Regional opportunities", adapter.regional_api))
    ]


def _prior(db, source, endpoint_rows=None, job_id=10):
    db.add(SyncJob(source_id=source.id, started_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 10, 1, 0, 2, tzinfo=timezone.utc), status="SUCCESS", job_state="COMPLETED",
        pagination_complete=True, metrics_json={"endpoints": endpoint_rows or _endpoints()}))
    db.flush()
    return job_id


def _metrics(endpoints=None, *, pagination=True, collection=True):
    return {"endpoints": endpoints or _endpoints(), "pagination_complete": pagination,
            "source_collection_complete": collection}


def test_complete_four_dataset_scan_allows_comparable_reconciliation():
    engine, db, source = _db(); _prior(db, source)
    result = assess_investsaudi_reconciliation_scope(db, source, _metrics())
    assert result["safe"] is True and result["reasons"] == []
    db.close(); engine.dispose()


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_missing_any_required_dataset_blocks_reconciliation(index):
    engine, db, source = _db(); _prior(db, source)
    endpoints = _endpoints(); endpoints.pop(index)
    result = assess_investsaudi_reconciliation_scope(db, source, _metrics(endpoints))
    assert result["safe"] is False
    assert any("DATASET" in reason for reason in result["reasons"])
    db.close(); engine.dispose()


@pytest.mark.parametrize("field,value", [("method", "POST"), ("page_size", 50), ("dataset_name", "Unknown"),
                                         ("endpoint", "https://investsaudi.sa/other"), ("request_params", {})])
def test_changed_dataset_request_scope_blocks_reconciliation(field, value):
    engine, db, source = _db(); _prior(db, source)
    endpoints = _endpoints(); endpoints[0][field] = value
    result = assess_investsaudi_reconciliation_scope(db, source, _metrics(endpoints))
    assert result["safe"] is False
    db.close(); engine.dispose()


@pytest.mark.parametrize("pagination,collection", [(False, True), (True, False), (False, False)])
def test_incomplete_multi_dataset_scan_blocks_all_removals(pagination, collection):
    engine, db, source = _db(); _prior(db, source)
    result = assess_investsaudi_reconciliation_scope(db, source,
        _metrics(pagination=pagination, collection=collection))
    assert result["safe"] is False
    assert "INCOMPLETE_MULTI_DATASET_SCAN" in result["reasons"]
    db.close(); engine.dispose()


def test_unexpected_empty_dataset_blocks_reconciliation():
    engine, db, source = _db(); _prior(db, source)
    endpoints = _endpoints(); endpoints[2]["total"] = 0
    result = assess_investsaudi_reconciliation_scope(db, source, _metrics(endpoints))
    assert result["safe"] is False
    assert "UNEXPECTED_EMPTY_DATASET:PIF opportunities" in result["reasons"]
    db.close(); engine.dispose()


@pytest.mark.parametrize("field,value", [("complete", False), ("pages_succeeded", 2),
                                         ("failed_pages", 1), ("empty_unexpected_pages", 1)])
def test_dataset_page_or_schema_failure_blocks_all_removals(field, value):
    engine, db, source = _db(); _prior(db, source)
    endpoints = _endpoints(); endpoints[1][field] = value
    result = assess_investsaudi_reconciliation_scope(db, source, _metrics(endpoints))
    assert result["safe"] is False
    assert "DATASET_PAGINATION_INCOMPLETE:Investment projects" in result["reasons"]
    db.close(); engine.dispose()


def test_population_drop_beyond_recent_variation_blocks_reconciliation():
    engine, db, source = _db()
    history = _endpoints()
    for total in (1000, 1000, 1000):
        rows = [dict(row, total=total) for row in history]
        _prior(db, source, rows)
    endpoints = _endpoints()
    endpoints[0]["total"] = 700
    result = assess_investsaudi_reconciliation_scope(db, source, _metrics(endpoints))
    assert result["safe"] is False
    assert "DATASET_POPULATION_DROP_OUTSIDE_HISTORY:Opportunities" in result["reasons"]
    db.close(); engine.dispose()


def test_population_drop_within_one_page_allowance_passes():
    engine, db, source = _db()
    history = _endpoints()
    for _ in range(3):
        rows = [dict(row, total=1000) for row in history]
        _prior(db, source, rows)
    endpoints = [dict(row, total=1000) for row in _endpoints()]; endpoints[0]["total"] = 900
    result = assess_investsaudi_reconciliation_scope(db, source, _metrics(endpoints))
    assert result["safe"] is True
    assert result["datasets"]["Opportunities"]["allowed_drop_from_history"] == 100
    db.close(); engine.dispose()


def _large_project_membership_population(db, source, size=101):
    now = datetime.now(timezone.utc)
    for index in range(size):
        row = _source_row(db, source, key=f"investsaudi:mass-{index}", misses=2)
        db.add(SourceOpportunityDatasetMembership(source_opportunity_id=row.id,
            dataset_name="Opportunities", endpoint=InvestSaudiAdapter.api, first_seen_at=now,
            last_seen_at=now, missing_successful_checks=2, is_current=True))
    db.flush()


def test_large_third_miss_candidate_population_blocks_first_scan():
    engine, db, source = _db(); _prior(db, source); _large_project_membership_population(db, source)
    result = assess_investsaudi_reconciliation_scope(db, source, _metrics(), seen_by_dataset={})
    assert result["safe"] is False
    assert "MASS_REMOVAL_CANDIDATE_ANOMALY:Opportunities" in result["reasons"]
    assert result["mass_removal_candidate_count"] == 101
    db.close(); engine.dispose()


def test_same_scope_second_scan_confirms_held_mass_removal_candidates():
    engine, db, source = _db(); _prior(db, source); _large_project_membership_population(db, source)
    first = assess_investsaudi_reconciliation_scope(db, source, _metrics(), seen_by_dataset={})
    db.add(SystemEvent(event_type="SOURCE_RECONCILIATION_GUARD_BLOCKED", created_at=datetime.now(timezone.utc),
        payload={"source":"invest-saudi","guard":first}))
    db.flush()
    second = assess_investsaudi_reconciliation_scope(db, source, _metrics(), seen_by_dataset={})
    assert second["safe"] is True
    assert second["datasets"]["Opportunities"]["mass_removal_confirmation"] == "CONFIRMED_SECOND_COMPARABLE_SCAN"
    db.close(); engine.dispose()


def test_existing_source_rows_without_comparable_baseline_block_removal():
    engine, db, source = _db(); _source_row(db, source)
    result = assess_investsaudi_reconciliation_scope(db, source, _metrics())
    assert result["safe"] is False
    assert "NO_COMPARABLE_SUCCESSFUL_BASELINE" in result["reasons"]
    db.close(); engine.dispose()


def _source_row(db, source, *, key="investsaudi:900", status="غير محددة", misses=0, linked=None):
    row = SourceOpportunity(source_id=source.id, master_opportunity_id=linked,
        source_opportunity_id=key, official_source_id_original=key.split(":")[-1],
        official_source_id_normalized=key.split(":")[-1], source_title="National candidate",
        normalized_source_title="national candidate", source_url="https://investsaudi.sa/opportunities/900",
        first_seen_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 10, 1, tzinfo=timezone.utc), content_hash="raw-hash",
        parser_version="test", raw_status=None, canonical_status=status,
        missing_successful_checks=misses, raw_data_json={"preserved": "source"})
    db.add(row); db.flush()
    return row


def test_complete_national_presence_resets_missing_counter():
    engine, db, source = _db(); row = _source_row(db, source, misses=4)
    removed = reconcile_missing_records(db, source, {row.source_opportunity_id}, datetime.now(timezone.utc))
    assert removed == [] and row.missing_successful_checks == 0 and row.last_missing_at is None
    assert row.canonical_status == "غير محددة"
    db.close(); engine.dispose()


def test_first_miss_does_not_remove_before_confirmation_threshold():
    engine, db, source = _db(); row = _source_row(db, source, misses=0)
    removed = reconcile_missing_records(db, source, set(), datetime.now(timezone.utc))
    assert removed == [] and row.canonical_status == "غير محددة" and row.missing_successful_checks == 1
    db.close(); engine.dispose()


def test_third_confirmed_miss_creates_one_source_removal_transition():
    engine, db, source = _db(); row = _source_row(db, source, misses=2)
    removed = reconcile_missing_records(db, source, set(), datetime.now(timezone.utc))
    assert len(removed) == 1 and row.canonical_status == "أزيلت من المصدر"
    assert db.scalar(select(SourceObservation.id).where(
        SourceObservation.source_opportunity_id == row.id,
        SourceObservation.dataset_name == "source-record-status-snapshot")) is not None
    db.close(); engine.dispose()


def test_already_removed_unlinked_row_is_not_counted_again():
    engine, db, source = _db(); row = _source_row(db, source, status="أزيلت من المصدر", misses=3)
    removed = reconcile_missing_records(db, source, set(), datetime.now(timezone.utc))
    assert removed == [] and row.canonical_status == "أزيلت من المصدر"
    db.close(); engine.dispose()


def test_counter_count_equals_only_new_source_lifecycle_transitions():
    engine, db, source = _db()
    newly_missing = _source_row(db, source, key="investsaudi:901", misses=2)
    already_missing = _source_row(db, source, key="investsaudi:902", status="أزيلت من المصدر", misses=3)
    removed = reconcile_missing_records(db, source, set(), datetime.now(timezone.utc))
    assert {item["source_opportunity_id"] for item in removed} == {newly_missing.source_opportunity_id}
    assert len(removed) == 1 and already_missing.canonical_status == "أزيلت من المصدر"
    db.close(); engine.dispose()


@pytest.mark.parametrize("raw_status", [None, "", "غير محددة"])
def test_removal_does_not_infer_cancellation_from_missing_source(raw_status):
    engine, db, source = _db(); row = _source_row(db, source, misses=2)
    row.raw_status = raw_status
    reconcile_missing_records(db, source, set(), datetime.now(timezone.utc))
    assert row.canonical_status == "أزيلت من المصدر"
    assert row.canonical_status != "ملغاة"
    db.close(); engine.dispose()


def test_source_identity_and_raw_payload_survive_lifecycle_transition():
    engine, db, source = _db(); row = _source_row(db, source, misses=2)
    source_id, official_id, raw = row.id, row.official_source_id_normalized, dict(row.raw_data_json)
    reconcile_missing_records(db, source, set(), datetime.now(timezone.utc))
    db.flush()
    assert db.get(SourceOpportunity, source_id).official_source_id_normalized == official_id
    assert db.get(SourceOpportunity, source_id).raw_data_json == raw
    db.close(); engine.dispose()


def test_dataset_scope_is_four_fixed_public_endpoints():
    adapter = InvestSaudiAdapter()
    assert [adapter.api, adapter.projects_api, adapter.pif_api, adapter.regional_api] == [
        ADAPTERS["invest-saudi"].api, ADAPTERS["invest-saudi"].projects_api,
        ADAPTERS["invest-saudi"].pif_api, ADAPTERS["invest-saudi"].regional_api]


def test_investsaudi_presence_uses_all_national_candidates_not_only_local_qualifications():
    qualified = [type("Raw", (), {"external_id": f"investsaudi:{n}"})() for n in range(8)]
    national = qualified + [type("Raw", (), {"external_id": f"investsaudi:{n}"})() for n in range(8, 2431)]
    assert len(source_presence_ids("invest-saudi", qualified, national)) == 2431


def test_other_sources_keep_their_qualified_scan_population():
    qualified = [type("Raw", (), {"external_id": "source:accepted"})()]
    candidates = qualified + [type("Raw", (), {"external_id": "source:rejected"})()]
    assert source_presence_ids("furas", qualified, candidates) == {"source:accepted"}


def test_removed_investsaudi_source_does_not_cancel_master_with_other_live_source():
    engine, db, source = _db()
    now = datetime.now(timezone.utc)
    master = Opportunity(canonical_id="AHSA-TEST-1", title_ar="فرصة اختبار", normalized_title="فرصة اختبار",
        primary_publication_platform="Invest Saudi", city="الأحساء", status="متاحة",
        first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
    other = Source(source_key="other", source_name_ar="مصدر", organization_name="جهة",
        base_url="https://example.test", opportunities_url="https://example.test",
        priority=20, polling_frequency_minutes=360, enabled=True, extraction_method="test", notes="")
    db.add_all([master, other]); db.flush()
    invest_row = _source_row(db, source, misses=2, linked=master.id)
    other_row = _source_row(db, other, key="other:1", status="متاحة", linked=master.id)
    before = master.status
    removed = reconcile_missing_records(db, source, set(), now)
    assert len(removed) == 1 and invest_row.canonical_status == "أزيلت من المصدر"
    assert other_row.canonical_status == "متاحة" and master.status == before == "متاحة"
    db.close(); engine.dispose()


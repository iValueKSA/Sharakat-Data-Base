import asyncio
import json
from datetime import datetime, timezone

import httpx
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app.adapters import ADAPTERS, RcjyAdapter, RawOpportunity, normalized_record
from app.models import AuditEvent, Base, GeographicReferenceDataset, GeographicReferenceUnit, Opportunity, OpportunityLocation, Source, SourceOpportunity, SystemEvent
from app.service import _safe_record, resolve_official_geography
from scripts.promote_rcjy_masters import promote_approved_rcjy_rows


CATALOG = "https://invest.rcjy.gov.sa/InvestmentPortal/InvestmentOpportunities"
API_URL = (
    "https://invest.rcjy.gov.sa/InvestmentPortal/screenservices/InvestmentPortal/MainFlow/"
    "InvestmentOpportunities/ScreenDataSetGetInvestmentOpportunitiesBySearchConditions"
)


def rcjy_item(identifier, title_ar, title_en, city="Yanbu", sector="Industrial", area="0.0"):
    return {
        "City": {"Id": 1, "Label": city, "LabelAr": ""},
        "SubSector": {"Id": 4, "Label": "Spare Part Desalination"},
        "InvestmentOpportunity": {
            "Id": str(identifier), "OpportunityCode": "", "OpportunityName": title_ar,
            "OpportunityNameEn": title_en, "OpportunityDescription": "",
            "OpportunityDescriptionEn": "", "Area": area, "OpportunityStatusId": 0,
            "PublishStatus": False, "Is_Active": False, "IsShowOnMap": False,
            "PurchaseDeadline": "1900-01-01", "BidSubmissionDeadline": "1900-01-01",
        },
        "Sector": {"Id": 1, "Label": sector},
        "MeasurementUnit": {"Id": 0, "Label": ""},
    }


def build_transport(pages, *, duplicate=False):
    script_path = "/InvestmentPortal/scripts/InvestmentPortal.MainFlow.InvestmentOpportunities.mvc.js?v1"
    script_text = (
        'callAggregateWithStartIndexAndClientVars("ScreenDataSetGetInvestmentOpportunitiesBySearchConditions", '
        '"screenservices/path", "api-v1", maxRecords, startIndex, function () {})'
    )
    async def handler(request):
        if str(request.url) == CATALOG:
            return httpx.Response(200, text='<script>OSManifestLoader.indexVersionToken = "idx-v1";</script>')
        if "/moduleservices/moduleversioninfo?" in str(request.url):
            return httpx.Response(200, json={"versionToken": "module-v1"})
        if str(request.url).endswith("/moduleservices/moduleinfo?module-v1"):
            return httpx.Response(200, json={"manifest": {"urlVersions": {script_path: "?v1"}}})
        if ".mvc.js?" in str(request.url):
            return httpx.Response(200, text=script_text)
        if str(request.url) == API_URL:
            body = json.loads(request.content)
            start = body["inputParameters"]["StartIndex"]
            size = body["inputParameters"]["MaxRecords"]
            rows = pages[start:start + size]
            if duplicate and start:
                rows = [pages[0], *rows]
            return httpx.Response(200, json={"data": {"Count": len(pages), "List": {"List": rows}}})
        raise AssertionError(f"Unexpected request {request.method} {request.url}")
    return httpx.MockTransport(handler)


def test_rcjy_api_enumeration_discovers_runtime_version_and_paginates_all_records():
    payloads = [rcjy_item(269, "إنشاء وتشغيل شقق فندقية", "Serviced Apartments", sector="Commercial"),
                rcjy_item(266, "تصنيع محولات الطاقة الكهربائية", "Electrical Transformers"),
                rcjy_item(265, "تصنيع وحدات مصابيح LED", "LED Lighting Fixtures")]
    async def run():
        adapter = RcjyAdapter()
        adapter.page_size = 2
        async with httpx.AsyncClient(transport=build_transport(payloads)) as client:
            records, pages = await adapter.fetch(client)
        return adapter, records, pages
    adapter, records, pages = asyncio.run(run())
    assert pages == 2
    assert [record.external_id for record in records] == ["269", "266", "265"]
    assert adapter.metrics["source_total_reported"] == 3
    assert adapter.metrics["pagination_complete"] is True
    assert adapter.metrics["unique_records"] == 3
    assert records[0].raw["provider_id_field"] == "InvestmentOpportunity.Id"
    assert records[0].raw["title_en"] == "Serviced Apartments"
    assert records[0].raw["provider_payload"] == payloads[0]
    assert records[0].location == "Yanbu"
    assert records[0].area_text is None
    assert records[0].latitude is None and records[0].longitude is None
    assert records[0].status == "unknown"
    assert records[0].owner is None


def test_rcjy_rejects_duplicate_provider_ids_across_pages():
    payloads = [rcjy_item(269, "فرصة أ", "Offer A"), rcjy_item(266, "فرصة ب", "Offer B")]
    async def run():
        adapter = RcjyAdapter()
        adapter.page_size = 1
        async with httpx.AsyncClient(transport=build_transport(payloads, duplicate=True)) as client:
            return await adapter.fetch(client)
    try:
        asyncio.run(run())
    except RuntimeError as exc:
        assert "repeated provider ID" in str(exc)
    else:
        raise AssertionError("Duplicate RCJY provider ID was accepted")


def test_rcjy_source_capture_is_idempotent_and_does_not_create_masters():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    source = Source(
        source_key=RcjyAdapter.key, source_name_ar="فرص الهيئة الملكية للجبيل وينبع (RCJY)",
        organization_name="الهيئة الملكية للجبيل وينبع", base_url="https://www.rcjy.gov.sa/",
        opportunities_url=CATALOG, enabled=True, priority=12, polling_frequency_minutes=1440,
        source_type="official_public_investment_opportunity_platform",
    )
    raw = RawOpportunity(
        external_id="269", title="إنشاء وتشغيل شقق فندقية", url=CATALOG,
        location="Yanbu", activity="Commercial", status="unknown",
        raw={"provider": "RCJY", "official_source_id_original": "269", "title_en": "Serviced Apartments",
             "source_lifecycle_classification": "CURRENT", "source_taxonomy": {"sector": "Commercial"},
             "provider_payload": rcjy_item(269, "إنشاء وتشغيل شقق فندقية", "Serviced Apartments")},
    )
    counts = {"raw_count": 0, "rejected_count": 0, "update_count": 0, "unchanged_count": 0}
    with Session() as db:
        db.add(source)
        db.commit()
        _safe_record(db, source, raw, counts)
        db.commit()
        first_id = db.scalar(select(SourceOpportunity.id).where(SourceOpportunity.source_id == source.id))
        raw.raw["capture_probe"] = "second observation"
        _safe_record(db, source, raw, counts)
        db.commit()
        rows = db.scalar(select(func.count()).select_from(SourceOpportunity).where(SourceOpportunity.source_id == source.id))
        masters = db.scalar(select(func.count()).select_from(Opportunity))
        row = db.get(SourceOpportunity, first_id)
        assert rows == 1
        assert masters == 0
        assert row.master_opportunity_id is None
        assert row.official_source_id_original == "269"
        assert row.raw_data_json["title_en"] == "Serviced Apartments"
        assert row.raw_data_json["provider_payload"]["InvestmentOpportunity"]["Id"] == "269"
    engine.dispose()


def test_rcjy_source_key_is_registered_as_a_distinct_adapter():
    assert RcjyAdapter.key == "rcjy-investment-opportunities"
    assert ADAPTERS[RcjyAdapter.key] is RcjyAdapter


def test_rcjy_location_stays_out_of_al_ahsa_and_resolves_only_by_exact_reference():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    raw = RawOpportunity(
        external_id="269", title="شقق فندقية", url=CATALOG, location="Yanbu",
        activity="Commercial", status="unknown",
        raw={"provider": "RCJY", "provider_payload": rcjy_item(269, "شقق فندقية", "Serviced Apartments")},
    )
    projected = normalized_record(raw)
    assert projected["relevant"] is False
    assert projected["city"] == ""
    assert projected["location_detection_method"] == "RCJY_PUBLIC_LOCATION_UNMAPPED"
    with Session() as db:
        dataset = GeographicReferenceDataset(
            dataset_key="saudi_administrative_units", version="test-v1", operator="test",
            source_url="https://example.test/geo", content_sha256="a" * 64,
            import_status="IMPORTED", is_current=True, created_at=datetime.now(timezone.utc),
        )
        db.add(dataset)
        db.flush()
        unit = GeographicReferenceUnit(
            dataset_id=dataset.id, level="governorate", external_id="301",
            name_ar="ينبع", name_en="Yanbu", aliases_json=["محافظة ينبع"],
            source_record_json={},
        )
        db.add(unit)
        db.commit()
        assert resolve_official_geography(db, "Yanbu").id == unit.id
        assert resolve_official_geography(db, "Yanbu Industrial City") is None
    engine.dispose()


def test_rcjy_high_confidence_promotion_links_and_audits_without_fabricating_fields():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with Session.begin() as db:
        source = Source(
            source_key=RcjyAdapter.key, source_name_ar="فرص الهيئة الملكية للجبيل وينبع (RCJY)",
            organization_name="الهيئة الملكية للجبيل وينبع", base_url="https://www.rcjy.gov.sa/",
            opportunities_url=CATALOG, enabled=True, priority=12, polling_frequency_minutes=1440,
            source_type="official_public_investment_opportunity_platform",
        )
        db.add(source)
        dataset = GeographicReferenceDataset(
            dataset_key="saudi_administrative_units", version="test-v1", operator="test",
            source_url="https://example.test/geo", content_sha256="b" * 64,
            import_status="IMPORTED", is_current=True, created_at=now,
        )
        db.add(dataset)
        db.flush()
        unit = GeographicReferenceUnit(
            dataset_id=dataset.id, level="governorate", external_id="301",
            name_ar="ينبع", name_en="Yanbu", aliases_json=["محافظة ينبع"], source_record_json={},
        )
        db.add(unit)
        db.flush()
        row = SourceOpportunity(
            source_id=source.id, source_opportunity_id="269", source_title="فرصة اختبار",
            normalized_source_title="فرصة اختبار", source_url=CATALOG, raw_location="Yanbu",
            source_sector="Industrial", source_activity="Industrial", source_sub_activity="Testing",
            raw_status="unknown", raw_data_json={
                "provider": "RCJY", "title_en": "Test opportunity", "industrial_city": "Yanbu",
                "source_lifecycle_classification": "CURRENT", "source_actionability_status": "UNKNOWN",
                "source_taxonomy": {"sector": "Industrial", "subsector": "Testing"},
            }, standardized_data_json={}, raw_dates={}, first_seen_at=now, last_seen_at=now,
            content_hash="c" * 64, parser_version="test",
        )
        db.add(row)
        db.flush()
        db.add(OpportunityLocation(
            source_opportunity_id=row.id, location_name="Yanbu", location_scope="SOURCE_NAMED_LOCATION",
            source_location_text="Yanbu", geography_reference_unit_id=unit.id,
            source_evidence_json={"verification_method": "EXACT_CURRENT_REFERENCE_NAME_OR_ALIAS"},
        ))
        plan = {"records": [{"provider_id": "269", "disposition": "A_READY_NEW_MASTER", "confidence": .95,
                              "identity_evidence": ["unique current provider record", "no strong cross-source match"]}]}
        result = promote_approved_rcjy_rows(db, plan, apply=True)
        assert result["actions"][0]["action"] == "CREATE_AND_LINK"
        master = db.scalar(select(Opportunity).where(Opportunity.canonical_id == "RCJY-269"))
        assert master and row.master_opportunity_id == master.id
        assert master.geography_reference_unit_id == unit.id
        assert master.city == "غير محدد" and master.status == "غير محددة"
        assert master.sector == "صناعي"
        assert master.opportunity_owner is None and master.latitude is None and master.longitude is None
        audit_row = db.scalar(select(AuditEvent).where(AuditEvent.event_type == "RCJY_MASTER_CREATED"))
        assert audit_row and audit_row.entity_id == str(master.id)
        assert audit_row.after_json["provider_id"] == "269"
        assert audit_row.after_json["source_record_id"] == row.id
        assert db.scalar(select(SystemEvent.id).where(
            SystemEvent.event_type == "SECTOR_GOVERNED_CLASSIFICATION_APPLIED"))
    engine.dispose()

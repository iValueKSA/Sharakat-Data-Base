import asyncio
import copy
import httpx
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app.adapters import ADAPTERS, RcuAdapter, normalized_record
from app.models import (AuditEvent, Base, GeographicReferenceDataset, GeographicReferenceUnit,
    Opportunity, OpportunityLocation, Source, SourceOpportunity)
from app.service import _safe_record
from scripts.promote_rcu_masters import promote_approved_rcu_rows
from scripts.classify_rcu_sectors import RCU_CATEGORY_MAP


def rcu_item(identifier, display, *, lat=26.48, lon=38.11):
    return {"id":identifier,"displayOpportunityId":display,"titleAR":"فرصة استثمارية في العلا",
        "titleEN":"AlUla investment opportunity","descriptionAR":"مشروع في محافظة العلا",
        "descriptionEN":"Project in AlUla Governorate","opportunityType":"PPP",
        "area":None,"latitude":lat,"longitude":lon,"submissionDeadline":None,
        "isClosed":False,"canApply":False,"attachments":[{"id":"doc-1","name":"RFP"}]}


def rcu_transport(rows):
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/investment-opportunities/list"
        page=int(request.url.params["Page.Index"])
        size=int(request.url.params["Page.Size"])
        batch=rows[(page-1)*size:page*size]
        return httpx.Response(200,json={"succeeded":True,"data":{"count":len(rows),"list":batch}})
    return httpx.MockTransport(handler)


def test_rcu_adapter_enumerates_all_pages_and_preserves_provider_evidence():
    rows=[rcu_item("uuid-a","RCU-OPP-001"),rcu_item("uuid-b","RCU-OPP-002",lat=26.60,lon=37.92),
          rcu_item("uuid-c","RCU-OPP-003")]
    async def run():
        adapter=RcuAdapter();adapter.page_size=2
        async with httpx.AsyncClient(transport=rcu_transport(rows)) as client:
            records,pages=await adapter.fetch(client)
        return adapter,records,pages
    adapter,records,pages=asyncio.run(run())
    assert ADAPTERS[RcuAdapter.key] is RcuAdapter
    assert pages==2 and len(records)==3
    assert adapter.metrics["pagination_complete"] is True
    assert adapter.metrics["source_total_reported"]==3
    assert adapter.metrics["provider_id_field"].startswith("id (UUID)")
    assert [r.external_id for r in records]==["uuid-a","uuid-b","uuid-c"]
    assert records[0].reference=="RCU-OPP-001"
    assert records[0].url=="https://eservices.rcu.gov.sa/opportunities/detail/uuid-a"
    assert records[0].raw["attachments"]==[{"id":"doc-1","name":"RFP"}]
    assert records[0].raw["publisher_ar"]=="الهيئة الملكية لمحافظة العلا"
    assert records[0].raw["opportunity_locations"]==["العلا"]
    assert records[0].status=="UNKNOWN"
    assert records[0].raw["lifecycle_evidence"]=={
        "isClosed":False,"canApply":False,"isApplicable":None,"submissionDeadline":None}
    assert adapter.metrics["coordinate_pairs_valid_numeric"]==3
    assert records[0].latitude==26.48 and records[0].longitude==38.11
    normalized=normalized_record(records[0])
    assert normalized["relevant"] is False
    assert normalized["city"]==""


def test_rcu_adapter_rerun_is_deterministic_and_rejects_unstable_ids():
    rows=[rcu_item("uuid-a","RCU-OPP-001"),rcu_item("uuid-b","RCU-OPP-002")]
    async def run():
        outputs=[]
        for _ in range(2):
            adapter=RcuAdapter()
            async with httpx.AsyncClient(transport=rcu_transport(rows)) as client:
                records,_=await adapter.fetch(client)
            outputs.append([(r.external_id,r.content_hash) for r in records])
        return outputs
    first,second=asyncio.run(run())
    assert first==second
    malformed=copy.deepcopy(rows);malformed[0]["id"]=""
    async def invalid_run():
        async with httpx.AsyncClient(transport=rcu_transport(malformed)) as client:
            await RcuAdapter().fetch(client)
    try:
        asyncio.run(invalid_run())
    except ValueError as exc:
        assert "stable provider UUID" in str(exc)
    else:
        raise AssertionError("RCU record without a stable UUID was accepted")


def test_rcu_source_capture_is_idempotent_and_does_not_create_masters():
    engine=create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine,expire_on_commit=False)
    source=Source(source_key=RcuAdapter.key,source_name_ar="فرص الهيئة الملكية لمحافظة العلا",
        organization_name="الهيئة الملكية لمحافظة العلا",base_url="https://eservices.rcu.gov.sa/",
        opportunities_url=RcuAdapter.catalog_url,enabled=True,priority=13,polling_frequency_minutes=1440,
        source_type="official_public_investment_opportunity_platform")
    raw=RcuAdapter()
    async def extract():
        async with httpx.AsyncClient(transport=rcu_transport([rcu_item("uuid-a","RCU-OPP-001")])) as client:
            return (await raw.fetch(client))[0][0]
    record=asyncio.run(extract())
    counts={"raw_count":0,"rejected_count":0,"update_count":0,"unchanged_count":0}
    with Session() as db:
        db.add(source);db.commit()
        _safe_record(db,source,record,counts);db.commit()
        first_id=db.scalar(select(SourceOpportunity.id).where(SourceOpportunity.source_id==source.id))
        _safe_record(db,source,record,counts);db.commit()
        assert db.scalar(select(func.count(SourceOpportunity.id)))==1
        assert db.scalar(select(func.count(Opportunity.id)))==0
        assert db.scalar(select(SourceOpportunity.id).where(SourceOpportunity.source_id==source.id))==first_id
        stored=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id))
        assert stored.master_opportunity_id is None
        assert stored.raw_data_json["provider_id"]=="uuid-a"
    engine.dispose()


def test_rcu_high_confidence_promotion_links_exact_geography_and_audits():
    engine=create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine,expire_on_commit=False)
    from datetime import datetime, timezone
    now=datetime.now(timezone.utc)
    with Session.begin() as db:
        source=Source(source_key=RcuAdapter.key,source_name_ar="فرص الهيئة الملكية لمحافظة العلا",
            organization_name="الهيئة الملكية لمحافظة العلا",base_url="https://eservices.rcu.gov.sa/",
            opportunities_url=RcuAdapter.catalog_url,enabled=True,priority=13,polling_frequency_minutes=1440,
            source_type="official_public_investment_opportunity_platform")
        db.add(source)
        dataset=GeographicReferenceDataset(dataset_key="saudi_administrative_units",version="test-v1",
            operator="test",source_url="https://example.test/geo",content_sha256="d"*64,
            import_status="IMPORTED",is_current=True,created_at=now)
        db.add(dataset);db.flush()
        region=GeographicReferenceUnit(dataset_id=dataset.id,level="region",external_id="3",
            name_ar="منطقة المدينة المنورة",name_en="Al-Madinah Region",aliases_json=[],source_record_json={})
        db.add(region);db.flush()
        governorate=GeographicReferenceUnit(dataset_id=dataset.id,level="governorate",external_id="302",
            parent_id=region.id,parent_external_id="3",name_ar="العلا",name_en="Al Ula",aliases_json=[],source_record_json={})
        db.add(governorate);db.flush()
        item=rcu_item("uuid-a","RCU-OPP-001")
        item["submissionDeadline"]="2027-06-30T17:00:00"
        item.update({"provider":"RCU","provider_id":"uuid-a","publisher_ar":"الهيئة الملكية لمحافظة العلا",
            "source_url":RcuAdapter.catalog_url,"detail_url":"https://eservices.rcu.gov.sa/opportunities/uuid-a",
            "opportunity_locations":["العلا"],"source_geography_evidence":"The project is in AlUla.",
            "lifecycle_evidence":{"isClosed":False,"isApplicable":True,"canApply":False,"submissionDeadline":None}})
        row=SourceOpportunity(source_id=source.id,source_opportunity_id="uuid-a",source_reference_number="RCU-OPP-001",
            source_title="فرصة اختبار في العلا",normalized_source_title="فرصة اختبار في العلا",source_url=RcuAdapter.catalog_url,
            raw_status="UNKNOWN",raw_data_json=item,raw_dates={"deadline":item["submissionDeadline"]},
            standardized_data_json={"fields":{"submission_deadline":{"raw":item["submissionDeadline"],
                "normalized":None,"mapping_status":"REVIEW_REQUIRED","rule":"unparsed_date_preserved"}}},
            first_seen_at=now,last_seen_at=now,
            content_hash="e"*64,parser_version=RcuAdapter.parser_version)
        db.add(row);db.flush()
        db.add(OpportunityLocation(source_opportunity_id=row.id,location_name="العلا",location_scope="SINGLE_LOCATION",
            source_location_text="العلا",geography_reference_unit_id=governorate.id,
            source_evidence_json={"verification_method":"EXACT_CURRENT_REFERENCE_NAME_OR_ALIAS"}))
        plan={"enumeration":{"coordinate_pair_frequencies":{"26.48,38.11":1}},"records":[{
            "provider_id":"uuid-a","disposition":"A_READY_NEW_MASTER","confidence":.95,"review_required":False,
            "identity_evidence":{"provider_uuid_unique":True,"title_similarity_is_not_merge_authority":True}}]}
        result=promote_approved_rcu_rows(db,plan,apply=True)
        master=db.scalar(select(Opportunity).where(Opportunity.canonical_id=="RCU-RCU-OPP-001"))
        audit=db.scalar(select(AuditEvent).where(AuditEvent.event_type=="RCU_MASTER_CREATED"))
        assert result["actions"][0]["action"]=="CREATE_AND_LINK"
        assert row.master_opportunity_id==master.id
        assert master.geography_reference_unit_id==governorate.id
        assert master.submission_deadline is None
        assert master.city=="غير محدد" and master.latitude is None and master.longitude is None
        assert master.opportunity_owner is None and master.manual_review_required is True
        assert audit.after_json["provider_id"]=="uuid-a"
        assert audit.after_json["source_opportunity_id"]==row.id
    engine.dispose()


def test_rcu_official_category_mapping_uses_explicit_source_fields():
    assert RCU_CATEGORY_MAP["Transport (e.g., Roads, Rail, Airports)"]==("الخدمات اللوجستية","sector:logistics")
    assert RCU_CATEGORY_MAP["Water & Waste"]==("البيئة","sector:environment")
    assert set(RCU_CATEGORY_MAP)=={"Transport (e.g., Roads, Rail, Airports)","Water & Waste"}

import asyncio
import json
import httpx
from datetime import datetime,timezone
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session

from app.adapters import AhdaAdapter, InvestSaudiAdapter, RawOpportunity, SourceBlocked, normalized_record, normalize_sector
from app.models import Base,Source,SourceOpportunity,SourceOpportunityDatasetMembership,SourceObservation,SourceOpportunityTaxonomy
from app.service import store_investsaudi_observations,reconcile_investsaudi_memberships,investsaudi_reconciliation_metrics


def test_ahda_investment_opportunity_qualified_but_general_project_is_not():
    sitemap='''<urlset><url><loc>https://www.ahda.gov.sa/invest-al-ahsa/investment-opportunities/retail-offering</loc></url><url><loc>https://www.ahda.gov.sa/invest-al-ahsa/major-projects/road-project</loc></url></urlset>'''
    def handler(request):
        if request.url.path=="/sitemap.xml":return httpx.Response(200,text=sitemap)
        if request.url.path.endswith("retail-offering"):
            return httpx.Response(200,text='<html><main><h1>Retail Development</h1><p>Investment opportunity for private investors.</p><a href="/files/offer.pdf">Download</a></main></html>')
        return httpx.Response(200,text='<html><main><h1>Road project</h1><p>Completed infrastructure development project.</p></main></html>')
    async def run():
        adapter=AhdaAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client: records,pages=await adapter.fetch(client)
        return adapter,records,pages
    adapter,records,pages=asyncio.run(run())
    assert pages==3
    assert len(adapter.content_items)==2
    assert len(records)==1
    assert records[0].raw["content_type"]=="INVESTMENT_OPPORTUNITY"
    assert records[0].raw["attachments"][0]["type"]=="pdf"
    normalized=normalized_record(records[0])
    assert normalized["location_detection_method"]=="SOURCE_SCOPE"
    assert normalized["city"]=="" and normalized["location_description"] is None
    assert adapter.metrics["pagination_complete"] is True


def test_ahda_news_about_investment_meeting_is_not_an_opportunity():
    sitemap='<urlset><url><loc>https://www.ahda.gov.sa/media-center/news/investment-forum</loc></url></urlset>'
    def handler(request):
        if request.url.path=="/sitemap.xml":return httpx.Response(200,text=sitemap)
        return httpx.Response(200,text='<html><main><h1>Investment forum</h1><p>Meeting with investors and officials; no offering.</p></main></html>')
    async def run():
        adapter=AhdaAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client: records,_=await adapter.fetch(client)
        return adapter,records
    adapter,records=asyncio.run(run())
    assert records==[]
    assert adapter.content_items[0]["content_type"]=="NON_INVESTMENT_CONTENT"


def test_ahda_403_is_reported_as_blocked():
    def handler(request):return httpx.Response(403)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client: await AhdaAdapter().fetch(client)
    try:asyncio.run(run())
    except SourceBlocked:pass
    else:raise AssertionError("403 must be surfaced as blocked")


def test_ahda_changed_page_structure_reports_incomplete_parser_state():
    sitemap='<urlset><url><loc>https://www.ahda.gov.sa/invest-al-ahsa/investment-opportunities/retail</loc></url></urlset>'
    def handler(request):
        if request.url.path=="/sitemap.xml":return httpx.Response(200,text=sitemap)
        return httpx.Response(200,text='<html><div id="new-layout">No main heading or expected text</div></html>')
    async def run():
        adapter=AhdaAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client: records,_=await adapter.fetch(client)
        return adapter,records
    adapter,records=asyncio.run(run())
    assert not records
    assert adapter.metrics["pagination_complete"] is False
    assert adapter.metrics["parser_warning"] is True
    assert adapter.metrics["qualified_opportunities"]==0
    assert adapter.content_items[0]["title"]==""


def invest_item(i,location="",region="",description="",coords=None):
    return {"id":i,"slug":f"listing-{i}","title":f"Opportunity {i}","description":description,"link":f"https://investsaudi.sa/opportunities/{i}","sector_name":"Real Estate and Construction","location":location,"region":region,"coordinates":coords or {}}


def test_investsaudi_location_evidence_and_review_threshold():
    items=[invest_item(1,location="الأحساء",region="Eastern Province"),invest_item(2,location="Hofuf"),invest_item(3,region="Eastern province"),invest_item(4,coords={"latitude":25.38,"longitude":49.59}),invest_item(5,region="Eastern Province",description="Project documentation specifies Al Ahsa")]
    def handler(request):
        if request.url.path.endswith("/investment-projects"):
            return httpx.Response(200,json={"data":[],"meta":{"page":1,"per_page":100,"total":0}})
        if request.url.path.endswith("/opportunities"):
            return httpx.Response(200,json={"data":items,"meta":{"page":1,"per_page":100,"total":5,"totalPages":1,"filters":{"regions":["Al Ahsa","Eastern province"]}}})
        return httpx.Response(200,json={"data":[],"meta":{"page":1,"per_page":100,"total":0,"totalPages":1}})
    async def run():
        adapter=InvestSaudiAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:records,pages=await adapter.fetch(client)
        return adapter,records,pages
    adapter,records,pages=asyncio.run(run())
    assert pages==4 and len(adapter.raw_candidates)==5
    assert {r.external_id for r in records}=={"investsaudi:1","investsaudi:2","investsaudi:4"}
    assert [r["external_id"] for r in adapter.location_reviews]==["investsaudi:5"]
    assert adapter.metrics["rejected_records"]==1
    assert adapter.metrics["source_total_reported"]==5 and adapter.metrics["pagination_complete"] is True
    assert normalized_record(records[0])["sector"]=="العقارات والإنشاءات"
    assert normalize_sector("Healthcare & Medical Devices")=="الرعاية الصحية"
    assert normalize_sector("Information and Communication Technology")=="التقنية والاتصالات"
    assert normalize_sector("a manufacturing project")==None
    assert normalize_sector("فرصة استثمارية")==None
    rejected=next(r for r in adapter.raw_candidates if r.external_id=="investsaudi:3")
    assert normalized_record(rejected)["relevant"] is False


def test_investsaudi_requires_reported_total_and_complete_pagination():
    def handler(request):return httpx.Response(200,json={"data":[],"meta":{"page":1,"per_page":100}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:await InvestSaudiAdapter().fetch(client)
    try:asyncio.run(run())
    except RuntimeError as exc:assert "completeness" in str(exc)
    else:raise AssertionError("unreported national total must fail closed")


def test_future_ingestion_keeps_sector_activity_and_type_separate():
    raw=RawOpportunity(external_id="fixture-1",title="مصنع تجريبي",url="https://example.test/1",
        activity="تصنيع المعدات",raw={"source_taxonomy":{"sector":"Industrial"},
        "normalized_taxonomy":{"sector":"Industrial"},"opportunity_type":"LEASE_OPPORTUNITY"})
    normalized=normalized_record(raw)
    assert normalized["sector"]=="صناعي"
    assert normalized["activity"]=="تصنيع المعدات"
    assert normalized["opportunity_type"]=="LEASE_OPPORTUNITY"
    uncertain=normalized_record(RawOpportunity(external_id="fixture-2",title="مصنع تجريبي",url="https://example.test/2",activity="مصنع تجريبي"))
    assert uncertain["sector"] is None
    assert uncertain["activity"]=="مصنع تجريبي"


def test_investsaudi_collects_projects_endpoint_and_preserves_furas_identifier():
    project={"id":10,"title":"Retail Development","description":"Develop retail space","type":"Government-Led","location":"الأحساء","region":"Eastern Province","category":"Real Estate & Construction","activity":"Retail","municipality":"أمانة الأحساء","modalData":{"opportunityNumber":"03-26-001","location":{"latitude":25.38,"longitude":49.59,"siteArea":"5000"},"descriptionSections":[]}}
    def handler(request):
        if request.url.path.endswith("/investment-projects"):
            return httpx.Response(200,json={"data":[project],"meta":{"page":1,"per_page":100,"total":1}})
        return httpx.Response(200,json={"data":[],"meta":{"page":1,"per_page":100,"total":0,"totalPages":1}})
    async def run():
        adapter=InvestSaudiAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:records,pages=await adapter.fetch(client)
        return adapter,records,pages
    adapter,records,pages=asyncio.run(run())
    assert pages==4 and len(records)==1
    assert records[0].external_id=="investsaudi:10"
    assert records[0].reference=="03-26-001"
    assert records[0].raw["source_api"].endswith("/investment-projects")
    assert adapter.metrics["investment_projects_total"]==1
    assert adapter.metrics["source_total_reported"]==1


def test_investsaudi_collects_pif_and_regional_public_datasets():
    pif={"id":7,"title":"Al Ahsa food processing investment","sector":{"name":"Agriculture"},"company":"Example Co","details":{"summary":"Al Ahsa opportunity"}}
    regional={"id":9,"title":"Hofuf logistics hub","category":"Logistics","city":"Hofuf","region":"Eastern Province","Coordinates":{"latitude":"25.38","longitude":"49.59"},"description":"Regional logistics development"}
    def handler(request):
        path=request.url.path
        if path.endswith("/pif-opportunities"):
            return httpx.Response(200,json={"data":[pif],"meta":{"page":1,"per_page":100,"total":1,"totalPages":1}})
        if path.endswith("/regional-opportunities"):
            return httpx.Response(200,json={"data":[regional],"meta":{"page":1,"per_page":100,"total":1,"totalPages":1}})
        return httpx.Response(200,json={"data":[],"meta":{"page":1,"per_page":100,"total":0,"total_pages":1}})
    async def run():
        adapter=InvestSaudiAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:records,pages=await adapter.fetch(client)
        return adapter,records,pages
    adapter,records,pages=asyncio.run(run())
    assert pages==4
    assert {r.external_id for r in records}=={"investsaudi:9"}
    assert len(adapter.location_reviews)==1 and adapter.location_reviews[0]["external_id"]=="investsaudi:7"
    pif_record=next(x for x in adapter.raw_candidates if x.external_id=="investsaudi:7")
    assert pif_record.raw["source_record_family"]=="pif"
    assert pif_record.raw["source_taxonomy"]["sector"]=="Agriculture"
    assert adapter.metrics["source_total_reported"]==2
    assert adapter.metrics["pif_opportunities_total"]==1
    assert adapter.metrics["regional_opportunities_total"]==1
    assert adapter.metrics["pagination_complete"] is True


def test_investsaudi_consolidates_exact_official_id_but_not_same_title():
    opportunity=invest_item(700,location="Hofuf",region="Al Ahsa")
    opportunity["title"]="Hofuf manufacturing project"
    pif={"id":700,"title":"مشروع تصنيع في الهفوف","sector":{"name":"Industrial"},"company":"PIF","details":{"summary":"Same official record represented in PIF collection"}}
    regional={"id":701,"title":"Hofuf manufacturing project","category":"Industrial","description":"A different official record with the same title"}
    def handler(request):
        path=request.url.path
        if path.endswith("/opportunities"):
            return httpx.Response(200,json={"data":[opportunity],"meta":{"page":1,"per_page":100,"total":1,"totalPages":1}})
        if path.endswith("/pif-opportunities"):
            return httpx.Response(200,json={"data":[pif],"meta":{"page":1,"per_page":100,"total":1,"totalPages":1}})
        if path.endswith("/regional-opportunities"):
            return httpx.Response(200,json={"data":[regional],"meta":{"page":1,"per_page":100,"total":1,"totalPages":1}})
        return httpx.Response(200,json={"data":[],"meta":{"page":1,"per_page":100,"total":0,"total_pages":1}})
    async def run():
        adapter=InvestSaudiAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:records,pages=await adapter.fetch(client)
        return adapter,records,pages
    adapter,records,pages=asyncio.run(run())
    assert pages==4
    assert len(adapter.raw_candidates)==2
    assert len(records)==1 and records[0].external_id=="investsaudi:700"
    consolidated=records[0].raw
    assert consolidated["official_source_id_original"]=="700"
    assert consolidated["official_source_id_normalized"]=="700"
    assert {m["dataset_name"] for m in consolidated["dataset_memberships"]}=={"Opportunities","PIF opportunities"}
    assert len(consolidated["source_observations"])==2
    assert adapter.metrics["endpoint_rows_received"]==3
    assert adapter.metrics["unique_official_ids"]==2
    assert adapter.metrics["duplicate_endpoint_memberships"]==1
    assert len(adapter.location_reviews)==0
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source=Source(source_key="invest-saudi",source_name_ar="Invest Saudi",organization_name="MISA",base_url="https://investsaudi.sa",opportunities_url="https://investsaudi.sa/investment-opportunities",source_type="national_opportunity_platform",priority=4,polling_frequency_minutes=360,enabled=True,extraction_method="test",notes="",sync_status="HEALTHY",last_record_count=0)
        db.add(source);db.flush()
        now=datetime.now(timezone.utc)
        for candidate in adapter.raw_candidates:
            record=SourceOpportunity(source_id=source.id,source_opportunity_id=candidate.external_id,
                official_source_id_original=candidate.raw["official_source_id_original"],official_source_id_normalized=candidate.raw["official_source_id_normalized"],
                source_title=candidate.title,normalized_source_title=candidate.title.casefold(),source_url=candidate.url,
                raw_data_json=candidate.raw,first_seen_at=now,last_seen_at=now,content_hash=candidate.content_hash,parser_version="test")
            db.add(record);db.flush();store_investsaudi_observations(db,source,record,candidate)
        assert db.scalar(select(func.count(SourceOpportunity.id)))==2
        assert db.scalar(select(func.count(SourceOpportunityDatasetMembership.id)))==3
        assert db.scalar(select(func.count(SourceObservation.id)))==3
        assert db.scalar(select(func.count(SourceOpportunityTaxonomy.id)))==3
        linked=db.scalar(select(SourceOpportunity).where(SourceOpportunity.official_source_id_normalized=="700"))
        assert linked.source_opportunity_id=="investsaudi:700"
        db.commit()


def test_investsaudi_dataset_membership_loss_does_not_remove_identity_from_other_dataset():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source=Source(source_key="invest-saudi",source_name_ar="Invest Saudi",organization_name="MISA",base_url="https://investsaudi.sa",opportunities_url="https://investsaudi.sa/investment-opportunities",source_type="national_opportunity_platform",priority=4,polling_frequency_minutes=360,enabled=True,extraction_method="test",notes="",sync_status="HEALTHY",last_record_count=0,missing_confirmation_threshold=3)
        db.add(source);db.flush()
        record=SourceOpportunity(source_id=source.id,source_opportunity_id="investsaudi:900",official_source_id_original="900",official_source_id_normalized="900",source_title="Example",normalized_source_title="example",source_url="https://investsaudi.sa/opportunities/900",first_seen_at=datetime.now(timezone.utc),last_seen_at=datetime.now(timezone.utc),content_hash="x",parser_version="test")
        db.add(record);db.flush()
        a=SourceOpportunityDatasetMembership(source_opportunity_id=record.id,dataset_name="Opportunities",endpoint="/opportunities",first_seen_at=datetime.now(timezone.utc),last_seen_at=datetime.now(timezone.utc))
        b=SourceOpportunityDatasetMembership(source_opportunity_id=record.id,dataset_name="PIF opportunities",endpoint="/pif-opportunities",first_seen_at=datetime.now(timezone.utc),last_seen_at=datetime.now(timezone.utc))
        db.add_all([a,b]);db.flush()
        reconcile_investsaudi_memberships(db,source,{"PIF opportunities":{record.id}},datetime.now(timezone.utc))
        db.flush()
        assert a.is_current is True and a.missing_successful_checks==1
        assert b.is_current is True and b.missing_successful_checks==0
        assert db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_opportunity_id=="investsaudi:900")) is not None


def test_investsaudi_all_dataset_memberships_deactivate_after_three_successful_misses():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source=Source(source_key="invest-saudi",source_name_ar="Invest Saudi",organization_name="MISA",base_url="https://investsaudi.sa",opportunities_url="https://investsaudi.sa/investment-opportunities",source_type="national_opportunity_platform",priority=4,polling_frequency_minutes=360,enabled=True,extraction_method="test",notes="",sync_status="HEALTHY",last_record_count=0,missing_confirmation_threshold=3)
        db.add(source);db.flush()
        record=SourceOpportunity(source_id=source.id,source_opportunity_id="investsaudi:901",official_source_id_original="901",official_source_id_normalized="901",source_title="Example",normalized_source_title="example",source_url="https://investsaudi.sa/opportunities/901",first_seen_at=datetime.now(timezone.utc),last_seen_at=datetime.now(timezone.utc),content_hash="x",parser_version="test")
        db.add(record);db.flush()
        membership=SourceOpportunityDatasetMembership(source_opportunity_id=record.id,dataset_name="Opportunities",endpoint="/opportunities",first_seen_at=datetime.now(timezone.utc),last_seen_at=datetime.now(timezone.utc))
        db.add(membership);db.flush()
        for _ in range(2):
            reconcile_investsaudi_memberships(db,source,{},datetime.now(timezone.utc));db.flush()
            assert membership.is_current is True
        reconcile_investsaudi_memberships(db,source,{},datetime.now(timezone.utc));db.flush()
        assert membership.is_current is False and membership.missing_successful_checks==3


def test_investsaudi_health_tracks_pagination_and_unique_dataset_reconciliation_separately():
    state=investsaudi_reconciliation_metrics(True,2555,2197,358)
    assert state["endpoint_completeness"]=="PAGINATION_COMPLETE"
    assert state["unique_dataset_reconciliation"]=="DATASET_RECONCILED"
    assert state["dataset_count"]==4 and state["datasets_complete"] is True
    assert state["ui_counter_observed"]==2197 and state["ui_counter_type"]=="STATIC_FRONTEND_VALUE"
    assert state["ui_counter_authoritative"] is False and state["ui_counter_semantics"]=="UNKNOWN"
    incomplete=investsaudi_reconciliation_metrics(False,2555,2197,358)
    assert incomplete["endpoint_completeness"]=="INCOMPLETE_COLLECTION"
    assert incomplete["unique_dataset_reconciliation"]=="DATASET_RECONCILIATION_WARNING"
    inconsistent=investsaudi_reconciliation_metrics(True,2555,2197,357)
    assert inconsistent["unique_dataset_reconciliation"]=="DATASET_RECONCILIATION_WARNING"
    missing_dataset=investsaudi_reconciliation_metrics(True,2555,2197,358,dataset_count=3)
    assert missing_dataset["datasets_complete"] is False
    assert missing_dataset["unique_dataset_reconciliation"]=="DATASET_RECONCILIATION_WARNING"

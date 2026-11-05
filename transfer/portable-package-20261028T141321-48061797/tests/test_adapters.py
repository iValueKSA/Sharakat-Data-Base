from urllib.parse import parse_qs, urlparse
import asyncio

import httpx
from app.adapters import AlAhsaOpportunitiesAdapter, FurasAdapter, normalized_record


def card(identifier, title=None):
    title=title or f"فرصة استثمارية {identifier}"
    return f'''<div class="opportunity-card-row"><h3 class="card-title">{title}</h3>
      <span class="status-badge">متاحة</span><a href="/opportunities/{identifier}">تفاصيل</a>
      <div class="detail-item"><span class="detail-label">الموقع:</span><span class="detail-value">الأحساء</span></div></div>'''


def page(cards, page_numbers, counts=(2,3)):
    links="".join(f'<a href="/?page={n}">{n}</a>' for n in page_numbers)
    return (f"<a href='/?category_id=2'>الفرص المميزة {counts[0]}</a>"
            f"<a href='/?category_id=3'>الفرص الاستثمارية {counts[1]}</a>"
            f"{links}{''.join(cards)}")


def test_server_pagination_visits_first_middle_and_short_final_page():
    payloads={
        1:page([card("10"),card("9")],[2,3],(2,3)),
        2:page([card("8"),card("7")],[1,3],(2,3)),
        3:page([card("6")],[1,2],(2,3)),
    }
    seen=[]
    async def handler(request):
        page_number=int(parse_qs(urlparse(str(request.url)).query).get("page",["1"])[0])
        seen.append(page_number)
        return httpx.Response(200,text=payloads[page_number])
    async def run():
        adapter=AlAhsaOpportunitiesAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            records,pages=await adapter.fetch(client)
        return adapter,records,pages
    adapter,records,pages=asyncio.run(run())
    assert seen==[1,2,3]
    assert pages==3
    assert len(records)==5
    assert adapter.metrics["source_total_reported"]==5
    assert adapter.metrics["pagination_complete"] is True
    assert adapter.metrics["records_received"]==5
    assert adapter.metrics["unique_records"]==5
    assert all(normalized_record(record)["location_detection_method"]=="SOURCE_FILTER" for record in records)
    assert all("Al-Ahsa-only public platform" in normalized_record(record)["location_evidence"] for record in records)


def test_overlapping_pages_deduplicate_source_ids_and_keep_completeness_signal():
    payloads={
        1:page([card("10"),card("9")],[2,3],(1,3)),
        2:page([card("8"),card("9")],[1,3],(1,3)),  # order changed; ID 9 repeated
        3:page([card("7")],[1,2],(1,3)),
    }
    async def handler(request):
        page_number=int(parse_qs(urlparse(str(request.url)).query).get("page",["1"])[0])
        return httpx.Response(200,text=payloads[page_number])
    async def run():
        adapter=AlAhsaOpportunitiesAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            records,_=await adapter.fetch(client)
        return adapter,records
    adapter,records=asyncio.run(run())
    assert len(records)==4
    assert len({r.external_id for r in records})==4
    assert adapter.metrics["records_received"]==5
    assert adapter.metrics["duplicate_items_between_pages"]==1
    assert adapter.metrics["pagination_complete"] is True


def test_furas_query_uses_city_filter_and_marks_source_filter_evidence():
    config_url=FurasAdapter.config_url
    layer="https://gis.example.test/Investment/MapServer/0"
    observations=[]
    async def handler(request):
        if str(request.url)==config_url:
            return httpx.Response(200,json={"gisLayerUrl":{"investmentMapServerInvestmentP":layer.rsplit("/",1)[0]},"gisLayerIndex":{"investmentMapServerInvestmentP":0}})
        params=dict(request.url.params);observations.append(params)
        if params.get("returnIdsOnly")=="true":return httpx.Response(200,json={"objectIds":[11,12]})
        features=[]
        for oid,ref in ((11,"03-26-001"),(12,"03-26-002")):
            features.append({"attributes":{"OBJECTID":oid,"OPPORTUNITYID":ref,"OPPORTUNITYDESCRIPTION":"موقع استثماري","CITY_ID":"1945","CITYNAME":" ","OPPORTUNITYTYPE":"TemporaryRental","OPPORTUNITYACTIVESTATUS":"Announced","QUALIFYINGOPPORTUNITY":0,"STARTDATE":1792540800000,"CREATED_DATE":1792454400000,"LASTRFPSELLDATE":1793059200000,"ENDDATE":1793059200000,"LASTBIDATE":1793145600000},"geometry":{"x":48.5,"y":25.5}})
        return httpx.Response(200,json={"features":features})
    async def run():
        adapter=FurasAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:records,pages=await adapter.fetch(client)
        return adapter,records,pages
    adapter,records,pages=asyncio.run(run())
    assert len(records)==2 and pages==2
    assert "CITY_ID IN" in observations[0]["where"]
    assert "OPPORTUNITYACTIVESTATUS='Announced'" in observations[0]["where"]
    assert "QualifyingOpportunity=0" in observations[0]["where"]
    assert records[0].external_id==records[0].reference
    assert records[0].url==f"https://furas.momah.gov.sa/index.php/ar/opportunity/{records[0].reference}?type=TempRental"
    assert records[0].location_source_filtered is True
    assert records[0].raw["publication_date"] is None
    assert records[0].raw["attributes"]["STARTDATE"] == 1792540800000
    assert records[0].deadline is None
    assert records[0].raw["attributes"]["LASTRFPSELLDATE"] == 1793059200000
    assert records[0].raw["attributes"]["ENDDATE"] == 1793059200000
    assert records[0].raw["attributes"]["LASTBIDATE"] == 1793145600000
    normalized=normalized_record(records[0])
    assert normalized["relevant"] is True
    assert normalized["location_detection_method"]=="SOURCE_FILTER"
    assert normalized["location_confidence_score"]==1.0
    assert "CITY_ID filter=1945" in normalized["location_evidence"]
    assert adapter.metrics["source_total_reported"]==2

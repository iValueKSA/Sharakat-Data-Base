import asyncio
from datetime import datetime, timezone

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.adapters import ADAPTERS, RawOpportunity, TaadeenAdapter, normalized_record
from app.models import Base, Opportunity, Source, SourceOpportunity
from app.service import _safe_record


BASE = "https://cms.taadeen.sa/en/mining-bids"


def page(title, status, extra=""):
    return f"""<html><body><h1>{title}</h1><p>{status}</p>{extra}</body></html>"""


def test_taadeen_adapter_enumerates_pages_rounds_and_site_children_deterministically():
    urls = {
        BASE: page("Mining Bids", "", '<a href="/en/mining-bids/round-11">More Details</a><a href="?page=1">Page 2</a><a href="?page=2">Page 3</a>')
        + '<a href="/en/mining-bids/round-11/jabal-idsas">More Details</a>',
        BASE + "?page=1": page("Mining Bids", "", '<a href="/en/mining-bids/round-11">More Details</a><a href="/en/mining-bids/round-11/ashab-adh-dhaib">More Details</a>'),
        BASE + "?page=2": page("Mining Bids", "", '<a href="/en/mining-bids/round-11">More Details</a>'),
        BASE + "/round-11": page("Round 11", "Active", """
            <p>2026-01-13</p><p>Pre- Qualification Questionnaire Open Window</p>
            <p>2026-07-31</p><p>The Deadline for PQQ submission</p>
            <p>Regions</p><p>Asir Terrane - Hail Region - Riyadh Region</p>
            <p>Area</p><p>1,878.00 km²</p>
            <a href="/en/oci-files/public?file=brochure.pdf">Round-11-Brochure.pdf</a>
            <a href="/en/mining-bids/round-11/ashab-adh-dhaib">More Details</a>
            <a href="/en/mining-bids/round-11/jabal-idsas">More Details</a>
        """),
        BASE + "/round-11/ashab-adh-dhaib": page("Ashab adh Dhaib", "Inactive", """
            <p>Riyadh Region</p><p>Site Bid</p><p>Area:</p><p>188.94 km²</p>
            <p>Minerals</p><p>Gold, Silver, Copper, Nickel, Zinc</p>
            <a href="https://bidding.taadeen.sa/admin/pqq-forms/public-form">Round 11 PQQ</a>
            <a href="https://objectstorage.example/Ashab.zip">Download Files</a>
        """),
        BASE + "/round-11/jabal-idsas": page("Jabal Idsas", "Inactive", """
            <p>Hail Region</p><p>Site Bid</p><p>Area</p><p>193.2 km²</p><p>الخام: ذهب ونحاس</p>
            <p>Minerals</p><p>Breadcrumb</p>
        """),
    }

    def handler(request):
        body = urls.get(str(request.url))
        assert body is not None, f"unexpected public route: {request.url}"
        return httpx.Response(200, text=body)

    async def run():
        adapter = TaadeenAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            records, pages = await adapter.fetch(client)
            second_records, second_pages = await adapter.fetch(client)
        return adapter, records, pages, second_records, second_pages

    adapter, records, pages, second_records, second_pages = asyncio.run(run())
    assert ADAPTERS[TaadeenAdapter.key] is TaadeenAdapter
    assert len(records) == 2
    assert pages == 6
    assert adapter.metrics["catalog_pages"] == 3
    assert adapter.metrics["public_round_count"] == 1
    assert adapter.metrics["pagination_complete"] is True
    assert second_pages == pages
    assert len({r.external_id for r in records}) == 2
    assert [(r.external_id, r.content_hash) for r in records] == [(r.external_id, r.content_hash) for r in second_records]
    first = next(r for r in records if r.title == "Ashab adh Dhaib")
    assert first.external_id == "taadeen:round-11:ashab-adh-dhaib"
    assert first.raw["round_id"] == "round-11"
    assert first.raw["round_status"] == "Active"
    assert first.status == "Inactive"
    assert first.raw["round_application_start"] == "2026-01-13"
    assert first.raw["round_application_deadline"] == "2026-07-31"
    assert first.raw["site"]["site_id"] == "ashab-adh-dhaib"
    assert first.raw["site"]["region"] == "Riyadh Region"
    assert first.raw["site"]["minerals"] == "Gold, Silver, Copper, Nickel, Zinc"
    assert first.raw["site"]["application_url"].endswith("public-form")
    assert first.raw["site"]["coordinates"] is None
    assert first.raw["site"]["documents"]
    jabal = next(r for r in records if r.title == "Jabal Idsas")
    assert jabal.raw["site"]["minerals"] == "ذهب ونحاس"
    assert normalized_record(first)["relevant"] is False
    assert normalized_record(first)["location_detection_method"] == "TAADEEN_SOURCE_CAPTURE_NO_AUTOPROMOTION"


def test_taadeen_source_capture_is_idempotent_and_creates_no_masters():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    source = Source(source_key=TaadeenAdapter.key, source_name_ar="منصة تعدين – مزايدات التعدين",
        organization_name="Ta'adeen Platform", base_url="https://cms.taadeen.sa/",
        opportunities_url=BASE, enabled=True, priority=14, polling_frequency_minutes=1440,
        source_type="official_public_mining_bid_catalog")
    now = datetime.now(timezone.utc).isoformat()
    raw = RawOpportunity(external_id="taadeen:round-11:ashab-adh-dhaib", title="Ashab adh Dhaib",
        url=BASE + "/round-11/ashab-adh-dhaib", location="Riyadh Region", status="Inactive",
        deadline="2026-07-31", raw={"provider":"TAADEEN", "provider_id":"taadeen:round-11:ashab-adh-dhaib",
            "round":{"round_id":"round-11","round_status":"Active","round_application_deadline":"2026-07-31"},
            "site":{"site_id":"ashab-adh-dhaib","region":"Riyadh Region"}, "source_timestamp":now})
    counts = {"raw_count":0,"rejected_count":0,"update_count":0,"unchanged_count":0}
    with Session() as db:
        db.add(source); db.commit()
        _safe_record(db, source, raw, counts); db.commit()
        first_id = db.scalar(select(SourceOpportunity.id).where(SourceOpportunity.source_id == source.id))
        _safe_record(db, source, raw, counts); db.commit()
        assert db.scalar(select(func.count(SourceOpportunity.id))) == 1
        assert db.scalar(select(func.count(Opportunity.id))) == 0
        stored = db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_id == source.id))
        assert stored.id == first_id
        assert stored.master_opportunity_id is None
        assert stored.raw_data_json["round"]["round_application_deadline"] == "2026-07-31"
    engine.dispose()

import asyncio
import hashlib
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters import KfuAdapter
from app.models import Base, Opportunity, Source, SourceOpportunity
from app.normalization import normalize_arabic
from app.source_identity_aliases import resolve_source_identity


FIXTURES = Path(__file__).parent / "fixtures" / "kfu_announcements"


def _parse_fixture(name, transform=None):
    html = (FIXTURES / name).read_text(encoding="utf-8")
    if transform:
        html = transform(html)

    def handler(request):
        return httpx.Response(200, text=html, request=request)

    async def run():
        adapter = KfuAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            records, pages = await adapter.fetch(client)
        return adapter, records, pages

    return asyncio.run(run())


def test_official_snapshot_keeps_booklet_with_exact_notice_and_form_as_application_link():
    adapter, records, _ = _parse_fixture("official_page_snapshot.html")
    assert len(records) == 2
    expired, current = records
    assert expired.status == "EXPIRED"
    assert [x["url"] for x in expired.raw["attachments"]] == [KfuAdapter.url.rsplit("/", 1)[0] + "/assets/booklet.pdf"]
    assert current.raw["attachments"] == []
    assert current.raw["application_links"][0]["url"].startswith("https://docs.google.com/forms/")
    assert current.deadline is None
    assert current.raw["source_url_provenance"]["source_url_scope"] == "LISTING_ONLY_NO_ITEM_URL"
    assert all(record.url == "" for record in records)
    assert len(adapter.content_items) == 1
    assert adapter.content_items[0]["attachments"] == [
        {**adapter.content_items[0]["attachments"][0], "association_status": "UNASSIGNED_LISTING_REFERENCE"}
    ]


def test_notice_documents_do_not_leak_and_repeated_cross_notice_url_is_unassigned():
    adapter, records, _ = _parse_fixture("provenance_cases.html")
    expired = next(record for record in records if "مزايدة" in record.title)
    current = next(record for record in records if "كليات جامعة الملك فيصل" in record.title and "فرصة" in record.title)
    riyadh = next(record for record in records if "الرياض" in record.title)
    jeddah = next(record for record in records if "جدة" in record.title)

    assert len(expired.raw["attachments"]) == 2
    assert len({x["url"] for x in expired.raw["attachments"]}) == 2
    assert current.raw["attachments"] == []
    assert len(current.raw["application_links"]) == 1
    assert [x["url"] for x in riyadh.raw["attachments"]] == [urljoin(KfuAdapter.url, "/files/riyadh.pdf")]
    assert [x["url"] for x in jeddah.raw["attachments"]] == [urljoin(KfuAdapter.url, "/files/jeddah.pdf")]
    assert not any("shared-ambiguous" in x["url"] for r in records for x in r.raw["attachments"])
    shared = [x for x in adapter.content_items[0]["attachments"] if "shared-ambiguous" in x["url"]]
    assert len(shared) == 1
    assert shared[0]["association_status"] == "AMBIGUOUS_REPEATED_ACROSS_NOTICES"
    assert adapter.metrics["ambiguous_attachment_count"] == 1
    assert adapter.metrics["source_collection_complete"] is False
    assert adapter.content_items[0]["attachments"][0]["association_status"] == "UNASSIGNED_LISTING_REFERENCE"


def test_similar_titles_have_stable_distinct_identity_independent_of_notice_order():
    html = (FIXTURES / "provenance_cases.html").read_text(encoding="utf-8")

    def reverse_panels(_html):
        soup = BeautifulSoup(_html, "html.parser")
        panels = soup.select("li.AccordionPanel")
        parent = panels[0].parent
        for panel in panels:
            panel.extract()
        for panel in reversed(panels):
            parent.append(panel)
        return str(soup)

    normal_adapter, normal, _ = _parse_fixture("provenance_cases.html")
    reversed_adapter, reversed_records, _ = _parse_fixture("provenance_cases.html", reverse_panels)
    normal_identity = {r.external_id: (r.title, sorted(x["url"] for x in r.raw["attachments"])) for r in normal}
    reversed_identity = {r.external_id: (r.title, sorted(x["url"] for x in r.raw["attachments"])) for r in reversed_records}
    assert normal_identity == reversed_identity
    similar = [r for r in normal if "فرصة استثمارية لتأجير مواقع غذائية في مدارس" in r.title]
    assert len(similar) == 2
    assert similar[0].external_id != similar[1].external_id


def test_repeated_collection_is_idempotent_and_provider_id_formula_is_title_stable():
    _, first, _ = _parse_fixture("official_page_snapshot.html")
    adapter, second, _ = _parse_fixture("official_page_snapshot.html")
    assert [(x.external_id, x.content_hash) for x in first] == [(x.external_id, x.content_hash) for x in second]
    assert adapter.content_items[0]["fingerprint"] == _parse_fixture("official_page_snapshot.html")[0].content_items[0]["fingerprint"]
    for record in first:
        expected = "kfu-announcement:" + hashlib.sha256((KfuAdapter.url + "\n" + normalize_arabic(record.title)).encode()).hexdigest()[:24]
        assert record.external_id == expected


def test_existing_current_kfu_provider_identity_2928_is_preserved_by_notice_capture():
    _, records, _ = _parse_fixture("current_seasonal_identity.html")
    assert len(records) == 1
    assert records[0].title == (
        'فرصة استثمارية " لتأجير مواقع مؤقته لتقديم الخدمات الغذائية بكليات جامعة الملك فيصل '
        'فرصة استثمارية " لتأجير مواقع مؤقته لتقديم الخدمات الغذائية بكليات جامعة الملك فيصل للتقديم على الفرصة'
    )
    assert records[0].external_id == "kfu-announcement:0aac035af08807f4f1755ee5"
    assert records[0].raw["attachments"] == []
    assert records[0].raw["application_links"][0]["url"].startswith("https://docs.google.com/forms/")


def test_existing_source_resolution_keeps_2774_and_2928_as_separate_identities_and_masters():
    _, records, _ = _parse_fixture("current_seasonal_identity.html")
    incoming = records[0]
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as db:
            source = Source(source_key="kfu", source_name_ar="جامعة الملك فيصل", organization_name="جامعة الملك فيصل",
                base_url=KfuAdapter.url, opportunities_url=KfuAdapter.url)
            db.add(source)
            masters = [
                Opportunity(id=225, canonical_id="KFU-MASTER-225", title_ar=incoming.title,
                    normalized_title=normalize_arabic(incoming.title), primary_publication_platform="جامعة الملك فيصل",
                    city="الأحساء", status="أزيلت من المصدر", first_seen_at=now, last_seen_at=now,
                    last_updated_at=now, created_at=now, updated_at=now),
                Opportunity(id=326, canonical_id="KFU-MASTER-326", title_ar=incoming.title,
                    normalized_title=normalize_arabic(incoming.title), primary_publication_platform="جامعة الملك فيصل",
                    city="الأحساء", status="حالة غير معروفة", first_seen_at=now, last_seen_at=now,
                    last_updated_at=now, created_at=now, updated_at=now),
            ]
            db.add_all(masters)
            db.flush()
            legacy = SourceOpportunity(id=2774, source_id=source.id, master_opportunity_id=225,
                source_opportunity_id="kfu-announcement:7e98c5dfb12b0a6d09f4c349",
                source_title=incoming.title, normalized_source_title=normalize_arabic(incoming.title),
                source_url="https://www.kfu.edu.sa/listing.html#kfu-announcement:legacy",
                raw_status="UNKNOWN", canonical_status="أزيلت من المصدر", raw_dates={},
                raw_data_json={"attachments": [{"url": "https://example.invalid/legacy.pdf"}]},
                standardized_data_json={}, first_seen_at=now, last_seen_at=now,
                content_hash="a" * 64, parser_version="legacy")
            source_record = SourceOpportunity(id=2928, source_id=source.id, master_opportunity_id=326,
                source_opportunity_id=incoming.external_id, source_title=incoming.title,
                normalized_source_title=normalize_arabic(incoming.title), source_url="",
                raw_status="UNKNOWN", canonical_status="حالة غير معروفة", raw_dates={}, raw_data_json={},
                standardized_data_json={}, first_seen_at=now, last_seen_at=now,
                content_hash=incoming.content_hash, parser_version="2026.10.12-kfu-1")
            db.add_all([legacy, source_record])
            db.flush()

            first = resolve_source_identity(db, source, incoming.external_id)
            second = resolve_source_identity(db, source, incoming.external_id)
            assert first.status == second.status == "EXACT"
            assert first.record.id == second.record.id == source_record.id == 2928
            assert first.record.master_opportunity_id == second.record.master_opportunity_id == 326
            assert first.record.source_opportunity_id == incoming.external_id
            assert legacy.id == 2774 and legacy.master_opportunity_id == 225
            assert db.query(SourceOpportunity).filter(SourceOpportunity.source_id == source.id).count() == 2
            assert db.query(Opportunity).filter(Opportunity.id.in_([225, 326])).count() == 2
    finally:
        engine.dispose()


def test_duplicate_normalized_notice_titles_fail_closed_without_fake_identity():
    html = (FIXTURES / "official_page_snapshot.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    first = soup.select_one("li.AccordionPanel")
    second = soup.select("li.AccordionPanel")[1]
    duplicate = BeautifulSoup(str(first), "html.parser").li
    duplicate["id"] = "volatile-other-id"
    second.replace_with(duplicate)
    changed = str(soup)

    def handler(request):
        return httpx.Response(200, text=changed, request=request)

    async def run():
        adapter = KfuAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            records, _ = await adapter.fetch(client)
        return adapter, records

    adapter, records = asyncio.run(run())
    assert records == []
    assert adapter.metrics["notice_identity_collision_count"] == 2
    assert adapter.metrics["source_collection_complete"] is False
    assert all(x["association_status"] in {"UNRESOLVED_NOTICE_IDENTITY_COLLISION", "AMBIGUOUS_REPEATED_ACROSS_NOTICES"}
               for x in adapter.content_items[0]["attachments"] if "booklet" in x["url"])


def test_missing_notice_containers_fail_closed_and_preserve_only_page_evidence():
    def handler(request):
        return httpx.Response(200, text='<html><main><a href="/shared.pdf">عام</a><p>فرصة استثمارية</p></main></html>', request=request)

    async def run():
        adapter = KfuAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            records, _ = await adapter.fetch(client)
        return adapter, records

    adapter, records = asyncio.run(run())
    assert records == []
    assert adapter.metrics["source_collection_complete"] is False
    assert adapter.content_items[0]["attachments"][0]["association_status"] == "UNASSIGNED_LISTING_REFERENCE"

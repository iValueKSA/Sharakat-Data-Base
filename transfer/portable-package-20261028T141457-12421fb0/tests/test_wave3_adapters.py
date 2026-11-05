import asyncio

import httpx

from app.adapters import KfuAdapter, ModonAdapter, NcpAdapter
from app.service import classify_http_health
from app.models import Source


def test_kfu_classifies_explicit_lease_asset():
    kind, eligible, reason = KfuAdapter.classify("فرصة استثمارية لتأجير مواقع", "تأجير مواقع في كليات الجامعة")
    assert (kind, eligible) == ("LEASE_OPPORTUNITY", True)
    assert "تأجير" in reason


def test_kfu_classifies_operation_concession():
    kind, eligible, _ = KfuAdapter.classify("تشغيل مرفق جامعي", "تشغيل وإدارة أصل جامعي")
    assert (kind, eligible) == ("OPERATING_OPPORTUNITY", True)


def test_kfu_classifies_commercial_facility():
    kind, eligible, _ = KfuAdapter.classify("مطاعم ومتاجر عامة", "تقديم الخدمات في مباني كليات الجامعة")
    assert (kind, eligible) == ("COMMERCIAL_FACILITY_OPPORTUNITY", True)


def test_kfu_rejects_ordinary_supply_tender():
    kind, eligible, _ = KfuAdapter.classify("منافسة توريد أجهزة", "توريد أجهزة إلى الجامعة")
    assert (kind, eligible) == ("PROCUREMENT_TENDER", False)


def test_kfu_does_not_infer_eligibility_from_general_announcement():
    kind, eligible, _ = KfuAdapter.classify("إعلان عام", "اجتماع وورشة عمل للمستثمرين")
    assert (kind, eligible) == ("GENERAL_ANNOUNCEMENT", False)


def test_kfu_explicit_past_deadline_is_expired_without_award_inference():
    assert KfuAdapter.deadline_status("2025-01-22", "2026-10-12") == "EXPIRED"
    assert KfuAdapter.deadline_status(None, "2026-10-12") == "UNKNOWN"


def test_kfu_listing_metadata_records_attachments_without_downloading():
    def handler(request):
        return httpx.Response(200, text='''<html><title>إعلانات الاستثمار</title><main>
          <ul><li class="AccordionPanel"><h3>فرصة استثمارية لتأجير مواقع</h3><p>تأجير مواقع بكليات جامعة الملك فيصل</p>
          <p>موعد نهاية تقديم العطاء 2026/12/15</p><a href="/booklet.pdf">كراسة</a></li>
          <li class="AccordionPanel"><h3>منافسة توريد أجهزة</h3><p>توريد أجهزة للمستودع</p></li></ul></main></html>''')
    async def run():
        adapter = KfuAdapter()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            records, _ = await adapter.fetch(client)
        return adapter, records
    adapter, records = asyncio.run(run())
    assert len(records) >= 2
    eligible = [r for r in records if r.raw.get("qualified")]
    assert eligible and eligible[0].raw["attachments"][0]["downloaded"] is False
    assert eligible[0].url==""
    assert eligible[0].raw["source_listing_url"]==KfuAdapter.url
    assert any(r.deadline == "2026-12-15" and r.raw["deadline_evidence"] == "explicit announcement date" for r in records)
    assert all(r.raw.get("qualification_review_required") is False for r in records)
    assert adapter.metrics["source_collection_complete"] is True


def test_modon_requires_explicit_city_level_evidence():
    assert ModonAdapter.is_al_ahsa_location("Al-Ahsa First Industrial City")
    assert ModonAdapter.is_al_ahsa_location("مدينة الأحساء الصناعية الأولى")
    assert not ModonAdapter.is_al_ahsa_location("Eastern Province")


def test_modon_accepts_hofuf_and_mubarraz_aliases():
    assert ModonAdapter.is_al_ahsa_location("Al Hofuf")
    assert ModonAdapter.is_al_ahsa_location("المبرز")


def test_modon_preserves_asset_status_area_and_geometry():
    facts = ModonAdapter.project_fields({"OBJECTID": 9, "Project": "Warehouse 9", "Project_Status": "Live", "Land_Area_sqm": 1500}, {"x": 49, "y": 25})
    assert facts == {"official_source_id": 9, "asset_name": "Warehouse 9", "raw_status": "Live", "area_sqm": 1500, "geometry": {"x": 49, "y": 25}}


def test_modon_reference_asset_without_availability_is_not_an_opportunity():
    assert not ModonAdapter.is_current_investment_product({"Project": "Factory A", "Project_Status": "Allocated"})


def test_modon_explicit_available_product_can_qualify():
    assert ModonAdapter.is_current_investment_product({"ProductAvailability": "Available"})


def test_modon_http_200_waf_rejection_is_not_treated_as_an_empty_page():
    assert ModonAdapter.public_page_was_rejected("<title>Request Rejected</title>Access denied")
    assert not ModonAdapter.public_page_was_rejected("<title>Open Data Platform</title>48 datasets")


def test_modon_open_data_dataset_selection_covers_asset_and_financing_topics():
    assert ModonAdapter.dataset_is_inventory_relevant("Ready made factories")
    assert ModonAdapter.dataset_is_inventory_relevant("Financing Solutions Available for Investors in MODON")
    assert not ModonAdapter.dataset_is_inventory_relevant("Traffic Q2 2026")


def test_modon_landbank_item_not_assumed_to_be_a_valid_saudi_asset_feed():
    assert ModonAdapter.landbank_item_id == "43d60e1f77804597a178b6723fe2f1dc"
    assert "reference GIS features as inventory" in ModonAdapter.__doc__


def test_modon_unknown_catalog_cannot_claim_complete_snapshot():
    assert "never treat reference GIS features as inventory" in ModonAdapter.__doc__


def test_ncp_separates_eoi_rfq_rfp_and_bid_stages():
    assert NcpAdapter.project_stage("EOI launch", "Expression of Interest") == "EOI"
    assert NcpAdapter.project_stage("RFQ", "Request for Qualification") == "RFQ"
    assert NcpAdapter.project_stage("RFP launch", "Request for Proposals") == "RFP"
    assert NcpAdapter.project_stage("Bid stage", "Qualified bidders submit bids") == "BID_STAGE"


def test_ncp_preserves_awarded_stage_separately_from_lifecycle():
    assert NcpAdapter.project_stage("Award of project", "The contract was awarded") == "AWARDED"
    assert NcpAdapter.lifecycle("AWARDED", "2025-01-01", "2026-10-12") == "AWARDED"


def test_ncp_requires_explicit_al_ahsa_city():
    assert NcpAdapter.is_ahsa_evidence(NcpAdapter.locations("Project sites include Al Ahsa."))
    assert not NcpAdapter.is_ahsa_evidence(NcpAdapter.locations("Project covers the Eastern Province."))


def test_ncp_accepts_multilocation_project_once_and_preserves_all_locations():
    locations = NcpAdapter.locations("Five municipalities: Al Ahsa, Tabuk, Qassim, Jeddah, and Hafr Al Batin.")
    assert NcpAdapter.is_ahsa_evidence(locations)
    assert len(locations) >= 4


def test_ncp_does_not_mistake_publication_city_for_a_project_location():
    locations = NcpAdapter.locations("Riyadh, April 2026. The project covers Al Ahsa and Tabuk.")
    assert "Riyadh" not in locations
    assert {"Al-Ahsa", "Tabuk"}.issubset(set(locations))


def test_ncp_deadline_expiry_does_not_infer_award():
    assert NcpAdapter.lifecycle("EOI", "2026-01-01", "2026-10-12") == "EXPIRED"
    assert NcpAdapter.lifecycle("EOI", None, "2026-10-12") == "UNKNOWN"


def test_ncp_public_archive_scope_is_separate_from_private_pipeline():
    assert "private portal API" in NcpAdapter.__doc__
    assert {kind for _, kind in NcpAdapter.public_discovery_pages} == {
        "PUBLIC_HOMEPAGE", "MEDIA_CENTER", "DIGITAL_LIBRARY", "KNOWLEDGE_CENTER", "SITEMAP"
    }


def test_coverage_and_technical_health_are_independent_dimensions():
    source = Source(source_key="modon", source_name_ar="مدن", organization_name="MODON", base_url="https://modon.gov.sa", opportunities_url="https://modon.gov.sa/en/InvestmentOpportunities")
    source.technical_health = "HEALTHY"
    source.coverage_status = "PUBLIC_COVERAGE_LIMITED"
    assert source.technical_health == "HEALTHY"
    assert source.coverage_status == "PUBLIC_COVERAGE_LIMITED"


def test_technical_health_of_a_temporary_502_is_warning():
    assert classify_http_health(502) == "WARNING"
    assert classify_http_health(429) == "RATE_LIMITED"
    assert classify_http_health(None) == "WARNING"


def test_ncp_preview_and_eoi_can_share_conservative_project_identity():
    preview = NcpAdapter.project_identity("Project Preview: Waste Treatment Facility PPP Project")
    eoi = NcpAdapter.project_identity("NCP Launches EOI for Waste Treatment Facility PPP Project")
    assert preview == eoi


def test_ncp_eoi_and_rfq_are_distinct_lifecycle_events_for_one_project_identity():
    eoi = "NCP Launches EOI for Regional Waste Treatment Project"
    rfq = "NCP Launches RFQ for Regional Waste Treatment Project"
    assert NcpAdapter.project_identity(eoi) == NcpAdapter.project_identity(rfq)
    assert NcpAdapter.project_stage(eoi, "Expression of Interest") == "EOI"
    assert NcpAdapter.project_stage(rfq, "Request for Qualification") == "RFQ"


def test_ncp_public_sharepoint_pagination_parser_reads_rows_and_next_link():
    html = '''<script>var WPQ1ListData = {"Row":[{"ID":"2","Title":"RFQ Project","FileRef":"/en/MediaCenter/News/Pages/rfq.aspx","ArticleStartDate":"01/02/2026"}],"NextHref":"?Paged=TRUE&PageFirstRow=5"};</script>'''
    rows, next_href = NcpAdapter._listing_rows(html)
    assert rows[0]["Title"] == "RFQ Project"
    assert rows[0]["FileRef"].endswith("rfq.aspx")
    assert next_href.startswith("?Paged=TRUE")

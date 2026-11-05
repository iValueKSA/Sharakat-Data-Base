from bs4 import BeautifulSoup
from pathlib import Path
import asyncio
from app.normalization import classify_location

from app.adapters import NhcAdapter, PifPrivateSectorAdapter, MwanAdapter
from app.regression import classify_live_regression
from app.entity_resolution import values_equivalent


def test_nhc_qualifies_business_roles_and_rejects_consumer_sales():
    assert NhcAdapter.classify_page("Real Estate Developer", "Investment opportunity for residential development")[1]
    assert NhcAdapter.classify_page("Development partnership", "Seeking a private sector partner")[0] == "DEVELOPER_PARTNERSHIP"
    assert NhcAdapter.classify_page("Facility operator", "Seeking an operator for healthcare facilities")[0] == "FACILITY_OPERATOR_OPPORTUNITY"
    assert NhcAdapter.classify_page("Residential units for sale", "Book your home now")[0] == "CONSUMER_PROPERTY_OFFERING"


def test_nhc_does_not_make_categories_or_qualification_documents_opportunities():
    kind, eligible = NhcAdapter.classify_page("Investment categories", "Download qualification requirements")
    assert (kind, eligible) == ("MARKETING_CONTENT", False)


def test_nhc_route_criticality_keeps_equivalent_english_page_supporting():
    assert len(NhcAdapter.pages) == 6
    assert NhcAdapter.route_criticality["https://www.nhc.sa/ar/investment-opportunities/"] == "CRITICAL"
    assert NhcAdapter.route_criticality["https://www.nhc.sa/en/investment-opportunities/"] == "SUPPORTING"
    assert set(NhcAdapter.route_criticality.values()) <= {"CRITICAL", "SUPPORTING", "OPTIONAL", "DISCOVERY_ONLY"}


def test_nhc_restricted_supporting_route_preserves_public_scope_and_never_reconciles():
    adapter = NhcAdapter()
    class Response:
        def __init__(self, url, status_code=200):
            self.url=url; self.status_code=status_code
            self.text='<html><body><main><h1>Investment Opportunities</h1><p>Types of investment opportunities and qualification requirements</p></main></body></html>'
        def raise_for_status(self):
            if self.status_code >= 400: raise __import__('httpx').HTTPStatusError('blocked', request=None, response=self)
    class Client:
        async def get(self, url, **kwargs):
            return Response(url, 403 if url == "https://www.nhc.sa/en/investment-opportunities/" else 200)
    rows, _ = asyncio.run(adapter.fetch(Client()))
    assert rows == []
    assert adapter.metrics["technical_health"] == "HEALTHY"
    assert adapter.metrics["public_scope_complete"] is True
    assert adapter.metrics["reconciliation_safe"] is False
    assert adapter.metrics["critical_routes_total"] == adapter.metrics["critical_routes_successful"] == 1
    assert adapter.metrics["supporting_routes_total"] == 5
    assert adapter.metrics["supporting_routes_successful"] == 4
    route = next(r for r in adapter.metrics["route_inventory"] if r["last_http_status"] == 403)
    assert route["route_state"] == "ACCESS_RESTRICTED"
    assert route["route_health"] == "ACCESS_RESTRICTED"
    assert route["route_criticality"] == "SUPPORTING"


def test_live_regression_accepts_valid_external_changes():
    assert classify_live_regression(legitimate_changes=2) == "VALID_LIVE_CHANGE"
    assert classify_live_regression() == "DATA_STABLE"
    assert classify_live_regression(unexpected_changes=1) == "UNEXPECTED_DATA_CHANGE"
    assert classify_live_regression(parser_failures=1, legitimate_changes=2) == "PARSER_REGRESSION"
    assert classify_live_regression(pagination_complete=False) == "PARSER_REGRESSION"
    assert classify_live_regression(ids_stable=False) == "PARSER_REGRESSION"
    assert classify_live_regression(provenance_preserved=False) == "PARSER_REGRESSION"


def test_unknown_source_status_does_not_create_a_false_field_conflict():
    assert values_equivalent("status", "Announced", "غير محددة")


def test_pif_money_unknown_and_ranges():
    assert PifPrivateSectorAdapter.parse_money("SAR 10-20 million") == (10_000_000.0, 20_000_000.0)
    assert PifPrivateSectorAdapter.parse_money("SAR 50-80mn") == (50_000_000.0, 80_000_000.0)
    assert PifPrivateSectorAdapter.parse_money("SAR 3.3bn") == (3_300_000_000.0, 3_300_000_000.0)
    assert PifPrivateSectorAdapter.parse_money("To be updated") == (None, None)


def test_pif_company_filter_is_context_and_mixed_item_owner_wins():
    adapter = PifPrivateSectorAdapter()
    html = Path("tests/fixtures/pif/company-mixed-filter.html").read_text(encoding="utf-8-sig")
    route = adapter.company_url + "?associatedcompany=Company+A"
    rows = adapter._parse_items(BeautifulSoup(html, "html.parser"), route, company_filter="Company A", route_type="COMPANY")
    assert len(rows) == 1
    assert rows[0]["requested_company_filter"] == "Company A"
    assert rows[0]["actual_item_portfolio_company"] == "Company B"
    assert rows[0]["interest_url"] == "https://www.pif.gov.sa/interest/mixed"


def test_pif_item_identity_distinguishes_generic_titles_and_reuses_official_id():
    first = PifPrivateSectorAdapter.item_identity("https://pif.gov.sa/a", "Co A", "Manufacturing opportunity", "123")
    same = PifPrivateSectorAdapter.item_identity("https://pif.gov.sa/b", "Co B", "Another title", "123")
    different = PifPrivateSectorAdapter.item_identity("https://pif.gov.sa/b", "Co B", "Manufacturing opportunity")
    assert first == same == "pif:123"
    assert different != first


def test_pif_classifies_procurement_separately_from_private_investment():
    assert PifPrivateSectorAdapter.item_semantic("RFQ supplier tender", "routine procurement") == "PROCUREMENT_LIKE"
    assert PifPrivateSectorAdapter.item_semantic("Manufacturing facility", "private sector investment") == "MANUFACTURING"


def test_pif_five_html_cards_parse_to_five_distinct_opportunities_and_preserve_economics():
    adapter = PifPrivateSectorAdapter()
    html = Path("tests/fixtures/pif/ecosystem-five-cards.html").read_text(encoding="utf-8-sig")
    url = next(iter(adapter.known_ecosystem_routes))
    rows = adapter._parse_items(BeautifulSoup(html, "html.parser"), url, ecosystem="advanced-manufacturing-and-innovation")
    assert len(rows) == 5
    assert rows[0]["investment_size_raw"] == "SAR 50-80mn"
    assert (rows[0]["investment_size_min_sar"], rows[0]["investment_size_max_sar"]) == (50_000_000, 80_000_000)
    unknown = next(row for row in rows if row["investment_size_raw"] == "To be updated")
    assert unknown["investment_size_min_sar"] is None and unknown["investment_size_max_sar"] is None
    assert rows[0]["interest_url"].endswith("/interest?id=11111111-1111-4111-8111-111111111111")


def test_pif_navigation_filters_and_no_results_text_are_not_opportunity_cards():
    adapter = PifPrivateSectorAdapter()
    html = Path("tests/fixtures/pif/no-results-no-false-cards.html").read_text(encoding="utf-8-sig")
    rows = adapter._parse_items(BeautifulSoup(html, "html.parser"), adapter.url, route_type="AGGREGATE_LISTING")
    assert rows == []


def test_pif_no_results_is_a_valid_empty_public_listing_and_not_a_parser_failure():
    adapter = PifPrivateSectorAdapter()
    body = '<html><body><h1>List of Opportunities in a PIF ecosystem</h1><h4>By Indicative Investment Size</h4><p>No results found</p></body></html>'
    landing = '<html><body><h1>Explore Opportunities</h1><p>No portfolio found</p>' + ''.join(
        f'<a href="{url}">ecosystem</a>' for url in adapter.known_ecosystem_routes
    ) + f'<a href="{adapter.company_url}">Companies</a></body></html>'

    class Response:
        def __init__(self, url, text): self.url=url; self.text=text; self.status_code=200
    class Client:
        async def get(self, url, **kwargs):
            if url == adapter.sitemap_url: return Response(url, '<urlset></urlset>')
            return Response(url, landing if url == adapter.url else body)

    accepted, _ = asyncio.run(adapter.fetch(Client()))
    assert accepted == []
    assert adapter.raw_candidates == []
    assert adapter.metrics['current_listing_state'] == 'CURRENT_PUBLIC_LISTINGS_EMPTY'
    assert adapter.metrics['technical_health'] == 'HEALTHY'
    assert adapter.metrics['coverage_status'] == 'PUBLIC_COVERAGE_LIMITED'
    assert adapter.metrics['public_route_monitor_complete'] is True
    assert adapter.metrics['current_population_enumerable'] is False
    assert adapter.metrics['company_filter_roster_public'] is False
    assert adapter.metrics['collection_incomplete'] is False


def test_pif_search_index_only_known_titles_do_not_create_source_opportunities():
    # Indexed titles such as passive circuit components and smart water meters
    # are discovery evidence only; the current public-page parser sees no card.
    adapter = PifPrivateSectorAdapter()
    html = '<main><h1>List of Opportunities in Advanced Manufacturing</h1><p>By Indicative Investment Size</p><p>No results found</p></main>'
    rows = adapter._parse_items(BeautifulSoup(html, 'html.parser'), next(iter(adapter.known_ecosystem_routes)), route_type='ECOSYSTEM')
    assert rows == []


def test_pif_public_hidden_json_opportunity_is_parsed_from_raw_html():
    payload = {
        "opportunities": [{
            "title": "Public data center cooling opportunity",
            "descriptionOfInvestmentOpportunity": "Establish local production of data center cooling equipment.",
            "opportunityId": "9b18e5e9-95d8-4afb-9398-f5f732ba3c7d",
            "portfolioCompany": "HUMAIN",
            "indicativeInvestmentSize": "SAR 93mn",
        }]
    }
    import json
    html = '<html><body><h1>List of Opportunities</h1><script type="application/json">' + json.dumps(payload) + '</script></body></html>'
    rows = PifPrivateSectorAdapter()._parse_items(BeautifulSoup(html, 'html.parser'),
        next(iter(PifPrivateSectorAdapter.known_ecosystem_routes)), route_type='ECOSYSTEM')
    assert len(rows) == 1
    assert rows[0]['title'] == 'Public data center cooling opportunity'
    assert rows[0]['raw_id'] == payload['opportunities'][0]['opportunityId'].upper()


def test_pif_query_guid_is_not_assumed_to_be_an_opportunity_identity():
    guid = '8fd598d8-89f9-459a-8cfe-64d79aaf1681'
    url = PifPrivateSectorAdapter.company_url + f'?associatedcompany=Example&opportunity={{{guid}}}'
    html = '<section><h3>Visible public opportunity</h3><p>Description of Investment Opportunity: Build an industrial facility for private investors.</p><a href="/interest">Register Interest</a></section>'
    rows = PifPrivateSectorAdapter()._parse_items(BeautifulSoup(html, 'html.parser'), url, route_type='OPPORTUNITY_DETAIL')
    assert len(rows) == 1
    assert rows[0]['raw_id'] is None
    assert rows[0]['pif_opportunity_id_type'] == 'fingerprint'
    assert rows[0]['external_id'] != f'pif:{guid.upper()}'


def test_pif_annualreport_host_is_not_traversed_as_a_current_catalog_route():
    adapter = PifPrivateSectorAdapter()
    html = '<a href="https://annualreport.pif.gov.sa/en/private-sector-hub/explore-opportunities/company-opportunities/?guid=%7BD3D97E3E-8F2E-479B-AAFF-BFB8383BFA81%7D">Snapshot</a>'
    routes, _, _, _ = adapter._discover_routes(BeautifulSoup(html, 'html.parser'), adapter.url)
    assert not any('annualreport.pif.gov.sa' in url for url in routes)


def test_pif_missing_listing_markers_is_a_parser_or_route_warning():
    adapter = PifPrivateSectorAdapter()
    body = '<html><body><h1>Unexpected system maintenance</h1></body></html>'
    landing = '<html><body><h1>Explore Opportunities</h1><p>No portfolio found</p>' + ''.join(
        f'<a href="{url}">ecosystem</a>' for url in adapter.known_ecosystem_routes
    ) + f'<a href="{adapter.company_url}">Companies</a></body></html>'

    class Response:
        def __init__(self, url, text): self.url=url; self.text=text; self.status_code=200
    class Client:
        async def get(self, url, **kwargs):
            if url == adapter.sitemap_url: return Response(url, '<urlset></urlset>')
            return Response(url, landing if url == adapter.url else body)

    asyncio.run(adapter.fetch(Client()))
    assert adapter.metrics['current_listing_state'] == 'PARSER_OR_ROUTE_UNCERTAIN'
    assert adapter.metrics['technical_health'] == 'WARNING'
    assert adapter.metrics['collection_incomplete'] is True


def test_pif_generic_json_ld_page_metadata_is_not_an_opportunity():
    html = '''<script type="application/ld+json">{"@type":"WebPage","name":"Explore Opportunities","description":"Explore investment opportunities in several sectors.","url":"https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/"}</script>'''
    rows = PifPrivateSectorAdapter()._parse_items(BeautifulSoup(html, "html.parser"), PifPrivateSectorAdapter.url, route_type="AGGREGATE_LISTING")
    assert rows == []


def test_pif_same_guid_across_routes_is_one_identity_with_two_memberships():
    adapter = PifPrivateSectorAdapter()
    first_url = "https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/advanced-manufacturing-and-innovation/"
    second_url = adapter.company_url + "?associatedcompany=Company+B"
    html = '<section><h3>Shared opportunity</h3><p>Portfolio Company: Company B</p><p>Description of Investment Opportunity: Build a private manufacturing facility for regional demand.</p><a href="/interest">Register Interest</a></section>'
    first = adapter._parse_items(BeautifulSoup(html, "html.parser"), first_url, route_type="ECOSYSTEM")[0]
    second = adapter._parse_items(BeautifulSoup(html, "html.parser"), second_url, company_filter="Company B", route_type="COMPANY")[0]
    first["route_memberships"].extend(second["route_memberships"])
    assert first["external_id"] == second["external_id"]
    assert len(first["route_memberships"]) == 2


def test_pif_location_classification_happens_after_collection():
    alahsa = classify_location("Al-Ahsa", "Manufacturing facility", "Build a private production facility")
    eastern = classify_location("Eastern Province", "Manufacturing facility", "Build a private production facility")
    national = classify_location("Saudi Arabia", "Manufacturing facility", "Establish local manufacturing for national demand")
    assert alahsa[0] is True and alahsa[1] >= .85
    assert eastern[0] is False and eastern[1] == .3
    assert national[0] is False


def test_pif_route_classification_includes_public_informational_route():
    assert any(url.endswith("/tasama-business-services/") for url in PifPrivateSectorAdapter.known_informational_routes)


def test_pif_lazy_linked_second_batch_is_fetched_and_route_membership_is_kept():
    adapter = PifPrivateSectorAdapter()
    landing = '<h1>Explore Opportunities</h1><p>No portfolio found</p><a href="' + adapter.company_url + '">Companies</a><a href="company-opportunities/?associatedcompany=Company+B">Company filter</a>' + "".join(
        f'<a href="{url}">ecosystem</a>' for url in adapter.known_ecosystem_routes)
    guid = "77777777-7777-4777-8777-777777777777"
    card = f'<section data-guid="{guid}"><h3>Shared investment</h3><p>Portfolio Company: Company B</p><p>Description of Investment Opportunity: Build a private manufacturing facility for national demand.</p><a href="/interest">Register Interest</a></section>'
    second = "https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/advanced-manufacturing-and-innovation/?page=2"
    ecosystem = next(iter(adapter.known_ecosystem_routes))
    company = adapter.company_url + "?associatedcompany=Company+B"

    class Response:
        def __init__(self, url, text, status=200): self.url=url; self.text=text; self.status_code=status
    class Client:
        async def get(self, url, **kwargs):
            if url==adapter.url:return Response(url,landing)
            if url==adapter.sitemap_url:return Response(url,"<urlset></urlset>")
            if url==ecosystem:return Response(url,card+f'<a href="{second}">Next page 2</a>')
            if url==second:return Response(url,card)
            if url==company:return Response(url,card)
            return Response(url,'<html><body><h1>List of Opportunities</h1><h4>By Indicative Investment Size</h4><p>No results found</p></body></html>')

    accepted, _ = asyncio.run(adapter.fetch(Client()))
    item = next(row for row in adapter.raw_candidates if row.external_id==f"pif:{guid.upper()}")
    assert adapter.metrics["public_routes_scanned"] >= 8
    assert adapter.metrics["raw_opportunity_observations"] >= 3
    assert len(item.raw["route_memberships"]) == 3
    assert adapter.metrics["unique_public_opportunity_ids"] == 1
    assert adapter.metrics["collection_incomplete"] is False, {k:adapter.metrics[k] for k in ("pagination_routes","route_inventory","pagination_complete","source_limitations")}
    assert accepted == []  # national demand does not enter the Al-Ahsa Master path


def test_pif_blocked_or_unparseable_public_route_is_incomplete_warning():
    adapter = PifPrivateSectorAdapter()
    class Response:
        url=adapter.url; text="Cloudflare challenge"; status_code=403
    class Client:
        async def get(self, url, **kwargs): return Response()
    asyncio.run(adapter.fetch(Client()))
    assert adapter.metrics["technical_health"] == "WARNING"
    assert adapter.metrics["coverage_status"] == "PUBLIC_COVERAGE_LIMITED"
    assert adapter.metrics["collection_incomplete"] is True
    assert adapter.metrics["reconciliation_safe"] is False
    assert adapter.raw_candidates == []


def test_mwan_does_not_accept_eastern_province_as_al_ahsa():
    adapter = MwanAdapter()
    html = '''<main><h1>Investment Opportunity: Recycling Facility</h1><p>Location: Eastern Province</p><p>Develop a recycling facility for private investors.</p><a href="https://furas.momah.gov.sa/opportunity/42">Apply</a></main>'''
    row = adapter._page_item(BeautifulSoup(html, "html.parser"), "https://mwan.gov.sa/en/investment-opportunitie-42")
    assert row is not None
    assert row.raw["location_detection_method"] == "province_only_not_qualified"
    assert row.raw["location_confidence_score"] == 0.3


def test_mwan_explicit_al_ahsa_project_is_qualified_and_identity_is_stable():
    adapter = MwanAdapter()
    html = '''<main><h1>Investment Opportunity: Recycling Facility</h1><p>Location: Al-Ahsa</p><p>Develop a recycling facility for private investors.</p><a href="https://furas.momah.gov.sa/opportunity/42?type=1">Apply</a></main>'''
    url = "https://mwan.gov.sa/en/investment-opportunitie-42"
    row = adapter._page_item(BeautifulSoup(html, "html.parser"), url)
    again = adapter._page_item(BeautifulSoup(html, "html.parser"), url)
    assert row.raw["location_confidence_score"] == 1.0
    assert row.external_id == again.external_id
    assert row.raw["record_semantic_type"] == "INVESTMENT_OPPORTUNITY"


def test_mwan_aggregate_sector_content_is_not_specific_opportunity():
    adapter = MwanAdapter()
    html = '''<main><h1>Investment Opportunity: Waste Sector</h1><p>The sector offers investment opportunities worth SAR 420 billion.</p></main>'''
    row = adapter._page_item(BeautifulSoup(html, "html.parser"), "https://mwan.gov.sa/en/investment-opportunities")
    assert row.raw["record_semantic_type"] == "SECTOR_INFORMATION"
    assert row.raw["location_confidence_score"] == 0.0


def test_mwan_future_facility_without_solicitation_is_pipeline_reference():
    adapter = MwanAdapter()
    html = '''<main><h1>Future Treatment Facility</h1><p>Strategic capacity plan and investment requirements for a planned facility.</p></main>'''
    row = adapter._page_item(BeautifulSoup(html, "html.parser"), "https://mwan.gov.sa/en/future-treatment-facility")
    assert row is not None
    assert row.raw["record_semantic_type"] == "PIPELINE_REFERENCE"
    assert row.raw["record_type"] == "PIPELINE_REFERENCE"


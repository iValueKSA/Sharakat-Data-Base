# PIF Private Sector Hub route map

**Review date:** 2026-10-12  
**Scope:** Unauthenticated public Private Sector Hub → Explore Opportunities pages and current item content exposed by them. Private APIs, authenticated services, and guessed company filters are excluded.

## Public route monitoring

The adapter scans the landing page, all five current ecosystem routes, the public company-opportunities base route, linked registration routes, the Tasama information page, and any linked pagination. The final ordered sync fetched 12 public HTML pages successfully, checked the public sitemap, and reported no page errors. The five ecosystem routes and company page displayed the expected page shell and a no-results state.

| Route family | Discovered/monitored | Current visible state | Coverage implication |
|---|---:|---|---|
| Explore Opportunities landing | 1 | Listing shell; no current items exposed | Public entry route is monitored |
| Ecosystem routes | 5 | Heading, filters, and no-results marker | Empty rendered view is valid monitor evidence; does not prove zero source population |
| Company-opportunities base | 1 | Heading, filters, and no-results marker | Public company filter roster is not exposed |
| Register Interest routes | 4 | Interest/form flows | Excluded from opportunity inventory |
| Tasama route | 1 | Informational page | Excluded from opportunity inventory |

The final sync metrics report 12 successful HTML routes (the six listing pages, four interest/form routes, Tasama, and the landing page), 0 current item-bearing routes, 0 current unique opportunity IDs, 0 public company filters, 0 page errors, and no discovered pagination or Load More action.

## Live versus indexed content

Official page reads on 2026-10-12 show no opportunity cards on the tested advanced manufacturing, clean-energy, and company routes. Official search-index results for these route families include item-level titles and detail fields. Examples include passive circuit components and wiring-harness cables in Advanced Manufacturing, centrifugal pumps, flow meters, and smart water meters in Clean Energy, and several company opportunity cards. Those index results are discovery evidence only.

See [PIF live versus indexed state](../validation/pif-live-vs-indexed-state.csv) for tested URLs and states. A local direct HTTP probe in the final review returned 403, so this review did not recapture raw bodies or network traffic. Earlier successful ordinary public syncs recorded the same no-results state. No access-control bypass or crawler impersonation was used.

## Payload and parser behavior

The adapter parses semantic opportunity cards, JSON-LD, embedded JSON, and JSON-valued data attributes. An item is accepted only when current page data contains opportunity semantics; navigation, filter controls, generic page metadata, and “No results found” cannot form a record.

The current page extraction has the opportunity heading, size/demand filters, sorting/search controls, and an explicit no-results marker but no item titles or item payload. Previously saved raw HTML and script inspection found no serialized item collection or stable public item endpoint. When an expected heading and no-results marker are present, the adapter records a valid empty rendered listing. Missing or unexpected markers remain technical warnings.

## Company filters and GUIDs

The current company page does not expose an enumerable company roster. Official indexed URLs include associatedcompany filters and GUID query parameters. Those patterns have not been verified against live item payloads. GUID semantics remain UNKNOWN; a query parameter alone is not an opportunity identity. Item company attribution must come from a current item payload, not a requested filter value.

## Annualreport host

The annualreport.pif.gov.sa route returns the same opportunity page shell and filters but the tested opportunity route shows no results. It has no visible archive year or as-of date; indexed item snippets cannot be attributed safely to the query GUID. The host is classified UNKNOWN, not a current inventory and not a proven dated snapshot. It is excluded from current production ingestion.

## Coverage decision

The defined scope monitors the public landing page, all publicly discoverable ecosystem routes, the public company-opportunities route, and current public content exposed by those routes without authentication. The adapter is technically HEALTHY when the route set is fetched and recognizable. Coverage remains PUBLIC_COVERAGE_LIMITED because no deterministic current opportunity inventory or company roster is exposed. Current route monitoring does not certify an empty PIF population, and does not authorize deletion or removal reconciliation.

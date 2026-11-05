# PIF public opportunity reconciliation

**Review date:** 2026-10-12  
**Defined scope:** Monitoring of the publicly accessible PIF Private Sector Hub Explore Opportunities landing page, all publicly discoverable ecosystem routes, publicly discoverable company-opportunity routes, and current public opportunity content exposed by those routes without authentication. Authenticated surfaces and private APIs are excluded.

## Resolution

PIF is classified HEALTHY / PUBLIC_COVERAGE_LIMITED when the adapter successfully monitors the defined public routes and their expected listing markers. Current official route reads show the listing shell, filters, and “No results found”, while official PIF search-index results still expose item-level content for some known titles.

The current opportunity population is not enumerable from the supported public surfaces. The public company filter roster is not enumerable. Search-index content is discovery and historical evidence only; it is not ingested as current source records. PIF has 0 current verified opportunities from the adapter, which does not mean PIF has no opportunities.

## Live vs indexed inconsistency

The official advanced manufacturing and clean-energy ecosystem routes and company-filter routes are returned as public pages with the expected headings and filters. The current page extraction reports “No results found”; no card or item payload is present in the extracted current page content. Search-index results for the same official route families contain item-level descriptions, rationales, strategic benefits, growth drivers, investment size, addressable demand, portfolio-company names, and Register Interest actions.

The state matrix is in pif-live-vs-indexed-state.csv. The matrix separates current public page output from indexed snippets and records title-level evidence. The official direct reads used for current page state were checked on 2026-10-12. A direct request from the local PowerShell client during this final review returned HTTP 403 for PIF pages; no challenge handling or alternate identity was attempted. Earlier successful ordinary public syncs and the public page extraction both observed the no-results listing shell. The local HTTP 403 is recorded as a client/network observation; it is not evidence that PIF is globally unavailable.

### Known indexed opportunity evidence

Official indexed PIF results show, among other examples:

- Advanced Manufacturing & Innovation: “Establish local manufacturing of passive circuit components,” “Cables for Wiring Harness,” and other manufacturing opportunities.
- Clean Energy, Water & Renewables Infrastructure: centrifugal pumps, flow meters, and smart water meters.
- Company-opportunity patterns: indexed company pages contain opportunity cards and detailed fields, while the current page extraction for the tested company/GUID routes returns “No results found”.

Index crawl labels vary from current day to several months old. Those timestamps do not establish that a particular card remains active. Even when a search result is recent, the item is not considered current unless a current official public page or payload exposes it directly.

## Current DOM, HTML, and payload analysis

The official public page extraction shows the site navigation, the opportunity heading, investment-size and demand-size filters, a sort control, keyword input, and the explicit no-results marker. It shows no opportunity card titles in the current result area. Previously saved direct HTTP inspection also found no opportunity objects in the successful raw HTML, no serialized opportunity collection in embedded scripts or data attributes, and no stable public item endpoint in the inspected public script bundles.

During this final review, local direct HTTP requests returned 403, so raw response bodies and browser network traffic could not be captured again from this machine. The page reader exposed the current official page representation but is not a substitute for a packet-level network trace. This limitation is distinguished from the prior successful local crawl evidence. The adapter continues to parse semantic cards and structured JSON from any current route response if those reappear.

The title probe across rendered page, raw HTML, embedded JSON, hydration data, public network responses, and official mirror did not produce an independently verifiable current item payload. Indexed snippets were excluded from the production parser and no title from them became a SourceOpportunity.

## Annual report / snapshot analysis

The annualreport.pif.gov.sa opportunity route uses the same Private Sector Hub page shell and filters. The tested KAEC route with associatedcompany and an opportunity GUID query currently extracts as “No results found”. The indexed version includes item-level snippets, but those snippets cannot be reliably attributed to the GUID in the URL.

No visible archive year, content-as-of date, snapshot version, or statement that the opportunity cards are current was found on the tested opportunity page. The annualreport subdomain also serves current-looking PIF content and a 2017–2026 footer. The surface is therefore classified UNKNOWN, not as a current inventory and not as a proven historical snapshot. Its item snippets remain historical reference / discovery evidence only. No annualreport-hosted record is ingested.

## GUID semantics

The public patterns include ?guid={GUID} and ?associatedcompany=<company>&opportunity={GUID}. Tested GUID routes produce page headings and no-results output; the current public responses do not expose a one-to-one item payload that establishes what the GUID identifies. Search-index snippets for the same route can contain multiple cards or cards whose portfolio-company text does not align clearly with the URL filter.

GUID semantics: UNKNOWN. A query GUID is not promoted to a PIF opportunity identity. The adapter uses an ID only when a current item payload itself contains that ID; otherwise a current parsed item gets a stable content fingerprint. A requested associatedcompany value remains route context and never overrides the actual item company.

## Current population enumerability

| Measure | Result |
|---|---|
| Current public ecosystem routes monitored | 5 |
| Public company-opportunities base route monitored | 1 |
| Public company filter roster enumerable | No |
| Current item-bearing routes verified by adapter | 0 |
| Current unique opportunity items verified by adapter | 0 |
| Official indexed item content observed | Yes |
| Public listing endpoint, complete payload, or stable pagination exposed | No |
| Current public population enumerable | No |
| Al-Ahsa opportunities accepted | 0 |
| Location reviews | 0 |
| New PIF Masters | 0 |

The public item-evidence state is INDEXED_OR_HISTORICAL_ITEMS_ONLY for the current records decision. If current cards return on monitored public routes, the state changes to PUBLIC_ITEMS_VISIBLE_BUT_NOT_ENUMERABLE unless a deterministic method enumerates the full population. Coverage remains PUBLIC_COVERAGE_LIMITED until complete current enumeration is established.

## Production ingestion decision

Only directly verified current PIF public page cards or public payload items may enter PIF source observations. Search results, index snippets, and the unclassified annualreport surface cannot create current SourceOpportunity or Master rows. Current PIF parsed counts therefore remain zero. No false Al-Ahsa record is created from broad national manufacturing or portfolio-company information.

Current item cards are parsed from semantic HTML, JSON-LD, embedded JSON, and JSON-valued data attributes. The adapter distinguishes a valid rendered empty listing from a parser or route failure:

- A successful page with an expected opportunity heading, filter shell, and explicit no-results marker is NO_RESULTS.
- A successful page with current, semantically valid opportunity objects is ITEMS_VISIBLE.
- A missing or changed listing shell, unexpected page body, failed route, or malformed response remains a technical warning.

source_collection_complete remains false and reconciliation_safe remains false while the current population cannot be enumerated. Successful monitoring can nevertheless return sync SUCCESS and technical health HEALTHY, because coverage limitations are recorded separately.

## Coverage limitation

Current PIF Explore Opportunities pages are publicly accessible and monitored, but a deterministic current opportunity inventory and company roster are not exposed by the defined public routes. Official indexed/historical PIF content indicates that a broader opportunity population has existed, but those records cannot safely be treated as a complete current public population.

## Monitoring strategy

Keep the PIF adapter active. Every sync continues to scan the landing page, the five ecosystem routes, the public company-opportunities route, linked public pages, and discovered pagination without authentication. It stores route observations and explicit listing states. An expected no-results page remains a healthy monitor observation; a missing marker or unavailable route remains a technical warning.

The evidence CSV includes stable non-production title probes. If a known title or a public opportunity payload reappears in current page content, emit PIF_PUBLIC_DATA_REAPPEARED / SOURCE_COVERAGE_CHANGED and rerun reconciliation. Never create current records from an index-only title. Do not generate guessed company filters or query private endpoints.

## Cross-source and database effect

PIF creates no current Masters, location reviews, or source opportunity rows from the index-only evidence. The ten-source database total therefore remains driven by verified source content. Historical-only evidence remains outside current Master exports and source completeness counts.

## Decision

PIF source integration is technically monitored and safe for production with HEALTHY / PUBLIC_COVERAGE_LIMITED. The limitation is external source coverage, not an adapter failure. The overall program gate may close as SOURCE_INTEGRATION_COMPLETE when the final ordered sync, test suite, API checks, exports, and migration-head checks pass.

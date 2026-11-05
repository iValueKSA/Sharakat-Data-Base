# NHC public route criticality and 403 review

**Review date:** 2026-10-12  
**Production public scope:** Monitor NHC pages that describe investment categories, publicly itemized offerings when exposed, and public qualification/application pathways. Do not access authenticated investor inventories.

## Route inventory

| Route | Purpose and available content | Opportunity items / categories / qualification | Authentication boundary | Criticality | Latest NHC retry |
|---|---|---|---|---|---|
| [`https://www.nhc.sa/en/investment-opportunities/`](https://www.nhc.sa/en/investment-opportunities/) | English investment landing page. When readable, describes the NHC investor proposition and seven categories, and links qualification requirements and the application portal. | No itemized current offerings; categories and qualification CTA only. Its category content is duplicated on the Arabic page. | Public page; no login required to read it. | `SUPPORTING` — equivalent locale copy. | `SUCCESS`, HTTP 200 at 12:35:37 UTC. The ordered run had HTTP 403 at 12:27:33 UTC; the failure remains in route history and consecutive failures reset to 0. |
| [`https://www.nhc.sa/ar/investment-opportunities/`](https://www.nhc.sa/ar/investment-opportunities/) | Arabic investment landing page and canonical required category surface. | No itemized current offerings; exposes residential, commercial, mixed-use, facilities operator, retail, restaurants/cafes, and other opportunity categories, plus qualification download and application link. | Public page. | `CRITICAL` — required category surface in the NHC contract. | `SUCCESS`, HTTP 200; latest NHC retry at 12:35:37 UTC. |
| [`https://nhc.sa/en/lo/`](https://nhc.sa/en/lo/) | English Real Estate Stimulation information page: investment-enablement service, goals, solutions, and program context. | Says it supports various residential and commercial opportunities across the Kingdom, but presents no itemized public catalogue. | Its e-services link goes to an SSO sign-in boundary. Authenticated services are not accessed. | `SUPPORTING`. | `SUCCESS`, HTTP 200. |
| [`https://nhc.sa/ar/lo/`](https://nhc.sa/ar/lo/) | Arabic equivalent Real Estate Stimulation information page. | General investment-enablement information; no itemized public catalogue. | E-services link points to sign-in. | `SUPPORTING`. | `SUCCESS`, HTTP 200. |
| [`https://investment.nhc.sa/ar/investments`](https://investment.nhc.sa/ar/investments) | Public investor-intake route, rendered as the generic “Investment Platform” shell. | No itemized offerings; supports the public application path. | Public shell only. No authenticated content or private API was requested. | `SUPPORTING`. | `SUCCESS`, HTTP 200; an earlier 403 at 12:11 UTC is retained in route history. |
| [`https://investment.nhc.sa/ar/developer-qualification`](https://investment.nhc.sa/ar/developer-qualification) | Developer qualification route, rendered as the generic “Investment Platform” shell. | Qualification pathway only; no itemized offerings. The qualification requirements download is also linked from the category page. | Public shell only; no authenticated flow accessed. | `SUPPORTING`. | `SUCCESS`, HTTP 200. |

## Exact 403 route and evidence

The intermittently denied route was **`https://www.nhc.sa/en/investment-opportunities/`**. The adapter had successfully captured it earlier on 2026-10-12, including the category-page content and qualification links. The route returned 403 twice in the prior retries and again in the final ordered sync at 12:27:33 UTC. It returned 200 in the standalone sync at 12:24:37 UTC and in the latest retry at 12:35:37 UTC. The public page is indexed and readable through NHC's public web presentation; the official English and Arabic pages expose matching category content. The Opportunities navigation links to the page.

The English page describes category types and qualification/application steps. No public evidence establishes a unique current itemized opportunity inventory behind it. The equivalent Arabic route is accessible and carries the same categories and calls to action. The linked Real Estate Stimulation pages are investment-enablement information pages; they describe opportunities generally and point e-services to sign-in, but do not show a public listing catalogue. “Various investment opportunities” is not treated as an itemized inventory.

Therefore the English route is `SUPPORTING`, `route_health=ACCESS_RESTRICTED`, and `coverage_redundancy=true`. Its failure does not represent zero opportunities and cannot trigger reconciliation or removals. Its last successful `SourceContentItem` is retained. No access-control bypass, private API, or authenticated service was used.

## Current NHC result

- Technical health: `HEALTHY`.
- Coverage: `PUBLIC_COVERAGE_LIMITED`.
- The production-hardening regression sync at 13:16 UTC returned HTTP 200 for the critical Arabic category page and two supporting pages; three supporting routes returned HTTP 403. The NHC adapter recorded three route-level `SourceError` observations. Their last successful public content and route histories remain retained.
- The three denied routes were the English category mirror, English Real Estate Stimulation page, and public investor-intake shell. Their 403 responses are access/availability limitations, not evidence of an empty inventory. The required Arabic category page remained available, so technical health stayed `HEALTHY`, coverage remained `PUBLIC_COVERAGE_LIMITED`, and no parser failure or opportunity reconciliation/removal occurred.
- The prior standalone retry at 12:35 UTC had 6/6 successful routes. The intermittent difference is retained in route metrics and does not change the completeness conclusion.
- Current publicly itemized Al-Ahsa opportunities: 0 verified. This is not a claim that no assets are available.
- NHC's page provides investment categories and qualification pathways, not a complete public current inventory. Authenticated e-services remain outside scope.

Official evidence: [English investment opportunities](https://www.nhc.sa/en/investment-opportunities/), [Arabic investment opportunities](https://www.nhc.sa/ar/investment-opportunities/), [English Real Estate Stimulation](https://nhc.sa/en/lo/), and [Arabic Real Estate Stimulation](https://nhc.sa/ar/lo/).

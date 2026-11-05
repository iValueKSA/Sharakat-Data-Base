# Saudi National Source Integration Roadmap

**Updated:** 2026-11-03  
**Status:** Discovery is complete at practical saturation. This is a proposed future implementation order only. No source sync, adapter, Master, source row, Master link, business data, or geographic-filter change was made.

## Integration waves

| Wave | Priority | Source | Observed volume | Extraction path | Readiness and entry gate |
|---|---|---|---:|---|---|
| 1 | P1 | RCU Investment Opportunities | 6 | Public frontend-consumed JSON list endpoint with page/index | Ready. Preserve `displayOpportunityId`, status, dates, `canApply`, coordinates and area. Reconcile project-level NCP overlap before creating Masters. |
| 1 | P1 | NCP Investors Portal | 159 (2 pages); 2 available to submit | Public config JSON and unauthenticated paginated REST JSON list/detail API; UUID identity | Ready as a separate structured portal feed from current NCP news. Preserve UUID and lifecycle stage. Reconcile against NCP news, Invest Saudi and PIF before Master creation. |
| 1 | P1 | RCJY Investment Opportunities | 3 | Public unauthenticated OutSystems screen-services API; filterable official page | Ready as a sparse catalog. Preserve provider IDs 265/266/269; current records all Yanbu. Detail/area/status fields are sparse/default, so do not infer active status or geometry. Deduplicate against MODON, NCP, Furas and Invest Saudi. |
| 2 | P2 | Ta’adeen Mining Bids | 8 Round 11 site records; 0 currently active | Public HTML round/site detail pages and linked public files | Source is structurally ready, but Round 11 is closed and all 8 sites are inactive. Model one parent round plus 8 site children; expected site-opportunity Master count is 8 if historical records are ever ingested. Wait for a new active round for current-offer integration. |
| 3 | — | Ministry of Tourism opportunity map | Unknown | Official map advertised; application returns an external-network restriction; no records/API exposed | Restricted. No adapter proposal until the public map/API is accessible through an ordinary public route. Do not infer access from the public FAQ or marketing page. |

P1 sources: **RCU, NCP Investors Portal, RCJY**. P2 sources: **Ta’adeen Mining Bids**. P3: **none**. Wave 3 is a restriction/maintenance gate, not an integration approval.

## Existing-source repair work

These are source quality items for a separate task and do not create new source adapters:

1. **PIF hub:** configured feed stores zero rows although public PIF opportunity pages contain itemized content. Review the existing public adapter and pagination before considering separate portfolio-company feeds.
2. **Furas and AHDA counts:** Furas latest parsed count (375) and stored rows (6,546), and AHDA latest parsed count (217) and stored rows (8), are not comparable live totals. Reconcile capture semantics and freshness.
3. **MODON and NHC:** configured sources currently have no stored opportunity rows. Treat these as zero observed records until source capture is repaired and validated.

## Source identity and lifecycle gates

| Source | Provider identity | Additional implementation gate |
|---|---|---|
| RCU | `displayOpportunityId` plus raw UUID | Keep status, applicability, close flag and submission availability distinct; reconcile NCP PPP project references. |
| NCP Investors Portal | Project UUID GUID | Existing NCP feed is news announcements. Compare UUID, project details and stage against all national feeds; do not equate portal project rows to open applications (only 2 currently `isAvailableToSubmit`). |
| RCJY | Numeric record IDs 265, 266, 269; `OpportunityCode` blank | Listing shows 3 Yanbu records, while city filters also offer Jubail, Ras Al-Khair and Jazan. No coordinates, area or substantive descriptions observed; status fields are default/blank. Preserve source status as unknown. |
| Ta’adeen | Canonical site slug/URL; no separate numeric license code observed | Parent round shares one PQQ window; each child site has distinct geography, area, commodities and data-room file link. Keep all eight inactive and avoid sign-in or bid actions. |
| Ministry of Tourism | None observed | Do not implement until public records and endpoint are accessible; the Ministry FAQ is evidence of itemization, not API access. |

## Overlap and net-new handling

Three current RCJY titles had no exact match in the current Masters query. This supports **3 known title-level nonmatches**, not a guarantee of global provider-identity uniqueness. NCP's 159 UUID-bearing projects and RCU's 6 records yield **165 additional current candidates** before project-level cross-catalog reconciliation. The Tourism map count is unknown. Ta’adeen's eight Round 11 site records are inactive historical items, excluded from current-live opportunity volume. Do not add mirror records twice or create Masters before provider-ID and semantic matching.

## Evidence links

- [RCU public opportunities](https://eservices.rcu.gov.sa/opportunities)
- [NCP Investors Portal](https://investors.ncp.gov.sa/home) and its [public configuration](https://investors.ncp.gov.sa/assets/config.prod.json)
- [RCJY official investment details](https://www.rcjy.gov.sa/investment-details), [dedicated investor portal catalog](https://invest.rcjy.gov.sa/InvestmentPortal/InvestmentOpportunities)
- [Ta’adeen Mining Bids](https://cms.taadeen.sa/en/mining-bids), [Round 11](https://cms.taadeen.sa/en/mining-bids/round-11), and [Jabal Idsas site detail](https://cms.taadeen.sa/en/mining-bids/round-11/jabal-idsas)
- [Ministry of Tourism investment page](https://mt.gov.sa/tourism-investment), [official investment FAQ](https://mt.gov.sa/faq/faq-category-6)

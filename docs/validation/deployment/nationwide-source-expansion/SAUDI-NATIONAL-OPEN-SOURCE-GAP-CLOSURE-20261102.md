# Saudi National Open Source Discovery — Gap Closure

**Closure date:** 2026-11-03  
**Project:** `C:\Sharakat Data Base`  
**Scope:** Targeted follow-up on RCJY, Ministry of Tourism map, NCP Investors Portal, Ta’adeen, RCU, and remaining coverage gaps. This report does not authorize or perform source integration.

## Final status

```text
NATIONAL_OPEN_SOURCE_DISCOVERY=COMPLETE
SEARCH_SATURATION_REACHED=TRUE
EXISTING_CONFIGURED_SOURCES=11
ORGANIZATIONS_INVESTIGATED_TOTAL=105
VALID_PUBLIC_ITEMIZED_SOURCES_FOUND_TOTAL=13
NEW_VALID_UNIQUE_PUBLIC_SOURCES_TOTAL=4
NEW_READY_TO_INTEGRATE_TOTAL=4
NEW_NEEDS_TECHNICAL_INVESTIGATION_TOTAL=0
```

Count basis: 13 distinct itemized source families are counted, including eight qualifying itemized families among the configured sources, four newly identified public feeds (RCU, Ta’adeen, RCJY, NCP Investors Portal), and the Ministry map, whose itemization is confirmed but whose records remain restricted externally. Mirrors are not separate sources. “Complete” means practical source discovery converged after each remaining candidate was verified or explicitly classified as restricted; it is not mathematical completeness.

## Candidate results

### RCJY

- `RCJY_ITEMIZED_OPPORTUNITIES=TRUE`
- `RCJY_PUBLIC_RECORD_COUNT=3`
- `RCJY_STABLE_PROVIDER_ID=TRUE` — numeric provider IDs 265, 266 and 269; the separate OpportunityCode field is blank.
- `RCJY_EXTRACTION_METHOD=Public unauthenticated official Investment Opportunities page plus its frontend-consumed OutSystems screen-services POST API; public filters include investment type, sector and city.`
- `RCJY_OVERLAP_WITH_EXISTING=UNKNOWN` — exact title lookups against current Masters returned no match for the three records, but wider identity matching against all catalogs has not been done.
- `RCJY_INTEGRATION_STATUS=READY_TO_INTEGRATE`

The three public records are all Yanbu: serviced apartments (commercial/tourism), electrical transformers (industrial), and industrial/infrastructure LED fixtures (industrial). The page exposes sector/subsector and city; the observed rows have empty descriptions, blank opportunity code, zero area and default/blank status dates/flags. The UI also exposes Jubail, Ras Al-Khair and Jazan as city filters, but no current records from those cities appeared. The official homepage’s legacy “View All” route remains broken; a separate [official investment details page](https://www.rcjy.gov.sa/investment-details) links to the working [RCJY investor catalog](https://invest.rcjy.gov.sa/InvestmentPortal/InvestmentOpportunities). The public listing is sufficient for source readiness, with field sparsity and deduplication gates for implementation.

### Ministry of Tourism opportunity map

- `TOURISM_MAP_ITEMIZED_INVESTMENT_OPPORTUNITIES=TRUE`
- `TOURISM_MAP_PUBLIC_RECORD_COUNT=UNKNOWN`
- `TOURISM_MAP_EXTRACTION_METHOD=Official Ministry page promotes an interactive map; direct map application access returns an external-network restriction (HTTP 403). No public record XHR, JSON or ArcGIS endpoint was exposed.`
- `TOURISM_MAP_STABLE_PROVIDER_ID=FALSE` — no public record identity was observed.
- `TOURISM_MAP_OVERLAP=UNKNOWN`
- `TOURISM_MAP_INTEGRATION_STATUS=RESTRICTED`

The official Ministry [FAQ](https://mt.gov.sa/faq/faq-category-6) identifies real investment opportunities and says public details include description, location, status, category, activities and amenities; login is required to register interest. This is distinct from tourism statistics, attractions, hotels/facilities or generic destination information. The [investment landing page](https://mt.gov.sa/tourism-investment) advertises the map, but the map records are not externally accessible. No restrictions were bypassed.

### NCP Investors Portal

- `NCP_INVESTORS_PORTAL_PUBLIC_ACCESS=TRUE` — unauthenticated API requests succeeded; the shell/root route is inconsistent and may display a login/loading state.
- `NCP_INVESTORS_PORTAL_ITEMIZED=TRUE`
- `NCP_INVESTORS_PORTAL_RECORD_COUNT=159`
- `NCP_INVESTORS_PORTAL_RELATION_TO_EXISTING_NCP=ADDITIONAL_UNIQUE_RECORDS`
- `NCP_INVESTORS_PORTAL_INTEGRATION_STATUS=READY_TO_INTEGRATE`

The public config at [investors.ncp.gov.sa/assets/config.prod.json](https://investors.ncp.gov.sa/assets/config.prod.json) identifies an API base. The unauthenticated project pipeline returns 159 records across two pages (100 + 59), and UUID project-detail endpoints work. Records include UUIDs, bilingual names/descriptions, sector, location, contract type, stage, closing and submission-availability fields; only two were currently marked available to submit. The existing configured NCP source contains 45 news/archive records and has no exact GUID overlap with the portal UUIDs. The portal is a separate structured pipeline dataset; news updates or other national feeds may still refer to the same underlying projects and must be reconciled before Master creation.

### Ta’adeen mining bids

- `TAADEEN_RECOMMENDED_MODEL=PARENT_WITH_SITE_CHILDREN`
- `TAADEEN_SITE_LEVEL_STABLE_IDS=TRUE` — each site has a stable canonical public detail slug/URL; no separate numeric license/block ID was observed.
- `TAADEEN_EXPECTED_MASTER_COUNT=8` — one parent round grouping entity and eight site-level opportunity records if the historical round is ever represented as opportunity Masters; the parent is not a Master opportunity.
- `TAADEEN_INTEGRATION_STATUS=READY_TO_INTEGRATE` (public source and item modeling are understood; current active offer count is zero).

Each site has its own public page, location, area, mineral commodity, exploration-license type and site-specific data-room file link. The separate site pages support eight site-level license/award targets, while Round 11 uses one shared PQQ window and parent-round qualification action; separate per-site application actions were not observed. All eight show Inactive; the parent page lists the PQQ deadline as 2026-07-31, which has passed. The round's public status badge is stale/inconsistent (“Active”), so lifecycle should be taken from the inactive child rows and expired stage dates. The official [Round 11 page](https://cms.taadeen.sa/en/mining-bids/round-11) describes eight sites over 1,878 km²; [Jabal Idsas detail](https://cms.taadeen.sa/en/mining-bids/round-11/jabal-idsas) demonstrates the separate site fields. No qualification, bidding, or login action was performed.

### RCU light reconfirmation

- `RCU_INTEGRATION_STATUS=READY_TO_INTEGRATE`
- `RCU_PUBLIC_RECORD_COUNT=6`
- `RCU_STABLE_PROVIDER_ID=TRUE` — display IDs RCU-OPP-000255 through RCU-OPP-000260 (and raw UUIDs).

The [public opportunity endpoint](https://eservices.rcu.gov.sa/opportunities) remained reachable, returned itemized records, and supplied geographic fields including coordinates. This was a light currentness check; no full re-audit was performed.

## Final source grouping

### A. Already integrated — 11 configured sources

Furas; Al-Ahsa investment platform; Al-Ahsa Development Authority (AHDA); Invest Saudi; King Faisal University; MODON; NCP news/archive; National Housing Company (NHC); PIF Private Sector Hub; MWAN; Waha Development (registered but disabled). A configured source does not imply successful current capture; PIF, MODON and NHC currently have zero stored rows in the audited baseline, and Furas/AHDA count reconciliation remains open.

### B. New ready to integrate — 4

- RCU — 6 current itemized opportunities (P1).
- NCP Investors Portal — 159 UUID-identified project records; only 2 currently available to submit (P1).
- RCJY — 3 itemized Yanbu listings with numeric provider IDs; sparse status/detail fields (P1).
- Ta’adeen — 8 inactive historical Round 11 site records; no current active offers (P2; wait for a future active round for live integration).

“Ready” describes the public source and extraction path. It does not imply all records are current offers or ready for Master creation without reconciliation.

### C. Needs technical investigation — 0

All prior technical candidates now have a resolved classification. Tourism’s access boundary is classified RESTRICTED rather than left as an open technical investigation.

### D. Mirror — do not integrate separately

The register’s 14 mirror rows are: Amanat and Municipal Investment Portals; Riyadh Municipality; NCVC; Aseer Development Authority teasers; public university investment portals; MEWA; MATARAT airport PPP projects; PIF portfolio-company opportunity pages; KAEC public plot pages; MIM general mining-license/geological pages; regional development authorities; other Royal Commissions; PIF development companies; and the broader local-authority/development-entity sweep. These resolve to Furas, NCP, PIF, or non-opportunity context already represented; preserve issuer attribution and deduplicate within existing source families.

### E. Not itemized

The six register rows classified NOT_ITEMIZED are: SPARK investor process; Mawani port-property leasing framework; Saudi Water Authority localization announcement; transport/port/airport operator pages; economic cities and special economic zones; and additional ministry/sector-authority pages. MODON and NHC are configured sources with zero stored rows in the audited baseline. These pages may describe investment pathways, service frameworks, strategies or assets without publishing actionable record-level offers.

### F. Not investment

The three register rows classified NOT_INVESTMENT_OPPORTUNITY are Etimad government procurement and the public-development-fund financing rows (public-funds financing and funding entities). This includes loans, grants, guarantees and financing products; ordinary procurement, supply, consulting and construction tenders are excluded from investable asset records. Tourism statistics/destination promotion, licensing services and general geological datasets are also not opportunity records.

### G. Restricted / broken

- Ministry of Tourism map: itemized opportunity platform confirmed, but map records/API are blocked from the external network (HTTP 403); no bypass attempted.
- TBC/EISC and public school/university asset-investment listings: the two register entries refer to login-gated education-asset systems; no login or bypass attempted.
- RCJY legacy homepage “View All” route: broken/404, but superseded operationally by the separate public investor portal catalog (therefore RCJY itself belongs in group B).
## Integration waves

- **Wave 1 (P1):** RCU, NCP Investors Portal, RCJY. Favor stable IDs and public structured fields; hold Master creation behind cross-source deduplication. RCJY requires explicit handling of blank/default status and zero area.
- **Wave 2 (P2):** Ta’adeen. Model one parent round plus eight independent site children. Current Round 11 is closed; wait for a new active round if only current actionable offers are wanted.
- **Wave 3:** no source adapter approved. Tourism remains restricted. Address existing PIF coverage repair and Furas/AHDA count reconciliation as separate maintenance work; do not add mirror adapters.

## Net-new estimate and controls

```text
KNOWN_NET_NEW_OPPORTUNITIES=3
POTENTIAL_ADDITIONAL_OPPORTUNITIES=RANGE: 0–165 further RCU/NCP candidates after dedupe, plus unknown Tourism volume
UNKNOWN_VOLUME_SOURCES=1
P1_SOURCES=[RCU, NCP Investors Portal, RCJY]
P2_SOURCES=[Ta’adeen Mining Bids]
P3_SOURCES=[]
MANUAL_SOURCE_SYNCS=0
NEW_SOURCE_ADAPTERS=0
SOURCEOPPORTUNITY_CHANGES=0
NEW_MASTERS_CREATED=0
MASTER_LINK_CHANGES=0
BUSINESS_DATA_CHANGES=0
GEOGRAPHIC_FILTER_CHANGES=0
```

The 3 known records are the three RCJY title searches with zero current-Master matches. The 165 remaining current records are RCU (6) plus NCP portal (159); actual additional unique Master count may range from zero to 165 after cross-catalog reconciliation. Tourism has an unknown number of inaccessible records. Ta’adeen’s eight inactive records are historical and excluded from current net-new live volume. Mirrors are never added twice.

## Targeted saturation and change boundary

All 13 regions and 20 sectors remain covered by the original sweep of 105 organizations. Targeted follow-up closed the RCJY and NCP endpoint gaps, reconfirmed RCU, examined Ta’adeen lifecycle/modeling, and classified Tourism as restricted. Remaining targeted results resolve to reviewed feeds, mirrors, procurement, non-itemized or restricted channels. Therefore `SEARCH_SATURATION_REACHED=TRUE` and `NATIONAL_OPEN_SOURCE_DISCOVERY=COMPLETE` in the practical, non-mathematical sense.

`MANUAL_SOURCE_SYNCS=0`; `NEW_SOURCE_ADAPTERS=0`; `SOURCEOPPORTUNITY_CHANGES=0`; `NEW_MASTERS_CREATED=0`; `MASTER_LINK_CHANGES=0`; `BUSINESS_DATA_CHANGES=0`; `GEOGRAPHIC_FILTER_CHANGES=0`. No live source or geographic configuration was changed.

## Evidence references

- [RCJY official investment-details page](https://www.rcjy.gov.sa/investment-details) and [public investor catalog](https://invest.rcjy.gov.sa/InvestmentPortal/InvestmentOpportunities)
- [Ministry of Tourism investment page](https://mt.gov.sa/tourism-investment) and [official investment opportunities FAQ](https://mt.gov.sa/faq/faq-category-6)
- [NCP Investors Portal](https://investors.ncp.gov.sa/home) and [public runtime config](https://investors.ncp.gov.sa/assets/config.prod.json)
- [Ta’adeen Mining Bids](https://cms.taadeen.sa/en/mining-bids), [Round 11 detail](https://cms.taadeen.sa/en/mining-bids/round-11), and [Jabal Idsas](https://cms.taadeen.sa/en/mining-bids/round-11/jabal-idsas)
- [RCU public opportunities](https://eservices.rcu.gov.sa/opportunities)




## Current closure update — 2026-11-03

> **Authoritative follow-up:** This targeted closure supersedes the earlier partial classification and candidate findings below. No geographic filters, source integrations, source rows, Masters, links, or business data were changed. See `SAUDI-NATIONAL-OPEN-SOURCE-GAP-CLOSURE-20261102.md` for field-by-field results and grouped inventory.
>
> **Current status: COMPLETE; practical search saturation: TRUE.** RCJY's dedicated investor portal and NCP's unauthenticated structured API are publicly itemized. The Ministry of Tourism's FAQ confirms itemized opportunity details, but its map endpoint blocks the external network and is classified RESTRICTED. Ta’adeen Round 11 has eight individually detailed site records, all inactive after the 2026-07-31 PQQ deadline. RCU remains publicly available with six records.
>
> **Current counts:** 11 configured sources; 105 organizations investigated; 13 valid public itemized source families including existing sources (7 qualifying configured families, 4 newly identified feeds, and the restricted-but-itemized Tourism map); 4 new unique public feeds; 4 ready-to-integrate source definitions; 0 unresolved technical-investigation candidates. “Ready” describes public source/extraction readiness; Ta’adeen currently has 0 active offers. Three RCJY titles have no exact current-Master title match. RCU (6) and NCP (159) add up to 165 further candidate records pending cross-catalog identity reconciliation. Tourism's public record count remains unknown.
>
> **Net-new count rule:** Known net-new = 3 RCJY records with zero exact current-Master title search results. Potential additional = 0–165 further RCU/NCP candidates after deduplication, plus an unknown number from the restricted Tourism map; 8 Ta’adeen Round 11 sites are inactive historical records and are excluded from current-live counts. This is a conservative evidence-based estimate, not a claim that title search replaces provider-ID reconciliation.
>
> **No-live-change controls:** manual syncs 0; new adapters 0; SourceOpportunity changes 0; new Masters 0; Master-link changes 0; business-data changes 0; geographic-filter changes 0.

# Saudi Arabia — National Open Investment Source Discovery

**Audit date:** 2026-11-02  
**Scope:** Public-source discovery and coverage audit only  
**Baseline outcome:** `PARTIAL` on 2026-11-02. The targeted follow-up dated 2026-11-03 supersedes that status with `COMPLETE` under practical saturation; the Tourism map remains restricted and its count unknown.

## Executive summary — original baseline (superseded by current closure update above)

The actual configured registry contains **11 sources**. The database currently has **6,623 canonical Masters** and **9,290 raw SourceOpportunity rows** across seven sources; these are different measures. The last job counts and source-row totals do not reconcile one-to-one (notably Furas 375 latest parsed vs 6,546 stored source rows; AHDA 217 latest vs 8 stored source rows). This report preserves both measures and does not treat a historical stored-row count as a live public-catalogue total.

The practical search found **two new, unique, publicly itemized sources ready for future integration**:

1. **Ta’adeen mining bids** — public HTML listing/detail pages and downloadable round brochures; Round 11 is active and describes eight exploration sites over multiple regions. The listing contains two currently active cards, one of which is a plan rather than a bid round. Preferred discovery is public HTML plus linked public documents; coordinates and site-level provider IDs were not confirmed.
2. **Royal Commission for AlUla (RCU)** — a public frontend-consumed JSON endpoint returned six applicable records with stable `RCU-OPP-000255` through `RCU-OPP-000260` IDs, status, dates, category, description, area, and latitude/longitude. These are distinct local PPP opportunities; NCP is cited as the privatization-plan authority, but the RCU catalogue is a separate issuer feed.

Three additional unique-source investigations are not ready for integration: **RCJY** (five itemized homepage teaser cards; the “View All” route was 404 and teaser detail links were empty), **the Ministry of Tourism investment map** (official FAQ confirms public opportunity details, but the page returned HTTP 500 during direct retrieval), and **the NCP Investors Portal** (official portal advertised, but a stable unauthenticated current itemized list/total was not confirmed). These are `NEEDS_TECHNICAL_INVESTIGATION`, not approvals to bypass login or access controls.

Municipal and many institutional records are already consolidated through Furas. Amanah/entity landing pages, university channels, environmental investment listings and some authority records explicitly route opportunities through Furas; these are mirrors unless a distinct public record set or material fields are demonstrated. Riyadh Municipality's public guidance says users should filter the Foras portal by Riyadh Municipality to see its opportunities. NCVC describes 2,500+ potential sites and 17+ opportunity types but says it publishes through Foras; that is not 2,500 verified active, itemized offers.

## Registry audit (read-only)

Registry inspected from the configured application database on 2026-11-02. “Latest parsed” is the most recent job's count where available. “Stored raw rows” is the present SourceOpportunity count for that source. Schedule status is the configured enabled flag and polling interval; it does not imply current extraction success.

| Key | Name / organization | Scope & implementation | Enabled / interval | Latest parsed | Stored raw rows | Assessment |
|---|---|---|---|---:|---:|---|
| `furas` | فرص — Ministry of Municipalities and Housing / participating entities | National municipal/real-estate; public ArcGIS REST through official catalogue proxy | yes / 60 min | 375 (warning) | 6,546 | Integrated; national breadth, count reconciliation warning |
| `alahsa-opportunities` | Al-Ahsa investment platform / Amanat Al-Ahsa | Local; server-rendered HTML cards | yes / 60 min | 104 | 123 | Integrated, itemized local source |
| `ahda` | هيئة تطوير الأحساء / AHDA | Al-Ahsa/Eastern; sitemap + HTML | yes / 360 min | 217 | 8 | Integrated; latest/stored count mismatch needs reconciliation |
| `invest-saudi` | Invest Saudi / Ministry of Investment | National, cross-sector; public paginated JSON API | yes / 360 min | 2,297 | 2,555 | Integrated; national investor-opportunity catalog |
| `kfu` | King Faisal University | Al-Ahsa/Eastern; official announcement page and qualifying PDFs/HTML | yes / 720 min | 2 | 6 | Integrated; small university asset feed |
| `modon` | MODON / Saudi Authority for Industrial Cities and Technology Zones | National industrial; public catalog/product/news/GIS surfaces | yes / 360 min | 0 (failed latest) | 0 | Integrated configuration, no currently stored itemized offers |
| `ncp` | National Center for Privatization & PPP | National PSP/PPP; public SharePoint news archives/articles | yes / 720 min | 46 | 45 | Integrated announcements; does not prove investor-portal completeness |
| `nhc` | National Housing Company | National housing/real estate; public investment/qualification pages | yes / 720 min | 0 (parser warning) | 0 | Integrated configuration, no currently stored itemized offers |
| `pif` | PIF Private Sector Hub | National/portfolio; public portfolio and company opportunity pages | yes / 1,440 min | 0 | 0 | Integrated config is under-capturing public itemized hub content |
| `mwan` | National Center for Waste Management / موان | National waste; public listing/detail cards | yes / 1,440 min | 8 | 7 | Integrated, itemized sector source |
| `waha-development` | Waha Development | Al-Ahsa local; public pages/GIS locations, no itemized opportunity adapter | no / 1,440 min | none | 0 | Registered but disabled; no current public itemized offers identified |

Latest successful sync timestamps and detailed method/health values are in the JSON register. No sync was initiated for this audit.

## New source decisions — original baseline (superseded by current closure update above)

| Source | Classification | Public count | Priority | Duplication expectation | Decision |
|---|---|---:|---|---|---|
| Ta’adeen Mining Bids | `READY_TO_INTEGRATE` | 2 active listing cards (1 plan + 1 active round); Round 11 covers 8 sites | P2 | Low vs Furas/Invest Saudi/NCP/MODON/PIF/NHC/MWAN | Prepare a separate mining adapter proposal after normal source governance and page-level record modeling |
| RCU Investment Opportunities | `READY_TO_INTEGRATE` | 6 current applicable records observed | P1 | Low | Public JSON API includes stable display IDs, dates, descriptions, geolocation and PPP fields; suitable for direct adapter design |
| RCJY | `NEEDS_TECHNICAL_INVESTIGATION` | 5 homepage cards; full catalogue unknown | P2 candidate | Medium vs MODON/NCP; unique commercial and industrial items likely | Revisit after the official list/detail route is repaired or an openly documented public feed is identified |
| Ministry of Tourism interactive map | `NEEDS_TECHNICAL_INVESTIGATION` | Unknown | P2 candidate | Medium vs PIF/Invest Saudi | Official FAQ confirms public item-level description/location/status/category/activities/amenities; public map page currently returns HTTP 500 |
| NCP Investors Portal | `NEEDS_TECHNICAL_INVESTIGATION` | Unknown; NCP site advertises hundreds overall | P1 candidate | High vs NCP news | Existing NCP integration scrapes news, not the separate investor portal. Reassess only public unauthenticated list endpoints |

“P1” on RCU reflects high-value, unique, stable API data with precise geography; the six-record volume is modest. Ta’adeen is P2 because there is one active round with eight sites and the public detail is primarily HTML/documents. No new adapters were created.

## Geographic coverage: all 13 regions

The region sweep looked for emirate, Amanah/municipal, development-authority, university, and regional-company opportunity channels. Furas is the nationwide baseline. The public Furas provider directory and entity filters cover authorities and universities; several named authorities explicitly state that live municipal opportunities are placed on Furas. Direct portals were not treated as new feeds without unique public records.

| Region | Existing integrated coverage | New unique source found | Ready unique local source | Coverage gap |
|---|---|---|---|---|
| Riyadh | Furas, Invest Saudi, NCP, PIF, MODON, NHC, MWAN | NCP airport PPP project announcements; PIF hub items | No new local feed | Airport/land/concession details split between NCP/PIF and Furas; separate Riyadh Airports catalog not found |
| Makkah | National integrations; Furas includes Jeddah/Makkah municipal offers | PIF hub company items (e.g. Jeddah Central); NCP PPP announcements | No new local feed | Municipal content is mainly Furas; developer-specific open catalogs vary |
| Madinah | National integrations; Furas; KFU is not in this region | RCU AlUla | **Yes — RCU** | RCU has six active/applicable entries; other authority-specific open catalogs not confirmed |
| Eastern Province | Furas, Al-Ahsa platform, AHDA, KFU, MODON, MWAN, NCP, PIF | Ta’adeen is nationwide; Eastern Region Development Authority records appear in Furas | Existing integrated Al-Ahsa/AHDA source | Strongest local breadth; determine whether RCJY has a usable public item feed |
| Qassim | Furas and national sources | NCP/Matarat airport PPP announcements | No new local feed | NCP project data is announcement/portal driven |
| Asir | Furas and national sources | ASDA teaser PDFs; PIF Soudah items | No new feed; teasers point back to Furas | Current offer status of archived PDFs unknown |
| Tabuk | Furas, national Invest Saudi/PIF | PIF includes NEOM/Red Sea-related opportunities; Ta’adeen multi-region | No new local feed | Developer-owned portals often lack open itemized catalogs |
| Hail | Furas and national sources | PIF ASFAR opportunity card | No new local feed | ASFAR card links to PIF record; no separate source |
| Northern Borders | Furas and national sources | No unique local catalog confirmed | No | No direct/local public itemized source found beyond national platforms |
| Jazan | Furas, national sources; RCJY/Jazan industrial city official relationship | RCJY teaser cards; Ta’adeen multi-region | No new local feed | RCJY public item details unavailable; direct separate offer catalog not confirmed |
| Najran | Furas and national sources | No unique local catalog confirmed | No | No direct/local public itemized source found beyond national platforms |
| Al-Baha | Furas and national sources | No unique local catalog confirmed | No | No direct/local public itemized source found beyond national platforms |
| Al-Jouf | Furas and national sources | No unique local catalog confirmed | No | No direct/local public itemized source found beyond national platforms |

This is public-source coverage, not a statement that all regions have equivalent opportunity volume. By the report's rule, **2 regions have direct/local unique public itemized sources when existing integrated local sources are included** (Eastern Province via Al-Ahsa/AHDA; Madinah via RCU). Only Madinah contributes a newly discovered ready source. Every region has a national platform baseline, but seven regions have no distinct direct/local source confirmed in this sweep.

## Sector coverage

| Sector | Integrated source(s) / public evidence | New candidates | Known gap |
|---|---|---|---|
| Municipal / real estate | Furas; Al-Ahsa platform; AHDA; NHC (currently zero rows) | Riyadh Municipality and other Amanat pages are Furas mirrors | Completeness and distinction between active bidding and asset-map inventory |
| Industrial | MODON (zero rows); Invest Saudi; PIF; Furas; RCJY teaser page | RCJY investigation | MODON/RCJY public-feed coverage and current offer statuses |
| Mining | Invest Saudi / PIF opportunity content, public Ta’adeen not integrated | Ta’adeen | Site-level bid/round fields and geometry normalization |
| Tourism | Invest Saudi, PIF; Furas; tourism platform item detail promised publicly | Ministry of Tourism map investigation | Map currently errors; direct count and open endpoint unknown |
| PPP / privatization | NCP announcement archive; Invest Saudi; PIF; RCU | NCP portal investigation; RCU ready | NCP investor portal current public record access; announcement archive is not a normalized live catalog |
| Transport | NCP PPP news, Invest Saudi, PIF, RCU | RCU airport PPP records | Airport operators' commercial concessions are not consistently public/itemized |
| Logistics | Invest Saudi, PIF, MODON, RCU | RCJY investigation | Direct port/airport logistics opportunity lists sparse |
| Ports | NCP/Invest Saudi; Mawani leasing framework; PIF | None validated outside existing feeds | Mawani public evidence describes leasing process, not current itemized assets |
| Airports | NCP announcements; RCU airport entry; PIF | RCU ready | Airport-specific concession pages not found across operators |
| Water | MEWA routes current opportunities to Furas; Invest Saudi/PIF; RCU; Saudi Water Authority announcement | RCU ready | SWA announced 18 opportunities in a news release; no itemized catalog confirmed |
| Waste | MWAN; RCU PPP; Furas | RCU ready | MWAN seven stored records; confirm item currency/status |
| Agriculture | Furas/MEWA; Invest Saudi; PIF | None validated | Ministry of Agriculture's open current catalog routes through Furas |
| Energy | Invest Saudi and PIF; NCP project notices | None validated | SPARK offers investor-request process/categories, no itemized public plots; renewable procurements excluded |
| Healthcare | Furas; Invest Saudi; PIF; NCP project announcements | None validated | Ministry/health-cluster opportunities commonly appear in Furas or NCP; no separate open inventory confirmed |
| Education | KFU; Furas university publishers | Restricted TBC/EISC route; university portals mostly Furas | Public catalog vs login boundary; no unique feed beyond KFU confirmed |
| Culture | Furas; PIF development company content | None validated | No independent itemized public source confirmed |
| Sports | Furas; PIF content | None validated | No independent itemized public source confirmed |
| Urban development | Furas, Invest Saudi, PIF, NHC, AHDA, RCU | RCU ready | Developer pages mostly marketing/EOI or PIF mirrors |
| Hospitality | Invest Saudi, PIF, Ministry of Tourism (map investigation), RCU | Tourism map investigation | Current source count from the map unknown |
| Commercial / retail | Furas, PIF, RCU, Al-Ahsa platform | RCJY investigation | Detail booklets can require account after public listing; don't ingest private bid content |

## Important classifications and overlap controls

- **Furas is the central municipal/real-estate opportunity publisher.** Its public agency dropdown spans ministries, regional authorities, government-owned companies, and universities. Riyadh Municipality instructs users to filter the Furas portal for its listings. Entity pages or regional map views are mirrors until distinct IDs or unique fields are demonstrated.
- **MEWA** explicitly directs investors to current opportunities through Furas. Its proposal intake form is not a public itemized source.
- **NCVC** describes potential sites and opportunity types, and says investment entities publish offers through Foras. Its “2,500+ sites” is a site inventory claim, not active listing count.
- **RCJY**: official terms describe public bidding/expression-of-interest service, and MyGov says investors browse the list and view details before account-based bid submission. However the current public homepage displayed five teaser cards with empty “Read More” links and “View All” resolved to 404. Previously probed Liferay headless routes returned 403; no access controls were bypassed. Stable public provider IDs, complete public list and public API remain unconfirmed.
- **Ta’adeen** is not general geology: its active Round 11 page describes eight specific exploration sites and links to the round brochure. The mining auction/competition pages are relevant; geological datasets and ordinary service/license workflow pages are not.
- **PIF portfolio companies** (RSG, JCDC, Soudah, AlUla Development, ASFAR, NEOM, NWC, Ma’aden and others) are reflected in the PIF hub. The PIF configured adapter has zero stored rows despite publicly indexed itemized opportunity category pages, so that is an existing-source coverage defect, not a reason to add duplicate company adapters without a unique direct feed.
- **NCP vs procurement:** only PPP, concession, long-term asset development, BOT/DBFOM and investment competitions qualify. Ordinary Etimad/RFQ/supply/consulting/construction tenders are excluded. NCP news includes project-level PPP announcements; the separate Investors Portal needs public-access review.
- **Funds:** TDF, SIDF, Agricultural Development Fund, Cultural Development Fund and NDF materials predominantly describe financing products or capital programs, not an open itemized third-party asset investment list; classify those content types `NOT_INVESTMENT_OPPORTUNITY`.

## Search saturation and limitations

**Search saturation reached: TRUE (practical, not mathematical).** The sweep covered all 13 regions, central ministries and authorities, regional development bodies and Amanat, universities, Royal Commissions, economic/special zones, major public development companies, PIF portfolio pages, PPP/ports/airports/water/mining/environment, and public funds. Follow-up search permutations across these groups mostly returned already-reviewed Furas/NCP/Invest Saudi/PIF channels, Furas mirrors, investor marketing pages, financing, procurement, or restricted/private portals. Distinct sources found late in the sweep were Ta’adeen, RCU, the Tourism map and the RCJY/NCP technical-investigation candidates.

The audit is **PARTIAL** because the official Tourism map route returns HTTP 500, RCJY public detail links are broken, NCP investor portal current public data was not verified, and direct records on some operator portals could not be confirmed. No inaccessible endpoint was treated as public. The source register classifies each material portal/organization examined. Search logs, source links, methods, field availability and row classifications are in the JSON/CSV artifacts.

## Change boundary

`MANUAL_SOURCE_SYNCS=0`; `NEW_SOURCE_ADAPTERS=0`; `NEW_MASTERS_CREATED=0`; `SOURCEOPPORTUNITY_CHANGES=0`; `MASTER_LINK_CHANGES=0`; no UI/map flag was changed. The only additions are these four discovery documents.

## Evidence links

- Furas platform and agency listings: [Furas](https://furas.momah.gov.sa/en), [official Riyadh Municipality Furas instructions](https://alriyadh.gov.sa/en/new/investment-opportunities), [MyGov Furas description](https://my.gov.sa/content/investing)
- MISA: [Invest Saudi sectors / opportunity catalog](https://investsaudi.sa/sectors/water?sectorId=water)
- NCP: [NCP homepage / Investors Portal reference](https://www.ncp.gov.sa/), [Qassim airport PPP EOI](https://ncp.gov.sa/en/MediaCenter/News/Pages/PNA-Airport-Qassim.aspx)
- RCU: [public investment opportunities](https://eservices.rcu.gov.sa/opportunities)
- RCJY: [public portal teaser cards](https://www.rcjy.gov.sa/en/web/guest), [RCJY public bidding service](https://my.gov.sa/en/services/323803), [RCJY portal terms](https://www.rcjy.gov.sa/en/terms-and-conditions)
- Ta’adeen: [Mining Bids](https://cms.taadeen.sa/en/mining-bids), [Round 11](https://cms.taadeen.sa/en/mining-bids/round-11)
- Tourism: [Ministry Tourism Investment](https://mt.gov.sa/tourism-investment), [official FAQ on public opportunity details](https://mt.gov.sa/faq/faq-category-6)
- Environment/water: [MEWA investment opportunities](https://www.mewa.gov.sa/en/Ministry/InvestmentOpportunities/Pages/default.aspx), [NCVC investment opportunities](https://ncvc.gov.sa/en/opportunities/Pages/default.aspx), [Saudi Water Authority announcement (18 opportunities)](https://www.spa.gov.sa/en/N2618510)
- Industrial/economic zones: [SPARK investment process](https://www.spark.sa/page/Become_an_Investor), [KAEC current land opportunities](https://www.kaec.net/invest/)
- Universities: [Majma’ah University Furas platform](https://www.mu.edu.sa/en/achievement/investment-opportunities-platform), [Ministry of Education educational investment service](https://www.moe.gov.sa/en/knowledgecenter/eservices/pages/estithmar.aspx)
- PIF: [Private Sector Hub](https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/), [Tourism opportunities](https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/tourism-travel-and-entertainment/), [Industrial and logistics opportunities](https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/industrials-and-logistics/)




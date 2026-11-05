# Public source nationwide expansion plan

**Date:** 2026-11-01 (Asia/Amman)  
**Status:** Audit and plan completed before any source ingestion. No production writes, source syncs, migrations, promotions, or feature-flag changes were performed for this task before this plan was created.  
**Production snapshot:** read-only query of `alahsa-local-api-1`; current deployed revision remains 0023 and lifecycle-fix API/worker/beat images remain deployed.

## Decision

Proceed with a controlled, one-source-at-a-time expansion using only public official surfaces. No external licensing/permission response is a rollout prerequisite. Public technical access, source identity, completeness, idempotency, safe reconciliation, and data quality remain required gates. Preserve raw source geography and only normalize exact known aliases or explicit source hierarchy. Do not infer geography or coordinates from titles, owners, or centroids.

The current production source inventory is 11 configured records (10 enabled; Waha disabled). Snapshot totals: **3,180 SourceOpportunity rows**, **587 Master rows / 566 current unmerged Masters**, **671 sync jobs**, and **0 active jobs**. Existing Invest Saudi rows are **2,555**, of which **19** are linked to Masters. Source row counts are the current persisted inventory, not estimates of what a national scan will return. Zero persisted rows is not evidence that the official source has no opportunity content.

## A. Audit of all configured sources

| Source | Current public collection scope / extraction | Nationwide capability and current limits | Snapshot rows (linked) | Assessment |
|---|---|---|---:|---|
| Furas | Official public ArcGIS catalogue proxy; counts, enumerates stable IDs, fetches 100-ID batches; checks every returned page against expected IDs. `FURAS_NATIONAL_ENUMERATION_ENABLED=false` currently inserts the verified Al-Ahsa CITY_ID filter. | The official portal describes itself as a national database for municipal and real-estate opportunities across regions. Adapter already has `SAUDI_NATIONAL_V1`; broad enumeration must stay distinct from Master eligibility and removal scope. | 436 (436) | **Priority 1.** National-capable; a read-only isolated public scan returned 6,494 unique IDs in 67/67 successful requests on 2026-11-01, with counts, IDs, and pages equal and `pagination_complete=true`. Existing-row overlap was not measured; at most 6,058 IDs are incremental. Keep production national flag off until DB identity/dry-run and removal-safety checks pass. |
| Al-Ahsa Investment Platform | Server-rendered HTML cards from `alahsa-opportunities.com`. | Explicitly Al-Ahsa-only platform; no national expansion to perform. | 123 (123) | **Local-only.** Retain as Al-Ahsa coverage and preserve all links/identities. |
| AHDA | Sitemap discovery plus server-rendered official HTML. | Regional-authority publication scope for Al-Ahsa/Eastern Region matters; it is not a national inventory. Public pages can be monitored only within their defined scope. | 8 (8) | **Regional/local scope.** Keep; do not mislabel as national-complete. |
| Invest Saudi | Public paginated JSON endpoints for opportunities, investment projects, PIF and regional opportunity families; endpoint totals/pages are checked. Existing rows already include nationwide records. | Nationwide-capable. Current linking/eligibility policy is Al-Ahsa-oriented in places; national eligibility must be reevaluated against each record's own published location. Reuse all 2,555 SourceOpportunity identities; do not re-create them or mass-promote. | 2,555 (19) | **Priority 2.** Reassess existing rows via dry-run; promote only explicit, itemized, identifiable opportunities after qualification and duplicate checks. |
| King Faisal University | Official university investment announcements / asset qualification pages. | Own institutional assets only; not a national cross-sector inventory. | 6 (3) | **Local/institutional scope.** Retain only itemized university offerings; no national scope assertion. |
| MODON | Public catalog/product/news pages and public GIS schema; adapter reports incomplete public live inventory. No private API access. | Industrial cities span multiple regions, but the current public product catalogue does not establish a complete itemized opportunity population. GIS/site catalogues are not opportunities by themselves. | 0 (0) | **Priority 3 after public item inventory verification.** Expand only itemized published offers, with source-supported site/city, stable identity, and full public paging. Zero records is not zero opportunities. |
| NCP | Paginated public Arabic/English News archives and linked articles. | Current adapter is complete only for the public news-archive scope, not the broader PPP/private-sector pipeline. NCP’s public site describes an investor portal and project pipeline; investor-portal detail/access must be tested without login. Do not scrape authenticated investor records. | 45 (2) | **Priority 4 conditional.** Keep news scope as announcements; add public project records only if an unauthenticated public listing has enumerable itemized projects and stable IDs. Otherwise document restricted/inaccessible scope and skip it. |
| NHC | Public investment, qualification, and stimulation pages; authenticated e-services excluded. | Current public pages describe opportunity categories and application paths, rather than enumerable live item-level opportunities. | 0 (0) | **Not eligible for opportunity ingestion today.** Continue coverage monitoring. Add records only when public item-level inventory appears. |
| PIF Private Sector Hub | Public ecosystem and portfolio-company opportunity pages, requiring item-level/company/location validation. | Nationally relevant public opportunity families exist, but the configured collector currently has no accepted persisted records. Do not promote general sector pages, strategy, or portfolio projects without explicit private-sector offer identity. | 0 (0) | **Priority 5 conditional.** Audit public itemized detail pages and exact IDs; keep existing source identity if records become collectible. |
| MWAN | Public investment opportunity listing, linked project details, public investor cards; licensed-company directories and sector statistics excluded. | Itemized opportunity concept is present; current notes/qualification are Al-Ahsa-specific. Expand to any published Saudi location only when explicit location is on the opportunity; keep unspecified locations unassigned. | 7 (0) | **Priority 6.** National eligibility expansion after isolated per-record location and identity review. |
| Waha Development | Official public pages; public map/GIS reference describes locations, but no opportunity adapter. Public opportunity page currently has no itemized offers; investment-flow details require account access. | Catalog/location features lack opportunity ID, offer terms, or public application detail. The conflicting historical 84-feature file is not a current inventory. Waha is disabled and absent from `ADAPTERS`. | 0 (0) | **Not an opportunity source today.** Leave disabled; do not convert sites or empty lots into opportunities. Reassess only if public itemized offers appear. |

The registry is truth for enabled state, health, last success, and current counts. At the snapshot, Furas and Al-Ahsa had successful post-lifecycle-fix jobs **671** and **670**; the latest Furas scan remained the local scope because the national flag was false. Invest Saudi job 667 was also successful. These are existing scheduled jobs, not manual expansion runs in this task.

## B. Existing sources that can expand nationally

1. **Furas:** already has a bounded national enumeration path and stable source IDs. Validate total-count/ID/page equality, resume/checkpoint approach, bounded requests, retry behavior, and scope-aware reconciliation in isolation. Preserve all three concepts independently: `SOURCE_ENUMERATION_SCOPE`, `MASTER_GEOGRAPHIC_ELIGIBILITY`, and `REMOVAL_RECONCILIATION_SCOPE`.
2. **Invest Saudi:** national JSON inventory is already persisted. Dry-run a new eligibility assessment against all existing rows, preserving source IDs, provenance, and unlinked rows. Never create all source rows as Masters by default.
3. **MODON:** national geography is plausible, but only verified public itemized offers count. Audit open routes and catalogue behavior first.
4. **NCP:** potentially national project announcements; current extraction is news-only. A public landing page alone is insufficient evidence that all pipeline items are anonymously enumerable.
5. **PIF:** public opportunities are national, but each detail record must be identified as an actual private-sector offer, not a sector thesis or generic project.
6. **MWAN:** expand accepted geography nationally when the specific opportunity’s public listing/detail names a Saudi location. Keep raw location; unresolved values become unspecified/review.

Al-Ahsa platform, AHDA, and KFU remain institutionally/regionally scoped. NHC and Waha remain page-monitoring/catalog-only until they publicly expose itemized offers.

## C. New official public source discovered

### Royal Commission for Jubail and Yanbu (RCJY) public Investment Opportunities

- Official site: <https://www.rcjy.gov.sa/en/web/guest>
- Public entry/listing: <https://www.rcjy.gov.sa/en/web/guest> (anonymous homepage currently exposes five itemized cards with title and city labels; card HTML has `data-analytics-asset-id`, but the “Read More” hrefs are empty).
- Public service/terms page: <https://www.rcjy.gov.sa/en/terms-and-conditions> describes public bidding and expression-of-intent services for its Investment Opportunities Portal.
- Scope: RCJY cities/industrial cities, not nationwide. It is a new regional source that increases source coverage in the locations it serves.
- Status: **discovered, not integrated**. The homepage’s “View All” links to `https://www.rcjy.gov.sa/investment-opportunities`, which returned HTTP 404 during an anonymous request; observed card detail anchors are empty. The five cards prove itemized public content exists but not complete enumeration or a stable identity contract. Do not ingest until RCJY exposes a complete public listing/detail surface. Do not use a login-only Yaseer e-service.
- Volume estimate: **unknown**; five homepage cards are a partial page, not a verified total. A missing listing is not evidence of zero opportunities.

Other official surfaces reviewed:

- **MOMAH Opportunities/Furas:** official portal content describes itemized municipal opportunities across the Kingdom but is the same unified Furas platform, so do not add a second source or duplicate records.
- **MEWA Investment Opportunities:** official page directs investors to apply through Furas; no separate itemized MEWA opportunity inventory was found there. Do not create a duplicate source from this landing page.
- **RCRC programs/projects:** publicly itemized programs exist, but program/project pages reviewed were not live solicitations or itemized investment offers. Exclude until an official open offer inventory appears.
- **NHC:** public categories and pathways only, as above.
- **NCP Investors Portal:** public landing content exists, but anonymous itemized inventory and stable public record identity were not established in this audit; treat as conditional and do not access logged-in pages.

This is a bounded discovery, not a claim that every Saudi public entity was exhaustively searched. Add sources only with evidence meeting all four acceptance criteria: public anonymous access, itemized opportunities, official/government-associated publisher, and preservable opportunity identity.

## D. Extraction and geographic normalization

- Preferred extraction order: anonymous public JSON/API or XHR, structured HTML, official downloadable table, then structured public PDF. Do not use login, API keys, private endpoints, CAPTCHA bypass, or access-control circumvention.
- Preserve each `SourceOpportunity` row, official ID, raw JSON, raw location text, original URL, and source observation/provenance. Source-row identity is source-scoped and must be idempotent.
- Add deterministic Arabic normalization aliases for orthographic/spacing variants (for example `الأحساء`, `محافظة الأحساء`, `الاحساء`) while preserving `original_location_text`. Exact normalized match, a reviewed alias, explicit source hierarchy, or verified coordinate lookup may support normalization. Unknown names remain `UNSPECIFIED/REVIEW`; no fuzzy/title/owner/centroid inference.
- Operational administrative reference should use publicly accessible official names and parent relations. NCAR publicly exposes its unified coding guide for regions, governorates, and administrative centers; the National Portal confirms 13 administrative regions; GASTAT publishes a statistical classification covering regions, governorates, and centers. Retrieve and verify the public guide contents/counts and cross-check names/parentage across official sources before import. This is public-source use, not a request for permission. Keep City optional and do not represent national- or region-wide scope as a physical location.
- Coordinates only from the source or already accepted verified provenance. Unknown coordinates produce no map marker while the item remains available in the list.

## E. Estimated volume and baseline

| Item | Observed baseline | Expansion estimate |
|---|---:|---|
| All SourceOpportunity rows | 3,180 | Unknown until isolated national source probes complete; existing rows reused |
| Invest Saudi SourceOpportunity rows | 2,555 | No new rows expected from re-enumerating the same IDs; eligibility/promotion result must be dry-run first |
| Current Masters | 566 (587 total including merged/history rows) | No automatic mass promotion; additions only from individually qualified new opportunities |
| Furas SourceOpportunity rows | 436 persisted; national public dry-run enumerated 6,494 IDs | At most 6,058 incremental IDs before overlap; exact overlap requires read-only ID comparison |
| New RCJY source | 0 configured rows | Unknown pending anonymous count/page probe |

Do not infer opportunity volume from UI counters, project portfolios, city GIS features, news counts, or marketing claims. The production master count and source counts are snapshot data, not target values.

## F. Priority and exact implementation sequence

1. **Baseline/backup and local invariants:** confirm production backup freshness, deployed image tags, lifecycle fix, current database revision, job state, source flags, and current immutable snapshots. No code deploy until this is recorded. Use an isolated DB restored from verified backup for all new adapter and migration work.
2. **Geography reference/aliases:** build and test a compact official public region/governorate reference with source evidence and exact alias map; leave city optional. Validate counts, names, parents, and uniqueness; do not seed guessed names or coordinates. Use 0024/0025 only after isolated migration validation.
3. **Furas first:** isolated flag-on full scan, count/ID/page agreement, bounded batches, retry/checkpoint behavior, national source scope, zero removals on incomplete scans, and stable IDs. The public scan passed count/ID/page agreement with 6,494 records; the adapter restarts a full enumeration after interruption rather than persisting a mid-scan checkpoint, so resumable checkpointing remains a production reconciliation gate. Dry-run compare new IDs against existing rows. Validate national enumeration cannot accidentally assign national records to an Al-Ahsa Master. If the existing adapter fails these checks, fix only the Furas adapter and focused tests; keep national flag off in production until verified.
4. **Invest Saudi second:** enumerate current public endpoints in isolation; preserve every existing row/ID. Run a machine-readable eligibility dry-run, review borderline classes, verify strong identity/no duplicate, and promote only accepted records. Compare Master and source-row digests before/after.
5. **MODON third:** verify open itemized inventory and total/page completeness; skip if public inventory is only a location catalogue or if live list cannot prove completeness. No mass import from GIS assets.
6. **NCP fourth:** retain news archive as a separate public-announcement collection. Add pipeline opportunities only if itemized project cards and stable public IDs are accessible anonymously. If investor registration is required for records, record `RESTRICTED` and skip those records.
7. **PIF fifth:** validate public detail records and opportunity identity; exclude general promotion and duplicates. Preserve the official page and company relationship as evidence, not as owner/location inference.
8. **MWAN sixth:** run nationwide public listings; accept opportunity geography only where explicitly published. Reconcile only a complete, stable source scope.
9. **RCJY seventh / new-source phase:** anonymously map the public listing/detail pagination and identity; isolated adapter and fixture tests; integrate only after complete scope evidence. Keep RCJY regional coverage labeled as such.
10. **Re-audit remaining configured sources:** Al-Ahsa, AHDA, KFU, NHC and Waha retain their current declared scopes; check for newly published itemized listings without converting generic material.
11. **Each source’s production sequence:** isolated focused tests → bounded dry-run and record-count estimate → source identity/removal checks → backup and active-job check → controlled one-source production sync/backfill → DQ and source-specific coverage verification. Pause on any mismatch. Never run all-source sync or several national backfills together.
12. **National activation last:** after migrations 0024/0025, reference validation, source coverage and Master DQ pass: full regression, five viewport Playwright, API/filter/CSV/XLSX parity, dependent-filter behavior with/without City, map provenance checks, duplicates, lifecycle monotonicity. Then enable national UI/map/dashboard flags only after a read-only preflight. Keep Furas enumeration flag separate and only enable it after its own source gate. Preserve Al-Ahsa quick view and local map behavior.

## G. Required source coverage reporting

The national matrix must report per source: `SOURCE`, `PUBLIC_ACCESS`, `CURRENT_SCOPE`, `IMPLEMENTED_SCOPE`, `REGIONS_OBSERVED`, `ITEMIZED_RECORDS`, `ACTIVE_RECORDS`, `EXTRACTION_METHOD`, `LAST_SUCCESS`, `TECHNICAL_HEALTH`, `COVERAGE_STATUS`. Unknown observed regions, unavailable active counts, and unassessed coverage must be `NOT_ASSESSED`/unknown rather than zero. Furas source enumeration, geographic eligibility, and removal reconciliation scope remain separate fields.

## H. Main risks and controls

- **Furas widening removal scope:** record enumeration version/fingerprint independently; removal only after full count/IDs/features and successful terminal lifecycle. Partial/error/timeout/truncation/scope-change/zero-page anomaly means no reconciliation.
- **Eligibility versus source enumeration:** nationally enumerated rows can remain source-only and unlinked until supported geography/identity exists. A source scan must not make every row eligible for Al-Ahsa or any Master.
- **Invest Saudi duplicate promotion:** reuse all existing SourceOpportunity records and preserve unlinked national rows; no title-only Master matching.
- **Source has public pages but restricted item details:** skip restricted detail paths without bypass; retain public coverage limitation.
- **Zero rows mistaken as zero inventory:** use explicit source paging/count evidence; otherwise label coverage limited/unknown.
- **Geography uncertainty:** preserve raw; unknown parent/city stays review; City may remain unpopulated. No centroid/HQ fallback.
- **National scope semantics:** nationwide is one scope label, not 13 locations. `LOCATION_UNSPECIFIED` remains distinct.
- **Lifecycle regression:** all deployable images must retain terminal-state monotonicity and atomic CAS transitions. No older base images or all-purpose deployment override.
- **Production drift/scheduled activity:** capture latest backup, job counts/active jobs and flags immediately before migration/sync; do not overlap controlled expansion with an active natural source run.

## Official public evidence reviewed

- Furas describes itself as the national unified platform for municipal/real-estate opportunities across regions: <https://furas.momah.gov.sa/en/about>
- MOMAH describes the Opportunities portal and its national investment categories: <https://momah.gov.sa/en/node/15370>
- MEWA directs current opportunities to Furas: <https://www.mewa.gov.sa/en/Ministry/InvestmentOpportunities/Pages/default.aspx>
- RCJY public listing with itemized cards and city labels: <https://www.rcjy.gov.sa/en/web/guest>
- RCJY investment portal service terms (public bidding / expression of intent): <https://www.rcjy.gov.sa/en/terms-and-conditions>
- NCP public investors portal: <https://www.ncp.gov.sa/>; its project pipeline is a separate scope from the existing public News adapter. Investor portal landing: <https://investors.ncp.gov.sa/home>
- NHC public categories: <https://www.nhc.sa/en/investment-opportunities/>
- PIF public opportunity example/category: <https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/tourism-travel-and-entertainment/>
- National Portal: Law of Provinces describes 13 administrative regions: <https://my.gov.sa/en/content/govmechanism>
- NCAR publicly published unified regional/governorate/administrative-center coding guide: <https://ncar.gov.sa/regions-coding>
- GASTAT methodology documents classification/coverage across regions, governorates, administrative centers and populated areas: <https://www.stats.gov.sa/en/w/methodology-and-quality-report-of-services-statistics>
- RCRC open-data catalog explains administrative-region/governorate hierarchy, useful as a cross-check rather than the canonical source: <https://opendata.rcrc.gov.sa/explore/dataset/dependent-population-by-citizenship-and-governorate-2022/api/>

## Implementation checkpoint after the pre-ingestion plan

The plan above was created before any source expansion. Afterward, implementation and tests were performed only in the workspace and a disposable clone restored from backup `20261101T100556Z-5bd5a0f5` (SHA-256 matched its manifest). The clone was explicitly upgraded from 0023 to 0025; no production schema or data was changed.

- The public national Furas scan returned **6,494 unique IDs** in 67/67 successful requests with complete count/ID/page agreement. A full isolated sync against the cloned database created **6,119 new Furas SourceOpportunity rows**, updated 375 existing Al-Ahsa rows, created **0 Masters**, and removed **0** rows. Existing source-scoped IDs were preserved. The clone now has 6,555 Furas SourceOpportunity rows; current/total Master counts stayed 566/587. All 6,119 newly enumerated national rows are source-only because they did not meet current Al-Ahsa Master eligibility; raw source payload/location remains attached.
- The sync's inline fast DQ initially reported `API_WORKER_STANDARDIZATION_PARITY` because that isolated run had no worker. A real isolated Celery worker was then started, the clone scheduler was explicitly paused for the single-source test (no gates changed), and a persisted fast post-sync DQ rerun passed **53 pass / 0 warning / 0 fail**. The missed-schedule gate therefore reflects the intentional isolated pause, not a disabled production gate.
- The existing adapter restarts the full ID enumeration after an interrupted fetch; it does not persist a per-batch resume checkpoint. This is a remaining production reconciliation gate under the requested resumable-batch requirement.
- A public exact-alias resolver now compares a raw value only against normalized reference names and stored aliases; ambiguous and unknown values remain unresolved. Reference import/readiness now requires verified public access and official source authority, stable IDs, hierarchy, completeness, counts, and digest, with no separate license/permission approval gate. License fields remain optional evidence and do not determine readiness. The previous migration runbook was updated to match this direction.
- Full regression passed: **634 tests, 41 warnings**. The tested national UI browser evidence from the prior isolated task remains in its existing report; national UI/map/dashboard were not enabled or re-run against production.
- Official RCJY cards prove public itemized content, but the anonymous “View All” target currently returns HTTP 404 and the homepage card detail anchors are empty. RCJY remains **discovered, not integrated**.

Production read-only recheck after this work: **3,180** SourceOpportunity rows, **587 total / 566 current** Masters, revision **0023**, maximum job **673**, **0 active jobs**. Latest production fast DQ (job 673) passed **49 pass / 0 warning / 0 fail**. Lifecycle-fix API/worker/scheduler tags remain deployed. The deployed API image has no Furas national enumeration switch and lacks the workspace geography module; national flags are effectively false/unset. No production source sync/backfill, migration, promotion, or feature-flag change was performed.

Therefore this plan is not a completed national rollout. Before any production source expansion, deploy the tested code while preserving lifecycle fixes, perform explicit migrations 0024/0025 using a fresh verified backup, add the required durable Furas batch-resume behavior, and rerun the source gates. National UI/map/dashboard remain off until a public reference version has been retrieved, cross-checked, validated, and imported in isolation and the national UI gates pass.

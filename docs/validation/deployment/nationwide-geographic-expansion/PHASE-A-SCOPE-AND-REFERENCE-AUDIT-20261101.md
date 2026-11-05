# Nationwide Expansion — Phase A Scope and Reference Audit

**Project:** Al-Ahsa Investment Opportunities Platform  
**Audit date:** 2026-11-01 (Asia/Amman)  
**State:** `PHASE_A_COMPLETE / NATIONWIDE_IMPLEMENTATION_BLOCKED_ON_AUTHORITATIVE_GEOGRAPHY_REFERENCE`

This is an implementation precondition report, not an acceptance report. No source sync, migration, service restart, or business-data write was performed for this audit.

## Live baseline and service state

The preserved baseline is in `baseline-20261101T071825Z/`. Its manifest records 587 Master rows (566 current), 3,180 SourceOpportunity rows, 33,377 observations, 1,189 review/history rows across the listed review tables, 652 source jobs, and Alembic `0023_quant_commercial`. The baseline was captured in one PostgreSQL repeatable-read, read-only transaction. The paired backup is `backups/nationwide-geographic-expansion/nationwide-pre-change-20261101T071658Z.dump`, SHA-256 `d9acad107c119d32ca349eb0592448ac2657eae417e488e975e6d7a37733cd3f`; its archive listing and isolated PostgreSQL restore were verified before this audit.

The live readiness endpoint returned `ready`; list and dashboard APIs both returned 566. Services are running. The live source registry has 11 entries: 10 enabled and Waha disabled. There are 652 jobs and 0 active jobs. No sync was enqueued by this audit.

The last scheduled Furas job is failed (job 651) after a PostgreSQL deadlock updating Master 249; the previous complete success is job 643. It reported zero pages and zero removals. This operational issue is preserved as an existing condition; this task did not retry it. MODON, NHC, and MWAN also have stale/limited public coverage states, while their rows and source histories remain intact.

## Current geographic model

`app/geography.py` contains a derived hierarchy for Saudi Arabia, the Eastern Province, Al-Ahsa Governorate, and 12 reviewed Al-Ahsa localities. It intentionally uses exact aliases. It has no national Region/Governorate/City reference dimension, stable administrative identifiers, or current national boundary layer. `Opportunity` retains its existing single-value city/district/location projection. `OpportunityLocation` preserves source-linked multi-location text but has no normalized administrative IDs. Current map boundary data is Al-Ahsa-only. The live API confirms 565 of 566 current Masters in its existing confirmed Eastern/Al-Ahsa projection and one unspecified; these counts do not establish national completeness.

## Existing-source geographic scope audit

| Source | Collector scope in current code | Public/official scope evidence and limitation | Safe expansion finding |
|---|---|---|---|
| Furas | 11 fixed Al-Ahsa `CITY_ID`s plus `Announced`, non-qualifying-opportunity, and deadline-today/future filters. | Public official GIS/ArcGIS layer is used; historical accepted filter audit measured only the Al-Ahsa subset. Current sync failure is unrelated to geography. | Nationwide enumeration may be possible, but must first separate full-scan identity/removal scope from local eligibility. `normalized_record()` currently promotes any source-filtered Furas item directly to Al-Ahsa. Do not remove the CITY_ID condition before that contract changes. |
| Al-Ahsa Investment Platform | Complete page/card traversal of the dedicated Municipality of Al-Ahsa listings. | The source is explicitly local and has no national coverage claim. | Keep local; do not widen. |
| AHDA | Public sitemap/page-defined AHDA content; source scope semantics identify AHDA institutional/campus scope. | Dedicated local development authority; public pages do not establish a national listing universe. | Keep source-defined/local. |
| Invest Saudi | All four paginated public JSON datasets, without collection-side region filtering. Master qualification is currently Al-Ahsa-only. | Accepted ADR defines the four official IDs/datasets as national discovery population. Current DB: 2,555 source rows; 19 linked and 2,536 unlinked. | Re-evaluate retained rows under Saudi-wide qualification; do not recreate IDs or link every row indiscriminately. Current unlinked population includes explicit regions, Eastern-only, multiregion, and missing location cases. |
| KFU | Public investment announcements from King Faisal University; procurement notices are excluded. | University-specific publisher and opportunity scope. | Keep source-defined/local unless the university itself publishes a nationwide asset/location; do not infer from publisher location. |
| MODON | Public catalogs, GIS/reference assets, route and product monitoring; no public itemized live opportunity inventory. | Coverage is public-limited; publicly viewable assets do not prove current availability. | No national opportunity expansion until official itemized availability is published. Preserve reference assets as non-opportunity evidence. |
| NCP | Public English news archive; only explicit Al-Ahsa evidence currently qualifies a Master. | National PPP/program archive, but a news article is not automatically a live investment offer; authenticated project pipeline remains outside public scope. | Re-evaluate specific public solicitations nationwide using source semantics and location evidence; retain announcements as source-only where not a specific offer. |
| NHC | Public investment categories, information pages, and application/qualification routes; no public itemized current inventory. | National policy/program scope; public catalog is limited and private e-services are not accessed. | Do not create opportunities from category pages or authenticated flows. |
| PIF | Public landing/ecosystem/company route monitoring; currently no deterministic itemized public opportunity population. | National hub, but public pages expose no current item rows; index-only content is not authoritative current inventory. | Keep limited public coverage; do not use private endpoints or indexed snippets. |
| MWAN | Specific public opportunity detail routes are traversed; only explicit Al-Ahsa location is currently accepted. | Public published projects may span multiple regions; project cards do not constitute a complete private opportunity pipeline. | Re-evaluate published itemized projects nationwide, retaining only specific offerings and source evidence. |
| Waha Development | Disabled catalog row; no adapter or sync support. | Public pages have no itemized offers; 58 public GIS features are locations/portfolio references without opportunity IDs or application terms. | Keep disabled and limited; no public listing supports Master creation. |

Historical acceptance evidence is in `docs/validation/data/source-coverage-completeness/FINAL-RECONCILIATION.md`, `docs/validation/data/location-geographic-eligibility/FINAL-REVIEW.md`, `docs/validation/data/waha-source-integration/FINAL-REVIEW.md`, `docs/source-analysis/furas.md`, `docs/source-analysis/alahsa-opportunities.md`, and `docs/source-analysis/pif-route-map.md`. Those reports are prior snapshots; live counts in this report use the 2026-11-01 baseline above.

## Retained national data — Invest Saudi read-only sample audit

At the audit snapshot, 2,536 of 2,555 Invest Saudi source identities had no Master link. Among those unlinked identities, 2,004 had non-empty raw location text and 532 had none; 347 were classified by the existing Al-Ahsa-only code as Eastern-Province-only, 2,184 had no Al-Ahsa evidence, and five carried description-only Al-Ahsa evidence. The database contains original records and endpoint memberships; no rows were changed.

The raw location distribution includes exact regional labels, specific cities/governorates, generic `Municipality`, `Saudi Arabia`, multiregion labels, and empty values. This confirms a real nationwide re-evaluation population, but does not itself establish a current administrative ID relationship or whether every record is a qualifying investable offer. The 14 `Saudi Arabia` strings and multiregion values were not promoted to `NATIONWIDE` or multiple physical locations.

## Authoritative reference blocker

GEOSA identifies the Official Saudi Map as the approved reference for national borders and administrative regions and points users to the National Geospatial Platform for viewing/downloading it. The public GEOSA map link returned an explicit request rejection in this environment. The public Saudi National Address lookup documentation requires an authenticated subscription key. GASTAT’s current methodological material supports 13 administrative regions; published governorate totals are not fully consistent across current publications (150 vs. 151), so a hand-assembled governorate list would not be safe. A 2010 GASTAT map is historical and is not accepted as a current city/governorate register.

Required before populating administrative IDs or drawing official national boundaries: a current authorized GEOSA/MOI administrative-units file (regions, governorates, administrative centers/cities, stable official IDs, parent relationships, version date, and permitted reuse terms), or an authorized SPL subscription/package that supplies the required complete hierarchy. Until then, exact region names alone can support display vocabulary but cannot safely satisfy the requested full Region → Governorate → City hierarchy, source-record reprocessing, region filters, geographic counts, or official map.

Do not use an old governorate list, public search snippets, fuzzy text matching, unverified third-party boundaries, a publisher/head-office address, or centroid defaults to fill this gap. The adapter changes and source backfills that depend on this reference remain unperformed. No migration is justified until the reference contract and exact field semantics are fixed.

## Rollback and preservation

The verified custom-format PostgreSQL backup is the full database rollback point. Schema/application rollback must restore the previous application/API/worker images and downgrade only the new, backward-compatible migration after the restore decision is made; do not delete any Master or source row. Source-scope rollback must disable the expanded collector contract and preserve current/historical dataset membership state; a new national partial scan must never be reconciled against an old Al-Ahsa-only population. No rollback operation was needed because no mutation occurred.

```ini
LIVE_PLATFORM_READY = TRUE
LIVE_MASTER_TOTAL = 587
LIVE_CURRENT_MASTERS = 566
LIVE_SOURCE_OPPORTUNITIES = 3180
LIVE_SOURCE_OBSERVATIONS = 33377
CONFIGURED_SOURCES = 11
ENABLED_SOURCES = 10
DISABLED_SOURCES = 1
ACTIVE_SYNC_JOBS = 0
FURAS_LATEST_JOB = 651 / FAILED / SCHEDULED / ZERO_RECORDS / ZERO_REMOVALS
INVEST_SAUDI_UNLINKED_SOURCE_ROWS = 2536
OFFICIAL_GEOGRAPHY_REFERENCE_AVAILABLE = FALSE
MANUAL_SOURCE_SYNC_STARTED = FALSE
BUSINESS_DATA_CHANGES = 0
SCHEMA_CHANGES = 0
```

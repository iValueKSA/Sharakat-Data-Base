# Cross-source duplicate review

**Review date:** 11 October 2026 (Asia/Amman)  
**Sources:** [Al-Ahsa Investment Platform](https://alahsa-opportunities.com/) and [Furas official GIS application/API](https://gisapps.balady.gov.sa/opportunities/index.html?lang=ar)  
**Scope:** The four highest-priority candidate pairs only. No additional source was implemented.

## Method and decision layers

- Candidate generation remains broad and cross-source only. Same-source idempotency uses stable source opportunity IDs.
- Duplicate scoring ranks candidates using core title, locality/GIS evidence, area, owner, parcel/plan, term, and deadline. Missing attributes remain unknown. Because neither reviewed portal exposes a distinct complete narrative for these listings, description similarity is explicitly a title proxy. Scores are ranking signals, not calibrated probabilities.
- Merge authorization is separate from scoring. Tier 1 allows deterministic auto-merge only for the same normalized official reference or propagated official source identifier. Tier 2 requires title similarity ≥ 0.92, normalized owner match, parcel or plan identity, compatible area and known term, no parcel/owner conflict, and total score ≥ 0.90. Title alone and generic city/area matches cannot auto-merge.
- The four records were reviewed against Al-Ahsa live detail pages (all returned HTTP 200) and official Furas GIS feature attributes and geometry (`verification_method=OFFICIAL_GIS_API`). Furas detail-page availability was not a blocker.
- All four were manually confirmed after the evidence review. Pair 4 remains below the auto-merge score gate because its Furas location is coarse and scores 0. The high-confidence parcel range, plan, area, activity, term, owner, and deadline support the manual decision. The threshold was not lowered.
- For all pairs, Furas `AMANA` names the local asset owner, Amanat Al-Ahsa. `ENTITIESNAME` identifies the publishing/agency entity, Ministry of Municipal and Rural Affairs; it is not treated as the opportunity owner. The publication platform remains Furas.
- Furas `RFPPRICE` is the booklet fee, not a bid, rent, or investment value. Grace period, minimum bid, annual rental, and investment value were not exposed in the reviewed records. No separate English title or complete narrative description was exposed.

## Pair 1 — Al-Ahsa 441 ↔ Furas 01-26-017001-27001

- **Candidate:** 1. **Master A / surviving:** 195. **Master B / recoverably merged:** 74.
- **Source A:** Al-Ahsa, platform *منصة الفرص الاستثمارية بالأحساء*. Source/external/official listing ID `441`. Reference and normalized reference were not published.
- **Source B:** Furas, platform *فرص – البوابة الموحدة للاستثمار*. Source/external ID and official GIS `OPPORTUNITYID`: `01-26-017001-27001`; normalized reference `012601700127001`; `OBJECTID` is retained in raw GIS data.
- **Original Arabic titles:** A: “انشاء و تشغيل وصيانة القطعة رقم 461 1و 461 2 لنشاط صناعات خفيفة أو ورشة بالمخطط رقم 14-16 بصناعية العيون”. B: “انشاء و تشغيل و صيانة القطعة رقم 461 1و 461 2 لنشاط صناعات خفيفة أو ورشة بالمخطط رقم 14 16 بصناعية العيون” followed by Furas activity/category suffix.
- **Normalized titles:** same asset wording after Arabic, punctuation, whitespace, and standard Furas suffix normalization. English titles are unavailable.
- **Owner:** A `أمانة الأحساء`; B `أمانة محافظة الأحساء`; normalized owner aliases match. Furas raw `AMANA=أمانة محافظة الأحساء`; `ENTITIESNAME=وزارة الشئون البلدية والقروية` is publisher/agency.
- **Location:** A governorate Al-Ahsa, site `العيون`, industrial area. B GIS `CITYNAME=العيون`, `CITY_ID=005011001`, district `الصناعية`, street `حارثة بن قيس`; coordinates latitude `25.635184`, longitude `49.543832`. Both titles identify the same industrial site and exact parcels.
- **Asset and area:** parcels `461 1` and `461 2`, plan `14-16`; light industrial use/workshop. Area A/B `752.34 / 752.34 m²`; absolute difference `0 m²`, relative difference `0.00%`.
- **Commercial terms:** the Al-Ahsa listing explicitly states `15 years`; Furas `DURATION=180` is retained as raw evidence without an asserted unit or contract-term interpretation. Other bid/rent terms were not published in inspected fields.
- **Dates:** submission deadline A/B `2026-10-21 / 2026-10-21`; Furas publication date `2026-08-21`. Application start, inquiry deadline, opening and expiry dates were not separately exposed. Furas booklet fee `RFPPRICE=1000` was excluded from investment terms.
- **Similarity:** deterministic identifier `false` (platform IDs differ); title `100.00%`; location `92.00%`; area `100.00%`; description proxy `100.00%`; same owner, plot, plan, duration and deadline: yes. Current score `0.980`; original candidate score `0.741`.
- **Decision:** `CONFIRMED_DUPLICATE`; confidence `0.99`; verification `OFFICIAL_GIS_API` plus live Al-Ahsa detail page.
- **Primary evidence:** exact two-lot identity and plan; exact area; matching owner, asset purpose, term and deadline; compatible Furas GIS coordinates and locality.
- **Contradicting evidence:** no material identity contradiction. Per-platform IDs differ and Al-Ahsa has no propagated Furas reference; source location fields have different granularity. Those differences are expected or non-conflicting.
- **Recommended action/result:** merge completed into Master 195. Both source rows (`441` and `01-26-017001-27001`) remain attached with URLs, raw data, IDs, titles, and timestamps. Audit reason/evidence, actor, and before/after snapshots are stored; undo is available and tested.

## Pair 2 — Al-Ahsa 472 ↔ Furas 01-26-017001-39001

- **Candidate:** 2. **Master A / surviving:** 164. **Master B / recoverably merged:** 140.
- **Source A:** Al-Ahsa, platform *منصة الفرص الاستثمارية بالأحساء*. Source/external/official listing ID `472`. Reference and normalized reference were not published.
- **Source B:** Furas, platform *فرص – البوابة الموحدة للاستثمار*. Source/external ID and official GIS `OPPORTUNITYID`: `01-26-017001-39001`; normalized reference `012601700139001`; GIS `OBJECTID` remains in raw data.
- **Original Arabic titles:** A names construction, operation and maintenance of a gas warehouse in plan `(14/53)` at Al-Jarn for selling and distributing gas cylinders. B has the same facility, plan, city, activity and purpose with formatting/category suffix differences. English titles are unavailable.
- **Normalized titles:** core title similarity `98.94%` after formatting and suffix normalization.
- **Owner:** A `أمانة الأحساء`; B `أمانة محافظة الأحساء`; normalized owner aliases match. Furas `AMANA` identifies the local Amanah; `ENTITIESNAME` is the publishing/agency entity.
- **Location:** A governorate Al-Ahsa, city/site `الجرن`. B title also names `الجرن`; GIS `CITYNAME=الاحساء`, `CITY_ID=005020001`, district `الاسكان`, street `الحارث بن شريح التميمي`, sub-municipality `بلدية العيون`, coordinates latitude `25.526516`, longitude `49.603610`. GIS address is less specific than the title and the Al-Ahsa card; it does not contradict the named site.
- **Asset and area:** gas warehouse, plan `14/53`, sale/distribution of gas cylinders. Area A/B `2,734 / 2,734 m²`; absolute difference `0 m²`, relative difference `0.00%`.
- **Commercial terms:** the Al-Ahsa listing explicitly states `25 years`; Furas `DURATION=300` is retained as raw evidence without an asserted unit or contract-term interpretation. Grace period, minimum bid, annual rent and investment value were not exposed.
- **Dates:** submission deadline A/B `2026-11-16 / 2026-11-16`; Furas publication date `2026-09-16`. Other lifecycle dates were not separately exposed. Furas booklet fee `RFPPRICE=1500` was excluded from investment terms.
- **Similarity:** deterministic identifier `false`; title `98.94%`; location `92.00%` (the locality appears in both titles); area `100.00%`; description proxy `98.94%`; same owner, plan, duration and deadline: yes. Separate plot number is not exposed. Current score `0.976`; original candidate score `0.736`.
- **Decision:** `CONFIRMED_DUPLICATE`; confidence `0.98`; verification `OFFICIAL_GIS_API` plus live Al-Ahsa detail page.
- **Primary evidence:** same named gas facility and exact subdivision plan; exact area; same owner, cylinder sales/distribution activity, contract duration and deadline.
- **Contradicting evidence:** no material contradiction. GIS city/address is less specific and differs in granularity; the site name is explicit in both titles. Platform IDs differ and no Al-Ahsa Furas reference is exposed.
- **Recommended action/result:** merge completed into Master 164. Both source records are preserved and attached. Merge audit, evidence, actor, and reversible before/after state are stored.

## Pair 3 — Al-Ahsa 443 ↔ Furas 01-26-017001-27002

- **Candidate:** 3. **Master A / surviving:** 193. **Master B / recoverably merged:** 75.
- **Source A:** Al-Ahsa, platform *منصة الفرص الاستثمارية بالأحساء*. Source/external/official listing ID `443`. Reference and normalized reference were not published.
- **Source B:** Furas, platform *فرص – البوابة الموحدة للاستثمار*. Source/external ID and official GIS `OPPORTUNITYID`: `01-26-017001-27002`; normalized reference `012601700127002`; `OBJECTID` is retained in raw GIS data.
- **Original Arabic titles:** both identify light-industry/workshop development of parcel `471` in plan `14-16` at industrial Al-Oyun; only spacing and Furas taxonomy suffix differ. English titles are unavailable.
- **Normalized titles:** core title similarity `98.95%`.
- **Owner:** A `أمانة الأحساء`; B `أمانة محافظة الأحساء`; normalized owner aliases match. Furas `AMANA` is owner and `ENTITIESNAME` is publisher/agency.
- **Location:** A governorate Al-Ahsa, site `العيون`, industrial area. B GIS `CITYNAME=العيون`, `CITY_ID=005011001`, district `الصناعية`, street `أسلم بن الحارث الهاشمي`; coordinates latitude `25.634749`, longitude `49.544749`. Titles and GIS locality align.
- **Asset and area:** exact parcel `471`, plan `14-16`, light industrial/workshop use. Area A/B `708.45 / 708.45 m²`; absolute difference `0 m²`, relative difference `0.00%`.
- **Commercial terms:** the Al-Ahsa listing explicitly states `15 years`; Furas `DURATION=180` is retained as raw evidence without an asserted unit or contract-term interpretation. No grace period or bid/rent values were exposed.
- **Dates:** submission deadline A/B `2026-10-21 / 2026-10-21`; Furas publication date `2026-08-21`. Other lifecycle dates were not separately exposed. Furas booklet fee `RFPPRICE=1000` was excluded from investment terms.
- **Similarity:** deterministic identifier `false`; title `98.95%`; location `92.00%`; area `100.00%`; description proxy `98.95%`; same owner, plot, plan, duration and deadline: yes. Current score `0.976`; original candidate score `0.711`.
- **Decision:** `CONFIRMED_DUPLICATE`; confidence `0.99`; verification `OFFICIAL_GIS_API` plus live Al-Ahsa detail page.
- **Primary evidence:** exact parcel and plan; exact area; same industrial activity, owner, site, term and deadline; GIS coordinates fall in the same industrial locality.
- **Contradicting evidence:** no material contradiction. Platform IDs differ and the Al-Ahsa source does not publish a Furas reference. Source street descriptions differ because each portal gives different address detail.
- **Recommended action/result:** merge completed into Master 193. Both source records remain attached and recoverable through the merge audit and undo endpoint.

## Pair 4 — Al-Ahsa 444 ↔ Furas 01-26-017001-36001

- **Candidate:** 4. **Master A / surviving:** 192. **Master B / recoverably merged:** 135.
- **Source A:** Al-Ahsa, platform *منصة الفرص الاستثمارية بالأحساء*. Source/external/official listing ID `444`. Reference and normalized reference were not published.
- **Source B:** Furas, platform *فرص – البوابة الموحدة للاستثمار*. Source/external ID and official GIS `OPPORTUNITYID`: `01-26-017001-36001`; normalized reference `012601700136001`; GIS `OBJECTID` remains in raw data.
- **Original Arabic titles:** both describe equipment transport/parking, workshop, warehouse, offices and staff housing on lots `405/ت` through `409/ت`, plan `14/154`, northern industrial area. Furas varies punctuation, spacing and the suffix for the lot letter and adds a taxonomy suffix. English titles are unavailable.
- **Normalized titles:** core title similarity `97.40%`; lot suffix formatting normalizes to the same numeric lot range.
- **Owner:** A `أمانة الأحساء`; B `أمانة محافظة الأحساء`; normalized owner aliases match. Furas `AMANA` is the local owner; `ENTITIESNAME` is the publisher/agency.
- **Location:** A governorate Al-Ahsa, named site `الصناعية الشمالية بالعيون`. B GIS only reports `CITYNAME=الاحساء`, `CITY_ID=005020001`, street `الاحساء 173`, coordinates latitude `25.548998`, longitude `49.685095`; the GIS address is coarse and does not independently pinpoint the named northern industrial site. The detailed lot range and plan match exactly across the source titles. Al-Ahsa provides no coordinates for a distance comparison.
- **Asset and area:** lots `405/ت–409/ت`, plan `14/154`, equipment trading/workshop, warehouse and support facilities. Area A/B `145,000 / 145,000 m²`; absolute difference `0 m²`, relative difference `0.00%`.
- **Commercial terms:** the Al-Ahsa listing explicitly states `25 years`; Furas `DURATION=300` is retained as raw evidence without an asserted unit or contract-term interpretation. Other bid/rent terms were not exposed.
- **Dates:** submission deadline A/B `2026-10-21 / 2026-10-21`; Furas publication date `2026-08-21`. Other lifecycle dates were not separately exposed. Furas booklet fee `RFPPRICE=3000` was excluded from investment terms.
- **Similarity:** deterministic identifier `false`; title `97.40%`; location `0.00%` because GIS has only a coarse Al-Ahsa locality/address; area `100.00%`; description proxy `97.40%`; same owner, normalized lot range, plan, duration and deadline: yes. Current score `0.741`; original candidate score `0.698`.
- **Decision:** `CONFIRMED_DUPLICATE`; confidence `0.98`; verification `OFFICIAL_GIS_API` plus live Al-Ahsa detail page.
- **Primary evidence:** exact lot range and plan; exact 145,000 m² area; matching named industrial investment and workshop/storage activity; same owner, 25-year term and deadline.
- **Contradicting evidence:** no contradictory parcel or commercial terms. GIS location is too coarse to confirm the precise site and its location similarity is scored zero; Al-Ahsa has no coordinates. This is an evidence limitation and drove the low ranking score, not a positive geographic match.
- **Recommended action/result:** after manual field review, merge completed into Master 192. Both source records remain attached with raw GIS geometry and the Al-Ahsa listing. Audit and undo state are stored. Pair 4 is specifically retained as a negative regression for automatic merging below the score gate.

## Summary

Candidates reviewed: 4  
Confirmed duplicates: 4  
Not duplicates: 0  
Insufficient evidence: 0  
Still awaiting manual decision: 0  
Masters before: 210  
Masters after: 206  
Source records after: 210  
Multi-source masters: 4  
Automatic threshold recommendation: AUTO MERGE ≥ 0.90; MANUAL REVIEW 0.75–0.899; SEPARATE < 0.75, with the scores interpreted as ranking bands rather than probabilities. Keep deterministic Tier 1 and strict Tier 2 conditions above. Never auto-merge on title alone. Pair 4’s manual confirmation does not lower the auto threshold.  
Expansion gate: `READY_TO_EXPAND`

## Regression and operational validation

- Stable fixture cases cover all four reviewed pairs, title-only rejection, plot conflicts, owner aliases, and lifecycle mapping. The fourth live pair is a low-location-score case that is not auto-merge-safe.
- Admin API merge/undo test confirms the target canonical snapshot, both master rows, source links, provenance, conflicts, and change history are restored. The merge emits `MASTER_DUPLICATE_MERGED`; undo emits `MASTER_DUPLICATE_MERGE_UNDONE`.
- A live database undo was also run inside a transaction and rolled back after checking the real audit’s target snapshot, archived-master link, source-record ownership, and merge-generated history IDs; the persisted merged state was unchanged afterward.
- Two fresh live sync runs retained 132/132 active Furas listings and 74/74 Al-Ahsa listings with full completeness and pagination. Repeat sync reported zero new, updated, or newly merged records. No merged listing was recreated as a master.
- Four historical Furas records whose raw source status is `Deleted` remain present as source/history rows and are not part of the current 132 active query. They are classified `DELETED_FROM_SOURCE`, not `CANCELLED`.
- CSV and XLSX each contain one row per current non-merged master (206, including four historical removed masters), with 18 columns, `عدد المصادر`, and joined `المصادر`; Arabic headers/text and right-to-left XLSX layout are retained. Dashboard/API distinguish 206 masters, 210 source listings, and 4 multi-source masters.

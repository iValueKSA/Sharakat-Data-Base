# Unspecified Sector Deep Semantic & Pattern Analysis

**Status:** `UNSPECIFIED_SECTOR_DEEP_SEMANTIC_PATTERN_ANALYSIS = COMPLETE`  
**Data mode:** read-only  
**Analysis snapshot:** 2026-10-21 09:27:58 UTC  
**Scope:** current, unmerged Master opportunities whose canonical sector was `UNSPECIFIED` in that fixed snapshot.

## Result

The fixed population contains **525 current Masters**: **146 specified** and **379 unspecified**. The complete row-level dataset contains all 379 distinct Master IDs and assigns each to exactly one mutually exclusive analysis bucket. The buckets sum to 379 and reconcile successfully.

| Analysis bucket | Masters |
| --- | ---: |
| Explicit source evidence present but unmapped | 7 |
| High-purity canonical activity | 0 |
| High-purity canonical sub-activity | 0 |
| Raw source classification resolvable | 1 |
| Title pattern resolvable | 0 |
| Description resolvable | 0 |
| Multi-signal resolvable | 0 |
| Conflicting evidence | 0 |
| Potential taxonomy gap | 0 |
| Genuinely unclassifiable from current evidence | 371 |
| **Total** | **379** |

“Title pattern resolvable” is zero after contextual review. Three phrase groups cover seven title mentions, but the terms describe nearby hospitals, a venue at a hospital, a place name, or a processed palm product. Those mentions do not establish the investment’s sector. One raw Furas activity value, `الأنشطة الزراعية والحيوانية`, supports an Agriculture review candidate (Master 78), but has no labeled Furas reference and the title describes palm by-product processing. It remains review-only.

No candidate meets a safe automatic rule threshold. The analysis estimates **0 safe automatic candidates**, **14 review candidates**, and **379 likely to remain unspecified** if no future review or rule work is approved. These are estimates, not applied classifications.

## Signal availability and usefulness

Field availability is not the same as sector evidence. Both short and full descriptions are populated for all 379 Masters, but only **4** contain description text distinct from the normalized title. Generic opportunity type and asset labels are common and do not resolve a sector by themselves.

| Signal | Masters |
| --- | ---: |
| Canonical activity / sub-activity | 8 / 7 |
| Raw activity / sub-activity in source columns | 8 / 7 |
| Asset type / opportunity type | 366 / 366 |
| Short / full description populated | 379 / 379 |
| Description distinct from title | 4 |
| Raw source category | 0 |
| Raw source sector | 7 |
| Other classification-like raw fields present | 378 |
| Title present with no supported non-title sector signal (`UNSPECIFIED_TITLE_ONLY`) | 378 |
| No useful, supported sector signal | 378 |

The title-only diagnostic counts opportunities with no supported non-title sector signal; it does not say each title is itself informative. The no-useful-signal count also treats generic values and contextual phrase mentions as insufficient. Both measures are defined in `signal-coverage.json`.

Signal combinations: activity + sub-activity **7**; activity + meaningful title phrase **3**; sub-activity + meaningful title phrase **3**; meaningful title + distinct description **0**; raw source category + title **0**; asset type + meaningful title phrase **4**.

## Source distribution

The database has 3,137 SourceOpportunity rows overall. The frozen analysis includes 550 source rows linked to current Masters. Source denominators below count unique current Masters with at least one row from that source, so they can overlap across sources.

| Source | Current Masters | Unspecified | Unspecified % | Raw sector | Raw activity | Raw sub-activity | Raw category | Other classification-like fields |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Furas | 415 | 373 | 89.88% | 0 | 7 | 7 | 0 | 373 |
| Al-Ahsa opportunities | 103 | 5 | 4.85% | 5 | 5 | 0 | 0 | 5 |
| KFU | 3 | 3 | 100% | 1 | 0 | 0 | 0 | 3 |
| AHDA | 8 | 1 | 12.50% | 0 | 0 | 0 | 0 | 0 |
| NCP | 1 | 1 | 100% | 1 | 0 | 0 | 0 | 1 |
| Invest Saudi | 19 | 0 | 0% | 0 | 0 | 0 | 0 | 0 |
| MODON | 0 | 0 | 0% | 0 | 0 | 0 | 0 | 0 |
| MWAN | 0 | 0 | 0% | 0 | 0 | 0 | 0 | 0 |
| NHC | 0 | 0 | 0% | 0 | 0 | 0 | 0 | 0 |
| PIF | 0 | 0 | 0% | 0 | 0 | 0 | 0 | 0 |

Furas contributes 373 of 379 unspecified Masters. Its raw payload exposes six currently unused classification-like fields: `ACTIVITYTYPE`, `ACTIVITYTYPEID`, `OPPORTUNITYTYPE`, `OPPORTUNITYTYPEID`, `SUBACTIVITYTYPE`, and `SUBACTIVITYTYPEID`. In the unspecified subset, these fields have 11, 11, 373, 373, 7, and 7 non-null Masters respectively. There are **8 unused classification-like fields in total**, including `raw.opportunity_type` at KFU and NCP. The Furas `TemporaryRental` / `Investment` opportunity types and several asset/location labels are not sector mappings. Source-specific extraction and validation are recommended before considering any adapter change.

## Semantic patterns and source evidence

- Canonical activity `الأنشطة التجارية` appears on 2 unspecified Masters, but its 5 labeled controls all map to `sector:other` and fail the minimum support threshold of 25. It is not a safe rule. `خدمي` has no labeled control.
- Canonical sub-activity `أخرى` appears on 4 unspecified Masters and has 16 labeled controls split between `other` (8), commercial (4), and industrial (4): 50% dominant purity. It is not resolvable.
- Furas raw `الأنشطة التجارية` has 18 labeled controls split 12 commercial, 5 other, and 1 industrial (66.67% dominant purity). Furas raw sub-activity `أخرى` is 50% pure. Neither supports automation.
- Seven Masters carry explicit but unmapped source classification values: Al-Ahsa opportunities `خدمي` (5), KFU `LEASE_OPPORTUNITY` (1), and NCP `PPP_PROJECT` (1). None maps obviously to a current canonical sector. `خدمي` is broad; the other values describe procurement or opportunity form. All require review.
- Title phrase groups: `مستشفى` (5; mostly a nearby landmark or a cafe/kiosk location), `تمور` (1; “مدينة التمور” is a place reference), and `نخيل` (1; palm by-product processing). The labeled controls show `مستشفى` is ambiguous (12 occurrences, 75% dominant `other`); `تمور` is 3/3 Agriculture in controls but the one current title uses it as a place name. Phrase purity cannot replace context.
- Distinct descriptions resolve no records; multi-signal combinations add no further candidates. Repeated descriptions duplicate titles and were not double-counted as independent evidence.
- No repeated, clearly evidenced population falls outside the current taxonomy. **Potential taxonomy gaps: 0.** Operational asset types and procurement mechanisms do not justify new sectors.

Tourism has **0 strong** and **34 ambiguous screening leads**: 23 park assets and 11 beach/frontage assets. They may be tourism, public amenity, or commercial use; an asset label alone is insufficient. Agriculture has **0 strong** and **1 ambiguous review candidate** (Master 78). False-positive risks include food retail/manufacturing, warehouses, generic land, mobile food carts, cafes at hospitals, parks, beaches, and place names associated with dates or palms.

The full sector-by-sector candidate summary is in `classifier-gap-analysis.json`. Across all current canonical sectors, no new candidate qualifies for automatic classification. The top gaps are source-specific raw classification underuse, sparse canonical activity/sub-activity coverage, and descriptions that repeat titles.

## Recommended next rule pack (not implemented)

- **Tier 1 safe high-impact automatic rules: 0.** No current pattern meets the evidence threshold without risk of false positives.
- **Tier 2 review-assist rules: 7.** Three exact source/value groups for `خدمي`, `LEASE_OPPORTUNITY`, and `PPP_PROJECT`; one exact Furas agriculture activity hint; and three title phrase groups for contextual human review. The Furas hint has zero labeled controls and is not automatic.
- **Tier 3 do not automate: 1 rule family.** Generic lease, location, land/building, food retail, warehouse, parking, park/beach asset, and place-name terms alone.

Recommended enrichment is limited to existing official source payloads. For Furas, expose and inspect stable activity/sub-activity identifiers and meanings, compare them against labeled controls, and preserve the raw payload. No unofficial source was browsed and no adapter, rule, or taxonomy change was made.

## Review queue impact

There are **64 open sector review cases**. **12** match current unspecified Masters with new analytical supporting evidence; **52** receive no new supporting evidence in this analysis. Review records were not created, resolved, or edited.

## Data and DQ safety

| Check | Before | After |
| --- | ---: | ---: |
| Live DQ gates: PASS / WARNING / FAIL | 53 / 2 / 0 | 53 / 2 / 0 |
| Current Masters | 525 | 525 |
| Specified / unspecified | 146 / 379 | 146 / 379 |
| All SourceOpportunity rows | 3,137 | 3,137 |
| Observations | 12,829 | 12,829 |
| Open reviews, all fields | 583 | 583 |
| Open sector review cases | 64 | 64 |
| Sync jobs / max job ID | 404 / 404 | 404 / 404 |

The same two expected DQ warnings remain: 782 records have only a generic official source page, and the open review backlog is 583. There are **0 failing gates before and after**. The specified-sector fingerprint remains `39706479abf8ebab0bd0278cc6baae9054634e2400fb025b141f0033b43ac089`; master, source-link, raw-provenance, and observation-history fingerprints also match the fixed snapshot. No scheduled sync ran during the analysis interval; no manual sync was started. Services remained running and `/health/ready` returned `ready`.

Separately, the analysis snapshot contains **550 SourceOpportunity rows linked to current Masters**; the post-analysis manifest reports the same value. The DQ snapshots count all 3,137 SourceOpportunity rows and 12,829 observations.

**Assertions:** `PREEXISTING_SPECIFIED_SECTOR_VALUES_CHANGED=0`; `BUSINESS_DATA_ROWS_MODIFIED=0`; `REVIEWS_CREATED=0`; `REVIEWS_RESOLVED=0`; `MANUAL_SOURCE_SYNC_STARTED=FALSE`; `LIVE_DQ_FAILING_GATES_BEFORE=0`; `LIVE_DQ_FAILING_GATES_AFTER=0`; `FULL_ANALYSIS_DATASET_ROWS=379`.

## Artifacts

The row-level CSV and JSON contain all required columns, plus raw activity/sub-activity, descriptions, owner/publisher, location/status/reference, source IDs and source evidence, open review references, and inference provenance. `analysis-snapshot.json` preserves the complete frozen source evidence for the 379 unspecified and 146 labeled control Masters.

Required analysis artifacts: `unspecified-sector-master-analysis.csv`, `unspecified-sector-master-analysis.json`, `signal-coverage.json`, `source-unspecified-breakdown.json`, `unused-source-classification-fields.json`, `activity-pattern-analysis.json`, `subactivity-pattern-analysis.json`, `raw-classification-pattern-analysis.json`, `title-pattern-groups.json`, `semantic-phrase-analysis.json`, `asset-type-pattern-analysis.json`, `taxonomy-gap-analysis.json`, `tourism-deep-analysis.json`, `agriculture-deep-analysis.json`, `classifier-gap-analysis.json`, and `recommended-rule-pack.json`.

Additional evidence: `analysis-snapshot.json`, `analysis-summary.json`, `source-enrichment-recommendations.json`, `scheduled-syncs-during-analysis.json`, `dq-before.json`, `dq-after.json`, and `post-live-manifest.json`.

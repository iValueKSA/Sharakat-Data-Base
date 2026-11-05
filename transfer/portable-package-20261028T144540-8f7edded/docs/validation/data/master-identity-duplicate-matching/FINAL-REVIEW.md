# Master Identity, Duplicate, and Cross-Source Review — Final Acceptance

**Result:** `MASTER_IDENTITY_DUPLICATE_CROSS_SOURCE_DEEP_REVIEW = COMPLETE`  
**Project:** Al-Ahsa Investment Opportunities Platform  
**Database:** local `sharakat_local`  
**Final validation snapshot:** 2026-10-20 10:17:13.956362 UTC  
**Standardization Engine:** 21  
**Identity Matching Policy:** 2

This final acceptance replaces the earlier incorrect rule that all 2,899 `SourceOpportunity` rows need a Master. General and national records without proven Al-Ahsa opportunity geography remain intentionally unlinked. See [the historical merge review](IDENTITY-MERGE-REVIEW-HISTORICAL.md) for the full pair-screen, merge evidence, and pre-eligibility UI evidence; this document is the final current-state reconciliation.

## Final source-linkage model

The required population is: every current, non-merged Master has at least one source listing; every source listing confirmed eligible for Al-Ahsa has one current Master; a source row cannot belong to multiple Masters. Records without qualifying opportunity geography remain source-only. Eligibility is not inferred from a keyword or a missing legacy `qualified_location` flag. The final cohort contains 312 source records identity-linked to current Al-Ahsa Masters; 19 rows carry the literal `qualified_location=true` flag, and all 19 link to a current Master. Of the 2,587 unlinked rows, six remain in location-eligibility review (Invest Saudi source row IDs 517, 524, 601, 896, 897, and 898); they are separately excluded from the eligible denominator and not mislabeled confirmed non-local. The other 2,581 are outside the qualified and pending-review populations under the current platform scope and remain unlinked.

## Targeted Invest Saudi adjudication

The 11 specific records were reviewed one by one. All qualify as actual Al-Ahsa opportunity/site/service geography (class A). None was merged to an existing Master: exact official references and current identity candidates were checked; fuzzy title resemblance alone was not used. Each was created via the existing admin location-review acceptance path, preserving the source row and original description/raw facts while recording the location decision in review metadata.

| SourceOpportunity ID | Invest Saudi ID / Furas reference | Final geography decision | Current Master | Evidence summary |
|---:|---|---|---:|---|
| 283 | `50952` | A — facility in Al-Ahsa | 328 | Full description places the distripark in Al-Ahsa; wider corridor is service area. |
| 466 | `44773` | A — site in Al-Ahsa National Park | 329 | Description and official Envi-004 brochure identify the park site and Al-Ahsa Governorate. |
| 671 | `33066` | A — centers established in Al-Ahsa | 330 | Official title and description specify Al-Ahsa centers; brochure body is generic. |
| 1038 | `32289` | A — reservoirs located in Al-Ahsaa | 331 | Description explicitly places reservoirs in Al-Ahsaa; separate Asir procurement clause is not a site contradiction. |
| 1166 | `32430` | A — intracity service in Al-Ahsa | 332 | Title and description scope the bus service to Alahsa residents and users. |
| 1167 | `32429` | A — bus stations in Al-Ahsa | 333 | Description places the stations and supporting service in Al-Ahsa city. |
| 2358 | `54961` / `06-26-183737-46016` | A — named hospital lease site in Al-Ahsa | 334 | Opportunity text identifies Al-Ahsa Maternity and Children's Hospital; payload carries its official Furas link/reference. |
| 2359 | `54962` / `06-26-183737-46015` | A — named hospital lease site in Al-Ahsa | 335 | Opportunity text identifies Prince Saud bin Jalawi Hospital; payload carries its Furas link/reference. |
| 2360 | `54960` / `06-26-183737-46017` | A — named hospital lease site in Al-Ahsa | 336 | Opportunity text identifies King Faisal Hospital; payload carries its Furas link/reference. |
| 2361 | `54959` / `06-26-183737-46018` | A — named hospital lease site in Al-Ahsa | 337 | Opportunity text identifies Al-Omran General Hospital; payload carries its Furas link/reference. |
| 2362 | `54958` / `06-26-183737-46019` | A — named hospital lease site in Al-Ahsa | 338 | Opportunity text identifies the Mental Health Hospital; payload carries its Furas link/reference. |

The five kiosk rows have no coordinates; `siteArea=2` has no stated unit and was not treated as geographic evidence. The geographic decision comes from each official opportunity's named physical hospital site and its linked Furas opportunity reference. The referenced project PDFs for records 671, 1038, 1166, and 1167 are generic/title-only and were not treated as location evidence. The Envi-004 brochure is the only one that adds substantive location detail. Detailed record payloads, original descriptions, structured fields, references, review evidence, and resulting Master IDs are in [invest-saudi-11-adjudication.json](invest-saudi-11-adjudication.json).

The 14-row locality screen is also fully dispositioned in [locality-14-adjudication.csv](locality-14-adjudication.csv): the 11 above are class A; Invest Saudi 601 is class D, unqualified and pending review because its structured region is Al Madinah and its multi-city PDF is a placeholder; KFU 2775 is class C (campus procurement notice, not a local investment site); NCP 2810 is class B and now linked to the existing Master 228. Five earlier Invest Saudi eligibility cases outside those 11 (source row IDs 517, 524, 896, 897, 898) remain pending, unqualified, and unlinked; this acceptance did not rerun that broader location review. Nine other pending location reviews are on already-linked records and concern their individual locality/coordinate evidence.

NCP rows 2781 and 2810 have the exact same source, official article URL, title, and five-municipality scope including Al-Ahsa. Row 2810 was linked to Master 228 under the same-article alias rule, without changing its raw payload or observations. A `SOURCE_RECORD_IDENTITY_LINKED` event records the before/after Master IDs and reversible evidence in [ncp-2810-identity-link-audit.json](ncp-2810-identity-link-audit.json).

## Merge and duplicate integrity

- All 16 new false-split merges were rechecked against the live ledger: 16 valid, 0 pending, 0 incorrect.
- All 21 merged Masters (5 historical + 16 new) have a current surviving Master, evidence, source and child snapshots, audit lineage, and an available undo path. Their merge-audit rows are byte-for-byte unchanged by this targeted eligibility work.
- No confirmed false merge or confirmed duplicate remains unresolved. The 10 open duplicate cases remain ambiguous and correctly retained for review: 8 same-source and 2 cross-source. No confirmed-distinct pair remains in the open queue.
- The final state has 25 current Masters with more than one source listing (24 identity-confirmed; Master 230 remains the one fact-review case). Of these, 24 have multiple distinct portal sources; Master 228 has two NCP article aliases for the same project. Incorrect multi-source identities: 0.

## Reconciled current counts

```ini
FINAL_TOTAL_MASTER_ROWS = 308
FINAL_NON_MERGED_MASTERS = 287
FINAL_MERGED_MASTERS = 21
FINAL_SOURCE_OPPORTUNITIES = 2899

FALSE_SPLIT_MERGES_APPLIED = 16
NEW_MERGES_AUDITED = 16
NEW_MERGES_CONFIRMED_VALID = 16
NEW_MERGES_REVIEW_REQUIRED = 0
NEW_MERGES_CONFIRMED_INCORRECT = 0
TOTAL_MERGED_MASTERS_AUDITED = 21
MERGE_LINEAGE_COMPLETE = TRUE
MERGES_REVERSIBLE = TRUE

SOURCE_RECORDS_WITH_CURRENT_MASTER = 312
SOURCE_RECORDS_WITHOUT_CURRENT_MASTER = 2587
QUALIFIED_SOURCE_RECORDS = 312
QUALIFIED_SOURCE_RECORDS_WITH_CURRENT_MASTER = 312
QUALIFIED_SOURCE_RECORDS_WITHOUT_CURRENT_MASTER = 0
LITERAL_QUALIFIED_LOCATION_TRUE = 19
LITERAL_QUALIFIED_LOCATION_TRUE_UNLINKED = 0
NON_QUALIFIED_SOURCE_RECORDS_WITHOUT_MASTER = 2581
ELIGIBILITY_REVIEW_REQUIRED_SOURCE_RECORDS_WITHOUT_MASTER = 6
SOURCE_RECORDS_LINKED_TO_MULTIPLE_CURRENT_MASTERS = 0
CURRENT_MASTERS_WITH_ZERO_SOURCES = 0
SOURCE_ROWS_STILL_LINKED_TO_MERGED_MASTERS = 0

INVEST_SAUDI_AL_AHSA_TEXT_CANDIDATES_REVIEWED = 11
INVEST_SAUDI_CONFIRMED_AL_AHSA = 11
INVEST_SAUDI_MULTI_LOCATION_WITH_AL_AHSA = 0
INVEST_SAUDI_MENTION_ONLY_NOT_PROJECT_LOCATION = 0
INVEST_SAUDI_LOCATION_REVIEW_REQUIRED_WITHIN_11 = 0
ADDITIONAL_INVEST_SAUDI_601_REVIEW_REQUIRED = 1

MULTI_SOURCE_MASTERS_BY_SOURCE_RECORD_COUNT = 25
MASTERS_WITH_MULTIPLE_DISTINCT_PORTAL_SOURCES = 24
MULTI_SOURCE_IDENTITY_CONFIRMED = 24
MULTI_SOURCE_IDENTITY_REVIEW_REQUIRED = 1
MULTI_SOURCE_IDENTITY_INCORRECT = 0

DUPLICATE_REVIEW_QUEUE_OPEN = 10
CONFIRMED_DUPLICATES_LEFT_UNMERGED = 0
CONFIRMED_DISTINCT_PAIRS_IN_QUEUE = 0
CORRECTLY_RETAINED_FOR_REVIEW = 10
STRICT_ALL_SOURCEOPPORTUNITIES_CURRENT_MASTER_GATE_REMOVED = TRUE
```

`QUALIFIED_SOURCE_RECORDS=312` is the model-defined final set of current-master-linked source listings, including legacy listings without a literal qualification flag and the 12 targeted linkage decisions. The strict all-source gate is replaced by this eligible-source rule; it is not a claim that every unlinked national/general record was individually re-audited.

## Runtime, exports, tests, and scheduled-sync boundary

Live API and dashboard both report 287 current Masters; the API returns 287 unique Master IDs. CSV has 287 data rows and XLSX has 287 opportunity rows. Master 228 detail shows the NCP aliases together. Current results are in [current-api-export-reconciliation.json](current-api-export-reconciliation.json). The local app remains healthy.

The full regression suite was run after the final targeted corrections against a read-only project checkout and disposable test database: **185 passed / 0 failed** (one upstream Starlette/httpx deprecation warning). See [full-regression-targeted-eligibility-final.txt](full-regression-targeted-eligibility-final.txt).

Observation boundary: the fixed post-merge snapshot at 09:59:32 UTC had 11,150 observations. The natural scheduled-sync sequence reached 11,163 (+13) before the targeted eligibility run; latest job 379 was `SUCCESS`, `scheduled`, 164 records received, and 0 new/duplicate/merged source rows. The 11 accepted location reviews appended one source-status observation each, reaching 11,174. No observations were removed and no manual source sync ran.

The 11 qualification decisions added only the administrative location-review fields (`qualified_location`, confidence, method, and evidence); all original raw titles, descriptions, location and payload facts were preserved. The NCP alias link changed only its Master pointer and wrote the reversible system event. All 2,899 source rows and all 297 prior Master identities remain present; 11 genuinely new opportunity Masters were added. No merge ledger or source row was deleted.

## Required final assertions

```ini
MASTER_IDENTITY_DUPLICATE_CROSS_SOURCE_DEEP_REVIEW = COMPLETE
FINAL_TOTAL_MASTER_ROWS = 308
FINAL_NON_MERGED_MASTERS = 287
FINAL_MERGED_MASTERS = 21
FINAL_SOURCE_OPPORTUNITIES = 2899
FALSE_SPLIT_MERGES_APPLIED = 16
TOTAL_MERGED_MASTERS_AUDITED = 21
MERGE_LINEAGE_COMPLETE = TRUE
MERGES_REVERSIBLE = TRUE
MULTI_SOURCE_MASTERS = 25
MULTI_SOURCE_IDENTITY_CONFIRMED = 24
MULTI_SOURCE_IDENTITY_REVIEW_REQUIRED = 1
MULTI_SOURCE_IDENTITY_INCORRECT = 0
SOURCE_RECORDS_WITH_CURRENT_MASTER = 312
SOURCE_RECORDS_WITHOUT_CURRENT_MASTER = 2587
QUALIFIED_SOURCE_RECORDS = 312
QUALIFIED_SOURCE_RECORDS_WITH_CURRENT_MASTER = 312
QUALIFIED_SOURCE_RECORDS_WITHOUT_CURRENT_MASTER = 0
NON_QUALIFIED_SOURCE_RECORDS_WITHOUT_MASTER = 2581
ELIGIBILITY_REVIEW_REQUIRED_SOURCE_RECORDS_WITHOUT_MASTER = 6
SOURCE_RECORDS_LINKED_TO_MULTIPLE_CURRENT_MASTERS = 0
CURRENT_MASTERS_WITH_ZERO_SOURCES = 0
INVEST_SAUDI_AL_AHSA_TEXT_CANDIDATES_REVIEWED = 11
INVEST_SAUDI_CONFIRMED_AL_AHSA = 11
INVEST_SAUDI_MULTI_LOCATION_WITH_AL_AHSA = 0
INVEST_SAUDI_MENTION_ONLY_NOT_PROJECT_LOCATION = 0
INVEST_SAUDI_LOCATION_REVIEW_REQUIRED = 0
CONFIRMED_FALSE_SPLITS_REMAINING = 0
CONFIRMED_FALSE_MERGES_REMAINING = 0
DUPLICATE_REVIEW_QUEUE_OPEN = 10
CORRECTLY_RETAINED_FOR_REVIEW = 10
STRICT_ALL_SOURCEOPPORTUNITIES_CURRENT_MASTER_GATE_REMOVED = TRUE
MASTER_IDENTITIES_PRESERVED_OR_AUDITABLY_MERGED = TRUE
SOURCE_LINKS_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
MERGE_AUDIT_PRESERVED = TRUE
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
FULL_REGRESSION_SUITE = 185 passed / 0 failed
```

Machine-readable final summary: [final-identity-eligibility-reconciliation.json](final-identity-eligibility-reconciliation.json). The previous strict-all-source blocker has been removed and replaced by the qualified-population gate.

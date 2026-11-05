# Owner Completion Deep Dive

**Result: COMPLETE**  
**Start snapshot:** 2026-10-19 12:11:28.818998 UTC  
**Final snapshot:** 2026-10-19 15:16:16 +03:00

This audit is limited to the 111 non-merged Masters currently displayed as غير محدد. The accepted Owner / Publisher / Entity review was not reopened. Masters 102 and 230 were outside this set and were not changed. No owner assignment was added because none of the inspected sources contained clear item-level owner evidence.

## A. Exact target set

The set was selected from non-merged Masters with a null/blank Master owner and independently matched the live API filter owner:missing count of 111. It contains 110 ordinary unspecified Masters plus review-required Master 228. Exact Master IDs:

1, 2, 3, 4, 5, 6, 7, 8, 9, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 194, 196, 197, 198, 199, 200, 201, 202, 203, 204, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223, 228, 236, 238, 241, 243, 245, 247, 250, 252, 254, 256, 259, 261, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 273, 274, 275, 276, 277

Each row’s title, linked SourceOpportunity ID, source, platform, raw payload, descriptions, URL and adapter owner projection is preserved in [target-evidence-inventory.jsonl](target-evidence-inventory.jsonl). Per-Master classification and rationale are in [target-owner-classification.csv](target-owner-classification.csv); IDs are in [target-master-ids.txt](target-master-ids.txt).

| Value | Start | Final |
|---|---:|---:|
| Total Master rows | 296 | 296 |
| Non-merged Masters | 291 | 291 |
| Displayed unspecified target | 111 | 111 |
| SourceOpportunity rows | 2,898 | 2,898 |
| Observations | 10,527 | 10,527 |
| Open owner review cases | 3 | 3 |

There are 111 target Masters and 111 source links, one source record per Master. No target has cross-source corroboration. Master identity, Master-source links, source raw payloads, observation raw payloads, owner assignments and owner-review case fingerprints match start/end. Latest job is scheduled sync 348, completed before this task’s snapshot; no sync ran during this task. No manual sync was started. Snapshots: [start](start-snapshot.json) and [final](final-snapshot.json).

## B. Target source distribution

| Source | Count | Master IDs | Finding |
|---|---:|---|---|
| Al-Ahsa Investment Platform | 97 | See [distribution](target-source-distribution.csv) | Listing/site metadata only; no item-level owner field. |
| AHDA | 7 | 211–217 | Narrative support/funding mentions; no clear owner. |
| Invest Saudi | 6 | 218–223 | No owner evidence in raw opportunity records or attached brochures. |
| NCP | 1 | 228 | Parser-derived candidate remains ambiguous and queued. |
| Furas | 0 | — | No target link. |
| MODON | 0 | — | No target link. |
| NHC | 0 | — | No target link. |
| KFU | 0 | — | No target link. |
| PIF | 0 | — | No target link. |
| MWAN | 0 | — | No target link. |

## C. Raw evidence review and safe source rules

All 111 linked records were inspected through their raw JSON, titles, descriptions/raw text, URLs and SourceOpportunity owner projections. Field paths and text candidates are in [raw-field-findings.jsonl](raw-field-findings.jsonl); the full payloads are in target-evidence-inventory.jsonl.

- **Al-Ahsa Investment Platform (97):** Raw keys are details, source/page, category counts and taxonomy. Details contain site, area, activity/category, contract term and deadline; no owner, agency, issuer, authority or responsible-entity field. Titles describe leases/sites/assets, not who owns or grants them. Portal identity is not owner evidence. All 97 remain unspecified.
- **AHDA (7):** No structured owner field. Raw text mentions government support, funds, ministries and sector enablers, not the responsible owner. For example, Master 211 mentions Education/Investment ministries and HRDF as support; 212/217 mention tourism bodies/fund support; 214 mentions Health/Education support. None uses clear ownership or offering language. AHDA platform identity is not evidence. All seven remain unspecified.
- **Invest Saudi (6):** Inspected raw opportunity-family fields include backed_by, contact_details, inner_data, description, source family, source identifiers and nested observations. backed_by is blank; contact_details and inner_data are empty; no owner/agency/company/responsible-entity field is present. Descriptions discuss operators, investors and market opportunities without naming the owner. All six linked brochures were also downloaded read-only and text-extracted: RECY-028, RECY-029, RECY-030, RECY-065, RECY-066 and RECY-067. Their "Key Stakeholders" panels list participating/regulatory or market entities, not an opportunity owner. Ministry of Investment is identified in the materials as publisher/contact and disclaimer author, not as the owner of these individual assets. The stored SourceOpportunity.source_owner value وزارة الاستثمار is a pre-review adapter projection, not item-level ownership evidence; the current adapter sets this source family’s owner to null. All six remain unspecified.
- **NCP (1):** Master 228 raw payload has project_owner_candidate = “the Ministry of Municipalities”. This is parser-derived from article wording, not a structured source owner. The announcement says MOMAH and NCP launched an EOI, describes operation across five municipalities, and invites operators/investors; it does not settle owner/grantor versus publisher/announcer or the role of participating municipalities. Do not assign the Ministry; retain review.
- **Furas:** Its accepted source rule is AMANA as owner evidence, with ENTITIESNAME as publishing/registered-entity context when AMANA is present. There are no Furas-linked target Masters.
- **MODON, NHC, KFU, PIF and MWAN:** No target links; their source identity or any related-company/publisher field was not used as owner evidence.

The only non-empty raw owner-like field across the target is NCP’s parser-derived candidate. The NCP adapter itself treats collaboration wording as insufficient and creates its RawOpportunity with owner=None. Older source projections remain on seven AHDA rows (platform default), six Invest Saudi rows (Ministry of Investment fallback), and the NCP candidate; none is treated as Master owner evidence. All 97 Al-Ahsa portal source owner projections are null. No target description/title provides explicit, unambiguous owner phrasing. No raw payload was changed, and no new canonical owner or alias was created.

## D. Master 228 and review queue

MASTER_228 = CORRECTLY_RETAINED_FOR_REVIEW. It displays غير محدد; owner conflict 120 remains open. The parser candidate and bilingual announcement do not settle owner versus publisher/announcer or contracting municipality. No guessed owner was assigned.

Target review cases resolved: 0. Target review cases retained: 1 (Master 228). Masters 102 and 230 are outside this target and unchanged.

## E. Classification and owner totals

| Target classification | Count |
|---|---:|
| RESOLVED_WITH_EXPLICIT_EVIDENCE | 0 |
| RESOLVED_WITH_CROSS_SOURCE_EVIDENCE | 0 |
| CORRECTLY_RETAINED_UNSPECIFIED | 110 |
| REVIEW_REQUIRED | 1 |
| **Sum** | **111** |

Global totals remain 178 confirmed, 110 ordinary unspecified and 3 review-required (102, 228, 230). UI/API displays 111 as غير محدد because Master 228 has no displayable owner.

## F. Filter, list, details and exports

The live API and كل الجهات filter expose exactly four specified canonical owners plus غير محدد. All five options are distinct, with zero alias duplicates. Counts reconcile: Amanah 175, KFU 3, Ministry of Environment 1, National Guard 1, missing 111. owner:missing returns 111; the unfiltered opportunity list returns 291.

The table retains الجهة المالكة. Master 228 details display غير محدد and separate owner from platform/publisher/operator. CSV and XLSX each contain 291 Masters and 111 unspecified owners. Playwright verified options, owner column, Master 228, filter, reset, search, pagination, details, CSV/XLSX, RTL and no horizontal overflow at 1920×1080, 1440×900, 1366×768, 768×900 and 390×844. Results and screenshots are in [playwright-results.json](playwright-results.json) and [screenshots/](screenshots/).

## G. Tests and data safety

Full regression after this audit: **158 passed / 0 failed**, with one existing Starlette/httpx deprecation warning. Tests used isolated in-memory SQLite fixtures with Redis disabled and did not write to the live PostgreSQL business database. The suite was rerun against a fresh copy of the current app/tests/scripts/docs at 2026-10-19 15:20 Asia/Amman; exact command and output: [full-regression-results.txt](full-regression-results.txt).

No owner values, Masters, source links, raw payloads, observations or review cases were modified. No new canonical owner/alias was created. Start/end fingerprints match and no manual source sync ran.

## Final assertions

OWNER_COMPLETION_DEEP_DIVE = COMPLETE
START_TARGET_DISPLAYED_UNSPECIFIED = 111
TARGET_RESOLVED_WITH_EXPLICIT_EVIDENCE = 0
TARGET_RESOLVED_WITH_CROSS_SOURCE_EVIDENCE = 0
TARGET_CORRECTLY_RETAINED_UNSPECIFIED = 110
TARGET_REVIEW_REQUIRED = 1
TARGET_RECONCILIATION_SUM = 111
FINAL_OWNER_CONFIRMED_MASTERS = 178
FINAL_OWNER_UNSPECIFIED_MASTERS = 110
FINAL_OWNER_REVIEW_REQUIRED_MASTERS = 3
FINAL_DISPLAYED_UNSPECIFIED_OWNER_COUNT = 111
NEW_CANONICAL_OWNERS_CREATED = 0
FINAL_CANONICAL_SPECIFIED_OWNER_COUNT = 4
MASTER_228 = CORRECTLY_RETAINED_FOR_REVIEW
OWNER_FILTER_RECONCILIATION = PASSED
OWNER_ALIAS_DUPLICATES_IN_FILTER = 0
OPPORTUNITIES_TABLE_OWNER_RECONCILIATION = PASSED
DETAIL_PAGE_OWNER_RECONCILIATION = PASSED
CSV_OWNER_RECONCILIATION = PASSED
XLSX_OWNER_RECONCILIATION = PASSED
OWNER_REVIEW_CASES_RESOLVED = 0
OWNER_REVIEW_CASES_RETAINED_IN_TARGET = 1
INTENTIONAL_OWNER_COMPLETION_CORRECTIONS = 0
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_LINKS_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
MANUAL_SOURCE_SYNC_STARTED = FALSE
FULL_REGRESSION_SUITE = 158 passed / 0 failed

# Ta’adeen mining bids integration — 2026-11-03

## Result

**TAADEEN_INTEGRATION=COMPLETE**  
**TAADEEN_ADAPTER_IMPLEMENTED=TRUE**  
**TAADEEN_SOURCE_CAPTURE=COMPLETE**  
**TAADEEN_MASTER_PROMOTION=NONE**

Ta’adeen is integrated as source `taadeen-mining-bids` (source ID 14). The adapter enumerates the official paginated [Mining Bids catalog](https://cms.taadeen.sa/en/mining-bids), then captures round/plan context and individual site or belt bid detail pages. The official [Round 11 page](https://cms.taadeen.sa/en/mining-bids/round-11) describes one round-level PQQ window and eight sites; each site detail is represented as a child bid record with its own URL identity and status.

## Source model and coverage

- **Extraction:** `PUBLIC_PAGINATED_HTML_WITH_ROUND_AND_SITE_DETAIL_PAGES`; no credentials, login, restricted endpoint, or file-download/geocoding step was used.
- **Enumeration:** 4 catalog pages, 4 public round/plan pages (Rounds 9, 10, 11, and the 2026–27 preliminary plan), and 28 unique site/belt detail pages; 36/36 pages succeeded. Three numbered bid rounds are represented. Round 11 has one parent and eight distinct site children.
- **Identity:** `round_id` is the official round route slug; site identity uses the canonical public detail URL slug, namespaced by round when present. All 28 provider IDs are unique. No title-only identity match was used.
- **Provenance:** Original page lines, source/detail URLs, source status, dates/stages, parent-round context, regions, areas, minerals when explicitly published, document URLs, and application links remain in the raw source payload. Publisher is `Ta'adeen Platform`; the licensing authority/owner is left null when a detail record does not establish it.
- **Geography:** Published region labels are retained as source text. There are zero direct numeric coordinate pairs in the captured HTML; no coordinates or city/governorate values were fabricated, and no map files were downloaded or geocoded.
- **Lifecycle:** The Round 11 parent page still labels the round Active, gives a PQQ deadline of 2026-07-31, and lists eight sites. All eight child detail records are Inactive and the deadline has passed as of 2026-11-03. Parent-round status and child-site status remain separate. All 28 site/belt records are historical/non-current for promotion; this does not imply cancellation.
- **Representation:** `PARENT_WITH_SITE_CHILDREN` for numbered rounds; standalone detail records are retained when the public catalog does not expose a numbered parent. All 28 rows remain source-only and unlinked. No current or historical Master was created.

## Controlled live capture

Exactly one manual Ta’adeen sync was run: job **762**, status `SUCCESS`, state `COMPLETED`, trigger `manual`. It captured 28 unique rows from 36 successful pages (100% complete), with zero removals and zero duplicate provider keys. First-run/bootstrap removals were disabled.

A post-capture parser correction updated 12 source rows using only their already-captured raw page lines: three records now carry the published Arabic mineral `بحص`; nine records have minerals set to null because their detail pages publish no minerals field. The original raw lines and all document/source evidence were preserved, and each corrected record carries correction provenance. All 28 persisted content hashes were reconstructed and verified after correction. This was a data correction, not another sync; no second Ta’adeen job was created.

The source filter is present. The existing current-opportunity query for this source returns **0**, consistent with the current-only view and the closed/inactive child records. The source reports **HEALTHY**, **FRESH**, `COMPLETE_FOR_DEFINED_SCOPE`, 28 captured records, and 36/36 successful pages despite having no current Master opportunities. Polling is configured for 1,440 minutes; the scheduler container is running. Exactly one Ta’adeen job exists. No other manual sync was initiated for this task. The Al-Ahsa job 763 was scheduler-triggered during environment startup, not manually initiated; pre-existing manual jobs are outside this integration.

## Master eligibility and protected sources

The read-only dry run in [TAADEEN-MASTER-ELIGIBILITY-DRY-RUN-20261103.json](TAADEEN-MASTER-ELIGIBILITY-DRY-RUN-20261103.json) classifies all 28 rows exactly once as historical/non-current: A ready new Master 0; B existing Master match 0; C identity review 0; D not qualifying 0; E historical/non-current 28; F same-source duplicate review 0. Existing Master links are 0; current Masters created 0; historical Masters created 0; fabricated coordinates 0.

The pre-capture PostgreSQL logical backup was restore-tested in an isolated PostgreSQL 16 container: `backups/pre-taadeen-20261103.dump`, 61,900,063 bytes, SHA-256 `5E77C7686ED24FBF4E20B9653D81B24047DEF8F5EE89D43B3E13456969B2E140`. Restore totals were 6,678 opportunities, 9,439 source opportunities, and 13 sources. No schema migration was needed. Final canonical Master count remains 6,657 (6,678 total opportunity rows including merged records).

Protected integrations remain in place: RCJY 3 source rows / 3 linked; RCU 6 / 6 linked; NCP 185 source rows / 27 linked. No Furas sync was manually run; Furas was not changed for this task. Tourism was not attempted.

## Validation

- Ta’adeen focused adapter tests after the final parser change: **2 passed**.
- Full regression: **687 passed, 1 justified skip, 0 failed**. The full run used `pytest-asyncio` installed temporarily inside the test container; it was not added as a project dependency. The latest parser-specific change was then verified by the focused Ta’adeen suite.
- Full platform DQ (`72e03888c409441385983b6cf99b6ec8`, scope `full`): **127 PASS / 7 WARNING / 0 FAIL** (the same warning count as the accepted baseline; no failing gates). Warnings remain in the existing baseline categories: generic source page as opportunity, open review backlog, historical review audit incompleteness, stale source success, sync runtime anomaly, source absence classification, and unknown area stored as zero.
- API liveness and readiness: **200**; readiness checks for database, Redis, and worker are `ok`.

## Stop boundary

Ta’adeen integration and validation are complete. Tourism and unrelated source integrations were not attempted.

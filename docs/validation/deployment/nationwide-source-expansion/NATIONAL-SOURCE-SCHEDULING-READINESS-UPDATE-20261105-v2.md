# National Source Scheduling Readiness Update — Furas Evidence Recovery v2 — 2026-11-05

**Generated after validation completion: 2026-11-05 08:25:51 UTC.** This version supplements rather than replaces the prior 2026-11-05 readiness report.

## Source status

| Source | Technical health | Freshness | Public coverage | Scheduling status |
|---|---|---|---|---|
| Furas | WARNING in live source registry; isolated national capture is technically complete | Persisted source sync remains stale since 2026-11-02; read-only national capture completed 2026-11-05 07:56 UTC | 6,548 public records captured; identity uncertainty remains for 603 of 678 unmatched IDs | National enumeration remains disabled; no pilot |
| MODON | WARNING / operationally blocked by MISSING_INTERMEDIATE_CA already established in prior investigation | Stale; strict TLS verification still blocks the configured source path | Public coverage not newly verified | No status changes or syncs in this task |
| NHC | WARNING, latest stored job reports 403 access restrictions and parser_failures=0 | Stale from last successful observation 2026-10-12 | PUBLIC_COVERAGE_LIMITED; no itemized unauthenticated inventory | Scheduled monitoring unchanged; no parser or access-control bypass |
| Other sources | No adapter or source-health changes in this task | Not re-synced | Existing scope retained | No source schedule changes |

Dimensions are independent: the Furas shadow capture is complete while the persisted source freshness is stale. Its local source warning is not overwritten by the isolated capture.

## Durable capture and set lineage

The complete read-only Furas capture is at FURAS-NATIONAL-DURABLE-CAPTURE-MANIFEST-20261105.json:

- 6,548 raw OPPORTUNITYID values; 6,548 unique provider IDs and 6,548 unique OBJECTIDs.
- 66 data pages and 70 observed HTTP requests, all 200. The adapter's internal request metric is 69 because the layer metadata GET is not included in that internal counter; the request recorder retains all 70.
- Pagination complete; zero duplicate provider IDs and zero missing OBJECTIDs.
- All full raw attributes and geometry, source status, title, detail URL, raw location/date fields, request response hashes, per-record hashes, page membership, and the sorted provider-ID/OBJECTID and ordered-index checksums are retained.
- The current provider-ID set exactly equals the previous 6,548 repeat ID set (0 added, 0 missing). All 678 previously retained unmatched raw attribute objects also equal the new capture's corresponding raw attributes. The previous matched 5,870 full payloads were not retained, so no payload-change statement is made for them.
- Against the previous national job 694 checkpoint set C: current capture A has 5,869 IDs in A∩C, 679 in A−C; checkpoint C has 615 IDs in C−A. This is membership comparison only; missing from the current date-filtered snapshot is not interpreted as expired, cancelled, or removed.
- Against current Furas SourceOpportunity set B (6,546): A∩B=5,870, A−B=678, B−A=676.

The original 6,511/641 population remains UNRECOVERABLE_ORIGINAL_RECORD_EVIDENCE. Its 5,870 aggregate matches are not assumed to be the same identities as the new capture's 5,870 matches.

## Identity and eligibility outcome

The 678 primary classifications sum exactly:

- VERIFIED_EXISTING_SOURCE_IDENTITY: 75. Official retained Invest Saudi records contain matching opportunityNumber and direct Furas links. Each has one old Furas source row, two historical raw observations retaining the prior provider key, same OBJECTID and CREATED_DATE, equal geometry, and raw attributes differing only by OPPORTUNITYID/LAST_EDITED_DATE. Each old row is linked to a current unmerged Master. Alias mappings remain proposals and have not been applied.
- UNRESOLVED_REVIEW_REQUIRED: 603. This includes the remaining 271 of the 346 OBJECTID/title candidates and 332 records without a current same-OBJECTID Furas row. Four of the latter have an explicit Invest Saudi cross-reference but no historical Furas row/current Master; they remain review-required.
- Other verified categories: 0. No genuinely new current Master candidate is asserted. No record is promoted.

The full per-record evidence, candidate source/Master IDs, raw geography/date evidence, source observation IDs/hashes, conflict reasons, and proposed actions are in FURAS-678-IDENTITY-ADJUDICATION-20261105.json. Every uncertain record remains unpromoted.

## Validation results

- Focused Furas identity, adapter, lifecycle, ingestion, alias, cross-source and checkpoint tests: **162 passed, 1 skipped, 0 failed**.
- Full DQ, read-only business snapshot: **128 PASS, 6 WARNING, 0 FAIL**. Snapshot: 6,657 current Masters, 6,678 total Master rows including 21 merged rows, 9,468 SourceOpportunity rows, 52,485 observations, 14 configured sources, 13 enabled sources, 12 open reviews, expected Alembic head 0025. Current Master/source links are preserved.
- Full isolated regression: **703 passed, 1 skipped, 0 failed**. Initial environment attempt omitted pytest-asyncio and had four async collection failures; the final run installed it inside the disposable test container and passed.
- API health/readiness both HTTP 200; database, Redis and worker readiness checks OK. API/PostgreSQL/Redis containers healthy; worker and scheduler running.
- National UI/map flags are TRUE. Furas national enumeration and removal flags are FALSE.
- No production sync, Master promotion, source-link change, merge, removal, schedule change, or business-data mutation occurred.

## Readiness decision

FURAS_CONTROLLED_PILOT_READY = FALSE.
FURAS_CONTROLLED_PILOT = NOT_RUN.

Required before reconsideration:

1. Recover the original 6,511/641 member-level artifact from its operator/archive, or submit an explicit acceptance-baseline amendment for approval. The prospective 6,548 capture does not waive the historical requirement.
2. Obtain governed approval before applying any of the 75 proposed alias mappings.
3. Keep the remaining 603 in explicit review/source-only quarantine; do not promote them.
4. Continue to preserve Furas raw date semantics until provider documentation supports canonical lifecycle mapping.

National scheduling remains PARTIAL; no production activation stage is authorized by this report.

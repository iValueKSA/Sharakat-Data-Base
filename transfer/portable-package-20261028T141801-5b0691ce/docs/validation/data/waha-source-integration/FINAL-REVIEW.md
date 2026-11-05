# Waha Development Source Coverage Review

Review date: 2026-10-26

## Decision

The official Waha public surfaces were inspected. The public Opportunities page currently displays no available itemized investment or tender offers. The Invest With Us page contains general themes and points investors to registered or authenticated deal flow. No authenticated pages were accessed.

The public map API returns 58 location features: 49 land parcels and 9 project locations. All have a title, coordinates, and area. The source status is 48 vacant, 9 invested, and 1 blank. No feature has an opportunity ID or detail URL. The source's computed status says available for all 58, including invested locations; that contradiction is preserved and is not interpreted as an active offer. The page itself currently says Coming Soon.

The public projects API has six unique project records. Five are named Waha initiatives; one is explicitly labelled Test Project and excluded from the project count. None has an opportunity ID. These are portfolio or case-study records, not investable offers.

The older public Waha_clean.json contains 84 features and conflicts with the location API's 58. It is treated as a legacy map asset and not as the current inventory. A raw copy of the current 58-feature API response and a field-preserving location snapshot are retained in this folder for source evidence only; neither was imported into the business database.

The source was added to the official source catalog as key waha-development with PUBLIC_COVERAGE_LIMITED. It is disabled, has no adapter, no last-success timestamp, and no sync action in the source card. It appears in the official sources list, health display, coverage counters, source filter, and source metrics with zero opportunity records. The source API reports sync_supported=false. This keeps Waha independent from Furas while avoiding an invented opportunity integration.

## Furas identity check

One existing Furas record is associated with Waha metadata: source record 2779, official Furas number 06-26-185611-16001, attached to Master 227. Its source owner is أمانة الأحساء; the raw publisher/entity field names شركة واحة للتنمية والتطوير; its publication platform is Furas. The public Waha project and location inventories contain no matching official opportunity ID or exact project reference. The Waha entity field and similar wording do not prove a second Waha opportunity record. The existing Furas row and Master were left unchanged.

Therefore WAHA_ONLY=0, FURAS_ONLY=1 associated candidate, CROSS_SOURCE_MATCHED=0. The Furas-only count is not a claim that Waha owns the opportunity; the row explicitly names the Municipality as owner.

## Source catalog and business-data checks

- Waha source key: waha-development; source ID 11; enabled=false; technical health=UNKNOWN; coverage=PUBLIC_COVERAGE_LIMITED; last successful scan=null.
- Al-Ahsa Investment Platform remains configured once as alahsa-opportunities at https://alahsa-opportunities.com/.
- Before the catalog change there were 10 sources; after it there are 11, with exactly one Waha source and one Al-Ahsa platform source.
- No Waha SourceOpportunity, Master, duplicate candidate, or Waha review was created. No existing Master identity was changed. No fuzzy-title match or merge occurred.
- Opportunity table rows stayed at 587; source opportunity rows stayed at 3,178. Source observations rose from 25,180 to 25,239 during two independently scheduled existing-source scans; the source job records show zero new, updated, or removed opportunity records.
- Manual source sync started=false. No Waha sync ran.

## Scheduled jobs that ran during this review

The existing scheduler independently ran Job 505 for alahsa-opportunities and Job 506 for Furas at 2026-10-26 08:03 UTC. Both were scheduled, successful, and reported zero new, updated, or removed records. They were not manually triggered by this task, and neither was a Waha job.

Those scans opened 386 existing-source conflict/review cases: 7 Al-Ahsa taxonomy conflicts; 23 Furas field conflicts; 336 Furas standardization reviews; and 20 Furas taxonomy conflicts. No review was resolved, closed, or edited by this task. These new unrelated cases now block the required live DQ closeout. Their evidence is in scheduled-job-side-effects.json.

## Validation

- Focused tests: 11 passed, 0 failed.
- Full isolated regression on the final API image: 528 passed, 0 failed. The suite used temporary SQLite in a Docker container with networking disabled; it did not use live PostgreSQL.
- Live read-only full DQ after the scheduled scans: 116 gates; 109 PASS, 5 WARNING, 2 FAIL. The run used persist=false.
- All five Waha DQ gates pass at zero: WAHA_GENERIC_CONTENT_INGESTED, WAHA_FURAS_DUPLICATE_MASTER, WAHA_MISSING_PROVENANCE, WAHA_OWNER_PUBLISHER_CONFUSION, and WAHA_UNRECONCILED_SOURCE_RECORD.
- The two live DQ failures are OPEN_ACTIONABLE_REVIEW_BACKLOG=386 and AUTONOMOUS_REVIEW_LEFT_UNRESOLVED=386. They are from Jobs 505 and 506 on the existing Al-Ahsa and Furas sources, not Waha. The 5 warnings are the 782 generic source-page records, 386 open conflicts, 120 historical review audit rows, one aggregated freshness gate covering MODON/NHC/MWAN, and one runtime-anomaly gate covering Jobs 496, 500, 393, and 497.
- The sources, coverage, filters, and opportunity-list APIs returned HTTP 200 after deployment. The source filter for waha-development returns 0 opportunities; Waha appears with zero records in source coverage and source filters. The UI omits sync controls for sources without an adapter.
- A visual browser capture could not be completed: the Windows browser automation stopped because it could not verify the active browser URL with sufficient confidence. API and served UI contracts were checked directly.
- Services are healthy after rebuilding/recreating only API and frontend. PostgreSQL, Redis, worker, and scheduler were not restarted.

## Final assertions

WAHA_SOURCE_INTEGRATION = COMPLETE

WAHA_PUBLIC_COVERAGE_TYPE = PUBLIC_INVESTMENT_LOCATIONS_AND_PROJECT_PORTFOLIO; NO_PUBLIC_ITEMIZED_OFFERS
WAHA_COVERAGE_STATUS = LIMITED_PUBLIC_COVERAGE
WAHA_PUBLIC_ITEMIZED_OPPORTUNITIES = 0
WAHA_PUBLIC_INVESTMENT_LOCATIONS = 58
WAHA_PUBLIC_PROJECTS = 5
WAHA_ENUMERATED = 0
WAHA_SOURCE_RECORDS = 0
WAHA_NEW_MASTERS = 0
WAHA_LINKED_TO_EXISTING_MASTERS = 0

CURRENT_FURAS_WAHA_RECORDS = 1
CURRENT_FURAS_WAHA_MASTERS = 1
WAHA_ONLY = 0
FURAS_ONLY = 1
CROSS_SOURCE_MATCHED = 0
WAHA_FURAS_DUPLICATE_MASTERS = 0
FUZZY_TITLE_ONLY_MERGES = 0

DQ_WAHA_GENERIC_CONTENT = 0
DQ_WAHA_FURAS_DUPLICATE_MASTER = 0
DQ_WAHA_MISSING_PROVENANCE = 0
DQ_WAHA_OWNER_PUBLISHER_CONFUSION = 0
DQ_WAHA_UNRECONCILED_SOURCE_RECORD = 0

ALAHSA_INVESTMENT_PLATFORM_ALREADY_CONFIGURED = TRUE
ALAHSA_PLATFORM_EXISTING_SOURCE_KEY = alahsa-opportunities
ALAHSA_PLATFORM_DUPLICATE_SOURCE_CREATED = FALSE

FOCUSED_TESTS = 11 passed / 0 failed
FULL_REGRESSION_SUITE = 528 passed / 0 failed
LIVE_DQ_TOTAL = 116
LIVE_DQ_PASS = 109
LIVE_DQ_WARNING = 5
LIVE_DQ_FAIL = 2

MANUAL_SOURCE_SYNC_STARTED = FALSE
WAHA_SOURCE_SYNC_STARTED = FALSE
WAHA_REVIEW_CASES_CREATED = 0
WAHA_BUSINESS_DATA_CHANGES = 0
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0

## Post-sync review backlog closeout

On 2026-10-26, Jobs 505 (Al-Ahsa Investment Platform) and 506 (Furas) were traced. They were scheduled, successful, and were not manually triggered. Job 505 created seven OPEN taxonomy review rows. Job 506 created 390 conflict rows; 11 taxonomy rows were already closed by current-evidence stale review, leaving 379 OPEN. The combined actionable population was 386.

Of the 386 open cases, 381 exactly matched conflicts already resolved by a prior audited SYSTEM decision. The old generator checked only for matching OPEN rows and did not consult terminal resolution history. Five further cases were first surfaced by the Phase 2 taxonomy rules: four contained cross-source activity/sub-activity differences between Furas and Al-Ahsa records, and one had an unmapped source classification. Those five were not prior resolved duplicates and were conservatively kept without canonical changes.

The approved autonomous resolver closed all 386 in one validated batch: 385 KEEP_CURRENT_CANONICAL, one stale review superseded, zero canonical changes, zero merges. The source and master rows were not changed or deleted. Business fingerprints before and after match. Every resolution has SYSTEM audit. The new scheduled path computes semantic review fingerprints, reuses terminal conflicts when evidence is materially unchanged, resolves actionable reviews, records fast post-sync DQ and lifecycle metrics, then finalizes the successful job. Material source/canonical/evidence changes remain eligible for reevaluation.

Live read-only full DQ after resolution and deployment: 121 gates, 117 PASS, 4 WARNING, 0 FAIL. The five new post-sync gates all PASS at zero. Existing warnings remain limited to the generic source-page links, historical pre-versioned review audit, source freshness, and historical sync runtime anomalies. Waha coverage/data were not changed.

The updated API and worker are ready. PostgreSQL, Redis, and the scheduler remained running. No manual source sync ran; no natural sync occurred during this task. Final details and the per-review trace are in `docs/validation/data/post-sync-autonomous-resolution/FINAL-REVIEW.md` and the adjacent JSON evidence.

WAHA_SOURCE_INTEGRATION = COMPLETE

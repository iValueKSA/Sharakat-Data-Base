# Al-Ahsa 118 Geographic Scope Correction — 2026-11-11

## Decision

**ALAHSA_118_GEOGRAPHIC_CORRECTION = APPLIED_AND_VERIFIED**

The user-designated live stack was `alahsa-local` at `http://localhost:8080/`. The API runtime reports `ENVIRONMENT=local_user`; this report preserves that runtime label rather than describing it as a separately hosted production environment. No application code, frontend assets, schema, boundaries, eligibility rules, or source schedules were changed.

## Acceptance results

| Check | Result | Evidence |
|---|---|---|
| Production backup | PASS | Custom-format PostgreSQL 16.15 dump restored in an isolated disposable instance. |
| Approval artifact | PASS | 118 approved, unique Master IDs; Master 64 held out; CSV SHA-256 matches its manifest. |
| Live revalidation | PASS | All 118 records matched the approved identities, existing coordinates, source links, Al-Ahsa governorate 501 / region 5 and review gates. |
| Atomic correction | PASS | Transaction 7902 committed once at SERIALIZABLE isolation; exactly 118 rows updated. |
| Scope transition | PASS | Exactly 118 `UNSPECIFIED -> SPECIFIC_LOCATION`; no other approved-row field changed. |
| Coordinate / geography preservation | PASS | 0 coordinate, region, or governorate changes. |
| Identity preservation | PASS | Master and SourceOpportunity identities and links remained unchanged; 118 source rows and their observation counts were guarded in the transaction. |
| Held / excluded records | PASS | Master 64 unchanged; the other 372 excluded records unchanged (302 source-filter, 55 boundary-conflict, 15 regional-failure records). |
| Map API | PASS | 145 unique exact-mapped Al-Ahsa Master IDs; all 118 approved plus all prior 27; Master 64 excluded; no extra or duplicate IDs. |
| API coordinates | PASS | Each approved ID’s returned point matches the existing source geometry within `0.000001°`; maximum observed delta `0.00000005°`. |
| Frontend map | PASS | Existing dashboard/map loaded at localhost; Eastern Region filter rendered 975 opportunities and 495 map points; tiles and attribution rendered; a cluster click expanded the map to smaller clusters. |
| Data integrity | PASS | Masters 6,680 total / 6,659 non-merged / 21 merged; Al-Ahsa remains 518; SourceOpportunities 9,470; SourceObservations 57,581. Counts match the pre-write snapshot. |
| Safety flags | PASS | Furas enumeration, Furas removals and RCU scheduled sync remain disabled; 0 unfinished sync jobs; no sync was triggered. |
| Runtime services | PASS | API readiness returned `ready`; all six `alahsa-local` services remain running. Services restarted: 0. |

### Scope counts

Among non-merged Masters, `SPECIFIC_LOCATION` increased from 6,066 to 6,184; `UNSPECIFIED` decreased from 591 to 473; the 2 null-scope records were unchanged. The 118 approved Masters are the only scope changes.

### Other deployment state

Migration head remains `0026_source_identity_aliases`. The existing Furas alias state remains 75 active aliases and 75 audit rows. No alias or migration operation was performed by this correction.

### Frontend observation

The dashboard’s governorate dropdown appeared disabled while the Eastern Region view was selected. The region filter, map tiles, cluster rendering and cluster zoom interaction worked. The Al-Ahsa-specific eligibility result was verified directly against the live governorate map endpoint. No frontend change was made. No visual rendering or clustering error appeared; browser console logs were not separately inspected.

## Mutation and recovery summary

- **Production data mutations:** 118 approved `opportunities.geographic_scope` values only.
- **Unauthorized Master mutations:** 0.
- **SourceOpportunity / SourceObservation mutations:** 0.
- **New or merged Masters:** 0.
- **Rollback:** not executed.
- **Services restarted:** 0.

## Evidence files

- `evidence/alahsa-119-adjudication-20261111/production-backup-verification.json`
- `evidence/alahsa-119-adjudication-20261111/live-118-prewrite-revalidation.json`
- `evidence/alahsa-119-adjudication-20261111/live-372-other-exclusions-prewrite.json`
- `evidence/alahsa-118-production-correction-20261111/production-transaction-result.json`
- `evidence/alahsa-118-production-correction-20261111/postwrite-database-check.json`
- `evidence/alahsa-118-production-correction-20261111/live-api-postwrite-verification.json`
- `evidence/alahsa-118-production-correction-20261111/live-api-identity-coordinate-verification.json`
- `evidence/alahsa-118-production-correction-20261111/live-frontend-map-verification.json`
- `evidence/alahsa-118-production-correction-20261111/apply-approved-118-scope-correction.sql`

## Final status

`PRODUCTION_BACKUP=PASS` · `APPROVAL_ARTIFACT_VALIDATION=PASS` · `LIVE_118_REVALIDATION=PASS` · `ATOMIC_CORRECTION=PASS` · `COORDINATE_PRESERVATION=PASS` · `IDENTITY_PRESERVATION=PASS` · `HELD_RECORD_PRESERVATION=PASS` · `MAP_API_ELIGIBILITY=PASS` · `FRONTEND_MAP_HEALTH=PASS` · `UNAUTHORIZED_DATA_MUTATIONS=ZERO`

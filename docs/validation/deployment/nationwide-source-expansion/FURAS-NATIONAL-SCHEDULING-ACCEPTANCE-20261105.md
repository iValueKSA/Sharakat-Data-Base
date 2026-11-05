# Furas national scheduling acceptance — 2026-11-05

## Decision

**FURAS_NATIONAL_CAPTURE = PASSED (public shadow capture).** **FURAS_NATIONAL_ENUMERATION_ENABLED remains FALSE.** **FURAS_REMOVALS_ENABLED remains FALSE.** The activation gate is withheld because `IDENTITY_SAFETY` is not established for 641 provider IDs that do not yet exist as current Furas SourceOpportunity rows. The identity-only shadow run did not decide Master eligibility, semantic duplicates, or changed payload versions for those candidates. A live controlled pilot and fresh pilot backup/restore were therefore **NOT RUN**.

## Live source state

- Furas registry key: `furas`; one source identity only.
- Source rows: 6,546; linked to current Masters: 6,493; unlinked: 53.
- Last successful stored scan: 2026-11-02T07:58:42Z; last attempt: 2026-11-02T09:59:30Z; last job 698 ended `RECONCILIATION_SCOPE_WARNING`; latest successful complete source capture is outside its 6-hour critical freshness limit (`STALE`).
- Runtime national enumeration flag is unset and resolves false. Removal reconciliation flag is unset and resolves false. The map and national UI/dashboard flags remain true.

## National capture and checkpoint evidence

The isolated official public ArcGIS capture used the published catalogue proxy, query capability, `OBJECTID` membership enumeration, and exact 100-ID batches. It made 69 requests, observed 6,511 membership IDs, returned 6,511 unique provider IDs, and completed pagination with checkpoint version `FURAS_ARCGIS_CHECKPOINT_V2`. No authenticated/private API, CAPTCHA bypass, or write occurred. Checkpointing in production binds the cursor to `SyncJob.metrics_json` and commits the page rows and cursor together; the focused recovery tests cover interruption after a committed batch, retry of an uncommitted page, snapshot membership deferral, reordered/duplicate IDs, and lock/recovery behavior. The shadow checkpoint itself is synthetic/in-memory (`job_id=0`), so it is not evidence of a new durable live job.

## Identity comparison

- Captured provider records: **6,511**.
- Exact IDs already in current Furas SourceOpportunity rows: **5,870**.
- IDs absent from current Furas SourceOpportunity rows: **641**; these remain unresolved to a current Master.
- Existing IDs absent from this current date-filtered snapshot: **676**. This difference is not treated as removal or cancellation.
- Duplicate provider IDs in captured snapshot: **0**.
- Records missing either region or city field: **2,245**; location unknowns stay unknown.
- Records with raw date fields of unverified deadline semantics: **6,511**.
- Potential new Masters, source updates, and possible semantic duplicates: **NOT EVALUATED** in this identity-only comparison; no confidence is invented from titles or locations.
- Potential/automatic removals: **0 / 0**.

The difference from the historical 6,546-row Furas inventory is therefore represented as 5,870 exact matches, 641 currently unmatched provider IDs, and 676 prior IDs absent from the current filter, with a net size difference of 35. Publication date-filter changes and source lifecycle evidence can explain membership differences; none establish source deletion.

## Safety and verification gates

| Gate | Result | Evidence |
|---|---|---|
| Public national capture | PASS | Complete 6,511-ID shadow enumeration |
| Checkpoint recovery | PASS (code + isolated tests) | Durable per-job cursor design; commit/replay and stale-job tests passed |
| Idempotency | PASS (isolated tests) | Furas replay/interruption tests; repeated source ID behavior; no Master creation in capture path |
| Duplicate prevention | PASS for provider IDs; broader identity unresolved | 0 repeated provider IDs; 641 identities await Master-eligibility assessment |
| Geography safety | PASS (isolated tests) | Existing canonical geography and no inferred location policy |
| Lifecycle safety | PASS (isolated tests) | Ambiguous dates retained; missing snapshot membership does not cancel |
| Removal protection | PASS | Removal flag resolves false; shadow `automatic_removals=0` |
| Full DQ | PASS | 128 PASS, 6 WARNING, 0 FAIL |
| Full regression | PASS | 695 passed, 1 skipped, 0 failed |
| Identity safety | **NOT PASSED** | 641 current unmatched IDs not evaluated for Master eligibility/duplicate review |
| Fresh backup + restore for pilot | NOT RUN | Pilot was not authorized by gates |
| Controlled pilot / post-pilot reconciliation | NOT RUN | No job ID; no live source sync was dispatched |

## Exact failed activation gate

`IDENTITY_SAFETY = NOT PASSED` because the shadow comparison did not resolve 641 unmatched provider identities against canonical Masters and governed review outcomes. `POTENTIAL_NEW_MASTERS` remains unknown, not zero. This is the critical failed gate. The task’s conditional pilot cannot proceed on the current evidence.

## Final flags and effects

- `FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE`.
- `FURAS_NATIONAL_REMOVAL_RECONCILIATION_ENABLED = FALSE` (`FURAS_REMOVALS_ENABLED = FALSE`).
- `FURAS_CONTROLLED_PILOT = NOT_RUN`; `FURAS_PILOT_JOB_ID = NOT_RUN`.
- Production source rows/Masters/links changed by this task: **0**.
- Manual non-Furas syncs: **0**.
- Unexplained duplicate Masters: **0** observed by full DQ; unauthorized removals: **0**.

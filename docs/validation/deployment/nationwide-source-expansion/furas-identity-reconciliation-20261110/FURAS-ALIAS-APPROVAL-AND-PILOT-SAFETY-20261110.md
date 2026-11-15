# Furas alias approval package and pilot safety assessment — 2026-11-10

## Executive decision

**FURAS_PILOT_READINESS = NO-GO.** This package supports decisions only. No aliases are approved or applied; no records, schedules, or configuration are changed. Identity-governance approval owner: **NOT DESIGNATED** in the reviewed artifacts.

| Classification | Count | Technical recommendation | Status |
|---|---:|---|---|
| Proposed aliases | 75 | READY_FOR_GOVERNANCE_APPROVAL | Pending row-level approval |
| Attribute conflicts | 3 | CONFLICT / DO_NOT_APPROVE | Hold; evidence required |
| Cross-source references, no Master | 4 | REQUIRES_ADDITIONAL_EVIDENCE | Master unresolved |
| Possible existing identities | 268 | Preserve existing review class | Unresolved |
| Insufficient-evidence possible new source keys | 328 | Preserve existing review class | Not confirmed new records |
| **Total** | **678** | | **No activation** |

The 75 entries have exact InvestSaudi opportunity numbers and direct Furas links, historical one-to-one Furas source-key lineage, matching geometry/stable attributes per the reconciliation report, and existing Master links. Proposed provider IDs, old Furas SourceOpportunity IDs, and linked Master IDs are each unique within the set. These facts support governance review, not automatic approval. Source identity, Master identity, geography, lifecycle, and eligibility remain separate decisions. No candidate relies on title similarity alone.

## A. 75 alias review table

Editable register: [FURAS-75-ALIAS-GOVERNANCE-REVIEW-20261110.csv](FURAS-75-ALIAS-GOVERNANCE-REVIEW-20261110.csv).

It contains exact IDs, official references/URLs, lineage, evidence hash, collision assessment, technical disposition, and separate blank governance decision, reviewer, date, rationale, implementation authorization, and notes fields. Every row is marked **PENDING_GOVERNANCE**. The proposals preserve the existing Furas SourceOpportunity and linked Master; they propose only a provider-key alias, with no merge or new Master. The inspected application models have no first-class provider-identity crosswalk. Any future mapping needs separate design approval, uniqueness constraints, reversibility, and authorization.

## B. Seven special cases

Editable register: [FURAS-7-IDENTITY-EXCEPTION-REGISTER-20261110.csv](FURAS-7-IDENTITY-EXCEPTION-REGISTER-20261110.csv). Decision fields remain blank.

- **Three attribute conflicts:** 25-12-2114880 → candidate SourceOpportunity 4313, no Master, changed OPPORTUNITYDESCRIPTION and OPPORTUNITYID; 01-26-008101-11002 → source 6333 / Master 3706, changed ENDDATE, LASTRFPSELLDATE, OPPORTUNITYID; 01-26-006202-22001 → source 7017 / Master 4387, same changed date/ID fields. Do not approve an alias automatically. Compare archived official detail versions and provider history. The saved adjudication export does not carry historical raw date values for side-by-side comparison, and Furas date semantics remain unverified.
- **Four exact cross-source references with no Master:** 06-26-189921-20001 (InvestSaudi source 2005 / provider investsaudi:54033), 06-26-189921-20002 (2006 / investsaudi:54032), 01-26-008202-12001 (2219 / investsaudi:55110), and 01-26-008202-12003 (2218 / investsaudi:55111). Exact official number/Furas URL establishes a publication reference, not historical one-to-one Furas identity or canonical Master. Review each pair and adjudicate any Master relation separately.

## C. Preserved 596 cases

The existing queue remains unchanged: 268 POSSIBLE_EXISTING_FURAS_IDENTITY_MANUAL_REVIEW + 328 INSUFFICIENT_EVIDENCE_POTENTIAL_NEW_FURAS_SOURCE. Do not treat the latter as new opportunities or create SourceOpportunity/Master records from these classifications. No new broad reconciliation was performed.

- [Full 678-record CSV](FURAS-678-RECORD-LEVEL-RECONCILIATION-20261110.csv)
- [Full 678-record JSON](FURAS-678-RECORD-LEVEL-RECONCILIATION-20261110.json)

Filter by the two classes above; retain the saved uncertainties and next actions.

## D. Explicit approval instructions

For each alias, the authorized reviewer should verify provider ID, old provider key, SourceOpportunity ID, Master ID, and official reference against the row evidence; assess source identity separately from Master identity; then enter APPROVE_ALIAS, REJECT_ALIAS, or HOLD_FOR_EVIDENCE, reviewer, date, rationale, and any separate implementation authorization. Leave implementation authorization blank absent separate change approval. An identity decision alone does not authorize production changes or Furas activation. Do not approve by title similarity. For the seven exceptions, decide source identity and canonical Master independently. No reviewer/owner is invented; approval owner is NOT DESIGNATED.

## E. Non-mutating pilot safety — assessment only

**Current production ingestion is not a non-mutating pilot boundary.** allow_master_creation=false prevents some new-Master creation when no Master resolves; it does not make the function read-only or protect already resolved Masters.

### Identified write paths

- app/service.py:817–845: the Furas source-only branch can insert/update SourceOpportunity raw/standardized fields, status, timestamps and missing checks; update taxonomy; append status observations.
- In the current Furas checkpoint call, allow_master_creation=false plus no resolved Master takes the source-only return at 817–845, so the generic Master-creation branch at 846 is bypassed for that case. When a Master does resolve, processing continues: app/service.py:871–904 can update existing Master fields, status, coordinates/location, and timestamps. 905–1013 can update SourceOpportunity/link/status, source taxonomy, observations, provenance, lifecycle/status projection, ChangeHistory, OpportunityConflict, asset-facility assignments, sector projection, alerts/events and review evidence.
- app/service.py:1111–1202 commits per-batch data and cursor plus SyncJob metrics/heartbeat and Source sync status. sync_source (1356–1387 and finalization 1680–1732) mutates job/source health, status/timestamps, counters and can persist events/errors/DQ outcomes.
- Lifecycle reconciliation can update missing counters/status, append observations and, if its separate removal guard is enabled, project status to Master and create history/reviews. A disabled removal flag does not disable other ingestion writes.
- Furas identity uses OPPORTUNITYID, falling back to OBJECTID only when absent. No first-class identity alias/crosswalk table was found. No direct administrative-boundary registry write was identified in this branch, but generic Master latitude/longitude/location updates remain a geographic write risk.
- Scheduler guards are in app/tasks.py:127 and 273; do not enable enumeration/removal flags or start scheduler/worker services for a pilot.

### Required controls before a future pilot

1. Default to saved-fixture replay with no database, source-network, notification, or scheduler access; emit proposed diff/quarantine artifacts only. Do not invoke _safe_record, lifecycle reconciliation, or production commits.
2. If ingestion-shaped behavior is needed, use a disposable isolated database or sanitized snapshot with separate database, credentials, secret store, and network policy. Production credentials/routes must be absent and unreachable; do not share production Postgres, Redis, Celery, Worker, or Beat.
3. Disable outbound network/notification side effects and schedulers; replay only captured payloads.
4. Add fail-closed, explicit table/field write allowlists and abort on unexpected writes to Masters, SourceOpportunity identity/link, coordinates/geography, lifecycle/removal, reviews, aliases, schedules, or production health state.
5. Compare before/after table counts and stable row hashes; assert zero unintended identity, Master, coordinate, lifecycle, review, schedule, or external changes. Keep fixture hashes and audit logs.
6. Separately approve the design, data handling, allowlist, cleanup/rollback, and any reversible alias-crosswalk schema. Do not implement or activate these controls under this task.

This is design only; no pilot, dry-run mode, feature flag, or app change was implemented.

## Focused validation and safety

Re-ran node scripts/reconcile_furas_678_readonly.mjs: **PASS**. It validated the 6,548-record capture (66 pages, 70 retained request entries), all 678 unique classifications and evidence hashes, counts 75/268/3/4/328, total 678, and reported mutations: 0. It reads saved local artifacts; no database, Docker, network, or sync was used. Python tests: NOT RUN (not needed for this read-only artifact task; no isolated Python test environment was selected). No production DB access, data mutation, restart, migration, sync, scheduler change, or activation occurred in this task. **PRODUCTION_DATA_MUTATIONS = NONE.**

## Remaining blockers and single next action

The identity-governance owner is not designated; 75 row-level decisions remain pending; seven exceptions need review/evidence; 596 cases remain unresolved; a crosswalk facility and isolated fail-closed pilot are not implemented or approved; geography/lifecycle decisions remain separate. **Next action:** designate an identity-governance owner to review the 75-row alias file and seven-row exception register; keep mappings unapplied until row decisions and separate implementation authorization exist. Furas national integration remains disabled.

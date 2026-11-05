# Furas National Master Promotion — 2026-11-02

**Status: COMPLETE.** The accepted high-confidence execution set was promoted in the `alahsa-local` / `local_user` environment. The promotion was resumable, grouped according to the accepted dry run, and followed by the existing governed sector classifier and full DQ.

The execution manifest contains the full group table, source/provider IDs, new Master IDs, retained links, deferred records, classifier evidence, backup evidence, final geography, and DQ gates: [FURAS-NATIONAL-MASTER-PROMOTION-MANIFEST-20261102.json](FURAS-NATIONAL-MASTER-PROMOTION-MANIFEST-20261102.json).

## Accepted plan and backup

- Dry-run input SHA-256: `0DF77D643E61DA0E3B11B6023B66027C71A3476047DE160E9535498A9BBC65EE`; all 6,546 rows reconcile to the accepted dispositions.
- Backup: `backups/20261102T084500Z-pre-furas-promotion.dump`; SHA-256 `6D345FCDADACEBE5DCD3A0AC044C9CF6D0B900B32CA555470028EB83E8EEC548`; timestamp `2026-11-02T08:44:41Z` UTC.
- Restore test: **PASSED** in an isolated PostgreSQL 16 container. Restored counts were 9,290 source opportunities, 6,546 Furas rows, 566 current Masters, Alembic `0025_source_geographic_coverage`.
- Promotion run: `f6a9c323-0a8c-4a79-8ed4-a9d1ebca9fd8`. Checkpointing committed Master creation, source links, field provenance, audit events, and progress together in 61 transactions of at most 100 groups.
- Idempotency replay: **PASSED**. Replaying the completed run ID returned the completed checkpoint; counts remained 6,623 current Masters, 6,546 Furas rows, and 6,493 linked Furas rows, with no extra Masters or links.

## Promotion results

| Result | Count |
|---|---:|
| Current Masters before → after | 566 → 6623 |
| New high-confidence Masters | 6057 |
| Furas source links created | 6057 |
| Invest Saudi source links created | 87 |
| Verified shared-reference groups | 87 |
| Existing correct Master links retained | 374 |
| Last-write guard linked/deferred groups | 0 / 0 |
| Ambiguous identity cases deferred | 46 |
| Same-source duplicate cases deferred | 7 |
| Historical/non-current rows preserved | 62 |
| New Masters without sources | 0 |
| Duplicate Furas provider keys | 0 |
| Invalid multi-Master source links | 0 |
| Fabricated coordinates | 0 |
| Source rows deleted | 0 |
| Existing Al-Ahsa Master duplicates created | 0 |

The 87 exact trusted Furas/Invest Saudi official-reference pairs were each represented by one new Master with both existing source rows attached. The remaining 5,970 new Masters each retain one Furas source row. No last-write guard collision appeared. All 374 pre-existing Furas links still point to their accepted Master IDs. The 46 identity-review rows, 7 same-source duplicate-review rows, and 62 non-current rows were left unpromoted or unchanged as specified.

## Canonical fields and geography

New Master values came from explicit Furas source data and accepted standardized mappings. Publisher is stored as “فرص – البوابة الموحدة للاستثمار”; opportunity owner remains the explicit source owner where supplied. No owner, value, deadline, duration, geography, or coordinate was fabricated. Unverified Furas date and duration semantics remain unset. Coordinates were copied from the explicit Furas point with source-row provenance; raw region/city labels were preserved without reverse-geocoding or inferred governorates.

The existing governed sector classifier assigned traceable inferred sectors to all 6,057 new Masters: 1,325 HIGH, 1,803 MEDIUM, and 2,929 LOW-confidence best-fit decisions. LOW confidence is recorded as inferred with evidence, rule, reason, and engine version; it is not represented as an official Furas sector. Sector counts: {"تجاري": 5182, "السياحة": 64, "أخرى": 266, "الخدمات المالية": 19, "الرياضة": 65, "صناعي": 217, "الزراعة": 53, "الرعاية الصحية": 9, "التعليم": 85, "الخدمات اللوجستية": 6, "العقارات والإنشاءات": 87, "البيئة": 3, "الثقافة": 1}.

Final canonical geography coverage: **14** regions, **0** governorates, **170** cities, and **566** current Masters with unspecified/unverified geographic scope. The 566 legacy Masters retain their prior null/unspecified scope; the new Furas Masters use direct point evidence and direct source labels.

## DQ and regression

Full DQ run `a06ce5a64b01411782395912b4279b79`: **129 PASS, 5 WARNING, 0 FAIL**. Failures: **0**. Warnings remain limited to: GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION, HISTORICAL_REVIEW_AUDIT_INCOMPLETE, SOURCE_LAST_SUCCESS_TOO_OLD, SYNC_RUNTIME_ANOMALY, UNKNOWN_AREA_STORED_AS_ZERO. DQ thresholds were not changed.

Focused regression: **92 passed, 2 warnings** across ingestion, entity resolution, duplicate review, geography, taxonomy, lifecycle, source links, and sync lifecycle. Runtime application code and migrations were not changed; the new operational runners are in `scripts/`.

## Final controls

- Manual source syncs: **0**. No Furas sync job was active during execution or at reconciliation; the runner held the existing `source-sync:1` Redis lock across each execution phase.
- The only later observed source job ID was the unrelated scheduled Al-Ahsa Job 695, completed before the refreshed backup. The promotion runner did not create a sync job.
- Business writes were limited to 6,057 new Masters, 6,144 source links, supported `FieldProvenance`, creation audit events, and governed sector inference/audit history.
- Job 692 remains `FAILED`; Job 694 remains `SUCCESS` with digest `e91cfe73f53184fb698ca4eec18926d196039ebd0219f27547fa706580ad74e0`.
- `FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE`; `NATIONAL_UI_ENABLED = FALSE`; `NATIONAL_MAP_ENABLED = FALSE`.

**Stop point reached.** No review cases were resolved, no source was synchronized, and no UI/map or removal setting was enabled.

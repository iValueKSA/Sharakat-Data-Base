# National Source Scheduling Readiness Update — 2026-11-05

## Readiness decision

| Source | Technical health | Freshness | Public coverage | Scheduling readiness |
|---|---|---|---|---|
| Furas | Adapter/provider ID extraction healthy for read-only capture; existing production source state not altered | Existing stored sync stale since Nov 2; national shadow capture current at Nov 5 | National public enumeration captured; 678 current repeat identities require review; lifecycle dates remain unverified | Not ready for national pilot until exact identity membership and safe quarantine/idempotency acceptance are restored |
| MODON | Blocked — missing server intermediate certificate breaks container strict trust | Existing successful content is stale; latest live TLS attempt fails | Public surfaces cannot be claimed complete while strict TLS fails | Blocked pending provider certificate-chain repair |
| NHC | Warning at latest job; current GET spot check returned 200 on 3 routes | Last persisted success Oct 12; Nov 5 job had 403 on all 6 routes | Limited: no itemized public inventory, access is route/time dependent | Keep scheduled monitoring and warnings; not a parser defect at job 787 |

## Platform and safety

Accepted national UI, dashboard, and map remain enabled. Configured sources remain 14; scheduled count remains 12. Final full-DQ snapshot observed 6,657 current Masters (6,678 total Opportunity rows including 21 merged rows), 9,468 SourceOpportunity rows, and 14 configured sources. The accepted Al-Ahsa baseline is 518; this run did not independently recompute the Al-Ahsa partition. No new source identities were added. NCP remains under ncp; RCJY, RCU, and Ta'adeen records were not modified.

Furas national enumeration remains disabled; removals remain disabled. No manual production source sync, Master promotion, or source-link modification was performed. The 346 repeat OBJECTID/title candidates remain review-only. Master-promotion safety is not established. Removal reconciliation safety is not established.

## Final activation decision

FURAS_READY_FOR_CONTROLLED_PILOT = FALSE; FURAS_CONTROLLED_PILOT = NOT_RUN.

Remaining blockers:
1. Recover the exact original 6,511-member capture or 641-ID unmatched manifest and payloads. The stored digest is not reversible; the current 6,548-member repeat cannot replace it.
2. Adjudicate same-OBJECTID/different-OPPORTUNITYID candidates with authoritative identity migration evidence and governed crosswalk approval; preserve existing links until then.
3. Validate isolated idempotency, checkpoint recovery, source-only quarantine, lifecycle and geography cases before reconsidering a pilot.
4. MODON provider must serve the missing DigiCert intermediate, followed by strict container TLS verification.
5. NHC must be assessed by independent route status and parser outcome on future ordinary monitoring; keep the last warning and coverage limitation.

Do not enable Furas national scheduling or removals until these gates are evidenced. No pilot was executed.


## Verification results

- Full read-only DQ: 128 PASS, 6 WARNING, 0 FAIL; current-master/source-link counts and schema heads were included in the snapshot.
- Focused adapter and sync-lifecycle tests: 18 passed.
- Full isolated regression: 695 passed, 1 skipped, 0 failed (90.53 seconds).
- API health: HTTP 200. API readiness: HTTP 200 with database, Redis, and worker checks all OK.
- Furas exact provider-key duplicate count in observed current rows: 0. The broader identity/idempotency scenario matrix is not fully proven; no promotion or migration was run.

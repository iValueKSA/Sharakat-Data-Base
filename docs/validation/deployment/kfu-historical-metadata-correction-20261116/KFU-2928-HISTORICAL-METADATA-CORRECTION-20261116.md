# KFU SourceOpportunity 2928 derived document-reference correction

**Execution:** 2026-11-16  
**Transaction timestamp:** 2026-11-16 12:15:17.483360 UTC.  
**Status:** APPLIED_AND_VERIFIED  
**Authorization:** User-authorized exact allowlist: SourceOpportunity 2928 only.

## Correction

One atomic PostgreSQL transaction (transaction ID 8410) updated only source_opportunities.raw_data_json for SourceOpportunity 2928 (kfu-announcement:0aac035af08807f4f1755ee5), linked to Master 326.

In raw_data_json.attachments, exactly these two confirmed incorrect inherited references were removed:

1. Investor guide: https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/assets/%d8%b1%d8%ad%d9%84%d8%a9-%d8%a7%d9%84%d9%85%d8%b3%d8%aa%d8%ab%d9%85%d8%b1.pdf
2. 2025 tender booklet: https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/assets/%d9%83%d8%b1%d8%a7%d8%b3%d8%a9%d9%85%d8%b7%d8%a7%d8%b9%d9%85-%d9%88%d9%85%d8%aa%d8%a7%d8%ac%d8%b1-%d8%b9%d8%a7%d9%85%d8%a9.pdf

Attachment associations changed from 2 to 0. A raw_data_json.attachment_provenance_review marker records the classification, reason, exact original reference objects, and preservation locations. Existing keys outside attachments are unchanged. The source content_hash is unchanged.

Metadata SHA-256: before 68f51907427a1491004d9d673e17208bfd6c03decb44d916e10f56463adc5ab7; after ab53aae739a9c55e5fffeed50d5142b25e44bbb2cdbdd7e19afc8a2a4e08abf0.

## Evidence and backup

The prior official-page review found the current seasonal-rental notice has an application form only; the investor guide is outside its notice panel, and the booklet belongs to a separate expired 2025 tender. The approved row-level classifications and URLs are in the [KFU reference decision register](../../development/kfu-document-provenance/kfu-reference-decision-register-20261116.csv) and [KFU identity review](../../development/kfu-document-provenance/KFU-AND-INVESTSAUDI-IDENTITY-REVIEW-20261116.md). The official evidence reviewed was the [KFU Investment Administration announcements page](https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/%D8%A7%D8%B9%D9%84%D8%A7%D9%86%D8%A7%D8%AA-%D8%A7%D9%84%D8%A5%D8%AF%D8%A7%D8%B1%D8%A9.html).

Fresh pre-correction PostgreSQL custom-format backup:

- Path: C:\Users\QusaiAbdElhalim\AppData\Local\Sharakat Data Base\backups\kfu-2928-correction-20261116T120200Z.dump
- Size: 67,578,296 bytes
- SHA-256: 90dfbb8a6dff1d2773c9aa65daa3ad1db299ed62c66990f1b0ff2b077ad79a64
- PostgreSQL and pg_dump: 16.15
- Archive: readable, 433 TOC entries.
- Restore: passed in an internal-only disposable PostgreSQL 16 instance. Restored snapshot had schema head 0027, 6,680 Masters, 9,470 SourceOpportunity rows, 61,006 observations, 7 KFU listing items, 960 sync jobs, and zero document rows. Target/provider/Master relationships and source evidence were present.

The isolated copy passed a committed correction simulation and compare-and-swap reversal, restoring the exact target before-image. Evidence: [backup verification](backup-verification.json), [isolated correction and reversal](isolated-correction-and-reversal-result.json). Production before/after row data, transaction ID and allowlist checks are in [production transaction evidence](production-transaction-result.json).

## Production verification

- SourceOpportunity 2928 remains linked to Master 326.
- SourceOpportunity 2774 remains kfu-announcement:7e98c5dfb12b0a6d09f4c349 -> Master 225. Masters 225 and 326 are unchanged.
- The target's three SourceObservations remain intact and still contain both original URLs in their raw payloads. All seven KFU listing snapshots remain intact and retain the original links.
- The other five KFU source rows were compared before and after and remain unchanged. The supported association and all nine unverified references remain untouched.
- Counts after correction: 6,680 Masters (21 merged; 6,659 non-merged), 9,470 SourceOpportunity rows, 61,006 SourceObservations, 75 Furas aliases, 6 KFU source records, 7 KFU listing items, and zero opportunity_documents.
- Schema head remains 0027_opportunity_documents_mvp. No migration, deployment, service recreation, source sync, document publication, source identity/lifecycle/geographic change, or unrelated data mutation occurred.
- API readiness and frontend returned HTTP 200. Worker ping passed and runtime parser is 2026.11.16-kfu-2. Scheduler Beat process is running and emitting routine dispatch logs; PostgreSQL and Redis are healthy. All six platform containers remain running with their preflight IDs.
- KFU remains enabled and healthy on its existing 720-minute interval. Latest KFU job remains 975, last successful run 2026-11-16 06:35:30 UTC. No KFU job was active, reserved, ETA-scheduled, queued, locked or started by this correction. Next normal schedule is approximately 18:35 UTC.
- Furas national enumeration, Furas removals and RCU scheduled sync remain disabled.

## Concurrency and recovery

Preflight found no active, reserved or ETA-scheduled Worker tasks; no active KFU database job; no KFU Redis lock/reservation; and empty source, maintenance and notification queues. The transaction acquired the same PostgreSQL advisory ingestion lock used by collection and locked the exact target row using FOR UPDATE. Identity and metadata checksum were rechecked under lock.

Targeted rollback readiness is PASS. The exact before-image and checksum are captured in the transaction evidence. A reversal must lock SourceOpportunity 2928, confirm provider ID and Master 326, compare the current metadata checksum with the verified after-image, and restore only the captured raw_data_json. Rollback was not executed.

An initial transaction-runner attempt failed on a harness key name before commit and rolled back. A read-only reread confirmed the original checksum and both references were unchanged before the successful transaction.

## Final status

- PRODUCTION_PREFLIGHT=PASS
- FRESH_DATABASE_BACKUP=PASS; BACKUP_RESTORE_VERIFICATION=PASS
- EXACT_REFERENCE_MATCH=PASS; TARGET_ROW_IDENTITY=PASS
- ISOLATED_CORRECTION_DRY_RUN=PASS; TARGETED_REVERSAL_DRY_RUN=PASS
- PRODUCTION_TRANSACTION=COMMITTED_AND_VERIFIED
- REFERENCE_COUNT_BEFORE=2; REFERENCE_COUNT_AFTER=0; OTHER_REFERENCES_REMOVED=0
- RAW_PROVENANCE_STATUS=PRESERVED; SOURCE_OBSERVATION_STATUS=PRESERVED
- SOURCE_IDENTITY_PRESERVED=PASS; MASTER_ASSOCIATIONS_PRESERVED=PASS
- UNRELATED_BUSINESS_DATA_MUTATIONS=0; DOCUMENT_ROWS_AFTER=0
- API_HEALTH=PASS; FRONTEND_HEALTH=PASS; WORKER_HEALTH=PASS; SCHEDULER_HEALTH=PASS
- SOURCE_SYNC_ACTIVITY=NONE; ROLLBACK_EXECUTED=NO
- REMAINING_UNVERIFIED_REFERENCES=9; UNCHANGED
- REMAINING_BLOCKERS=NONE FOR THIS AUTHORIZED CORRECTION
- FINAL_DECISION=KFU_HISTORICAL_METADATA_CORRECTION_APPLIED_AND_VERIFIED

**Next action:** Keep the nine unresolved references on hold for separate evidence-based review. This task authorizes no further correction or document publication.
# Furas real booklet onboarding pilot — read-only review

**Review date:** 2026-11-17 (Asia/Amman)  
**Status:** `FURAS_FIRST_DOCUMENT_BATCH=PARTIAL_OR_BLOCKED`  
**Execution:** Production reads only; no sync, writes, publication, deployment, or restarts.

## Result

No first-batch document is ready for publication review. Twenty-five existing Furas SourceOpportunity records were selected from the stored Al-Ahsa active pool. Each had a non-merged Master, exact equality among provider ID, source reference and raw `OPPORTUNITYID`, an official Furas opportunity URL, and stored `Announced` / `متاحة` status. All 25 records were last observed on 2026-11-02; their current availability therefore could not be established from stored data alone.

A bounded direct GET was attempted for all 25 exact official detail URLs, with five concurrent requests and a six-second client timeout. **0/25 returned an HTTP response; 25/25 timed out.** A separate ten-second curl GET to the first record returned HTTP 000. The web reader also could not fetch the pages, and Chrome automation was unavailable. No login, purchase, submission, restricted endpoint, proxy, or header spoofing was used. Because the pages could not be inspected, no booklet, preview, direct download, purchase route, login gate, payment gate, application route, price, currency, or reuse term is verified.

The row-level decision register is [furas-active-al-ahsa-document-review-20261117.csv](furas-active-al-ahsa-document-review-20261117.csv). It records all 25 source/Master IDs, exact provider keys, official page URLs, stored status and observation date, raw `RFPPRICE` and date fields without interpretation, and the verification hold. The selected set comprises 13 `Investment` and 12 `TemporaryRental` records, all Al-Ahsa `CITY_ID` values. Stored Al-Ahsa active pool count was 375; that count is a stale database classification, not current availability.

## Candidate and price decisions

- `VERIFIED_BOOKLETS=0`; `PUBLIC_DIRECT_DOWNLOAD_CANDIDATES=0`; `OFFICIAL_SOURCE_PAGE_CANDIDATES=0`.
- `PURCHASE_REQUIRED_CANDIDATES=0`; `LOGIN_REQUIRED_CANDIDATES=0`; `VERIFIED_BOOKLET_PRICES=0`.
- `RESTRICTED_DOCUMENTS=0 confirmed`; `UNVERIFIED_DOCUMENTS=25 opportunity records held for lack of retrievable page evidence`.
- `FIRST_PUBLICATION_BATCH_COUNT=0`; no proposed `SourceOpportunity` or Master IDs.
- Stored `RFPPRICE` contains raw values on some records, including values such as 1500, 1000, 500, 2.5 and 0.10. The GIS schema response and source adapter do not establish that these are booklet prices, their currency, or whether they represent document access, bid participation, rent, deposit or another charge. No amount was projected into the document model.
- No document URL, document-specific stable ID, login/payment flag or permission term is present in the captured GIS attribute payload for these selected records. The opportunity detail URLs remain the only verified URL field at the record level; they are not being presented as document links.
- Ordinary official-page linking may be preferable to rehosting, but page access and source linking conditions were not verified here. No file was copied, proxied, mirrored or hosted.

## Isolated validation

`ISOLATED_DATABASE_TESTS=NOT_RUN_NO_VERIFIED_REAL_CANDIDATE`  
`ISOLATED_API_TESTS=NOT_RUN_NO_VERIFIED_REAL_CANDIDATE`  
`ISOLATED_BROWSER_RESULTS=NOT_RUN_NO_VERIFIED_REAL_CANDIDATE`

No disposable candidate rows were seeded, and no unresolved document was marked approved. This preserves the requirement to test only real metadata supported by evidence. The Documents MVP synthetic/API/migration/browser suite has prior accepted evidence in [implementation report](../opportunity-documents-mvp/OPPORTUNITY-DOCUMENTS-MVP-IMPLEMENTATION-REPORT-20261115.md); it was not repeated in this real-source investigation.

## Collection readiness

`FURAS_DOCUMENT_AUTOMATION_READINESS=NOT_READY_FOR_DOCUMENT_EXTRACTION`.

Existing collector payloads preserve exact `OPPORTUNITYID`, GIS `OBJECTID`, `OPPORTUNITYTYPE`, `OPPORTUNITYACTIVESTATUS` / `STATUS`, `CITY_ID`, raw date fields such as `LASTRFPSELLDATE` and `ENVELOPESOPENDATE`, and raw `RFPPRICE`. The stable source identity is `OPPORTUNITYID`; it matches the provider ID for all 25 selected rows and each already links to a valid non-merged Master. The selected raw attributes expose no document URL or document ID, and the existing public page layer does not give verified labels/semantics for price or access requirements.

After public page access is restored, a narrow per-record detail capture could collect page-level attachment labels/URLs, an official stable document ID if present, displayed booklet price with currency and its exact label, and separate authentication, document-payment, purchase-for-participation and application requirements. Normalize only explicit labels; keep raw field values and timestamp/source URL provenance; detect changes by exact provider ID plus normalized destination/label/version. Keep the existing publication gate and manual review, source-link destination, and no-proxy/no-rehosting boundary. Do not activate national enumeration or collection as part of that follow-up.

## Required KFU follow-up

`KFU_POST_CORRECTION_STABILITY=PASS` for the required brief read-only check. Scheduled KFU job **996** succeeded on 2026-11-17 06:46:56 UTC, after the 2026-11-16 correction. SourceOpportunity 2928 still has `attachments=[]` and remains linked to Master 326. KFU remains enabled with a 720-minute interval and healthy status. No KFU sync was triggered by this review.

## Safety and final decision

- `PRODUCTION_DATA_MUTATIONS=0`; `DOCUMENTS_PUBLISHED=0`.
- No Furas sync, enumeration, removal reconciliation, or schedule/flag changes were made. The worker’s national-enumeration and national-removal variables are unset, which the deployed fail-closed flag reader treats as false. The existing Furas source row is enabled but last successful collection was 2026-11-02 10:03:10 UTC with `RECONCILIATION_SCOPE_WARNING`; no activation or retry was initiated.
- The deployed `opportunity_documents` table remains empty (0 rows).

**Remaining blockers:** the 25 detail pages timed out; stored candidate snapshots are stale (15 days at review); no booklet or purchase evidence can be verified; raw price semantics/currency and source-linking terms are unknown.  
**Next recommended action:** restore ordinary public access to the official Furas detail pages, then re-verify these existing Al-Ahsa records only. Do not sync, publish, or enumerate new IDs until that read-only evidence pass succeeds.

**Final decision:** `PARTIAL_OR_BLOCKED — FURAS_FIRST_DOCUMENT_BATCH_NOT_READY_FOR_PUBLICATION_REVIEW`.

## Requested status fields

```text
FURAS_DOCUMENT_ONBOARDING_STATUS=PARTIAL_OR_BLOCKED
ACTIVE_EXISTING_OPPORTUNITIES_REVIEWED=25 (stored active status; current status unverified)
ALAHSA_OPPORTUNITIES_REVIEWED=25
OTHER_REGIONS_REVIEWED=0
VERIFIED_BOOKLETS=0
PUBLIC_DIRECT_DOWNLOAD_CANDIDATES=0
OFFICIAL_SOURCE_PAGE_CANDIDATES=0
PURCHASE_REQUIRED_CANDIDATES=0
LOGIN_REQUIRED_CANDIDATES=0
VERIFIED_BOOKLET_PRICES=0
RESTRICTED_DOCUMENTS=0_CONFIRMED
UNVERIFIED_DOCUMENTS=25_OPPORTUNITY_RECORDS_HELD
FIRST_PUBLICATION_BATCH_COUNT=0
PROPOSED_SOURCEOPPORTUNITY_IDS=NONE
PROPOSED_MASTER_IDS=NONE
ISOLATED_DATABASE_TESTS=NOT_RUN_NO_VERIFIED_REAL_CANDIDATE
ISOLATED_API_TESTS=NOT_RUN_NO_VERIFIED_REAL_CANDIDATE
ISOLATED_BROWSER_RESULTS=NOT_RUN_NO_VERIFIED_REAL_CANDIDATE
FURAS_DOCUMENT_AUTOMATION_READINESS=NOT_READY_FOR_DOCUMENT_EXTRACTION
KFU_POST_CORRECTION_STABILITY=PASS
PRODUCTION_DATA_MUTATIONS=0
DOCUMENTS_PUBLISHED=0
REMAINING_BLOCKERS=PUBLIC_DETAIL_PAGE_TIMEOUT; STALE_SOURCE_SNAPSHOT; DOCUMENT/PRICE/ACCESS/RIGHTS EVIDENCE UNAVAILABLE
NEXT_RECOMMENDED_ACTION=RESTORE_PUBLIC_FURAS_DETAIL_PAGE_ACCESS; RETRY_READ_ONLY_REVIEW_OF_EXISTING_RECORDS_ONLY
FINAL_DECISION=PARTIAL_OR_BLOCKED
```

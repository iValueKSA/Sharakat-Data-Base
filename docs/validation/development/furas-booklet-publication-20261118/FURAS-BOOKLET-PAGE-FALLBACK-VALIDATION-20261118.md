# Furas booklet page-only publication candidate

**Review date:** 2026-11-18 (Asia/Amman)  
**Mode:** Read-only live-platform inspection; isolated disposable PostgreSQL/API validation only.  
**Production writes/publication/deployment:** None.

## Candidate identity lookup

The read-only exact-reference lookup found SourceOpportunity **3188** / Master **597** for provider reference `01-26-017001-42008`. The source row points to the matching Furas official page, has an exact provider reference, and is linked to a non-merged Master.

The three additional references were not found in Furas production SourceOpportunity records:

| Provider reference | SourceOpportunity | Master | Result |
|---|---:|---:|---|
| `06-25-189921-5002` | — | — | Not found; no record created or linked. |
| `01-25-005001-43026` | — | — | Not found; no record created or linked. |
| `06-26-187795-1003` | — | — | Not found; no record created or linked. |

Those three leads were not promoted. The page reader returned an older crawl for two and timed out for one, so none supplies current database identity or lifecycle evidence.

## SourceOpportunity 3188 evidence

- **Provider reference:** `01-26-017001-42008`; exact equality with the stored source reference.
- **Linked Master:** 597; stored Master status `متاحة`; source row last observed 2026-11-02. The stored snapshot is stale.
- **Individual official page:** `https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-42008?type=Investment`. The current page returned HTTP 200 and displays the exact opportunity reference, “كراسة الشروط و المواصفات”, “مسودة العقد”, the booklet purchase action, and a live remaining-time display. The page was observed to show about 39 days remaining. Normal browser interaction remains unverified.
- **Booklet attachment reference:** official page anchor contains attachment ID `270741756`. The ordinary attachment request returned HTTP 302 to `/list-opportunities`; the destination was an HTML listing, not a PDF. This is a known failed direct download and must never be represented as a working download.
- **Booklet price:** raw `attributes.RFPPRICE=1500` matches the same page’s Arabic label `سعر الكراسة` and displayed amount `1500`.
- **Currency:** not displayed or independently established. The proposed application record stores amount `1500` only in provenance and leaves `booklet_price_amount` and `currency` null. The investor UI therefore hides the amount.
- **Participation purchase:** the individual page has a “شراء الكراسة” action. The official [Furas investment-competitions service](https://furas.momah.gov.sa/ar/services/117) lists buying the terms booklet before submitting the bid; the [Ministry service description](https://momah.gov.sa/ar/e-services/almnafsat-alastthmaryt) describes login, selecting a competition, purchasing and paying for the booklet, then submitting an electronic bid. Together with the individual page’s purchase action, this supports `PURCHASE_REQUIRED_FOR_PARTICIPATION` for this candidate. No purchase or login was attempted. No purchase URL is proposed because the action destination was not manually verified.
- **Publication destination:** exact opportunity page only. Do not use the failed attachment URL or general listing URL as the document destination.

## Proposed record (not written to production)

| Field | Proposed value |
|---|---|
| SourceOpportunity | `3188` |
| MasterOpportunity | `597` |
| Provider reference | `01-26-017001-42008` |
| Document title | `كراسة الشروط والمواصفات` |
| Category | `TERMS_AND_CONDITIONS_BOOKLET` |
| Direct document URL | None; the observed attachment redirects to listings. |
| Investor link | Exact Furas opportunity page above. |
| Access / rights | `PUBLIC_SOURCE_PAGE` / `SOURCE_PAGE_LINK_ONLY` |
| Link verification | `VERIFIED_SOURCE_PAGE`; direct status recorded separately as `UNAVAILABLE`. |
| Participation requirement | `PURCHASE_REQUIRED_FOR_PARTICIPATION` |
| Displayed price evidence | Raw `1500`, label `سعر الكراسة`; retained only in provenance. |
| Published amount/currency | Null / null; currency unverified. |
| Lifecycle | Current page shows remaining time; stored status is stale and must not override a new page observation. |
| Publication state | Draft proposal only; production approval/publication not performed. |

## Schema and isolated changes

The current 0027 schema supports this page-only mode without migration: keep `url` and `source_opportunity_url` on the exact official opportunity page, use `PUBLIC_SOURCE_PAGE`, `SOURCE_PAGE_LINK_ONLY`, and `VERIFIED_SOURCE_PAGE`, and retain the failed attachment response, raw amount/label, currency uncertainty, and evidence timestamp in `source_provenance_json`. Unknown currency remains hidden under the existing price/currency gate.

The prior UI only said “زيارة المصدر الرسمي” and did not surface the verified failed-download state. A small isolated API/UI change now exposes only the whitelisted `direct_download_status` from provenance and renders:

- `رابط تحميل الكراسة غير متاح حاليًا`
- `عرض الفرصة لدى المصدر الرسمي`

This mode does not render “تحميل الكراسة” and does not expose the failed file URL. No schema or migration change was needed.

**Isolated code files changed:** `app/documents.py`, `app/static/app.js`, `tests/test_opportunity_documents.py`.

## Validation results

- Exact candidate identity, SourceOpportunity and Master linkage: passed in the isolated candidate test.
- Page-only official destination serialized by the API; failed attachment URL and general listings redirect were not serialized: passed.
- Unknown price/currency remained null and hidden; purchase status was separate: passed.
- Cross-Master leakage check: passed.
- Duplicate source-scoped version insertion: rejected by the unique constraint (idempotency check passed).
- Targeted opportunity-document suite on disposable PostgreSQL 16: **8 passed**.
- `node --check app/static/app.js`: passed.
- Browser acceptance: **not run**. The current session could not attach to the native browser; the available document browser container had no Chromium/Playwright runtime. No browser PASS is claimed.
- Disposable PostgreSQL container was stopped and removed after the test.

## Readiness and remaining manual check

`MODE_D_SCHEMA_COMPATIBILITY=PASS`  
`SOURCEOPPORTUNITY_3188_PAGE_ONLY_CANDIDATE=READY_FOR_PUBLICATION_APPROVAL`  
`NORMAL_BROWSER_ACCEPTANCE=PENDING`  
`PRODUCTION_DATA_MUTATIONS=0`  
`DOCUMENTS_PUBLISHED=0`

Before a production publication decision, manually open the exact Furas page in a normal browser and verify (without signing in, purchasing, or submitting):

1. The page still identifies reference `01-26-017001-42008` and shows current lifecycle/deadline.
2. The booklet download action’s actual navigation still redirects to listings and does not produce a PDF.
3. The booklet purchase action and official service workflow still support purchase before bid submission.
4. Whether the displayed `1500` has a currency label. Until explicitly shown, keep the amount hidden.

**Final decision:** `FIRST_REAL_BOOKLET_RECORD=READY_FOR_PUBLICATION_APPROVAL`; browser acceptance and any later production publication approval remain pending. No production record was inserted.

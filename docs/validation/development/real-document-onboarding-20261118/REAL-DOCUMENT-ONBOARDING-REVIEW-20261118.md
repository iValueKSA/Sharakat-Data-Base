# Furas access recovery and multi-source real document review

**Review time:** 2026-11-18 (Asia/Amman)  
**Mode:** Read-only production inspection; bounded public page requests.  
**Decision:** `REAL_DOCUMENT_ONBOARDING=SOURCE_ACCESS_OR_EVIDENCE_BLOCKED`

## Findings

### Furas access diagnosis

- **Windows host:** DNS/TCP/TLS succeeded. A normal `curl.exe` GET to the exact current detail URL returned HTTP 200; connect 0.065 s, TLS 0.119 s, first byte 1.371 s, total 2.884 s.
- **Application container:** DNS resolved, TCP/443 connected, TLS 1.2 completed in 0.09 s, and the same detail GET returned HTTP 200 in 2.35 s. The response was the Furas page (1,619,438 bytes), not an error page.
- **Normal browser:** Not verified. The active Edge window was not exposed to UI automation; Edge browser creation was unavailable and the in-app browser timed out attaching. The web reader also could not fetch Furas. This is an automation limitation, not evidence that a user browser is blocked.
- **URL integrity:** The existing helper’s `/index.php/ar/opportunity/{OPPORTUNITYID}?type=Investment` route is valid for SourceOpportunity 3188 / Master 597 and displays the matching Furas opportunity reference `01-26-017001-42008`. No URL/client correction is indicated. Prior 25/25 timeouts are not reproducible now; the evidence supports a transient connection/read stall, but does not identify a historical network component as the cause.
- **Attachment route:** The exact page lists “كراسة الشروط و المواصفات” and “مسودة العقد”. Its booklet anchor returned HTTP 302 to `/list-opportunities`; the final response was an HTML listing, not a PDF. No direct document is verified. No login or payment flow was attempted.

### RFPPRICE field

For the exact matching Furas record, the stored raw `attributes.RFPPRICE` is `1500`. The current official opportunity page labels the matching displayed amount `سعر الكراسة` (“booklet price”), showing `1500`. This verifies the field mapping as **booklet price** for this record, rather than rent, bid security, or investment value. The page does not identify a currency; **currency remains unverified** and no SAR is inferred. The page also has a “شراء الكراسة” (“buy booklet”) action, but whether purchase is mandatory to participate was not established.

### Reconciliation warning and freshness

- Job **698** ran 2026-11-02 09:59:30–10:03:10 UTC and ended `RECONCILIATION_SCOPE_WARNING` / `COMPLETED_WITH_WARNINGS`.
- It collected 375/375 records, 100% completeness, 7/7 pages, zero missing object IDs, and zero collection errors. Its exact guard was `CURRENT_SCOPE_IS_NARROWER_THAN_PRIOR_SCOPE`: job 694 had completed `SAUDI_NATIONAL_V1`; job 698 was `AL_AHSA_SUBSET_V1`. The guard correctly prevented removals from being inferred from a narrower scan. Removal reconciliation was disabled.
- Source state remains `technical_health=WARNING`, `coverage_status=COMPLETE_PUBLIC_SOURCE`, `sync_status=RECONCILIATION_SCOPE_WARNING`. The Nov. 2 snapshot is stale for lifecycle decisions as of Nov. 18. The current Furas detail page is live, but it does not refresh the stored national snapshot or prove current status for all 375 records.

## Alternative source review

Exactly 13 existing non-merged Master-linked records were reviewed across the three selected registered sources (the Furas representative row below is separate):

| Source | Records | Evidence and outcome |
|---|---:|---|
| Al-Ahsa platform | 5 | Source rows 2780/2866/2865/2864/2862 map exactly to provider IDs 515/521/522/523/524 and Masters 226/231/264/263/253. Status/deadline snapshots were current as of Nov. 17. Four public pages reviewed by the web reader show opportunity details and available status, but no opportunity document section or attachment. The fifth page timed out in the web reader. Captured payloads have no attachment/document fields. |
| NCP Investors Portal | 5 | Source rows 2781/9465/9462/9458/9454 map to Masters 228/6702/6704/6686/6705. The four project-detail payloads explicitly have `documents=[]`; the fifth is an expired NCP news item with `attachments=[]`. The exact UUID pages could not be fetched by the web reader. Four current portal records have unknown lifecycle in the platform, so none is accepted as a current publication candidate. |
| RCJY Investment Portal | 3 | Source rows 9322/9321/9323 map exactly to provider IDs 266/269/265 and Masters 6676/6677/6675. Raw provider payload has an OfficialBooklet file ID 2205 and a displayed purchase deadline for ID 269, but the linked Master/source lifecycle is unknown and the adapter stores only the generic catalog URL. IDs 265 and 266 have brochure IDs but no booklet ID; dates use the 1900 sentinel. The public catalog requires JavaScript and its detail/document destinations, currency, document content, and current status were not verified. File IDs alone are not publication evidence. |

No unrelated NCP branding/sponsor assets were treated as project documents. The records and decisions are listed in [the review CSV](real-document-review-20261118.csv).

## Publication decision

- **Verified public direct documents:** 0. The Furas document anchor redirects to the general listing; alternative-source records have no verifiable document destinations.
- **Verified purchase-required documents:** 0. Furas displays a booklet price and purchase label, but currency and the requirement to buy for participation are unverified; the purchase flow was not followed.
- **Verified login-required documents:** 0. No login gate was observed or tested.
- **Verified application forms:** 0.
- **Official page-level Furas evidence:** 1 page-level candidate (SourceOpportunity 3188 / Master 597) with the exact opportunity, booklet label, draft contract label, and amount 1500. It is held because the booklet link resolves to the general listing; this is not yet a defensible document record or an action-ready purchase destination.
- **Current/historical publication candidates:** 0 / 0.
- **First real document batch:** 0. No `SourceOpportunity` or Master IDs are proposed for insertion.
- **Isolated database/API/browser validation:** Not run because no candidate passed the document destination/access gates. This avoids manufacturing a real-data test success. Previously accepted synthetic MVP validation was not repeated.

## Automation readiness

- **Furas:** Not ready for document extraction. Preserve exact `OPPORTUNITYID`; add per-item page observations for document title/type, stable document ID, official destination, access/login/payment state, amount/currency exactly as displayed, participation requirement, timestamp, and page/link fingerprints. Do not infer from `RFPPRICE` outside a matching page comparison.
- **Al-Ahsa:** Existing capture has no document fields. A future bounded detail capture needs exact provider ID plus document links/labels and access conditions.
- **NCP:** Keep the exact portal UUID; `documents=[]` in the sampled detail payload. Do not promote sponsor logos/branding into project documents. Recheck only when the official project payload exposes an item-level document.
- **RCJY:** Preserve `InvestmentOpportunity.Id` and `OpportunityCode`, but add a verified detail/file destination, document title/type, lifecycle label, file ID semantics, explicit price field label/currency, access and participation conditions. Do not interpret `BookletPrice`, `BookletPriceValue`, or file IDs by name alone.
- Across sources, refresh only individually approved existing identities using bounded read-only page checks and evidence timestamps. Keep human verification and the current publication gate; no national enumeration or automatic publication.

## Safety and final status

- `PRODUCTION_DATA_MUTATIONS=0`
- `SOURCE_SYNCHRONIZATIONS=0`
- `SERVICE_RESTARTS_OR_DEPLOYMENTS=0`
- `DOCUMENTS_PUBLISHED=0`
- Live `opportunity_documents` count observed read-only: 0
- No migration, account/login, purchase, application, identity change, Furas activation, removal, or schedule change was performed.

**Remaining blockers:** Furas attachment URL redirects to `/list-opportunities`; normal browser verification was unavailable; Furas currency and participation-purchase semantics are unknown; alternatives have empty/unverified document evidence or unknown lifecycle; no candidate passed publication validation.

**Next recommended action:** In an ordinary browser session, open the exact Furas page and inspect the booklet link and purchase details without signing in, buying, or submitting anything. If its link still routes to the listings page, request the official Furas team to correct the attachment destination and confirm the currency and whether booklet purchase is mandatory for bidding. Then repeat a one-record read-only verification before preparing any real document row.

**Final decision:** `REAL_DOCUMENT_ONBOARDING=SOURCE_ACCESS_OR_EVIDENCE_BLOCKED`.

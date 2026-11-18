# Final KFU provenance review: nine unresolved references

**Review date:** 2026-11-16  
**Status:** REVIEW_COMPLETED_WITH_LIVE_PAGE_FETCH_LIMITATION  
**Mode:** Read-only production verification; no deployment or data changes.

## Decision summary

All nine register entries were individually reviewed. No new exact association was approved and no publication candidate is ready.

- EXACT_ASSOCIATIONS_VERIFIED: 0
- DIFFERENT_NOTICE_CONFIRMED: 1
- SHARED_LISTING_REFERENCES: 5
- INSUFFICIENT_EVIDENCE: 3
- RESTRICTED_REFERENCES: 0
- CURRENT_DOCUMENT_CANDIDATES: 0

The full row-level register, including exact URLs, source record/provider/Master, source snapshot pointers, file type, evidence and reasoning, is in [kfu-nine-reference-decision-register-20261116.csv](kfu-nine-reference-decision-register-20261116.csv).

## Evidence and limitations

The historical register contains exactly nine unresolved association instances: the same investor-guide PDF on SourceOpportunity 2773–2777, and the same 2025 tender booklet on 2774–2777. Both URLs are stored under derived raw_data_json.attachments with downloaded=false and checksum=null. They are absent from normalized opportunity_documents (0 rows).

Production SourceObservations and old SourceContentItems retain the repeated links, but these entries were captured by the former parser that copied page-wide links onto each row. They are not independent evidence of item-level ownership. The register gives each source row's SourceObservation range/count and matching SourceContentItem ID. SourceOpportunity 2775–2777 are removed procurement-text fragments with no Master and no stable official notice ID.

A bounded direct GET to the official KFU announcements page timed out after 8 seconds (HTTP 000). The official search index returned a page snapshot crawled about two weeks before this review, showing two distinct panels: the expired 2025 food-services/general-services tender and the seasonal-rental opportunity. It shows the booklet with the old tender, deadline 2025-01-22, price SAR 300, and purchase required to participate. The seasonal-rental panel has an application link and no booklet. The official booklet PDF index result, crawled three days before this review, identifies it as the food-services/general-services tender booklet. These index results corroborate the prior direct official-page inspection documented in the [KFU identity review](../kfu-document-provenance/KFU-AND-INVESTSAUDI-IDENTITY-REVIEW-20261116.md), but they do not replace a successful live GET today.

The archived [official_page_snapshot.html](../../../../tests/fixtures/kfu_announcements/official_page_snapshot.html) test fixture records the same two-panel distinction and shows the guide outside the notice panels. It is a parser fixture, not a production capture. The previous direct page inspection reported the investor guide outside notice panels. Today's direct request could not refresh that observation.

## Per-reference findings

**Five investor-guide associations — SHARED_LISTING_REFERENCE.** The KFU link label is رحلة المستثمر. The URL is a general investor-guide PDF outside the notice panels, so it has no item-level link to any of SourceOpportunity 2773–2777.

**Booklet association on SourceOpportunity 2774 — DIFFERENT_NOTICE_CONFIRMED.** The official item-level evidence places the booklet on the 2025 food-services/general-services tender represented by SourceOpportunity 2773 / Master 224. SourceOpportunity 2774 is a removed seasonal-rental record linked to Master 225. The prior legacy 2774/2928 identity question remains open. This classification confirms the link belongs to another notice; it does not authorize a move, deletion, merge or relink.

**Booklet associations on SourceOpportunity 2775, 2776 and 2777 — INSUFFICIENT_EVIDENCE.** The booklet is verified on the old tender notice, but the three separately keyed rows contain short removed procurement-text fragments. Their observations repeat the old parser's page-wide attachment array. No stable official notice ID or independent item-level file link establishes that each fragment should carry an opportunity-level booklet association. Leave all three unassociated.

None of the nine is classified RESTRICTED because no affirmative access restriction was established. Rights to host or redistribute either PDF remain unverified. The live KFU page request timed out, and neither PDF was downloaded. Search-index visibility is not a reuse license.

## Publication assessment

No new document candidate is ready. The booklet belongs to an expired 2025 tender (deadline 2025-01-22); its notice states a SAR 300 booklet price and that purchase was required to participate. This confirms a participation purchase requirement, not whether payment is required to access the public copy. Rights/reuse and fresh direct access were not verified. The investor guide has no exact opportunity association, and its rights/access terms are unverified. No document was downloaded, hosted or published.

The previously supported booklet association on 2773 is outside this nine-reference register and was not reopened or changed.

## Post-correction status and integrity

- Worker parser: 2026.11.16-kfu-2.
- KFU remains enabled and healthy at its unchanged 720-minute interval.
- Latest KFU sync is job 975, successful at 2026-11-16 06:35:30 UTC, before the 2026-11-16 12:15 UTC correction.
- No natural KFU sync has completed after the correction: POST_SYNC_STABILITY=PENDING. No manual sync was run; the schedule was not changed.
- SourceOpportunity 2928 still has attachments=[] and remains linked to Master 326. SourceOpportunity 2774 remains linked to Master 225.
- KFU_2928_CORRECTION_STABILITY=PASS_FOR_CURRENT_READ; POST_SYNC_STABILITY=PENDING. The corrected metadata has not yet been exercised by a natural post-correction collection.
- KFU source and Master identities remain unchanged. Furas and RCU settings were not changed.

## Safety and next action

PRODUCTION_DATA_MUTATIONS=0  
PRODUCTION_DEPLOYMENT_STATUS=NONE  
DOCUMENT_ROWS=0  
SOURCE_SYNCHRONIZATION=NONE  
SCHEDULE_CHANGES=0

Remaining limitations: the direct KFU page fetch timed out; post-correction natural-sync stability is pending. Existing official-page review and indexed evidence support conservative individual classifications.

**Next recommended action:** after the next natural KFU run, perform a read-only check that SourceOpportunity 2928 still has no inherited attachments and all source/Master identities remain unchanged. Keep the nine reviewed associations unapproved and unpublished; do not trigger a manual sync.
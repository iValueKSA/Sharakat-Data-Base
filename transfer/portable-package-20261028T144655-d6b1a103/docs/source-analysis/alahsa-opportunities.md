# Source assessment: Al-Ahsa Investment Opportunities Platform

**Assessment date:** 11 October 2026 (Asia/Amman)  
**Source:** منصة الفرص الاستثمارية بالأحساء — أمانة الأحساء  
**Main URL:** https://alahsa-opportunities.com/

## Current findings

- The listing is server-rendered HTML. No public JSON API or relevant XHR/fetch listing endpoint was found in the inspected pages.
- The first page advertised numbered pagination through page 9. The adapter visits every page and deduplicates on numeric `/opportunities/{id}` links.
- Category totals are 72 general listings, 2 featured listings, and 0 direct-lease listings. The first two categories have disjoint IDs, for 74 distinct records total.
- The `status=متاحة` page has 74 visible records; `status=منتهية` returns 0. All 74 current cards show “متاحة”; none has a past deadline on the assessment date.
- Because the platform is dedicated to Al-Ahsa, records are classified with `SOURCE_FILTER`; each card's location and title remain as evidence. This avoids dropping listings for spelling variants such as جواثى.
- Latest complete snapshot: source-reported 74, pages requested/successful 9/9, received/parsed/unique/accepted 74, rejected 0, completeness 100%, active 74, expired 0.

## Extraction and data notes

The adapter reads card title, status, numeric detail ID, location, area, activity, contract duration, deadline, and details URL. Individual attachments are not yet extracted. Missing references remain NULL because the public cards do not expose them. No financial value is inferred from unrelated fees.

The complete count reconciliation and remaining validation findings are in [first-live-integration-validation.md](../validation/first-live-integration-validation.md).

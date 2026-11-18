# KFU document provenance and Invest Saudi identity review

**Date:** 2026-11-16  
**Mode:** isolated parser implementation; production database queried read-only  
**Decision:** isolated fix validated; production metadata remains unchanged and requires a separate approved correction.

## Final status

- KFU_DOCUMENT_PROVENANCE=ISOLATED_FIX_VALIDATED
- KFU_COLLECTOR_CORRECTION_STATUS=ISOLATED_FIX_VALIDATED_NOT_DEPLOYED
- KFU_SOURCE_IDENTITY_REGRESSION=PASS_FOR_CURRENT_AND_VERIFIED_HISTORIC_KEYS; LEGACY_DUPLICATE_REQUIRES_SEPARATE_REVIEW
- INVEST_SAUDI_IDENTITY_REVIEW=4_REVIEWED; 0_SUPPORTED_MASTER_ASSOCIATIONS
- INVEST_SAUDI_EXACT_MASTER_ASSOCIATION_SUPPORTED=0
- INVEST_SAUDI_POTENTIAL_MATCH_REQUIRES_REVIEW=0
- INVEST_SAUDI_NO_SUPPORTED_MASTER_MATCH=4
- INVEST_SAUDI_SOURCE_RECORD_NOT_ELIGIBLE=0
- KFU_RECORDS_POTENTIALLY_AFFECTED=6; PERSISTED_ATTACHMENT_REFERENCES=12
- KFU_CONFIRMED_INCORRECT_CURRENT_ITEM_REFERENCES=2; OTHER_UNVERIFIED_OR_UNASSIGNED_REFERENCES=9; ITEM_LINK_SUPPORTED=1
- DOCUMENTS_READY_FOR_PUBLICATION=0
- PRODUCTION_DATA_MUTATIONS=0
- PRODUCTION_DEPLOYMENT=NONE

The parser now limits document association to an exact top-level notice panel. Generic page references and repeated cross-notice references remain listing-level evidence. An incomplete or ambiguous parse reports an incomplete collection so the normal collector cannot treat it as a complete empty snapshot.

## Root cause and official-page evidence

KfuAdapter.fetch() previously collected every PDF/DOC/XLSX anchor on the shared listing page into one links array, then copied that same array onto every notice. It also emitted one content item per notice with url="", and the content-item upsert uses that URL as its external key, so those page items collided. The source opportunity URL was blank for some rows and other rows carried a fabricated #kfu-announcement:<hash> fragment. Neither represented an item-specific page.

The official KFU listing is [KFU Investment Administration announcements](https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/%D8%A7%D8%B9%D9%84%D8%A7%D9%86%D8%A7%D8%AA-%D8%A7%D9%84%D8%A5%D8%AF%D8%A7%D8%B1%D8%A9.html). A bounded read-only GET returned HTTP 200 HTML. It has two top-level li.AccordionPanel notice containers, with no item-specific detail URL or stable official notice identifier. The DOM IDs (u12393, u11652) are generated presentation IDs and are not used for identity.

Observed links and relationships:

- The old food-services tender panel contains the official booklet [كراسة مطاعم ومتاجر عامة](https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/assets/%d9%83%d8%b1%d8%a7%d8%b3%d8%a9%d9%85%d8%b7%d8%a7%d8%b9%d9%85-%d9%88%d9%85%d8%aa%d8%a7%d8%ac%d8%b1-%d8%b9%d8%a7%d9%85%d8%a9.pdf). Its explicit deadline is 2025-01-22 and the notice says the booklet costs SAR 300.
- The current seasonal-rental panel has a Google Forms [application form](https://docs.google.com/forms/d/e/1FAIpQLScezmr8dYl4I6uTkaEmTse7EKBz5rH7pMu1eqOj2iHO05ipzw/viewform?usp=sf_link), but no booklet or other file attachment.
- The “رحلة المستثمر” investor guide is outside the notice panels. It is listing-level material, not an attachment to every opportunity.
- The current seasonal-rental item exposes no verified deadline, booklet purchase instructions, or booklet price. The unrelated old tender price is not transferred.

The collector does not download or publish these documents. Public accessibility is not treated as redistribution permission.

## Isolated change

Modified files:

- app/adapters.py: per-panel parsing; exact panel-only document association; forms recorded separately as application_links; page-level references retained once in a listing SourceContentItem keyed by the actual listing URL; source_url remains empty when no item URL exists; raw provenance explicitly says listing-only. Repeated document URLs across notice panels and duplicate normalized notice titles fail closed and mark collection incomplete. Missing notice containers also fail closed.
- tests/test_wave3_adapters.py: updated KFU behavior assertions.
- tests/test_kfu_document_provenance.py: parser and identity regression tests.
- tests/fixtures/kfu_announcements/official_page_snapshot.html
- tests/fixtures/kfu_announcements/provenance_cases.html
- tests/fixtures/kfu_announcements/current_seasonal_identity.html

Stable identity remains kfu-announcement: plus the existing hash of the listing URL and normalized title. No generated DOM ID, fuzzy title, or synthetic detail URL is used.

## Production impact register

Read-only production query found six KFU SourceOpportunity rows. Each presently stores the same two listing-wide references: the generic “رحلة المستثمر” guide and the 2025 food-services booklet. That is 12 persisted opportunity-level references:

- 1 supported item-level reference: booklet on SourceOpportunity 2773, Master 224, whose notice is the matching expired food-services tender.
- 2 confirmed wrong for the current item: both inherited links on SourceOpportunity 2928, Master 326; its current panel has only the application form.
- 9 unverified/unassigned references: one generic guide on 2773, both inherited references on 2774, and both on each of 2775–2777. The four removed historic rows do not have enough item-level page evidence to reassign either file.

“Unverified” is not converted into a claim that a particular historical notice owned a booklet. No row or raw observation was changed. See the row-level [KFU impact CSV](kfu-production-impact-register-20261116.csv).

| SourceOpportunity | Master | Database lifecycle | Evidence and proposed treatment |
|---:|---:|---|---|
| 2773 | 224 | منتهية / EXPIRED | The old official panel contains the booklet, so preserve that item-level reference. Move the generic investor guide out of opportunity-level associations only after separate authorization. |
| 2774 | 225 | أزيلت من المصدر; 32 missing checks | Title equals the current seasonal notice title, but provider ID differs and the row is removed. Both links are unverified. Preserve identity and Master 225; no merge/reassignment. |
| 2775 | — | أزيلت من المصدر; 27 missing checks | Removed historic procurement-text snippet; no item-level file link evidence. Preserve the source observation; hold both links unassigned. |
| 2776 | — | أزيلت من المصدر; 27 missing checks | Removed historic procurement-text snippet; no item-level file link evidence. Preserve the source observation; hold both links unassigned. |
| 2777 | — | أزيلت من المصدر; 27 missing checks | Removed historic procurement-text snippet; no item-level file link evidence. Preserve the source observation; hold both links unassigned. |
| 2928 | 326 | حالة غير معروفة / UNKNOWN; last seen 2026-11-11 | Current seasonal-rental notice: application form only, no booklet/price/deadline. Remove inherited guide and old booklet references only with separate approval; preserve Master 326. |

The full source IDs, titles, links, last-seen values, and proposed future treatment are in the impact CSV. Production had zero opportunity_documents rows and seven KFU SourceContentItem rows at query time: six used constructed hash-fragment keys and contained the same two links, while one used a blank key and also contained both links. A future collector run will create one correctly keyed listing-page item; it must not silently delete or rewrite the seven historical page observations.

### Future production correction plan (not applied)

1. Retain all six SourceOpportunity rows, lifecycle observations, provider IDs, and current Master links exactly as stored.
2. For 2773, retain the exact old-tender booklet association and remove the generic guide from its opportunity-level attachment list; record the listing-page provenance for the guide.
3. For 2928, remove both copied links from its opportunity-level metadata and retain the Google Forms URL as an application link, not a document.
4. For 2774–2777, leave all document ownership unresolved. Do not move the booklet to these records and do not delete their source observations.
5. Keep the seven historical SourceContentItem observations intact; a future valid listing-key item should be additive until separately reviewed.
6. Preserve evidence of every correction and the before/after payload in an approved audit artifact before any separately authorized write.
7. Do not publish any document until its item association, access class, purchase requirement, and reuse/linking rights pass existing Documents MVP gates.

## KFU source identity review

The read-only production query found:

- SourceOpportunity 2773 has provider ID kfu-announcement:0d11721853f11a8fcd75be5e; recomputing the established URL + normalized-title formula from the stored title gives the same value.
- Current SourceOpportunity 2928 has provider ID kfu-announcement:0aac035af08807f4f1755ee5; the same formula produces the same value. The synthetic current-notice fixture verifies the parser emits this existing ID.
- SourceOpportunity 2774 has the same stored source title as 2928, but provider ID kfu-announcement:7e98c5dfb12b0a6d09f4c349 does not equal the current formula result and it links to different Master 225 (versus Master 326 for 2928). This is a pre-existing legacy identity/Master duplication requiring a separately evidenced review. The parser does not merge, overwrite, or relink either row.
- Rows 2774–2777 contain constructed hash fragments in source_url; these are not detail URLs. The updated collector emits source_url="" and an explicit listing-only URL provenance marker.

The parser itself has no database write path. Tests cover repeat collection and order-independent provider IDs; production identity and Master links were queried read-only. No master creation, merging, or link change occurred.

## Invest Saudi records 218–221

Official Invest Saudi listing and opportunity detail text is present on [Invest Saudi’s regional investment page](https://investsaudi.sa/invest-in-region) and its [sports sector page](https://investsaudi.sa/sectors/sport). The listed titles, sectors, and locations agree with the stored provider IDs/slugs. The official page supports the opportunity identities; it does not supply an exact Master ID/reference for these database records.

Read-only exact matching checked provider IDs, original/normalized official IDs, source references, raw provider IDs, Master canonical IDs/references, active identity aliases, and exact Master titles. Results: exactly the four intended Invest Saudi source rows; zero other source rows with those exact identifier tokens; zero matching Masters; zero aliases; zero exact-title Master matches. All four have no current Master link, raw lifecycle UNKNOWN/غير محددة, and last_seen_at 2026-11-11. No fuzzy-title matching was used.

| SourceOpportunity | Provider ID / official ID | Opportunity | Sector / location | Decision |
|---:|---|---|---|---|
| 218 | investsaudi:54682 / 54682 | Equestrian Training Academy in Public Schools – Riyadh | Education / Riyadh | NO_SUPPORTED_MASTER_MATCH |
| 219 | investsaudi:54681 / 54681 | Investing in Sports Facilities in Public Schools – Jeddah | Education / Makkah | NO_SUPPORTED_MASTER_MATCH |
| 220 | investsaudi:54680 / 54680 | Investing in Sports Facilities in Public Schools – Dammam | Education / Eastern province | NO_SUPPORTED_MASTER_MATCH |
| 221 | investsaudi:54679 / 54679 | Investing in Sports Facilities in Public Schools – Riyadh | Education / Riyadh | NO_SUPPORTED_MASTER_MATCH |

Each raw payload contains the same provider PDF URL twice (pdf_url and pdf_file.url). These are references only: no downloaded document, verified access classification, or reuse licence is established, and the production opportunity-document table remains empty. All four source rows are eligible for later manual Master-link review; none is classified SOURCE_RECORD_NOT_ELIGIBLE. No source or Master link was altered. The row-level [Invest Saudi review CSV](invest-saudi-master-review-20261116.csv) records the URLs and exact-match basis.

## Validation

Isolated container tests used the candidate API image with the current worktree mounted; no production database was used for tests. Documents MVP API tests used a newly created disposable PostgreSQL container on a private Docker network, then removed it.

Coverage included:

- Independent notices with their own PDF; one notice with multiple files; no-file notice; generic shared-page PDF; expired booklet vs current form-only notice.
- Similar-but-distinct titles; repeated same-panel URL deduplication; repeated cross-notice URL unassignment; duplicate-title collision; missing panel fail-closed behavior.
- No fabricated detail URL; form-vs-booklet distinction; order-independent source IDs; identical repeated-capture hashes; existing current KFU provider ID 0aac035af08807f4f1755ee5; two exact resolver lookups select the same existing SourceOpportunity and Master relationship in an isolated SQLite fixture.
- Existing adapter, source-link, source-identity-alias, and Documents MVP publication-gate regressions.

Latest combined focused run: 110 passed, 2 skipped, with one upstream Starlette/httpx deprecation warning. The two skips are optional PostgreSQL-only source-identity alias integration tests whose separate test database was not configured. Documents MVP API gates passed against the disposable database. The initially attempted database-gate run without that disposable DB failed its safety precondition; it was then run successfully against the isolated database. No broad UI/map/export test cycle was repeated because this patch changes only KFU adapter parsing.

## Blockers and next action

- The KFU parser fix is not deployed; production still contains the old associations.
- Production cleanup requires separate explicit authorization and an audited record-level correction. The already deployed Documents MVP publication gates remain unchanged.
- SourceOpportunity 2774 / Master 225 versus current 2928 / Master 326 is an existing identity/Master duplication. Do not resolve using title similarity; obtain official item identity history or other independent evidence first.
- Invest Saudi PDFs need document-level access/rights review; their raw URLs alone do not approve publication.

**Next recommended action:** review and approve a narrowly scoped production correction plan and the separate 2774/2928 identity adjudication before any production write or deployment.

## Safety record

No production writes, synchronization, migration, deployment, service restart, document publication/import, Master change, or source/link correction was executed. Only isolated worktree source/tests/report files changed.

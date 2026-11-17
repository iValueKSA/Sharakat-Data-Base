# First Real Opportunity Documents — Current Shortlist and URL Provenance Review

**Review date:** 2026-11-16  
**Mode:** Read-only production evidence review; isolated validator guard check; no deployment or document insertion

## Decision

**FIRST_REAL_DOCUMENT_BATCH = PARTIAL_OR_BLOCKED**  
**FIRST_PUBLICATION_CANDIDATE_COUNT = 0**  
**PRODUCTION_DATA_MUTATIONS = 0**  
**PRODUCTION_DEPLOYMENT = NONE**

No real document currently satisfies current availability, exact SourceOpportunity-to-Master association, document-level relationship, access and rights evidence, and the deployed publication gate at once. No record was inserted or approved.

The existing classified register was reused: 3,832 reference occurrences, 4 previously verified document files, and **0 seed-eligible documents**. No full 3,832-reference re-audit was repeated. The existing verified register and schema/readiness reports remain unchanged.

## Bounded current-opportunity review

The read-only live scan found **34 SourceOpportunity rows** with explicit attachment/document references (158 attachment occurrences across KFU and Ta'adeen). The official/source-page metadata and available exact identity fields reduced the bounded current review to five official-site entries: KFU row 2928 and Invest Saudi rows 218–221. These five have either unknown lifecycle or an unstated closing window and **none has a publishable document record**. Four additional historical/negative controls were checked to resolve the KFU issue and apply prior rights findings. The record-level shortlist is in `current-opportunity-shortlist-20261116.csv`.

- **KFU 2928 → Master 326:** The current KFU page lists seasonal temporary food-service rentals and links an application form. It states no deadline, booklet, price, or participation purchase terms. The source row is locally `حالة غير معروفة`. Its two stored PDF attachments are page-wide links, not links nested under this item; the visible booklet is associated with the separate 2025 tender. They cannot be attached to Master 326.
- **Invest Saudi 218–221:** Official pages currently surface the Equestrian Academy and public-school sports facility opportunities. Their local SourceOpportunity records have provider IDs and stored official detail routes, but `master_opportunity_id` is null. The `pdf_url`/`pdf_file` references are not proof of a booklet or of document access, rights, or association to a platform Master. These are `REQUIRES_ADDITIONAL_EVIDENCE`, not publication candidates.
- **Ta'adeen 9494:** The official opportunity detail page identifies it as **Inactive** and its bidding stages concluded in February 2026. It has no Master association. Excluded.
- **Ta'adeen 9497:** Historical/inactive and Master-unlinked. Prior verification found three PDFs and one DOCX link on the page; one PDF carries confidentiality/no-redistribution language. Do not expose that file. Rights for the other items remain unresolved.
- **KFU 2773 → Master 224:** Retained only as historical reference. The official notice lists the deadline as 2025-01-22, a SAR 300 booklet, and says purchase plus proof was required to bid. The publicly viewable PDF is separate from that participation requirement. The opportunity is expired and KFU linking/reuse terms remain unclear.

The official Ta'adeen 2026–2027 preliminary plan page is marked Active and reports 17 available sites, but the plan is not an exact SourceOpportunity/Master-linked opportunity with a verified document in the live records. No identity or document row was inferred from that aggregate program.

## Source URL provenance gap

**SOURCE_URL_ROOT_CAUSE:** The KFU adapter intentionally constructs each notice as `RawOpportunity(url="")` and stores only the shared announcements page in `raw_data_json.source_listing_url`. It scrapes the page’s PDF links once and assigns that page-level list to each parsed notice. Thus KFU SourceOpportunity rows 2773 and 2928 have empty `source_url`, and row 2928 inherits the 2025 booklet even though its own listing item links to a seasonal-rental application form. The structured field is blank to avoid claiming the shared page as an exact opportunity page; the broad attachment assignment is the actual association defect.

**SOURCE_URL_FIX_REQUIRED:** Yes, at source capture for KFU. Capture a stable, official per-item detail/anchor only if the KFU page provides and verifies one; capture each document link from within that exact item. Keep the shared listing URL as listing provenance only. No fuzzy title URL or synthetic fragment is acceptable.

**SOURCE_URL_ISOLATED_FIX_STATUS:** No API fallback patch prepared or applied. This is the correct outcome because the current KFU payload contains no verified source-specific opportunity URL. The deployed exact-source gate correctly rejects a generic listing as the opportunity page and the safe empty-page serializer returns no link for a blank structured URL. A targeted isolated run confirmed both behaviors. Do not loosen either gate.

**Similar fields:** The live database has 75 Invest Saudi SourceOpportunity records with blank structured `source_url`; sampled blank rows have a numeric provider ID but no raw `link`, `url`, slug, or opportunity-detail URL. No route was inferred. Ta'adeen rows have exact detail URLs in both structured and explicit source fields. The six RCU rows have structured `source_url` populated and explicit `source_opportunity_url` metadata. Furas already has its source-ID/type-based URL resolver; this review found no Furas document attachment references. No analogous document fallback is justified.

## Document evidence and schema candidates

The prior verified-document register remains the document-level evidence register:

- Four files had prior response/content evidence (the KFU booklet and three Ta'adeen PDFs). The historical KFU booklet is tied to row 2773/Master 224; the Ta'adeen files are tied to row 9497 but have no Master association.
- One Ta'adeen PDF is `RESTRICTED_DO_NOT_PUBLISH`; the other verified document rights are unresolved. KFU rights to direct-link/reuse are unresolved.
- Only the historical KFU price is verified: **SAR 300**, purchase required to participate; the public preview did not require payment. No current candidate has a verified price or purchase requirement.
- Direct-link candidates: **0**. Official-source-page-only candidates: **0**. Additional-evidence records: **8** in the bounded shortlist. Restricted document records: **1** known Ta'adeen file (plus the parent opportunity remains unlinked/inactive).

No Migration 0027 record JSON was proposed for insertion because no real candidate passed its required gates. The proposed source/master ID arrays are empty: `PROPOSED_SOURCEOPPORTUNITY_IDS=[]`, `PROPOSED_MASTER_IDS=[]`.

## Isolated checks

- Production read-only snapshot: `opportunity_documents=0`, `source_opportunities=9,470`, `opportunities=6,680`, Alembic head `0027_opportunity_documents_mvp`.
- Targeted isolated code check using the production-compatible candidate: generic KFU listing supplied as an exact opportunity URL was rejected with `Opportunity page must match the exact stored SourceOpportunity URL`; blank KFU URL produced no safe source-page fallback. No database write occurred.
- Fresh isolated PostgreSQL run of `tests/test_opportunity_documents.py` and `tests/test_opportunity_documents_migration_postgres.py`: **7 passed**. This covered API association/provenance, access/rights gates, safe URL serialization, duplicate/version constraints, and Migration 0027 behavior in a newly created disposable database. The database container and isolated network were removed after the run.
- Fresh-context Playwright simulation against the static frontend with synthetic API fixtures: **PASS**; zero browser errors, unexpected API calls, or failed requests. Scenarios covered direct-download vs source-page fallback, purchase labels/price, login/payment separation, safe external links, empty state, and mobile RTL. The temporary screenshot files were kept in the disposable runner only. This is not a real-opportunity publication simulation; no eligible real candidate exists.

## Status summary

| Field | Result |
|---|---|
| `SOURCE_URL_ROOT_CAUSE` | KFU parser leaves exact URL blank; page-level attachments are copied onto each notice |
| `SOURCE_URL_FIX_REQUIRED` | Yes, source-capture correction after a verifiable item-level URL is available |
| `SOURCE_URL_ISOLATED_FIX_STATUS` | No API patch; exact-match security gate retained and tested |
| `CURRENT_OPPORTUNITIES_REVIEWED` | 5 official-site entries (KFU 2928; Invest Saudi 218–221); none meets document publication gates |
| `OFFICIAL_DOCUMENTS_VERIFIED` | 4 prior verified files; 0 new current-opportunity documents |
| `DIRECT_LINK_CANDIDATES` | 0 |
| `SOURCE_PAGE_ONLY_CANDIDATES` | 0 |
| `ADDITIONAL_EVIDENCE_REQUIRED` | 8 shortlist rows |
| `RESTRICTED_DOCUMENTS` | 1 confirmed Ta'adeen file |
| `BOOKLET_PRICES_VERIFIED` | SAR 300 for expired KFU row 2773 only |
| `PARTICIPATION_PURCHASE_REQUIREMENTS` | KFU 2773 only; purchase/proof required to bid |
| `FIRST_PUBLICATION_CANDIDATE_COUNT` | 0 |
| `PROPOSED_SOURCEOPPORTUNITY_IDS` | `[]` |
| `PROPOSED_MASTER_IDS` | `[]` |
| `ISOLATED_API_TESTS` | 7 focused disposable-PostgreSQL tests passed; targeted exact-URL guard rejection passed; no real-record candidate available |
| `ISOLATED_BROWSER_TESTS` | Fresh synthetic Playwright context passed; no real candidates to exercise |
| `PRODUCTION_DATA_MUTATIONS` | 0 |
| `PRODUCTION_DEPLOYMENT` | None |
| `REMAINING_BLOCKERS` | KFU item-level URL/document capture and reuse terms; KFU 2928 current window; Invest Saudi Master associations and document evidence; Ta'adeen Master and rights gates |

**NEXT_RECOMMENDED_ACTION:** Correct the KFU collector in an isolated source-capture candidate so it records a verifiable item-level source URL and item-scoped attachments; separately reconcile the four current Invest Saudi source rows to their exact Masters. Then revalidate document identity, access and rights. Keep all document rows unpublished until a real candidate passes and receives separate approval.

**FINAL_DECISION = PARTIAL_OR_BLOCKED**  
**FIRST_REAL_DOCUMENT_BATCH = PARTIAL_OR_BLOCKED**

## Official sources checked

- [KFU Investment Administration announcements](https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/%D8%A7%D8%B9%D9%84%D8%A7%D9%86%D8%A7%D8%AA-%D8%A7%D9%84%D8%A5%D8%AF%D8%A7%D8%B1%D8%A9.html) — the older dated tender/booklet and the current seasonal-rental form appear as separate entries.
- [KFU seasonal-rental application form](https://docs.google.com/forms/d/e/1FAIpQLScezmr8dYl4I6uTkaEmTse7EKBz5rH7pMu1eqOj2iHO05ipzw/viewform?usp=sf_link) — form only; no booklet evidence.
- [KFU publishing policy](https://www.kfu.edu.sa/ar/Deans/it/Documents/Publishing_policy.pdf) — linking/reuse conditions require case-specific review; no permission to copy or host was established.
- [Invest Saudi sports opportunities](https://investsaudi.sa/sectors/sport) and [Invest Saudi official portal](https://investsaudi.sa/) — current opportunity cards, without verified SourceOpportunity-to-Master associations for rows 218–221.
- [Ta'adeen mining bids](https://cms.taadeen.sa/en/mining-bids) and [Jubaihah detail](https://cms.taadeen.sa/en/mining-bids/sand-ore-and-backfill-complex-jubaihah) — official round/listing status; Jubaihah inactive.
- [Ta'adeen 2026–2027 preliminary plan](https://cms.taadeen.sa/en/mining-bids/exploration-licensing-tender-rounds-preliminary-plan-2026-2027) — aggregate active plan, not an exact Master-linked candidate.

**Safety:** No production writes, document publication, deployment, migration, service restart, source synchronization, Furas enumeration/removal, or source identity/geographic change occurred.



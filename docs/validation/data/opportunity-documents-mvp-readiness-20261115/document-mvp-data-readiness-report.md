# Opportunity Documents MVP Data Readiness

**Project:** Saudi Investment Opportunities Platform  
**Review date:** 2026-11-15  
**Execution mode:** Read-only database/API inspection, reuse of the prior feasibility audit, and bounded official-source samples. No production or project runtime changes.

## Final result

**DOCUMENT_MVP_READINESS_STATUS = PARTIAL.** All 3,832 saved reference occurrences have been classified without collapsing source rows. They represent 2,017 distinct non-empty, source-scoped URL values, 1,809 repeated occurrences, and 6 non-comparable malformed references. Two of the 2,017 distinct values are flagged `URL_NOT_HTTPS_OR_NOT_A_URL`; they remain unverified and are not seed-eligible. Four sampled references returned verified PDFs; they are not national coverage. No record meets every required MVP seed gate, so the eligible seed register contains zero data rows.

The live opportunity_documents table has zero rows and cannot preserve SourceOpportunity provenance or independent access, participation, rights, and verification states. No candidate was inserted.

## Project root and prior evidence

Compose labels identify `C:\Users\QusaiAbdElhalim\OneDrive - iValue\Desktop\الشراكات - الأحساء\Sharakat-Data-Base` as the active runtime workspace and identify both Compose configuration files there. `C:\Sharakat Data Base` is a distinct directory, not the same directory or a mounted alias; it has no Git checkout and its core-file hashes differ. The five accepted feasibility inputs in that copy were read and left unchanged. The classified output preserves all 18 original candidate-register fields in the same row order (3,832 input and output rows; 0 mismatches). New outputs are confined to the Compose-authoritative tree's docs/validation directory.

The active database's read-only snapshot check matched the accepted baseline: 14 registered sources, 6,680 total MasterOpportunity rows (6,659 current non-merged and 21 merged), 9,470 SourceOpportunity rows, 1,943 rows with candidate references, 3,832 reference occurrences, and 0 OpportunityDocument rows. The source-readiness matrix also contains 14 sources and sums to 3,832 occurrences. The full feasibility study was not repeated. No ingestion, blocked-endpoint retry, or broad regression was run.

## Required counts

| Metric | Result |
|---|---:|
| TOTAL_CANDIDATE_REFERENCES | 3,832 occurrences |
| UNIQUE_CANDIDATE_REFERENCES | 2,017 distinct non-empty source-scoped URL values (2 flagged as not HTTPS or not URL) |
| DUPLICATE_REFERENCES | 1,809 repeated occurrences, retained |
| VERIFIED_DOCUMENT_REFERENCES | 4 sampled PDF references |
| VERIFIED_BOOKLET_REFERENCES | 1 (KFU) |
| VERIFIED_OTHER_ATTACHMENTS | 3 PDFs (Ta'adeen) |
| EXACT_SOURCEOPPORTUNITY_ASSOCIATIONS | 5 official-page attachment references: 4 PDFs verified by response, plus 1 DOCX link whose content type was not verified |
| EXACT_MASTEROPPORTUNITY_ASSOCIATIONS | 1 (KFU Master 224) |
| PUBLIC_DIRECT_DOWNLOADS | 4 observed PDF responses |
| OFFICIAL_SOURCE_PAGES_WITH_DOCUMENT_LINKS | 2 sampled pages (KFU, Ta'adeen); platform-approved link destinations: 0 |
| LOGIN_REQUIRED | 0 confirmed |
| PAYMENT_REQUIRED_FOR_DOCUMENT_ACCESS | 0 confirmed |
| PURCHASE_REQUIRED_FOR_PARTICIPATION | 1 exact KFU opportunity; prior audit also found a separate Furas example, not generalized |
| PRICE_VERIFIED | 1 exact amount/currency: SAR 300 (KFU) |
| RIGHTS_RESTRICTED | 1 verified Ta'adeen PDF with confidentiality/no-redistribution notice |
| RIGHTS_UNKNOWN | 3 of the 4 verified PDFs |
| BROKEN_LINKS_CONFIRMED | 0 |
| ACCESS_UNKNOWN | 2,012 distinct source-scoped references: includes 1 sampled 403/HTML case; remaining references were not verified in the bounded sample |
| MVP_SEED_ELIGIBLE_DOCUMENTS | 0 |
| MASTERS_WITH_MVP_ELIGIBLE_DOCUMENTS | 0 |
| SOURCEOPPORTUNITIES_WITH_MVP_DOCUMENTS | 0 |
| SOURCES_FULLY_READY_FOR_MVP | 0 |

The access-unknown count is about unique URL references, not opportunities. The six malformed/non-comparable occurrences are not part of the 2,017 distinct non-empty URL values. The 403 result is not proof of a broken link or login requirement. Public file response does not establish reuse permission. Five references have exact opportunity-page attachment association: KFU row 2773 / Master 224 plus four attachment entries on Ta'adeen row 9497; only four of those attachment files were confirmed as PDFs, and Ta'adeen row 9497 has no Master association.

## Sample findings and disposition

- **KFU:** Official notice matches SourceOpportunity row 2773 / Master 224. The “كراسة الشروط و المواصفات” PDF returned application/pdf (13 pages). The notice states SAR 300 and requires booklet purchase/proof to bid. Public preview access and purchase required for participation are separate facts. Exact association is verified, but right-to-link terms are unresolved. It is excluded from the seed register. Other KFU page-wide links copied to multiple rows remain unverified associations.
- **Ta'adeen:** Three PDFs and one DOCX link are attached to the official Umm Hijlan page for source row 9497, which has no Master ID and is inactive. The three PDFs are verified; the DOCX content type is not. One general PDF includes confidentiality/no-redistribution language and is RESTRICTED_DO_NOT_EXPOSE. Rights remain unclear for the other two PDFs and the DOCX. Do not expose direct document URLs; any official-page fallback still requires rights review. The DOCX is excluded from the verified-document register.
- **Invest Saudi:** One PDF-like candidate returned HTTP 403 with HTML. Access and association remain unknown; it is not a confirmed PDF or broken link. No retry or bypass was attempted.
- **Furas:** No document URL exists in the local opportunity payload. An official indexed opportunity showed a 1,000 price and a download action, but the detail retrieval timed out; binary and currency were not verified. A separate official Furas participation-purchase example was not generalized to that record or all Furas opportunities.
- All other source-level findings and blockers are recorded in source-readiness-matrix.csv.

## Schema decision and first implementation scope

Read-only inspection found opportunity_documents empty, with id, opportunity_id (FK to opportunities), source_id (FK to sources), title, URL, nullable document_type, and first_seen_at. It has a primary key and opportunity_id index; no observed uniqueness constraint, SourceOpportunity FK, rights/access fields, bid-purchase fields, price/currency, verification evidence or source-page provenance. Therefore **SCHEMA_CHANGES_REQUIRED = YES** before loading a trusted record.

Recommended first implementation scope is an official-source link-out workflow only, with human-reviewed per-record evidence and no file hosting/proxy/cache. The exact minimum data model, API response fields, Arabic display rules, safe-link validation, refresh/versioning and acceptance gates are in mvp-implementation-specification.md. This task did not implement that specification.

## Remaining blockers

1. Confirm KFU terms/right-to-link and perform a bounded authorized recency check before considering row 2773 for a later seed.
2. Separately authorize a schema plan that retains SourceOpportunity provenance and distinct access, participation, rights and verification states.
3. Resolve Ta'adeen rights and Master association; never expose the restricted file.
4. Obtain item-level official association/access/rights evidence for Invest Saudi and additional sources; do not infer from file extensions or source-level examples.

**FINAL_DECISION = PARTIAL. Evidence preparation is complete; eligible seed count is zero.** No production data or schema, source schedule, source collector, application code, UI or service was changed.

## Official source references

- [Furas opportunity listing](https://furas.momah.gov.sa/ar/list-opportunities) — prior indexed example only; direct detail retrieval timed out.
- [King Faisal University investment announcements](https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/اعلانات-الإدارة.html) — exact sampled notice and booklet.
- [Ta'adeen Umm Hijlan (Mamilah) opportunity page](https://cms.taadeen.sa/en/mining-bids/umm-hijlan-mamilah%E2%80%8B) — sampled inactive opportunity and attachment list.
- [Invest Saudi](https://investsaudi.sa/) — one stored candidate returned HTTP 403/HTML; no retry.

**PRODUCTION_DATA_MUTATIONS = 0**  
**CODE_MODIFICATIONS = 0**  
**PRODUCTION_DEPLOYMENTS = 0**


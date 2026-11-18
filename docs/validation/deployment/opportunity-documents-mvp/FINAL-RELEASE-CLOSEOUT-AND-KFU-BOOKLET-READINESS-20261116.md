# Final Documents MVP Release Closeout and KFU Booklet Readiness

**Verified:** 2026-11-16 08:58 UTC  
**Mode:** Read-only production verification; no deployment or production writes

## Release closeout

**DOCUMENTS_MVP_RELEASE = ACCEPTED_AND_CLOSED_FOR_LOCAL_DEPLOYMENT**

The fresh unauthenticated browser opened `http://localhost:8080/` as a visitor. The national dashboard rendered its map, attribution, markers and clusters. The accepted canonical-origin network evidence shows Stadia tile responses are HTTP 200 at `localhost` and `127.0.0.1`. The previously reported 401 was specific to using `host.docker.internal` as the browser page origin; classify it as **TEST_ORIGIN_CONFIGURATION_ERROR**. No map/provider change is needed.

The region selector accepted Eastern Region (`region_id=5`) and Al-Ahsa (`governorate_id=501`). After the dashboard finished refreshing, it displayed 518 opportunities, 447 map-eligible, 71 ineligible, and zero truly missing coordinate pairs. The Al-Ahsa basemap and clusters rendered; clicking the 437 cluster expanded it to smaller clusters. An opportunity row opened its details modal. The details view contained zero document sections/actions/buttons. Browser console logs had no warnings or errors.

The active database remains at Alembic head `0027_opportunity_documents_mvp`; `opportunity_documents` remains empty. `/api/opportunities/224` returned a present `documents` array with zero records. No migration, service recreation, deployment, source sync, or production data mutation occurred.

The current local map and filter view were also visually observed in the fresh browser. A zero-document Al-Ahsa opportunity details modal showed no document controls. The current detail endpoint for KFU Master 224 also returns `documents: []`.

## KFU candidate identity and evidence

The read-only production record verifies SourceOpportunity `2773`, source `5` (King Faisal University), linked to MasterOpportunity `224`. Its provider key is `kfu-announcement:0d11721853f11a8fcd75be5e`; no separate KFU tender/reference number is published in the record or the official listing. The KFU source row's `source_url` column is empty; its official listing URL exists in `raw_data_json.source_listing_url`.

The current [KFU investment-administration listing](https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/%D8%A7%D8%B9%D9%84%D8%A7%D9%86%D8%A7%D8%AA-%D8%A7%D9%84%D8%A5%D8%AF%D8%A7%D8%B1%D8%A9.html) returns HTTP 200. It identifies the food services/restaurants/general stores opportunity and its addition for sites in university college buildings. It states a booklet price of SAR 300, requires booklet purchase and proof of purchase to submit a bid, and says purchase/bidding are handled by the university's Procurement and Bids Administration. Payment is described as bank payment (cash or certified check payable to KFU). The submission deadline was 2025-01-22 and bid opening was 2025-01-23. The production record is marked expired. Do not describe this opportunity as open or accepting bids.

The linked [KFU booklet PDF](https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/assets/%D9%83%D8%B1%D8%A7%D8%B3%D8%A9%D9%85%D8%B7%D8%A7%D8%B9%D9%85%D9%88%D9%85%D8%AA%D8%A7%D8%AC%D8%B1%D8%B9%D8%A7%D9%85%D8%A9.pdf) returned HTTP 200 (`application/pdf`, 1,161,269 bytes; Last-Modified 2025-01-26). Its title and contents identify the tender for food-service and general-store sites in KFU college buildings, including the site schedule. It is the opportunity-specific booklet, not the separately listed generic “Investor Journey” PDF. The listing calls the PDF the public version; the PDF was available without login or payment. This public access is separate from the SAR 300 participation booklet purchase.

KFU's [publishing and use policy](https://www.kfu.edu.sa/ar/Deans/it/Documents/Publishing_policy.pdf) conditionally allows links to the university portal from sites that do not conflict with its objectives, while protecting portal content and restricting copying, redistribution, public display, and other reuse without prior written approval. It does not clearly grant direct deep-linking or republication rights for this booklet. Therefore the proposed destination below is the official opportunity page, not the PDF. Do not host or redistribute a PDF copy. Confirm that the platform's use qualifies under KFU's conditions before publication.

## Proposed record — not inserted

Disposition: **PENDING_PUBLICATION_APPROVAL**. Values below use the deployed `OpportunityDocument` model. The opportunity is expired; any display would need to make that historical status clear.

```json
{
  "opportunity_id": 224,
  "source_opportunity_id": 2773,
  "source_id": 5,
  "official_provider_document_id": null,
  "title": "كراسة الشروط والمواصفات الخاصة بتأجير مواقع تقديم الخدمات الغذائية والعامة (مطاعم ومتاجر عامة) بمباني كليات الجامعة",
  "document_type": "PDF",
  "document_category": "TERMS_AND_CONDITIONS_BOOKLET",
  "url": "https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/اعلانات-الإدارة.html",
  "source_opportunity_url": "https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/اعلانات-الإدارة.html",
  "official_purchase_url": null,
  "purchase_url_verified": null,
  "access_status": "PUBLIC_SOURCE_PAGE",
  "rights_status": "SOURCE_PAGE_LINK_ONLY",
  "authentication_required": false,
  "payment_required_for_document": false,
  "participation_requirement": "PURCHASE_REQUIRED_FOR_PARTICIPATION",
  "booklet_price_amount": 300.00,
  "currency": "SAR",
  "link_verification_status": "VERIFIED_SOURCE_PAGE",
  "last_verified_at": "2026-11-16T08:58:52Z",
  "first_seen_at": "2026-10-12T07:47:11.552588Z",
  "document_version": 1,
  "deduplication_key": null,
  "publication_status": "DRAFT",
  "publication_decision": "PENDING_PUBLICATION_APPROVAL"
}
```

Evidence provenance for any future draft should include the KFU listing URL, the verified PDF URL as evidence only (not the user destination), the KFU publishing policy URL, the production association IDs, the expired deadline, the purchase terms, and the verification timestamp above.

## Isolated candidate gate and blockers

Using the candidate application code against the disposable restored database, read-only `validate_document_candidate` evaluation of the source-page-only draft was blocked with:

> Opportunity page must match the exact stored SourceOpportunity URL

That validator requires `source_opportunity_url == SourceOpportunity.source_url`. For source row 2773, `source_url` is empty even though the verified official URL is present in `raw_data_json.source_listing_url`. No row was inserted or changed. The actual candidate therefore cannot pass the deployed validation gate until this provenance-field mismatch is resolved under separate authorization.

The direct-PDF permission is also unresolved, and the opportunity is expired. Leave the candidate unpublished. Existing isolated Documents MVP rendering/security tests (including synthetic approved-document fixtures and source-page-only rights gating) passed in the prior accepted release validation; no fixtures were inserted into production and those completed tests were not repeated here.

**PRODUCTION_DATA_MUTATIONS = ZERO**  
**PRODUCTION_DEPLOYMENT = NONE**  
**KFU_PUBLICATION_READINESS = PENDING_PUBLICATION_APPROVAL**

**Next action:** separately authorize a narrow reconciliation of the verified KFU source-page URL into the appropriate SourceOpportunity provenance field, then re-run the candidate validator and obtain any required KFU rights clarification. Keep the document unpublished until both gates and a separate publication approval pass.

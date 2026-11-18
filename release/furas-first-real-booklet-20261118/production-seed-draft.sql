-- PREPARED ONLY. DO NOT RUN without a separately authorized production window.
-- Inserts exactly one DRAFT page-only record after migration 0027 and identity checks.
-- It does not publish the document. Price and currency remain NULL.
BEGIN;

DO $$
DECLARE identity_count integer;
BEGIN
    SELECT count(*) INTO identity_count
    FROM source_opportunities so
    JOIN sources s ON s.id = so.source_id
    JOIN opportunities m ON m.id = so.master_opportunity_id
    WHERE so.id = 3188
      AND s.source_key = 'furas'
      AND so.source_opportunity_id = '01-26-017001-42008'
      AND so.master_opportunity_id = 597
      AND m.merged_into_id IS NULL;
    IF identity_count <> 1 THEN
        RAISE EXCEPTION 'Expected exact active Furas SourceOpportunity 3188 -> Master 597 identity; found %', identity_count;
    END IF;
END $$;

INSERT INTO opportunity_documents (
    opportunity_id, source_id, source_opportunity_id, official_provider_document_id,
    official_purchase_url, purchase_url_verified, title, url, document_type,
    document_category, first_seen_at, source_opportunity_url, access_status,
    rights_status, authentication_required, payment_required_for_document,
    participation_requirement, booklet_price_amount, currency,
    link_verification_status, last_verified_at, source_provenance_json,
    document_version, deduplication_key, publication_status, created_at, updated_at
)
SELECT
    597, s.id, so.id, '270741756',
    NULL, NULL, 'كراسة الشروط والمواصفات',
    'https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-42008?type=Investment',
    'HTML_SOURCE_PAGE', 'TERMS_AND_CONDITIONS_BOOKLET',
    '2026-11-18T07:35:02Z'::timestamptz,
    'https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-42008?type=Investment',
    'PUBLIC_SOURCE_PAGE', 'SOURCE_PAGE_LINK_ONLY', false, NULL,
    'PURCHASE_REQUIRED_FOR_PARTICIPATION', NULL, NULL,
    'VERIFIED_SOURCE_PAGE', '2026-11-18T07:35:02Z'::timestamptz,
    $$
    {
      "evidence_record_type": "FURAS_PAGE_ONLY_BOOKLET",
      "provider_reference": "01-26-017001-42008",
      "official_opportunity_page": "https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-42008?type=Investment",
      "page_http_status": 200,
      "page_observed_at_utc": "2026-11-18T07:35:02Z",
      "page_lifecycle_observation": "The page showed a live remaining-time countdown (39 days, 17 hours) and the label تاريخ فتح المظاريف with 2026-12-28 10:00. The user must confirm lifecycle and date meaning in a normal browser before publication.",
      "direct_download_status": "UNAVAILABLE",
      "direct_download_http_status": 302,
      "direct_attachment_provider_id": "270741756",
      "direct_download_destination": "/list-opportunities",
      "direct_download_content_type": "text/html",
      "direct_download_failure_observed_date": "2026-11-18; exact time not retained",
      "displayed_booklet_amount_raw": "1500",
      "displayed_booklet_amount_label": "سعر الكراسة",
      "currency": null,
      "currency_status": "UNVERIFIED",
      "purchase_requirement_evidence": {
        "individual_page_action": "شراء الكراسة",
        "official_service_url": "https://furas.momah.gov.sa/ar/services/117",
        "ministry_service_url": "https://momah.gov.sa/ar/e-services/almnafsat-alastthmaryt",
        "purchase_url": null,
        "purchase_url_verification": "NOT_VERIFIED"
      },
      "publication_decision": "DRAFT; separate explicit production publication approval required"
    }
    $$::json,
    1,
    '8cc33bf2d6e8825d1d0f7592ce7826ae98de5b6e18bfa0bf795bca9f3e03c42c',
    'DRAFT', now(), now()
FROM sources s
JOIN source_opportunities so ON so.source_id = s.id
JOIN opportunities m ON m.id = so.master_opportunity_id
WHERE s.source_key = 'furas'
  AND so.id = 3188
  AND so.source_opportunity_id = '01-26-017001-42008'
  AND so.master_opportunity_id = 597
  AND m.merged_into_id IS NULL
ON CONFLICT (source_opportunity_id, deduplication_key, document_version)
    WHERE source_opportunity_id IS NOT NULL AND deduplication_key IS NOT NULL
DO NOTHING;

DO $$
DECLARE exact_count integer;
BEGIN
    SELECT count(*) INTO exact_count
    FROM opportunity_documents d
    JOIN sources s ON s.id = d.source_id
    WHERE s.source_key = 'furas'
      AND d.opportunity_id = 597
      AND d.source_opportunity_id = 3188
      AND d.official_provider_document_id = '270741756'
      AND d.document_category = 'TERMS_AND_CONDITIONS_BOOKLET'
      AND d.url = 'https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-42008?type=Investment'
      AND d.source_opportunity_url = d.url
      AND d.access_status = 'PUBLIC_SOURCE_PAGE'
      AND d.rights_status = 'SOURCE_PAGE_LINK_ONLY'
      AND d.link_verification_status = 'VERIFIED_SOURCE_PAGE'
      AND d.booklet_price_amount IS NULL
      AND d.currency IS NULL
      AND d.deduplication_key = '8cc33bf2d6e8825d1d0f7592ce7826ae98de5b6e18bfa0bf795bca9f3e03c42c'
      AND d.document_version = 1
      AND d.publication_status = 'DRAFT';
    IF exact_count <> 1 THEN
        RAISE EXCEPTION 'Expected one exact DRAFT booklet row with NULL amount/currency; found %', exact_count;
    END IF;
END $$;

COMMIT;

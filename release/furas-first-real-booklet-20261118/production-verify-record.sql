-- Read-only verification after the prepared seed transaction.
SELECT d.id, s.source_key, so.id AS source_opportunity_id,
       so.source_opportunity_id AS provider_reference,
       so.master_opportunity_id AS master_opportunity_id,
       d.official_provider_document_id, d.title, d.url, d.access_status,
       d.rights_status, d.link_verification_status, d.participation_requirement,
       d.booklet_price_amount, d.currency, d.publication_status,
       d.deduplication_key, d.document_version
FROM opportunity_documents d
JOIN sources s ON s.id = d.source_id
JOIN source_opportunities so ON so.id = d.source_opportunity_id AND so.source_id = d.source_id
WHERE s.source_key = 'furas'
  AND d.opportunity_id = 597
  AND so.id = 3188
  AND so.source_opportunity_id = '01-26-017001-42008'
  AND d.official_provider_document_id = '270741756'
  AND d.deduplication_key = '8cc33bf2d6e8825d1d0f7592ce7826ae98de5b6e18bfa0bf795bca9f3e03c42c'
  AND d.document_version = 1;

-- Expected exactly one row; booklet_price_amount and currency are NULL;
-- publication_status remains DRAFT until explicit approval is separately authorized.

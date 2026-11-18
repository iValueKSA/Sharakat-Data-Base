-- Prepared, targeted removal for an unpublished DRAFT row only.
-- If the row was ever APPROVED, preserve its evidence and set REVOKED instead of deleting it.
BEGIN;
DO $$
DECLARE removed_count integer;
BEGIN
    DELETE FROM opportunity_documents AS d
    USING sources AS s
    WHERE d.source_id = s.id
      AND s.source_key = 'furas'
      AND d.opportunity_id = 597
      AND d.source_opportunity_id = 3188
      AND d.official_provider_document_id = '270741756'
      AND d.document_category = 'TERMS_AND_CONDITIONS_BOOKLET'
      AND d.url = 'https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-42008?type=Investment'
      AND d.deduplication_key = '8cc33bf2d6e8825d1d0f7592ce7826ae98de5b6e18bfa0bf795bca9f3e03c42c'
      AND d.document_version = 1
      AND d.publication_status = 'DRAFT';
    GET DIAGNOSTICS removed_count = ROW_COUNT;
    IF removed_count <> 1 THEN
        RAISE EXCEPTION 'Expected to remove exactly one unpublished DRAFT booklet row; removed %', removed_count;
    END IF;
END $$;
COMMIT;

SELECT json_build_object(
  'master_id', o.id,
  'canonical_id', o.canonical_id,
  'title', o.title_ar,
  'owner', o.opportunity_owner,
  'owner_evidence_class', CASE WHEN o.id IN (102,228,230) THEN 'OWNER_REVIEW_REQUIRED' WHEN o.opportunity_owner IS NULL OR btrim(o.opportunity_owner)='' THEN 'OWNER_UNSPECIFIED' ELSE 'OWNER_CONFIRMED' END,
  'source_records', COALESCE((
    SELECT json_agg(json_build_object(
      'source_key', s.source_key,
      'platform', s.source_name_ar,
      'source_operator', s.organization_name,
      'source_opportunity_id', so.source_opportunity_id,
      'source_owner_projection', so.source_owner,
      'record_publisher', CASE WHEN s.source_key='furas' THEN so.raw_data_json->'attributes'->>'ENTITIESNAME' ELSE COALESCE(so.raw_data_json->>'publishing_entity',so.raw_data_json->>'publisher') END,
      'raw_entity_fields', json_build_object(
        'AMANA',so.raw_data_json->'attributes'->>'AMANA',
        'ENTITIESNAME',so.raw_data_json->'attributes'->>'ENTITIESNAME',
        'municipality',so.raw_data_json->>'municipality',
        'company_name',so.raw_data_json->>'company_name',
        'company',so.raw_data_json->>'company',
        'portfolio_company',so.raw_data_json->>'portfolio_company',
        'project_owner_candidate',so.raw_data_json->>'project_owner_candidate',
        'publisher',so.raw_data_json->>'publisher'
      )
    ) ORDER BY s.source_key, so.id)
    FROM source_opportunities so JOIN sources s ON s.id=so.source_id
    WHERE so.master_opportunity_id=o.id
  ), '[]'::json)
)::text
FROM opportunities o
WHERE o.merged_into_id IS NULL
ORDER BY o.id;

SELECT json_build_object(
  'source_key', s.source_key,
  'field', 'SourceOpportunity.source_owner',
  'raw_or_adapter_owner_value', so.source_owner,
  'value_state', CASE WHEN so.source_owner IS NULL THEN 'NULL' WHEN btrim(so.source_owner)='' THEN 'EMPTY' ELSE 'VALUE' END,
  'source_record_count', count(*),
  'linked_record_count', count(*) FILTER (WHERE so.master_opportunity_id IS NOT NULL),
  'linked_non_merged_master_count', count(DISTINCT so.master_opportunity_id) FILTER (WHERE o.merged_into_id IS NULL),
  'canonical_current_owner_values', COALESCE(json_agg(DISTINCT o.opportunity_owner) FILTER (WHERE o.id IS NOT NULL), '[]'::json),
  'note', CASE WHEN s.source_key IN ('ahda','alahsa-opportunities','invest-saudi','ncp','mwan') THEN 'Adapter-derived value audited; current raw payload preserved; corrected rules no longer use portal/publisher/context as an owner.' ELSE 'Source-specific owner projection; inspect raw fields before treating as canonical.' END
)::text
FROM source_opportunities so
JOIN sources s ON s.id=so.source_id
LEFT JOIN opportunities o ON o.id=so.master_opportunity_id
GROUP BY s.source_key,so.source_owner
ORDER BY s.source_key,so.source_owner NULLS FIRST;

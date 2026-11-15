SELECT jsonb_build_object(
 'captured_at_utc', clock_timestamp(),
 'master_total', (SELECT count(*) FROM opportunities),
 'non_merged_masters', (SELECT count(*) FROM opportunities WHERE merged_into_id IS NULL),
 'merged_masters', (SELECT count(*) FROM opportunities WHERE merged_into_id IS NOT NULL),
 'alahsa_nonmerged', (SELECT count(*) FROM opportunities o JOIN geographic_reference_units g ON g.id=o.geography_reference_unit_id WHERE o.merged_into_id IS NULL AND g.external_id='501'),
 'scope_distribution_nonmerged', (SELECT jsonb_object_agg(scope,count) FROM (SELECT coalesce(geographic_scope,'NULL') scope,count(*) FROM opportunities WHERE merged_into_id IS NULL GROUP BY geographic_scope) s),
 'source_opportunities', (SELECT count(*) FROM source_opportunities),
 'source_observations', (SELECT count(*) FROM source_observations),
 'held_master_64', (SELECT jsonb_build_object('scope',geographic_scope,'canonical_id',canonical_id,'merged_into_id',merged_into_id) FROM opportunities WHERE id=64),
 'furas_active_aliases', (SELECT count(*) FROM source_identity_aliases WHERE status='ACTIVE'),
 'alias_audit_rows', (SELECT count(*) FROM source_identity_alias_audits)
)::text;

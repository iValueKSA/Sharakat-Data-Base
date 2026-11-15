SELECT jsonb_build_object(
 'captured_at_utc',clock_timestamp(),
 'governorate_external_id','501',
 'region_external_id','5',
 'record_count',(SELECT count(*) FROM opportunities o JOIN geographic_reference_units g ON g.id=o.geography_reference_unit_id WHERE o.merged_into_id IS NULL AND g.external_id='501'),
 'rows',(SELECT jsonb_agg(jsonb_build_object('record',to_jsonb(o),'governorate_external_id',g.external_id,'region_external_id',pg.external_id) ORDER BY o.id) FROM opportunities o JOIN geographic_reference_units g ON g.id=o.geography_reference_unit_id LEFT JOIN geographic_reference_units pg ON pg.id=g.parent_id WHERE o.merged_into_id IS NULL AND g.external_id='501')
)::text;

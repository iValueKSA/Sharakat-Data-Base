WITH vals AS (
 SELECT s.source_key,'attributes.AMANA' AS field,so.raw_data_json->'attributes'->>'AMANA' AS value,so.master_opportunity_id
 FROM source_opportunities so JOIN sources s ON s.id=so.source_id WHERE s.source_key='furas'
 UNION ALL
 SELECT s.source_key,'attributes.ENTITIESNAME',so.raw_data_json->'attributes'->>'ENTITIESNAME',so.master_opportunity_id
 FROM source_opportunities so JOIN sources s ON s.id=so.source_id WHERE s.source_key='furas'
)
SELECT json_build_object('source_key',source_key,'field',field,'raw_value',value,'state',CASE WHEN value IS NULL THEN 'NULL' WHEN btrim(value)='' THEN 'EMPTY' ELSE 'VALUE' END,'records',count(*),'linked_records',count(*) FILTER(WHERE master_opportunity_id IS NOT NULL))::text
FROM vals GROUP BY source_key,field,value ORDER BY field,value NULLS FIRST;

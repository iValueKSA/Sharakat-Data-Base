SELECT json_build_object('master_id',o.id,'title',o.title_ar,'old_master_owner',o.opportunity_owner,'source_record_id',so.id,'source_key',s.source_key,'external_id',so.source_opportunity_id,'old_source_owner_projection',so.source_owner,'raw_owner_AMANA',so.raw_data_json->'attributes'->>'AMANA','raw_publisher_ENTITIESNAME',so.raw_data_json->'attributes'->>'ENTITIESNAME','raw_payload_preserved',true)::text
FROM opportunities o JOIN source_opportunities so ON so.master_opportunity_id=o.id JOIN sources s ON s.id=so.source_id
WHERE s.source_key='furas' AND NULLIF(btrim(so.raw_data_json->'attributes'->>'AMANA'),'') IS NOT NULL
AND so.source_owner IS DISTINCT FROM so.raw_data_json->'attributes'->>'AMANA'
ORDER BY o.id;

BEGIN;
CREATE TEMP TABLE furas_owner_fix ON COMMIT DROP AS
SELECT o.id AS master_id,o.opportunity_owner AS old_master_owner,so.id AS source_record_id,so.source_id,so.raw_data_json->'attributes'->>'AMANA' AS amana_owner
FROM opportunities o JOIN source_opportunities so ON so.master_opportunity_id=o.id JOIN sources s ON s.id=so.source_id
WHERE s.source_key='furas' AND NULLIF(btrim(so.raw_data_json->'attributes'->>'AMANA'),'') IS NOT NULL
AND so.source_owner IS DISTINCT FROM so.raw_data_json->'attributes'->>'AMANA';
UPDATE source_opportunities so
SET source_owner=f.amana_owner,
    standardization_version='17',
    standardized_data_json=jsonb_set(
      jsonb_set(COALESCE(so.standardized_data_json::jsonb,'{}'::jsonb),'{fields,opportunity_owner}',
        jsonb_build_object('raw',f.amana_owner,'canonical_id','al_ahsa_municipality','canonical_label','أمانة الأحساء','mapping_status','MAPPED','rule','furas_explicit_amana_owner_v1'),true),
      '{version}','"17"'::jsonb,true
    )::json
FROM furas_owner_fix f WHERE so.id=f.source_record_id;
UPDATE opportunities o
SET opportunity_owner='أمانة الأحساء',last_updated_at=now(),updated_at=now()
FROM furas_owner_fix f WHERE o.id=f.master_id;
INSERT INTO opportunity_field_provenance(opportunity_id,field_name,selected_value,source_id,source_record_id,captured_at,confidence)
SELECT master_id,'opportunity_owner','أمانة الأحساء',source_id,source_record_id,now(),1.0 FROM furas_owner_fix;
INSERT INTO opportunity_change_history(opportunity_id,changed_field,previous_value,new_value,source_id,detected_at)
SELECT master_id,'opportunity_owner',old_master_owner,'أمانة الأحساء',source_id,now() FROM furas_owner_fix;
SELECT 'corrected_furas_records',count(*) FROM furas_owner_fix;
COMMIT;

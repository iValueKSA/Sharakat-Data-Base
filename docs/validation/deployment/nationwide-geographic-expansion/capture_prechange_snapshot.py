from __future__ import annotations
import hashlib, json, os
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import create_engine, inspect, text

URL=os.environ['DATABASE_URL']
engine=create_engine(URL, pool_pre_ping=True, connect_args={'connect_timeout': 10})
def clean(value):
    if isinstance(value, (datetime,date)): return value.isoformat()
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, (bytes,bytearray)): return {'sha256':hashlib.sha256(value).hexdigest(),'bytes':len(value)}
    return value
def normalized(row): return {k:clean(v) for k,v in dict(row).items()}
def sha(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()
def fetch(conn, table, columns=None):
    if columns is None: columns=[c['name'] for c in inspector.get_columns(table)]
    if not columns: return []
    order=','.join('"'+c.replace('"','""')+'"' for c in (['id'] if 'id' in columns else columns[:1]))
    return [normalized(r) for r in conn.execute(text('SELECT '+','.join('"'+c.replace('"','""')+'"' for c in columns)+' FROM "'+table+'" ORDER BY '+order)).mappings().all()]

def keyed_rows(rows, keys, hash_fields=None):
    out=[]
    for r in rows:
        item={k:r[k] for k in keys if k in r}
        if hash_fields is None: item['row_sha256']=sha(r)
        else: item['payload_sha256']=sha({k:r.get(k) for k in hash_fields})
        out.append(item)
    return out

with engine.connect() as conn:
    conn.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    inspector=inspect(conn)
    tables=sorted(inspector.get_table_names())
    counts={t:int(conn.scalar(text('SELECT count(*) FROM "'+t+'"')) or 0) for t in tables if t!='alembic_version'}
    schema={t:[{'name':c['name'],'type':str(c['type']),'nullable':c['nullable'],'primary_key':c.get('primary_key',False)} for c in inspector.get_columns(t)] for t in tables}
    source_cols=['id','source_key','source_name_ar','organization_name','base_url','opportunities_url','source_type','priority','polling_frequency_minutes','enabled','extraction_method','technical_health','coverage_status','coverage_notes','sync_status','last_attempted_sync','last_successful_sync','last_record_count','last_source_total_reported','last_collection_completeness_percent','last_pagination_complete','missing_confirmation_threshold']
    sources=fetch(conn,'sources',source_cols)
    master_cols=['id','merged_into_id','canonical_id','title_ar','title_en','normalized_title','reference_number','reference_number_normalized','opportunity_owner','primary_publication_platform','sector','activity','sub_activity','subsector','opportunity_type','investment_model','city','district','location_description','latitude','longitude','land_area_sqm','plot_number','investment_value','currency','contract_duration_years','publication_date','submission_deadline','status','location_confidence_score','location_detection_method','location_evidence','manual_review_required','first_seen_at','last_seen_at','last_updated_at','created_at','updated_at']
    masters=fetch(conn,'opportunities',master_cols)
    source_cols2=['id','source_id','master_opportunity_id','source_opportunity_id','official_source_id_original','official_source_id_normalized','source_reference_number','source_title','source_url','source_owner','source_sector','source_activity','source_sub_activity','raw_location','raw_status','canonical_status','content_hash','parser_version','missing_successful_checks','last_missing_at','raw_data_json','standardized_data_json']
    source_rows=fetch(conn,'source_opportunities',source_cols2)
    relationships=[{'source_opportunity_id':r['id'],'source_id':r['source_id'],'master_opportunity_id':r['master_opportunity_id']} for r in source_rows]
    observations=fetch(conn,'source_observations',['id','source_opportunity_id','dataset_name','endpoint','official_source_id_normalized','content_hash','raw_data_json'])
    observation_index=keyed_rows(observations,['id','source_opportunity_id','dataset_name','endpoint','official_source_id_normalized','content_hash'],['raw_data_json'])
    membership_tables=['source_opportunity_dataset_memberships','opportunity_locations','opportunity_asset_facility_types','opportunity_merge_audit','opportunity_field_provenance']
    memberships={t:keyed_rows(fetch(conn,t),['id','source_opportunity_id','dataset_name','master_opportunity_id','opportunity_id','canonical_id','location_name','location_scope','is_current','event_type','field_name']) for t in membership_tables if t in tables}
    review_tables=['qualification_reviews','location_reviews','duplicate_candidates','opportunity_data_conflicts']
    reviews={t:keyed_rows(fetch(conn,t),['id','source_id','source_record_id','external_id','opportunity_id','left_opportunity_id','right_opportunity_id','status','reason','created_at','resolved_at','resolution']) for t in review_tables if t in tables}
    change_rows=fetch(conn,'opportunity_change_history')
    changes=keyed_rows(change_rows,['id','opportunity_id','changed_field','source_id','detected_at','previous_value','new_value'])
    audit_rows=fetch(conn,'audit_events')
    audit=keyed_rows(audit_rows,['id','event_type','action','actor_type','actor_id','object_type','object_id','created_at','event_key'])
    sys_rows=fetch(conn,'system_events')
    system_events=keyed_rows(sys_rows,['id','event_type','event_key','actor_type','created_at'])
    job_rows=fetch(conn,'source_sync_jobs',['id','source_id','started_at','finished_at','status','job_state','trigger_type','pages_scanned','pages_requested','pages_successful','source_total_reported','raw_count','unique_records','new_count','update_count','removed_records_count','pagination_complete','collection_completeness_percent','error_message'])
    jobs=[{k:clean(v) for k,v in r.items() if k!='error_message'}|{'error_sha256':sha(r.get('error_message')) if r.get('error_message') else None} for r in job_rows]
    current=[r for r in masters if r.get('merged_into_id') is None]
    canonical={}
    for field in ['sector','activity','sub_activity','subsector','opportunity_type','investment_model','status','city','district']:
        counter={}
        for r in current:
            value=r.get(field) or None
            key='(null)' if value is None else str(value)
            counter[key]=counter.get(key,0)+1
        canonical[field]=dict(sorted(counter.items(),key=lambda x:x[0]))
    role_rows=conn.execute(text('SELECT lower(role) AS role,count(*) AS n FROM users GROUP BY lower(role) ORDER BY lower(role)')).mappings().all() if 'users' in tables else []
    role_counts={r['role']:int(r['n']) for r in role_rows}
    versions=[r[0] for r in conn.execute(text('SELECT version_num FROM alembic_version ORDER BY version_num')).all()] if 'alembic_version' in tables else []
    result={
      'captured_at_utc':datetime.now(timezone.utc).isoformat(),
      'database_identity':'sharakat_local PostgreSQL; credentials excluded',
      'alembic_versions':versions,'table_counts':counts,'schema':schema,
      'master_ids':[r['id'] for r in masters],'current_master_ids':[r['id'] for r in current],
      'merged_master_links':[{'id':r['id'],'merged_into_id':r['merged_into_id']} for r in masters if r.get('merged_into_id') is not None],
      'master_canonical_values':masters,'canonical_value_counts':canonical,
      'source_inventory':sources,'source_opportunity_ids':[r['id'] for r in source_rows],
      'source_opportunities':keyed_rows(source_rows,['id','source_id','master_opportunity_id','source_opportunity_id','official_source_id_original','official_source_id_normalized','source_reference_number','source_url','raw_location','raw_status','canonical_status','content_hash','missing_successful_checks'],['raw_data_json','standardized_data_json']),
      'source_to_master_relationships':relationships,
      'observation_records':observation_index,
      'review_states':reviews,
      'change_history_records':changes,'audit_event_records':audit,'system_event_records':system_events,
      'source_sync_jobs':jobs,
      'rbac_role_counts':role_counts,
      'data_id_sha256':{
        'master_ids':sha([r['id'] for r in masters]),
        'current_master_ids':sha([r['id'] for r in current]),
        'source_opportunity_ids':sha([r['id'] for r in source_rows]),
        'source_to_master_relationships':sha(relationships),
        'source_inventory':sha(sources),
        'raw_source_payload_hashes':sha([{'id':r['id'],'h':sha(r.get('raw_data_json'))} for r in source_rows]),
        'observation_payload_hashes':sha([{'id':r['id'],'h':sha(r.get('raw_data_json'))} for r in observations]),
        'review_states':sha(reviews),'change_history':sha(changes),'audit_events':sha(audit),
        'canonical_values':sha(masters),'schema':sha(schema)
      }
    }
    print(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str))
engine.dispose()

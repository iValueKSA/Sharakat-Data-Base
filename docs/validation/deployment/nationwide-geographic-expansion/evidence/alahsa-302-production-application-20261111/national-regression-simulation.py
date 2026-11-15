import csv,json,sys,hashlib
from pathlib import Path
from datetime import datetime,timezone
from sqlalchemy import text,bindparam
from app.database import engine
import app.main as main
from fastapi.testclient import TestClient
reg_path,cov_path,out_path=map(Path,sys.argv[1:4])
with reg_path.open(encoding='utf-8-sig',newline='') as f: reg=list(csv.DictReader(f))
with cov_path.open(encoding='utf-8-sig',newline='') as f: cov=list(csv.DictReader(f))
targets={int(r['master_id']) for r in reg if r['adjudication_decision']=='APPROVED_FOR_GEOGRAPHIC_CORRECTION' and r['simulated_map_eligibility']=='PASS'}
held={int(r['MasterId']) for r in cov if r['PrimaryClass'] in {'REGION_GOVERNORATE_BOUNDARY_CONFLICT','OUTSIDE_SAVED_REGION_BOUNDARY'}}|{64}
checks={'register_exact_302_unique':len(reg)==302 and len(targets)==302,
        'snapshot_version_is_post_0026':True}
def api_payload():
    response=TestClient(main.app,raise_server_exceptions=True).get('/api/data-dashboard/geography')
    if response.status_code!=200: raise RuntimeError(f'national API HTTP {response.status_code}: {response.text[:300]}')
    value=response.json()
    if value.get('map_scope')!='NATIONAL': raise RuntimeError(f'expected NATIONAL scope, got {value.get("map_scope")}')
    return value,response.status_code

def flat_ids(p): return [int(i) for point in p.get('points',[]) for i in point.get('ids',[])]
def counts(c):
    with engine.connect() as conn:
        return {'master_total':conn.scalar(text('select count(*) from opportunities')),
          'non_merged':conn.scalar(text('select count(*) from opportunities where merged_into_id is null')),
          'source_opportunities':conn.scalar(text('select count(*) from source_opportunities')),
          'source_observations':conn.scalar(text('select count(*) from source_observations')),
          'migration_versions':list(conn.execute(text('select version_num from alembic_version order by version_num')).scalars())}
def all_rows():
    with engine.connect() as conn:
        return {int(r['row']['id']):r['row'] for r in conn.execute(text('select to_jsonb(o) as row from opportunities o order by o.id')).mappings().all()}
def admin_map():
    with engine.connect() as conn:
        return {int(r['id']):(r['gov'],r['region']) for r in conn.execute(text("select o.id,g.external_id gov,pg.external_id region from opportunities o left join geographic_reference_units g on g.id=o.geography_reference_unit_id left join geographic_reference_units pg on pg.id=g.parent_id")).mappings().all()}
def source_snapshot():
    with engine.connect() as conn:
        return {int(r['id']):r['row'] for r in conn.execute(text("select so.id,to_jsonb(so)||jsonb_build_object('source_key',s.source_key,'observations',(select count(*) from source_observations ob where ob.source_opportunity_id=so.id)) as row from source_opportunities so join sources s on s.id=so.source_id where so.master_opportunity_id=any(:ids) order by so.id"),{'ids':sorted(targets)}).mappings().all()}
def unit_fingerprint():
    with engine.connect() as conn:
        raw=conn.execute(text('select to_jsonb(x) as row from (select * from geographic_reference_datasets order by id) x')).scalars().all()
        units=conn.execute(text('select to_jsonb(x) as row from (select * from geographic_reference_units order by id) x')).scalars().all()
    data=json.dumps([raw,units],sort_keys=True,ensure_ascii=False,default=str).encode()
    return hashlib.sha256(data).hexdigest()
def grouped(ids,units):
    d={}
    for i in ids:
        gov,region=units.get(i,(None,None)); d.setdefault((str(region),str(gov)),set()).add(i)
    return d

before_counts=counts(None); before_rows=all_rows(); before_sources=source_snapshot(); before_admin=admin_map(); units_hash_before=unit_fingerprint()
before_api,before_http=api_payload(); before_list=flat_ids(before_api); before_ids=set(before_list)
checks['backup_restored_master_counts_match_known_snapshot']=before_counts['master_total']==6680 and before_counts['non_merged']==6659
checks['backup_restored_source_counts_match_current_prewrite']=before_counts['source_opportunities']==9470 and before_counts['source_observations']==57661
checks['migration_0026']=before_counts['migration_versions']==['0026_source_identity_aliases']
checks['national_map_api_baseline_http_200']=before_http==200
checks['national_map_api_baseline_scope']=before_api.get('map_scope')=='NATIONAL'
checks['national_map_baseline_unique_ids']=len(before_list)==len(before_ids)
pre_rows={i:before_rows.get(i) for i in targets}
checks['all_302_live_in_snapshot']=all(v is not None for v in pre_rows.values())
checks['all_302_are_unmerged_unspecified']=all(r and r.get('merged_into_id') is None and r.get('geographic_scope')=='UNSPECIFIED' for r in pre_rows.values())
checks['all_302_governorate_501_region_5']=all(before_admin.get(i)==('501','5') for i in targets)
checks['held_records_present_in_snapshot']=held <= set(before_rows)
checks['no_302_already_mapped']=not bool(targets & before_ids)
# Apply only to disposable restored snapshot.
stmt=text("update opportunities set geographic_scope='SPECIFIC_LOCATION' where id in :ids and geographic_scope='UNSPECIFIED' returning id").bindparams(bindparam('ids',expanding=True))
with engine.begin() as conn:
    conn.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
    changed={int(x) for x in conn.execute(stmt,{'ids':sorted(targets)}).scalars().all()}
checks['simulation_updated_exactly_302']=changed==targets
sim_api,sim_http=api_payload(); sim_list=flat_ids(sim_api); sim_ids=set(sim_list)
after_counts=counts(None); after_rows=all_rows(); after_sources=source_snapshot(); after_admin=admin_map(); units_hash_after=unit_fingerprint()
checks['national_map_api_after_http_200']=sim_http==200
checks['national_map_api_after_scope']=sim_api.get('map_scope')=='NATIONAL'
checks['all_preexisting_ids_preserved']=before_ids<=sim_ids
checks['only_approved_ids_added']=sim_ids-before_ids==targets
checks['all_302_in_national_api']=targets<=sim_ids
checks['no_duplicate_ids_before_or_after']=len(before_list)==len(before_ids) and len(sim_list)==len(sim_ids)
checks['held_records_unchanged']=all(before_rows[i]==after_rows[i] for i in held)
checks['no_unrelated_master_promoted']=sim_ids-before_ids==targets
checks['all_302_only_in_al_ahsa']=all(after_admin.get(i)==('501','5') for i in targets)
checks['other_governorate_eligible_sets_unchanged']=all(grouped(before_ids,before_admin).get(k,set())==grouped(sim_ids,after_admin).get(k,set()) for k in set(grouped(before_ids,before_admin))|set(grouped(sim_ids,after_admin)) if k!=('5','501'))
checks['all_master_fields_except_target_scope_unchanged']=all((before_rows[i] if i not in targets else {k:v for k,v in before_rows[i].items() if k!='geographic_scope'})==(after_rows[i] if i not in targets else {k:v for k,v in after_rows[i].items() if k!='geographic_scope'}) for i in before_rows)
checks['target_scope_only']=all(before_rows[i]['geographic_scope']=='UNSPECIFIED' and after_rows[i]['geographic_scope']=='SPECIFIC_LOCATION' for i in targets)
checks['source_opportunities_and_observation_counts_unchanged']=before_sources==after_sources
checks['geography_reference_datasets_unchanged']=units_hash_before==units_hash_after
checks['record_counts_unchanged_except_scope']=before_counts==after_counts
checks['held_master_64_unchanged']=before_rows[64]==after_rows[64]
result={'captured_at_utc':datetime.now(timezone.utc).isoformat(),'mode':'NATIONAL_API_SERIALIZABLE_SIMULATION_ON_RESTORED_PRODUCTION_SNAPSHOT','network':'Docker internal network; no internet, host port publishing, or production database connectivity','snapshot_database':engine.url.database,'api_image':'sha256:1536c3e3229684fd2feee62aa3bf896c2b3d35d1bf585522abed3d7d6d62a59a','migration':'0026_source_identity_aliases','approved_ids':sorted(targets),'approved_count':len(targets),'held_ids':sorted(held),'counts_before':before_counts,'counts_after':after_counts,'baseline_api':{'http_status':before_http,'map_scope':before_api.get('map_scope'),'counts':before_api.get('counts'),'unique_ids':sorted(before_ids),'unique_point_count':len(before_api.get('points',[]))},'simulated_api':{'http_status':sim_http,'map_scope':sim_api.get('map_scope'),'counts':sim_api.get('counts'),'unique_ids':sorted(sim_ids),'added_ids':sorted(sim_ids-before_ids),'unique_point_count':len(sim_api.get('points',[]))},'other_governorate_eligible_counts_before':{f'{k[0]}:{k[1]}':len(v) for k,v in grouped(before_ids,before_admin).items() if k!=('5','501')},'other_governorate_eligible_counts_after':{f'{k[0]}:{k[1]}':len(v) for k,v in grouped(sim_ids,after_admin).items() if k!=('5','501')},'geography_reference_sha256_before':units_hash_before,'geography_reference_sha256_after':units_hash_after,'checks':checks,'passed':all(checks.values()),'production_database_writes':0,'production_service_restarts':0}
out_path.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({'passed':result['passed'],'checks':checks,'baseline_counts':before_api.get('counts'),'simulated_counts':sim_api.get('counts'),'baseline_ids':len(before_ids),'simulated_ids':len(sim_ids),'added_ids':len(sim_ids-before_ids),'other_gov_before':result['other_governorate_eligible_counts_before'],'other_gov_after':result['other_governorate_eligible_counts_after']},ensure_ascii=False,indent=2))
sys.exit(0 if result['passed'] else 2)
import json,sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
D=json.loads(Path('docs/validation/data/master-identity-duplicate-matching/snapshot-final-targeted-eligibility.json').read_text(encoding='utf-8'))
for id in [228,229]:
 m=next(x for x in D['masters'] if x['id']==id);print('MASTER',id,json.dumps({k:m.get(k) for k in ['id','merged_into_id','title_ar','title_en','reference_number','city','status','full_description']},ensure_ascii=False)[:1500])
for rid in [2781,2810]:
 r=next(x for x in D['source_opportunities'] if x['id']==rid);raw=r.get('raw_data_json') or {};print('SOURCE',rid,json.dumps({k:r.get(k) for k in ['id','source_id','master_opportunity_id','source_opportunity_id','source_reference_number','source_title','source_url','raw_location','canonical_status']},ensure_ascii=False)); print('RAW',json.dumps({k:raw.get(k) for k in ['title','description','location','city','region','location_confidence_score','location_detection_method','location_evidence','qualified_location','source_record_family','source_api','source_observations','link','source_url','project_status','contract_duration'] if k in raw},ensure_ascii=False)[:5000])

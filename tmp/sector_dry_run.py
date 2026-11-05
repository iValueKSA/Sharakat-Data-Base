import json, time, random
from collections import Counter
from app.sector_classification import classify_governed, evidence_fingerprint, ENGINE_VERSION
from app.standardization import canonical_id
p='docs/validation/data/complete-sector-classification/sector-classification-before.json'
d=json.load(open(p,encoding='utf-8')); rows=d['unspecified_records']; t0=time.perf_counter(); out=[]
for r in rows:
    a=classify_governed(r); b=classify_governed(r)
    if a!=b: raise RuntimeError(f'non-deterministic {r["id"]}')
    out.append({'master_id':r['id'],'canonical_id':r['canonical_id'],'reference':r.get('reference_number'),'title':r['title_ar'],'sources':[{'source_key':s.get('source_key'),'source_record_id':s.get('source_record_id'),'source_opportunity_id':s.get('source_opportunity_id')} for s in r.get('sources',[])],
      'available_evidence':{'activity':r.get('activity'),'sub_activity':r.get('sub_activity'),'subsector':r.get('subsector'),'opportunity_type':r.get('opportunity_type'),'investment_model':r.get('investment_model'),'asset_facility_type':r.get('asset_facility_type'),'short_description':r.get('short_description'),'full_description':r.get('full_description'),'sources':[{'source_key':s.get('source_key'),'source_sector':s.get('source_sector'),'source_activity':s.get('source_activity'),'source_sub_activity':s.get('source_sub_activity'),'raw_data_json':s.get('raw_data_json'),'observations':s.get('observations')} for s in r.get('sources',[])]},
      'proposed_sector':a['sector'],'sector_id':a['sector_id'],'confidence':a.get('confidence_label') or a.get('classification'),'classification_method':a.get('method'),'top_score':a.get('top_score'),'second_sector':a.get('second_sector_id'),'second_score':a.get('second_score'),'margin':a.get('confidence_margin'),'reason':a.get('reason'),'rule_key':a.get('rule_key'),'rule_keys':a.get('rule_keys'),'supporting_evidence':a.get('positive_evidence'),'evidence_fingerprint':evidence_fingerprint(r,a),'classification_result':a})
sec=Counter(x['sector_id'] for x in out); conf=Counter(x['confidence'] for x in out); methods=Counter(x['classification_method'] for x in out)
for x in out:
    if x['proposed_sector'] is None: raise RuntimeError('unclassified '+str(x['master_id']))
    if x['classification_method']=='FORCED_BEST_FIT' and not x['supporting_evidence']: raise RuntimeError('forced no evidence '+str(x['master_id']))
    if x['sector_id']=='sector:other' and not any(e.get('sector_id')=='sector:other' and e.get('weight',0)>0 for e in x['supporting_evidence']): raise RuntimeError('Other fallback '+str(x['master_id']))
secs=time.perf_counter()-t0
result={'engine_version':ENGINE_VERSION,'snapshot_at':d['snapshot_at'],'input_master_count':len(rows),'dry_run_unclassified':0,'projected_unspecified_after':d['unspecified']-len(out),'distribution_after':dict(sec),'confidence_counts':dict(conf),'method_counts':dict(methods),'runtime_seconds':round(secs,3),'avg_ms_per_master':round(secs*1000/max(1,len(rows)),3),'deterministic_same_input':True,'other_missing_fallback':0,'dry_run_records':out}
json.dump(result,open('docs/validation/data/complete-sector-classification/sector-classification-dry-run.json','w',encoding='utf-8'),ensure_ascii=False,indent=2,default=str)
print(json.dumps({k:v for k,v in result.items() if k!='dry_run_records'},ensure_ascii=False,indent=2))
print('LOW SAMPLE')
for x in out[:12]: print(x['master_id'],x['proposed_sector'],x['rule_key'],x['top_score'],x['second_sector'],x['second_score'],x['title'][:120])

import json,collections
from app.sector_inference_relaxed import classify_relaxed
from app.sector_inference_phase2 import classify_phase2
p='/tmp/current-sector-snapshot.json'
d=json.load(open(p,encoding='utf-8'))
rows=d['unspecified_records']
counts=collections.Counter(); result_rows=[]; field_counts=collections.Counter(); vals=collections.defaultdict(collections.Counter)
for r in rows:
    res=classify_relaxed(r)
    counts[res.get('classification')]+=1
    for f in ('activity','sub_activity','subsector','opportunity_type','investment_model','short_description','full_description','location_description'):
        if r.get(f): field_counts[f]+=1; vals[f][str(r[f])]+=1
    for s in r.get('sources',[]):
        for f in ('source_sector','source_activity','source_sub_activity','source_subsector','source_owner','raw_location'):
            if s.get(f): field_counts['source.'+f]+=1; vals['source.'+f][str(s[f])]+=1
    result_rows.append({'id':r['id'],'title':r['title_ar'],'decision':res.get('classification'),'sector':res.get('sector'),'confidence':res.get('confidence'),'rule_key':res.get('rule_key'),'positive_evidence':res.get('positive_evidence',[]),'negative_evidence':res.get('negative_evidence',[]),'top_sector_id':res.get('top_sector_id'),'top_score':res.get('top_score'),'second_sector_id':res.get('second_sector_id'),'second_score':res.get('second_score'),'sources':r.get('sources',[])})
print('EXISTING_CLASSIFIER',json.dumps(counts,ensure_ascii=False))
print('FIELD_COUNTS',json.dumps(field_counts,ensure_ascii=False))
for f in sorted(vals): print('VALUES',f,json.dumps(vals[f].most_common(30),ensure_ascii=False))
with open('/tmp/sector-existing-decisions.json','w',encoding='utf-8') as f:json.dump(result_rows,f,ensure_ascii=False,indent=2,default=str)

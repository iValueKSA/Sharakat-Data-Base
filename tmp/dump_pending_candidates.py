import json,re
from pathlib import Path
b=json.loads(Path('/tmp/master_identity_snapshot_start.json').read_text(encoding='utf8'))
masters={x['id']:x for x in b['masters']};sources={x['id']:x for x in b['sources']};records={}
for r in b['source_opportunities']:
 if r.get('master_opportunity_id') is not None:records.setdefault(r['master_opportunity_id'],[]).append(r)
for dc in b['duplicate_candidates']:
 if dc['status']!='PENDING':continue
 a=masters[dc['left_opportunity_id']];bb=masters[dc['right_opportunity_id']]
 def srcs(mid): return ' + '.join(f"{sources[r['source_id']]['source_key']}:{r['source_opportunity_id']}" for r in records.get(mid,[]))
 def parts(m):
  t=m['title_ar'];plots=re.findall(r'(?:القطع|القطعة|قطعة|للقطع|للقطعة)\s*(?:رقم)?\s*([^\n،]+?)(?=\s+(?:لنشاط|بالمخطط|في نشاط|بمدينة)|$)',t)
  return t[:130],plots[:1]
 print(json.dumps({'candidate_id':dc['id'],'a':dc['left_opportunity_id'],'b':dc['right_opportunity_id'],'score':dc['confidence_score'],'title_a':parts(a)[0],'title_b':parts(bb)[0],'sources_a':srcs(a['id']),'sources_b':srcs(bb['id']),'plots_a':parts(a)[1],'plots_b':parts(bb)[1],'feature':dc.get('explanation_json',{}).get('features'),'positive':dc.get('explanation_json',{}).get('positive_evidence'),'contradictions':dc.get('explanation_json',{}).get('contradicting_evidence')},ensure_ascii=False))


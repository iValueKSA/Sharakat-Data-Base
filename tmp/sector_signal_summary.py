import json,collections,re
D=json.load(open('/tmp/current-sector-snapshot.json',encoding='utf-8')); rows=D['unspecified_records']
for field in ('opportunity_type','activity','sub_activity','subsector'):
 c=collections.Counter(r.get(field) or '(null)' for r in rows); print(field, json.dumps(c,ensure_ascii=False))
rawacts=collections.Counter(); locs=collections.Counter(); tit=collections.Counter()
for r in rows:
 for s in r['sources']:
  raw=s.get('raw_data_json') or {}; a=raw.get('attributes') or {}
  rawacts[str(a.get('ACTIVITYTYPE') or '(null)')]+=1
  locs[str(a.get('LOCATIONTYPE') or '(null)')]+=1
  t=(r.get('title_ar') or '').replace('تاجير مؤقت لموقع','').replace('تأجير مؤقت لموقع','')
  t=re.sub(r'رقم\s*\d+','رقم #',t); t=re.sub(r'\b\d+\b','#',t)
  # retain important right-most purpose clause, normalize whitespace
  tit[t[:160]]+=1
print('raw_ACTIVITYTYPE',json.dumps(rawacts.most_common(60),ensure_ascii=False))
print('raw_LOCATIONTYPE',json.dumps(locs.most_common(40),ensure_ascii=False))
print('title_patterns',json.dumps(tit.most_common(80),ensure_ascii=False))

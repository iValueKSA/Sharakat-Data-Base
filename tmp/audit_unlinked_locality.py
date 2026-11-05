import json,re
from collections import Counter,defaultdict
p='docs/validation/data/master-identity-duplicate-matching/snapshot-pre-correction-live.json'
d=json.load(open(p,encoding='utf-8')); src={x['id']:x['source_key'] for x in d['sources']}
rows=[r for r in d['source_opportunities'] if r.get('master_opportunity_id') is None]
pat=re.compile(r'al[\s-]?ahsa|الأحساء|الاحساء|الهفوف|المبرز|hofuf|mubarraz|al[- ]ahsa|jawatha|جواثا|العيون',re.I)
by=defaultdict(list); strict=Counter(); loc=Counter()
for r in rows:
 sk=src[r['source_id']]; by[sk].append(r)
 raw=r.get('raw_data_json') or {}; text=' '.join(str(x or '') for x in [r.get('raw_location'),r.get('source_title'),r.get('source_url'),raw.get('city'),raw.get('location'),raw.get('location_name'),raw.get('cityName'),json.dumps(raw.get('details') or {},ensure_ascii=False)])
 if pat.search(text):
  strict[sk]+=1
  if len(loc[sk])<8: loc[sk]+=1; print(json.dumps({'source':sk,'record':r['id'],'external_id':r['source_opportunity_id'],'location':r.get('raw_location'),'title':r.get('source_title'),'url':r.get('source_url'),'payload_loc':{k:raw.get(k) for k in ('city','location','location_name','cityName') if raw.get(k)}},ensure_ascii=False))
print('UNLINKED_TOTAL',len(rows)); print('UNLINKED_BY_SOURCE',{k:len(v) for k,v in by.items()}); print('EXPLICIT_LOCALITY_KEYWORD_HITS',dict(strict))

import json
from pathlib import Path
p=Path('docs/validation/data/master-identity-duplicate-matching/snapshot-final-targeted-eligibility.json')
d=json.loads(p.read_text(encoding='utf-8'))
s={x['id']:x['source_key'] for x in d['sources']}
ids={283,466,601,671,1038,1166,1167,2358,2359,2360,2361,2362}
for r in d['source_opportunities']:
 if r['id'] not in ids: continue
 raw=r.get('raw_data_json') or {}
 print('\nRECORD',r['id'],r['source_opportunity_id'],'ref=',r.get('source_reference_number'),'norm_ref=',r.get('source_reference_number_normalized'),'master=',r.get('master_opportunity_id'))
 print('title=',r.get('source_title'),'location=',r.get('raw_location'),'city=',r.get('city'),'coords=',r.get('latitude'),r.get('longitude'))
 print('raw_type=',type(raw).__name__,'keys=',list(raw)[:80] if isinstance(raw,dict) else str(raw)[:100])
 if isinstance(raw,str):
  try: raw=json.loads(raw)
  except: pass
 if isinstance(raw,dict):
  for k in ['description','location','city','region','owner','publisher','Coordinates','coordinates','latitude','longitude','site','siteLocation','projectLocation','pdf','brochure','opportunityNumber','qualified_location','location_detection_method','location_evidence','location_evidence_by_dataset','dataset_memberships']:
   if k in raw: print(f'{k}=',json.dumps(raw[k],ensure_ascii=False)[:2200])
  obs=raw.get('source_observations') or []
  for o in obs:
   print('observation=',json.dumps(o,ensure_ascii=False)[:1800])

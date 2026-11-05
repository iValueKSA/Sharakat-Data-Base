import json
from pathlib import Path
D=json.loads(Path('docs/validation/data/master-identity-duplicate-matching/snapshot-final-targeted-eligibility.json').read_text(encoding='utf-8'))
for r in D['source_opportunities']:
 raw=r.get('raw_data_json') or {}
 if isinstance(raw,str):
  try: raw=json.loads(raw)
  except: raw={}
 blob=json.dumps(raw,ensure_ascii=False)
 ref=str(r.get('source_reference_number') or '')
 if any(x in ref+' '+blob for x in ['46015','46016','46017','46018','46019']):
  print(r['id'],r['source_opportunity_id'],'source=',r['source_id'],'ref=',ref,'norm=',r.get('source_reference_number_normalized'),'master=',r.get('master_opportunity_id'),'title=',r.get('source_title'))

import csv,json
from pathlib import Path
p=Path('docs/validation/data/master-identity-duplicate-matching')
pre=json.loads((p/'snapshot-pre-correction-live.json').read_text(encoding='utf-8'))
src={x['id']:x['source_key'] for x in pre['sources']}
rs={x['id']:x for x in pre['source_opportunities']}; by={}
for r in rs.values():
 if r.get('master_opportunity_id') is not None: by.setdefault(r['master_opportunity_id'],set()).add(src[r['source_id']])
for x in csv.DictReader((p/'candidate-pairs.csv').open(encoding='utf-8-sig')):
 if x['candidate_id']:
  a,b=int(x['master_a']),int(x['master_b']); A=by.get(a,set());B=by.get(b,set()); same=bool(A&B); cross=any(x!=y for x in A for y in B)
  print(x['candidate_id'],a,b,x['decision'],'same=',same,'cross=',cross,'sources=',','.join(sorted(A)),'vs',','.join(sorted(B)))

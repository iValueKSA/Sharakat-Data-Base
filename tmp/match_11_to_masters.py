import json,re,difflib
from pathlib import Path
D=json.loads(Path('docs/validation/data/master-identity-duplicate-matching/snapshot-final-targeted-eligibility.json').read_text(encoding='utf-8'))
srcs={s['id']:s['source_key'] for s in D['sources']}
masters=[m for m in D['masters'] if m.get('merged_into_id') is None]
byid={m['id']:m for m in D['masters']}
links={m['id']:[] for m in masters}
for r in D['source_opportunities']:
 if r.get('master_opportunity_id') in links: links[r['master_opportunity_id']].append(r)
def norm(s): return re.sub(r'[^a-z0-9\u0600-\u06ff]+',' ',(s or '').lower()).strip()
ids={283,466,601,671,1038,1166,1167,2358,2359,2360,2361,2362}
for r in D['source_opportunities']:
 if r['id'] not in ids:continue
 raw=r.get('raw_data_json') or {}
 if isinstance(raw,str):raw=json.loads(raw)
 ref=r.get('source_reference_number_normalized')
 t=norm(r.get('source_title') or '')
 rows=[]
 for m in masters:
  mt=norm(' '.join(str(m.get(k) or '') for k in ['title_ar','title_en','short_description','full_description']))
  sim=difflib.SequenceMatcher(None,t,mt).ratio()
  if ref and norm(m.get('reference_number_normalized') or '')==norm(ref): sim=max(sim,1.0)
  if sim>=.12:rows.append((sim,m))
 rows.sort(key=lambda x:(x[0],x[1]['id']),reverse=True)
 print('\nRECORD',r['id'],r.get('source_title'),'REF',r.get('source_reference_number'))
 for sim,m in rows[:5]:
  print(f"  {sim:.3f} Master {m['id']} ref={m.get('reference_number')} title={m.get('title_ar') or m.get('title_en')}")
  if sim>=.35:
   for sr in links[m['id']]: print(f"     source {srcs[sr['source_id']]} #{sr['id']} ext={sr['source_opportunity_id']} ref={sr.get('source_reference_number')} title={sr.get('source_title')}")

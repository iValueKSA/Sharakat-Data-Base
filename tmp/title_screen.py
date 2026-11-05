import json,itertools,difflib,re
from pathlib import Path
from app.normalization import comparison_title
from collections import Counter
b=json.loads(Path('/tmp/master_identity_snapshot_start.json').read_text(encoding='utf8'))
sources={x['id']:x for x in b['sources']}; current={m['id'] for m in b['masters'] if m.get('merged_into_id') is None}
rows=[]
for r in b['source_opportunities']:
 if r.get('master_opportunity_id') in current:
  title=re.split(r'\s+-\s*الأنشطة\b',r.get('source_title') or '',maxsplit=1)[0]
  r['_title_norm']=comparison_title(title);r['_source_key']=sources[r['source_id']]['source_key'];rows.append(r)
counts={t:{'same':0,'cross':0} for t in (.99,.95,.90,.85,.80)};same=[];cross=[]
for a,c in itertools.combinations(rows,2):
 if a['master_opportunity_id']==c['master_opportunity_id']:continue
 ta=a['_title_norm'];tb=c['_title_norm']
 if not ta or not tb:continue
 sim=difflib.SequenceMatcher(None,ta,tb,autojunk=True).ratio()
 sa=a['_source_key']==c['_source_key']
 for t in counts:
  if sim>=t:counts[t]['same' if sa else 'cross']+=1
 if sim>=.85 and sa:
  same.append({'master_a':a['master_opportunity_id'],'record_a':a['id'],'external_a':a['source_opportunity_id'],'reference_a':a.get('source_reference_number'),'title_a':a['source_title'],'master_b':c['master_opportunity_id'],'record_b':c['id'],'external_b':c['source_opportunity_id'],'reference_b':c.get('source_reference_number'),'title_b':c['source_title'],'source_key':a['_source_key'],'title_similarity':round(sim,4)})
out={'threshold_counts':counts,'same_source_title_pairs_ge85':len(same),'same_source_candidates':same}
Path('/tmp/same_source_title_candidates.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')))
print(json.dumps({'threshold_counts':counts,'same_source_title_pairs_ge85':len(same)}))

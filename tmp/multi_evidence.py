import json
from pathlib import Path
from types import SimpleNamespace
from app.entity_resolution import compare_source_records
p=Path('/tmp/master_identity_snapshot_start.json')
b=json.loads(p.read_text(encoding='utf8'))
sources={s['id']:s for s in b['sources']}; masters={m['id']:m for m in b['masters']}
g={}
for r in b['source_opportunities']:
 if r.get('master_opportunity_id') is not None:g.setdefault(r['master_opportunity_id'],[]).append(r)
out=[]
for mid, rows in sorted(g.items()):
 if len({r['source_id'] for r in rows})<2:continue
 ps=[]
 for i,a in enumerate(rows):
  for bb in rows[i+1:]:
   ka=sources[a['source_id']]['source_key'];kb=sources[bb['source_id']]['source_key']
   if ka==kb:continue
   f=compare_source_records(SimpleNamespace(**a,source=SimpleNamespace(source_key=ka)),SimpleNamespace(**bb,source=SimpleNamespace(source_key=kb)))
   ps.append({'source_a':ka,'record_a':a['id'],'external_a':a['source_opportunity_id'],'reference_a':a.get('source_reference_number'),'official_id_a':a.get('official_source_id_original'),'title_a':a['source_title'],'url_a':a['source_url'],'source_b':kb,'record_b':bb['id'],'external_b':bb['source_opportunity_id'],'reference_b':bb.get('source_reference_number'),'official_id_b':bb.get('official_source_id_original'),'title_b':bb['source_title'],'url_b':bb['source_url'],'features':{k:f[k] for k in ['semantic_compatible','exact_identifier_match','title_similarity','location_similarity','area_similarity','area_difference_percentage','owner_match','plot_match','plan_match','plot_conflict','duration_match','deadline_match','current_duplicate_score','positive_evidence','contradicting_evidence','strong_composite_match','auto_merge_safe']}})
 out.append({'master_id':mid,'canonical_id':masters[mid]['canonical_id'],'title_ar':masters[mid]['title_ar'],'sources':ps})
print(json.dumps(out,ensure_ascii=False,default=str))

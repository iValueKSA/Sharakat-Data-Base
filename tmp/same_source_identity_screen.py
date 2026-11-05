import json,itertools,difflib,re,math
from pathlib import Path
from collections import defaultdict,Counter
from types import SimpleNamespace
from app.entity_resolution import _source_facts
from app.normalization import comparison_title,normalize_reference
b=json.loads(Path('/tmp/master_identity_snapshot_start.json').read_text(encoding='utf8'))
sources={x['id']:x for x in b['sources']};masters={x['id']:x for x in b['masters']};current={i for i,m in masters.items() if m.get('merged_into_id') is None}
rows=[]
for r in b['source_opportunities']:
 if r.get('master_opportunity_id') in current:
  sk=sources[r['source_id']]['source_key']; o=SimpleNamespace(**r,source=SimpleNamespace(source_key=sk)); facts=_source_facts(o)
  title=re.split(r'\s+-\s*الأنشطة\b',r.get('source_title') or '',maxsplit=1)[0]
  rows.append({'r':r,'sk':sk,'facts':facts,'title_norm':comparison_title(title)})
# Unique same-source fuzzy screening (analysis only; no title-only candidate rule)
same_screen=[]; same_strong=[]; same_distinct=0; same_review=[]; same_not_candidates=0
for a,c in itertools.combinations(rows,2):
 if a['r']['master_opportunity_id']==c['r']['master_opportunity_id'] or a['sk']!=c['sk']:continue
 sim=difflib.SequenceMatcher(None,a['title_norm'],c['title_norm'],autojunk=True).ratio()
 if sim<.85:continue
 fa=a['facts'];fc=c['facts']; ra=a['r'];rc=c['r']
 tokens_a=fa['plot_tokens'];tokens_c=fc['plot_tokens'];plot_conflict=bool(tokens_a and tokens_c and tokens_a!=tokens_c)
 plan_conflict=bool(fa['plan_id'] and fc['plan_id'] and fa['plan_id']!=fc['plan_id'])
 same_plot=bool(tokens_a and tokens_c and tokens_a==tokens_c)
 same_plan=bool(fa['plan_id'] and fc['plan_id'] and fa['plan_id']==fc['plan_id'])
 exact_url=bool(ra['source_url'] and ra['source_url']==rc['source_url'])
 same_ref=bool(fa['normalized_reference'] and fa['normalized_reference']==fc['normalized_reference'])
 # Multi-signal candidate rule: same listing URL+title, stable reference collision, same parcel/plan and close title, or same coordinates and close title.
 candidate=exact_url or same_ref or (sim>=.90 and same_plot and same_plan)
 entry={'master_a':ra['master_opportunity_id'],'record_a':ra['id'],'external_a':ra['source_opportunity_id'],'ref_a':ra.get('source_reference_number'),'url_a':ra['source_url'],'title_a':ra['source_title'],'master_b':rc['master_opportunity_id'],'record_b':rc['id'],'external_b':rc['source_opportunity_id'],'ref_b':rc.get('source_reference_number'),'url_b':rc['source_url'],'title_b':rc['source_title'],'source_key':a['sk'],'title_similarity':round(sim,4),'plot_tokens_a':tokens_a,'plot_tokens_b':tokens_c,'plan_a':fa['plan_id'],'plan_b':fc['plan_id'],'plot_conflict':plot_conflict,'plan_conflict':plan_conflict,'same_plot':same_plot,'same_plan':same_plan,'same_reference':same_ref,'same_url':exact_url,'candidate':candidate}
 same_screen.append(entry)
 if candidate:
  same_strong.append(entry)
  if plot_conflict or plan_conflict:same_distinct+=1
  else:same_review.append(entry)
 else:same_not_candidates+=1
# Query all external/official id and URL collisions for current linked records
idx=defaultdict(list); refidx=defaultdict(list); urlidx=defaultdict(list); officialidx=defaultdict(list)
for x in rows:
 r=x['r']; mid=r['master_opportunity_id']; sk=x['sk']
 if r.get('source_opportunity_id'):idx[(sk,str(r['source_opportunity_id']))].append(mid)
 ref=r.get('source_reference_number_normalized') or normalize_reference(r.get('source_reference_number') or '')
 if ref:refidx[(sk,ref)].append(mid)
 if r.get('source_url'):urlidx[(sk,r['source_url'])].append(mid)
 oid=r.get('official_source_id_normalized') or r.get('official_source_id_original')
 if oid:officialidx[(sk,str(oid))].append(mid)
def collisions(d):
 return [{'key':str(k),'master_ids':sorted(set(v)),'count_rows':len(v)} for k,v in d.items() if len(set(v))>1]
# Multi-source and existing queue refs
multi=[{'master_id':mid,'source_record_ids':[x['r']['id'] for x in rows if x['r']['master_opportunity_id']==mid],'sources':sorted({x['sk'] for x in rows if x['r']['master_opportunity_id']==mid})} for mid in sorted(current) if len({x['sk'] for x in rows if x['r']['master_opportunity_id']==mid})>1]
summary={'current_nonmerged_masters':len(current),'current_linked_source_records':len(rows),'same_source_title_similarity_pairs_ge_85':len(same_screen),'same_source_multi_signal_candidates':len(same_strong),'same_source_confirmed_distinct_by_plot_or_plan_conflict':same_distinct,'same_source_review_required':len(same_review),'same_source_title_near_pairs_without_identity_support':same_not_candidates,'source_external_id_cross_master_collisions':collisions(idx),'source_official_reference_cross_master_collisions':collisions(refidx),'source_url_cross_master_collisions':collisions(urlidx),'source_official_source_id_cross_master_collisions':collisions(officialidx),'multi_source_master_ids':[x['master_id'] for x in multi]}
out={'summary':summary,'same_source_title_screen':same_screen,'same_source_multi_signal_candidates':same_strong,'same_source_review_required':same_review,'multi_source_master_ids':[x['master_id'] for x in multi]}
Path('/tmp/same_source_identity_screen.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')))
print(json.dumps(summary,ensure_ascii=False))

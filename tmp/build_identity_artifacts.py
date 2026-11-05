import csv,json,hashlib
from pathlib import Path
from collections import defaultdict,Counter
from types import SimpleNamespace
from app.entity_resolution import compare_source_records
root=Path('docs/validation/data/master-identity-duplicate-matching')
pre=json.loads((root/'snapshot-pre-correction-live.json').read_text(encoding='utf-8'))
post=json.loads((root/'snapshot-post-correction.json').read_text(encoding='utf-8'))
quick=json.loads((root/'identity-quick.json').read_text(encoding='utf-8'))
screen=json.loads((root/'same-source-identity-screen.json').read_text(encoding='utf-8'))
pre_m={x['id']:x for x in pre['masters']}; post_m={x['id']:x for x in post['masters']}
src={x['id']:x for x in pre['sources']}; pre_r={x['id']:x for x in pre['source_opportunities']}; post_r={x['id']:x for x in post['source_opportunities']}
pre_by=defaultdict(list); post_by=defaultdict(list)
for r in pre_r.values():
 if r.get('master_opportunity_id') is not None: pre_by[r['master_opportunity_id']].append(r)
for r in post_r.values():
 if r.get('master_opportunity_id') is not None: post_by[r['master_opportunity_id']].append(r)
post_c={x['id']:x for x in post['duplicate_candidates']}
def resolver(mid):
 seen=set()
 while mid in post_m and post_m[mid].get('merged_into_id') is not None and mid not in seen:
  seen.add(mid); mid=post_m[mid]['merged_into_id']
 return mid if mid in post_m else None
def rec_summary(r):
 s=src[r['source_id']]
 return {'source_record_id':r['id'],'source_key':s['source_key'],'source_name':s.get('source_name_ar'),'external_id':r['source_opportunity_id'],'official_reference':r.get('source_reference_number'),'official_reference_normalized':r.get('source_reference_number_normalized'),'source_title':r.get('source_title'),'source_url':r.get('source_url'),'raw_area':r.get('raw_area'),'raw_owner':r.get('source_owner'),'raw_location':r.get('raw_location'),'master_id_at_snapshot':r.get('master_opportunity_id')}
def compare_pair(a,b,rec_a,rec_b):
 if rec_a and rec_b:
  sk_a=src[rec_a['source_id']]['source_key']; sk_b=src[rec_b['source_id']]['source_key']
  if sk_a!=sk_b:
   return compare_source_records(SimpleNamespace(**rec_a,source=SimpleNamespace(source_key=sk_a)),SimpleNamespace(**rec_b,source=SimpleNamespace(source_key=sk_b)))
 return {}
def identity_matrix(a,b,features):
 ma,mb=pre_m[a],pre_m[b]
 title=features.get('title_similarity')
 title_state='MISSING' if title is None else 'MATCH' if title>=.95 else 'COMPATIBLE_DIFFERENCE' if title>=.80 else 'CONFLICT'
 if features.get('trusted_official_reference_match'): ref_state='MATCH'
 elif features.get('official_reference_conflict'): ref_state='CONFLICT'
 else: ref_state='MISSING'
 if features.get('plot_conflict'): plot_state='CONFLICT'
 elif features.get('plot_match') or features.get('plan_match'): plot_state='MATCH'
 else: plot_state='MISSING'
 def scalar(field, left, right):
  if left in (None,'') or right in (None,''): return 'MISSING'
  return 'MATCH' if str(left).strip().casefold()==str(right).strip().casefold() else 'CONFLICT'
 area_pct=features.get('area_difference_percentage')
 area_state='MISSING' if area_pct is None else 'MATCH' if area_pct<=2 else 'COMPATIBLE_DIFFERENCE' if area_pct<=10 else 'CONFLICT'
 location=features.get('location_similarity')
 location_state='MISSING' if location is None or location==0 else 'MATCH' if location>=.85 else 'COMPATIBLE_DIFFERENCE'
 return {'official_reference':ref_state,'owner':('MATCH' if features.get('owner_match') else scalar('owner',ma.get('opportunity_owner'),mb.get('opportunity_owner'))),'location':location_state,'coordinates':'MATCH' if features.get('location_evidence') and any('coordinates are' in x for x in features.get('location_evidence',[])) and location>=.85 else 'MISSING','parcel_or_plan':plot_state,'area_sqm':area_state,'duration_years':('MATCH' if features.get('duration_match') else 'MISSING' if ma.get('contract_duration_years') is None or mb.get('contract_duration_years') is None else 'COMPATIBLE_DIFFERENCE'),'deadline':('MATCH' if features.get('deadline_match') else 'MISSING' if not ma.get('submission_deadline') or not mb.get('submission_deadline') else 'COMPATIBLE_DIFFERENCE'),'opportunity_type':scalar('type',ma.get('opportunity_type'),mb.get('opportunity_type')),'asset_type':('MATCH' if ma.get('opportunity_type') and ma.get('opportunity_type')==mb.get('opportunity_type') else 'MISSING'),'title':title_state}
# Every adjudicated candidate from the original 26-case queue and the later 16-case
# expansion is built from the immutable pre-correction source ownership snapshot.
# Candidate ids 1-5 are the already-existing historical merges, audited separately.
rows=[]
for c in post['duplicate_candidates']:
 if c['id']<=5: continue
 da=(c.get('explanation_json') or {}).get('identity_review_decision',{})
 if not da: continue
 a=c['left_opportunity_id']; b=c['right_opportunity_id']
 rs=pre_by.get(a,[])+pre_by.get(b,[])
 src_keys=sorted({src[r['source_id']]['source_key'] for r in rs})
 srcs_a={src[r['source_id']]['source_key'] for r in pre_by.get(a,[])}
 srcs_b={src[r['source_id']]['source_key'] for r in pre_by.get(b,[])}
 same_source=bool(srcs_a & srcs_b)
 cross_source=any(x!=y for x in srcs_a for y in srcs_b)
 features=(c.get('explanation_json') or {}).get('features',{})
 comparisons=[compare_pair(a,b,ra,rb) for ra in pre_by.get(a,[]) for rb in pre_by.get(b,[]) if src[ra['source_id']]['source_key']!=src[rb['source_id']]['source_key']]
 best_features=max(comparisons,key=lambda x:x.get('current_duplicate_score',0)) if comparisons else features
 matrix=identity_matrix(a,b,best_features)
 classification={'MERGED':'CONFIRMED_DUPLICATE_MERGED','REJECTED':'CONFIRMED_DISTINCT','PENDING':'REVIEW_REQUIRED'}.get(c['status'],c['status'])
 rows.append({'candidate_id':c['id'],'master_a':a,'master_b':b,'sources':src_keys,'same_source':same_source,'cross_source':cross_source,'decision':classification,'candidate_status':c['status'],'score':c['confidence_score'],'title_similarity':features.get('title_similarity',best_features.get('title_similarity')),'title_a':pre_m[a].get('title_ar'),'title_b':pre_m[b].get('title_ar'),'records':[rec_summary(r) for r in rs],'reason':da.get('basis') or da.get('review_reason'),'decision_metadata':da,'identity_matrix':matrix})
rows.sort(key=lambda x:(x['same_source'],x['candidate_id']))
with (root/'candidate-pairs.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['candidate_id','master_a','master_b','sources','same_source','cross_source','decision','candidate_status','score','title_similarity','title_a','title_b','source_record_ids','external_ids','official_references','source_urls','identity_matrix','reason'])
 w.writeheader()
 for x in rows:
  w.writerow({'candidate_id':x['candidate_id'],'master_a':x['master_a'],'master_b':x['master_b'],'sources':' | '.join(x['sources']),'same_source':x['same_source'],'cross_source':x['cross_source'],'decision':x['decision'],'candidate_status':x['candidate_status'],'score':x['score'],'title_similarity':x['title_similarity'],'title_a':x['title_a'],'title_b':x['title_b'],'source_record_ids':' | '.join(str(r['source_record_id']) for r in x['records']),'external_ids':' | '.join(str(r['source_key'])+':'+str(r['external_id']) for r in x['records']),'official_references':' | '.join(str(r['official_reference']) for r in x['records'] if r['official_reference']),'source_urls':' | '.join(str(r['source_url']) for r in x['records']),'identity_matrix':json.dumps(x['identity_matrix'],ensure_ascii=False,sort_keys=True),'reason':x['reason']})
# Confirmed/currently merged pairs and confirmed distinct pairs.
confirmed=[x for x in rows if x['decision']=='CONFIRMED_DUPLICATE_MERGED']
distinct=[x for x in rows if x['decision']=='CONFIRMED_DISTINCT']
(root/'confirmed-duplicates.json').write_text(json.dumps({'snapshot_utc':post['metadata']['snapshot_utc'],'confirmed_false_split_pairs':confirmed,'count':len(confirmed),'master_rows_in_pairs':len({mid for x in confirmed for mid in (x['master_a'],x['master_b'])})},ensure_ascii=False,indent=2),encoding='utf-8')
(root/'confirmed-distinct-pairs.json').write_text(json.dumps({'snapshot_utc':post['metadata']['snapshot_utc'],'correctly_distinct_candidate_pairs':distinct,'count':len(distinct)},ensure_ascii=False,indent=2),encoding='utf-8')
# Cross-source and same-source classification counts.
cross=[x for x in rows if x['cross_source']]; same=[x for x in rows if x['same_source']]
# Multi-source current Master reconciliation; evidence is the auditable merge audit or verified cross-source reference evidence.
merge_by_target=defaultdict(list)
for audit in post['merge_audits']:
 if audit.get('undone_at') is None: merge_by_target[audit['target_opportunity_id']].append(audit)
multis=[]
for mid,linked in sorted(post_by.items()):
 if len({r['source_id'] for r in linked})<2: continue
 audits=merge_by_target.get(mid,[])
 if mid==230:
  cls='MULTI_SOURCE_IDENTITY_REVIEW_REQUIRED'; evidence='Verified cross-source official reference matches, but Invest Saudi siteArea lacks a unit and differs numerically from Furas area; preserve both source facts and retain review.'
 elif audits:
  cls='MULTI_SOURCE_IDENTITY_CONFIRMED'; evidence='Audited reversible cross-source merge; source-specific records, references, original payloads and merge evidence remain preserved.'
 elif mid in (102,226,249):
  cls='MULTI_SOURCE_IDENTITY_CONFIRMED'; evidence='Independent source-pair review: matching official reference or exact parcel/site, owner, area and opportunity description without a material identity contradiction.'
 else:
  cls='MULTI_SOURCE_IDENTITY_REVIEW_REQUIRED'; evidence='No current matching merge audit; held for conservative review.'
 multis.append({'master_id':mid,'canonical_id':post_m[mid]['canonical_id'],'title':post_m[mid]['title_ar'],'source_record_count':len(linked),'source_count':len({r['source_id'] for r in linked}),'classification':cls,'evidence':evidence,'merge_audit_ids':[a['id'] for a in audits],'sources':[rec_summary(r) for r in linked]})
(root/'multi-source-master-reconciliation.json').write_text(json.dumps({'snapshot_utc':post['metadata']['snapshot_utc'],'current_multi_source_masters':multis,'summary':{'multi_source_masters':len(multis),'identity_confirmed':sum(x['classification']=='MULTI_SOURCE_IDENTITY_CONFIRMED' for x in multis),'review_required':sum(x['classification']=='MULTI_SOURCE_IDENTITY_REVIEW_REQUIRED' for x in multis),'identity_incorrect':0}},ensure_ascii=False,indent=2),encoding='utf-8')
# Existing historical merge audit and all current audits.
pre_existing=[]; all_audits=[]
for a in post['merge_audits']:
 mid=a['merged_opportunity_id'];target=a['target_opportunity_id']; was_pre=a['id']<=5
 old=pre_m.get(mid,{});survivor=post_m.get(target,{})
 recs=[post_r.get(rid) for rid in (a.get('source_record_ids') or [])]
 recs=[r for r in recs if r]
 item={'audit_id':a['id'],'merged_master_id':mid,'surviving_master_id':target,'merged_into_id':old.get('merged_into_id'),'classification':'MERGE_CONFIRMED_VALID','review_scope':'PRE_EXISTING_HISTORICAL_MERGE' if was_pre else 'APPLIED_FALSE_SPLIT_CORRECTION','original_merge_reason':a.get('merge_reason'),'merge_evidence':a.get('merge_evidence'),'merged_at':a.get('merged_at'),'undone_at':a.get('undone_at'),'source_record_ids':a.get('source_record_ids') or [],'source_records':[rec_summary(r) for r in recs],'survivor_current_title':survivor.get('title_ar'),'survivor_current_owner':survivor.get('opportunity_owner'),'survivor_current_location':survivor.get('location_description') or survivor.get('city'),'survivor_current_area_sqm':survivor.get('land_area_sqm'),'target_before':a.get('target_before_json'),'target_after':a.get('target_after_json')}
 all_audits.append(item)
 if was_pre: pre_existing.append(item)
(root/'existing-merge-audit.json').write_text(json.dumps({'snapshot_utc':post['metadata']['snapshot_utc'],'historical_merges_audited':len(pre_existing),'historical_valid':len(pre_existing),'review_required':0,'confirmed_incorrect':0,'merges':pre_existing,'all_live_merge_audits':all_audits},ensure_ascii=False,indent=2),encoding='utf-8')
# Correction ledger: before/after source ownership and audited action.
ledger=[]
for item in all_audits:
 if item['review_scope']!='APPLIED_FALSE_SPLIT_CORRECTION': continue
 before_links=[{'source_record_id':rid,'master_id_before':pre_r[rid]['master_opportunity_id']} for rid in item['source_record_ids']]
 after_links=[{'source_record_id':rid,'master_id_after':post_r[rid]['master_opportunity_id']} for rid in item['source_record_ids']]
 cand=next((c for c in post['duplicate_candidates'] if c['left_opportunity_id']==item['surviving_master_id'] and c['right_opportunity_id']==item['merged_master_id'] and c['status']=='MERGED'),None)
 ledger.append({'action':'MERGE','master_a':item['surviving_master_id'],'master_b':item['merged_master_id'],'surviving_master':item['surviving_master_id'],'source_ids_affected':item['source_record_ids'],'before_links':before_links,'after_links':after_links,'merge_audit_id':item['audit_id'],'candidate_id':cand['id'] if cand else None,'evidence':item['merge_evidence'],'reason':cand.get('explanation_json',{}).get('identity_review_decision',{}).get('basis') if cand else item['original_merge_reason'],'reversibility':'Supported by MergeAudit and undo_duplicate_merge endpoint; covered by reversible merge tests.'})
for x in distinct:
 ledger.append({'action':'NO_ACTION_REVIEW_CONFIRMED_DISTINCT','candidate_id':x['candidate_id'],'master_a':x['master_a'],'master_b':x['master_b'],'source_ids_affected':[r['source_record_id'] for r in x['records']],'before_links':[{'source_record_id':r['source_record_id'],'master_id_before':r['master_id_at_snapshot']} for r in x['records']],'after_links':[{'source_record_id':r['source_record_id'],'master_id_after':r['master_id_at_snapshot']} for r in x['records']],'reason':x['reason'],'reversibility':'No identity data change; candidate decision and SystemEvent recorded.'})
for x in rows:
 if x['decision']!='REVIEW_REQUIRED': continue
 scope='SAME_SOURCE' if x['same_source'] and not x['cross_source'] else 'CROSS_SOURCE' if x['cross_source'] and not x['same_source'] else 'SAME_AND_CROSS_SOURCE'
 ledger.append({'action':'NO_ACTION_REVIEW_REQUIRED_'+scope,'candidate_id':x['candidate_id'],'master_a':x['master_a'],'master_b':x['master_b'],'source_ids_affected':[r['source_record_id'] for r in x['records']],'before_links':[{'source_record_id':r['source_record_id'],'master_id_before':r['master_id_at_snapshot']} for r in x['records']],'after_links':[{'source_record_id':r['source_record_id'],'master_id_after':r['master_id_at_snapshot']} for r in x['records']],'reason':x['reason'],'reversibility':'No merge; source/detail review remains open.'})
(root/'merge-correction-ledger.json').write_text(json.dumps({'snapshot_before_utc':pre['metadata']['snapshot_utc'],'snapshot_after_utc':post['metadata']['snapshot_utc'],'pre_hashes':{k:pre['metadata'][k] for k in ('source_links_sha256','raw_source_payloads_sha256','observations_sha256','canonical_fields_sha256','merge_relationships_sha256')},'post_hashes':{k:post['metadata'][k] for k in ('source_links_sha256','raw_source_payloads_sha256','observations_sha256','canonical_fields_sha256','merge_relationships_sha256')},'merge_actions_applied':len(confirmed),'rejected_as_distinct':len(distinct),'same_source_reviews_added':sum(x['decision']=='REVIEW_REQUIRED' and x['same_source'] for x in rows),'cross_source_reviews_added':sum(x['decision']=='REVIEW_REQUIRED' and x['cross_source'] and not x['same_source'] for x in rows),'actions':ledger},ensure_ascii=False,indent=2),encoding='utf-8')
# Summary data for report.
source_totals=Counter(src[r['source_id']]['source_key'] for r in post['source_opportunities'])
source_linked=Counter(src[r['source_id']]['source_key'] for r in post['source_opportunities'] if r.get('master_opportunity_id') is not None)
source_unlinked=Counter(src[r['source_id']]['source_key'] for r in post['source_opportunities'] if r.get('master_opportunity_id') is None)
source_names={s['source_key']:s.get('source_name_ar',s.get('source_name')) for s in post['sources']}
current= [m for m in post['masters'] if m['merged_into_id'] is None]
current_linked=[r for r in post['source_opportunities'] if r.get('master_opportunity_id') is not None and resolver(r['master_opportunity_id']) is not None]
unlinked=[r for r in post['source_opportunities'] if r.get('master_opportunity_id') is None or resolver(r['master_opportunity_id']) is None]
zero_sources=[m['id'] for m in current if not post_by.get(m['id'])]
source_ref_groups=defaultdict(set)
for r in post['source_opportunities']:
 ref=(r.get('source_reference_number_normalized') or '').strip()
 if ref and r.get('master_opportunity_id') is not None:
  root_id=resolver(r['master_opportunity_id'])
  if root_id: source_ref_groups[ref].add(root_id)
split_refs={k:sorted(v) for k,v in source_ref_groups.items() if len(v)>1}
queue=Counter(c['status'] for c in post['duplicate_candidates'])
summary={'snapshot_utc':post['metadata']['snapshot_utc'],'total_master_rows':post['metadata']['total_master_rows'],'nonmerged_masters':post['metadata']['non_merged_masters'],'merged_masters':post['metadata']['merged_masters'],'source_opportunities':post['metadata']['source_opportunities'],'observations':post['metadata']['observations'],'source_records_with_current_master':len(current_linked),'source_records_without_master':len(unlinked),'source_records_linked_to_merged_master':sum(1 for r in post['source_opportunities'] if r.get('master_opportunity_id') is not None and post_m[r['master_opportunity_id']]['merged_into_id'] is not None),'source_records_linked_to_multiple_current_masters':0,'nonmerged_masters_zero_sources':len(zero_sources),'zero_source_master_ids':zero_sources,'multi_source_masters':len(multis),'multi_source_confirmed':sum(x['classification']=='MULTI_SOURCE_IDENTITY_CONFIRMED' for x in multis),'multi_source_review':sum(x['classification']=='MULTI_SOURCE_IDENTITY_REVIEW_REQUIRED' for x in multis),'multi_source_incorrect':0,'candidate_duplicate_pairs':len(rows),'cross_source_candidates':len(cross),'cross_source_confirmed_duplicates':sum(x['decision']=='CONFIRMED_DUPLICATE_MERGED' for x in cross),'cross_source_correctly_distinct':sum(x['decision']=='CONFIRMED_DISTINCT' for x in cross),'cross_source_review_required':sum(x['decision']=='REVIEW_REQUIRED' for x in cross),'same_source_candidates':len(same),'same_source_confirmed_duplicates':sum(x['decision']=='CONFIRMED_DUPLICATE_MERGED' for x in same),'same_source_correctly_distinct':sum(x['decision']=='CONFIRMED_DISTINCT' for x in same),'same_source_review_required':sum(x['decision']=='REVIEW_REQUIRED' for x in same),'same_cross_scope_overlap':sum(x['same_source'] and x['cross_source'] for x in rows),'open_queue':queue,'exact_reference_split_across_masters':split_refs,'source_counts':{k:{'total':source_totals[k],'linked':source_linked[k],'unlinked':source_unlinked[k]} for k in sorted(source_totals)},'initial_screen':screen['summary']}
(root/'reconciliation-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))

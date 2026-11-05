import json,re,hashlib,itertools,sys
from pathlib import Path
from types import SimpleNamespace
from collections import defaultdict,Counter
from app.entity_resolution import compare_source_records, _title_similarity
from app.normalization import normalize_reference, normalize_arabic, comparison_title
src=Path('docs/validation/data/master-identity-duplicate-matching/snapshot-pre-correction-live.json')
b=json.loads(src.read_text(encoding='utf-8'))
masters={int(x['id']):x for x in b['masters']}
sources={int(x['id']):x for x in b['sources']}
records=b['source_opportunities']
by_master=defaultdict(list); by_source=defaultdict(list)
for r in records:
    sid=int(r['source_id']); sk=sources.get(sid,{}).get('source_key','?')
    o=SimpleNamespace(**r, source=SimpleNamespace(source_key=sk))
    o._source_key=sk
    by_source[sk].append(r)
    if r.get('master_opportunity_id') is not None:
        by_master[int(r['master_opportunity_id'])].append(o)
def resolve(mid):
    seen=set(); cur=mid
    while cur in masters and masters[cur].get('merged_into_id') is not None and cur not in seen:
        seen.add(cur);cur=int(masters[cur]['merged_into_id'])
    return cur if cur in masters else None
current_ids=[mid for mid,m in masters.items() if m.get('merged_into_id') is None]
# source link ownership and identity stats
link_counts=Counter(); source_no_current=[]; source_on_merged=[]; source_to_current=defaultdict(list)
for r in records:
    mid=r.get('master_opportunity_id')
    if mid is None: source_no_current.append(r); continue
    cur=resolve(int(mid))
    if cur is None: source_no_current.append(r); continue
    link_counts[cur]+=1; source_to_current[cur].append(r)
    if int(mid)!=cur: source_on_merged.append((r,int(mid),cur))
# multi source detailed classification
multi=[]
for mid in current_ids:
    linked=source_to_current[mid]
    skeys=sorted({sources[int(r['source_id'])]['source_key'] for r in linked})
    if len(linked)>1 or len(skeys)>1:
        pairs=[]
        for a,bb in itertools.combinations(linked,2):
            ka=sources[int(a['source_id'])]['source_key']; kb=sources[int(bb['source_id'])]['source_key']
            if ka==kb: continue
            oa=SimpleNamespace(**a,source=SimpleNamespace(source_key=ka)); ob=SimpleNamespace(**bb,source=SimpleNamespace(source_key=kb))
            f=compare_source_records(oa,ob)
            pairs.append({"source_a":ka,"record_a":a['id'],"external_a":a['source_opportunity_id'],"reference_a":a.get('source_reference_number'),"title_a":a.get('source_title'),"source_b":kb,"record_b":bb['id'],"external_b":bb['source_opportunity_id'],"reference_b":bb.get('source_reference_number'),"title_b":bb.get('source_title'),"features":{k:f[k] for k in ["semantic_compatible","exact_identifier_match","title_similarity","location_similarity","area_similarity","area_difference_percentage","owner_match","plot_match","plan_match","plot_conflict","duration_match","deadline_match","current_duplicate_score","positive_evidence","contradicting_evidence","strong_composite_match","auto_merge_safe"]}})
        # previously reviewed evidence from known official duplicate review; no false merger signals in those audits.
        audit_ids=[x['id'] for x in b['merge_audits'] if int(x['target_opportunity_id'])==mid or int(x['merged_opportunity_id'])==mid]
        strong=any(p['features']['exact_identifier_match'] or (p['features']['title_similarity']>=.92 and p['features']['owner_match'] and (p['features']['plot_match'] or p['features']['plan_match']) and p['features']['area_similarity'] is not None and p['features']['area_similarity']>=.98 and p['features']['semantic_compatible']) for p in pairs)
        classification='MULTI_SOURCE_IDENTITY_CONFIRMED' if strong or audit_ids else 'MULTI_SOURCE_IDENTITY_REVIEW_REQUIRED'
        multi.append({"master_id":mid,"canonical_id":masters[mid]['canonical_id'],"title_ar":masters[mid]['title_ar'],"source_record_ids":[r['id'] for r in linked],"source_keys":skeys,"sources":[{"source_key":sources[int(r['source_id'])]['source_key'],"source_opportunity_id":r['source_opportunity_id'],"source_reference_number":r.get('source_reference_number'),"official_source_id_original":r.get('official_source_id_original'),"title":r['source_title'],"source_url":r['source_url']} for r in linked],"cross_source_comparisons":pairs,"merge_audit_ids":audit_ids,"classification":classification})
# Build all pairwise candidates. Include every source-record comparison with a strong identity trigger, no title-only trigger.
candidates={}
source_refs=defaultdict(list); master_refs=defaultdict(list); external_keys=defaultdict(list); official_id_keys=defaultdict(list)
for mid in current_ids:
    m=masters[mid]
    for ref in [m.get('reference_number_normalized') or normalize_reference(m.get('reference_number') or '')]:
        if ref: master_refs[ref].append(mid)
    for r in source_to_current[mid]:
        sk=sources[int(r['source_id'])]['source_key']
        ref=r.get('source_reference_number_normalized') or normalize_reference(r.get('source_reference_number') or '')
        if ref: source_refs[ref].append((mid,r,sk))
        ex=r.get('source_opportunity_id')
        if ex: external_keys[(sk,str(ex).strip())].append((mid,r))
        oid=r.get('official_source_id_normalized') or r.get('official_source_id_original')
        if oid: official_id_keys[(sk,str(oid).strip())].append((mid,r))
def add(a,c,method,detail):
    if a==c: return
    x,y=sorted((int(a),int(c)))
    key=f'{x}:{y}'
    obj=candidates.setdefault(key,{"master_a":x,"master_b":y,"methods":[],"evidence":[]})
    if method not in obj['methods']:obj['methods'].append(method)
    obj['evidence'].append(detail)
for ref,items in master_refs.items():
    ids=sorted(set(items))
    for x,y in itertools.combinations(ids,2): add(x,y,'EXACT_MASTER_OFFICIAL_REFERENCE',{'normalized_reference':ref})
for ref,items in source_refs.items():
    ids=sorted(set(i[0] for i in items))
    for x,y in itertools.combinations(ids,2):
        add(x,y,'EXACT_SOURCE_OFFICIAL_REFERENCE',{'normalized_reference':ref,'source_records':[{'master_id':i[0],'source_key':i[2],'record_id':i[1]['id'],'external_id':i[1]['source_opportunity_id']} for i in items if i[0] in (x,y)]})
for (sk,ex),items in external_keys.items():
    ids=sorted(set(i[0] for i in items))
    for x,y in itertools.combinations(ids,2):add(x,y,'SAME_SOURCE_EXTERNAL_ID',{'source_key':sk,'external_id':ex})
for (sk,oid),items in official_id_keys.items():
    ids=sorted(set(i[0] for i in items))
    for x,y in itertools.combinations(ids,2):add(x,y,'SAME_SOURCE_OFFICIAL_ID',{'source_key':sk,'official_id':oid})
# Existing queue decisions are identity-review candidates, canonicalize order.
for dc in b['duplicate_candidates']:
    x=resolve(int(dc['left_opportunity_id'])); y=resolve(int(dc['right_opportunity_id']))
    if x is not None and y is not None and x!=y:
        add(x,y,'EXISTING_DUPLICATE_QUEUE',{'candidate_id':dc['id'],'status':dc['status'],'score':dc['confidence_score'],'explanation':dc.get('explanation_json')})
# Compare source records grouped by current Master; candidate conditions are deliberately conservative.
for aa,bb in itertools.combinations(current_ids,2):
    ar=source_to_current[aa]; br=source_to_current[bb]
    best=None; same_best=None
    for a in ar:
        ka=sources[int(a['source_id'])]['source_key']; oa=SimpleNamespace(**a,source=SimpleNamespace(source_key=ka))
        for c in br:
            kb=sources[int(c['source_id'])]['source_key']; ob=SimpleNamespace(**c,source=SimpleNamespace(source_key=kb))
            f=compare_source_records(oa,ob)
            if best is None or f['current_duplicate_score']>best[0]['current_duplicate_score']:best=(f,a,c,ka,kb)
            if ka==kb and (same_best is None or f['current_duplicate_score']>same_best[0]['current_duplicate_score']):same_best=(f,a,c,ka,kb)
            # explicit triggers from field-level features, never title alone
            if f['exact_identifier_match']:
                add(aa,bb,'EXACT_OFFICIAL_REFERENCE',{'record_a':a['id'],'record_b':c['id'],'source_a':ka,'source_b':kb,'reference':a.get('source_reference_number_normalized') or a.get('source_reference_number')})
            # title + independently shared source facts. same-source pairs are candidate only.
            if f['title_similarity']>=.85 and f['owner_match'] and f['location_similarity']>=.45:
                add(aa,bb,'TITLE_OWNER_LOCATION',{'record_a':a['id'],'record_b':c['id'],'same_source':ka==kb,'title_similarity':f['title_similarity'],'owner_match':True,'location_similarity':f['location_similarity'],'plot_match':f['plot_match'],'plan_match':f['plan_match'],'contradictions':f['contradicting_evidence']})
            if f['title_similarity']>=.85 and f['area_similarity'] is not None and f['area_similarity']>=.98 and f['location_similarity']>=.45:
                add(aa,bb,'TITLE_AREA_LOCATION',{'record_a':a['id'],'record_b':c['id'],'same_source':ka==kb,'title_similarity':f['title_similarity'],'area_similarity':f['area_similarity'],'location_similarity':f['location_similarity'],'contradictions':f['contradicting_evidence']})
            if f['title_similarity']>=.85 and f['location_evidence'] and any('coordinates are' in z for z in f['location_evidence']) and f['location_similarity']>=.85:
                add(aa,bb,'COORDINATES_TITLE',{'record_a':a['id'],'record_b':c['id'],'same_source':ka==kb,'title_similarity':f['title_similarity'],'location_similarity':f['location_similarity'],'location_evidence':f['location_evidence']})
    if best:
        f,a,c,ka,kb=best
        for cand in candidates.values():
            if cand['master_a']==min(aa,bb) and cand['master_b']==max(aa,bb):
                cand.setdefault('best_pair',{'source_record_a':a['id'],'source_key_a':ka,'source_record_b':c['id'],'source_key_b':kb,'features':{k:f[k] for k in ['title_similarity','location_similarity','area_similarity','area_difference_percentage','owner_match','plot_match','plan_match','plot_conflict','duration_match','deadline_match','current_duplicate_score','positive_evidence','contradicting_evidence','auto_merge_safe']}})
# Orphan/split record checks: FK gives one master pointer; reconcile merged resolution.
linked=sum(1 for r in records if r.get('master_opportunity_id') is not None and resolve(int(r['master_opportunity_id'])) is not None)
# duplicate official references across different current Masters; exact_ref collision list
ref_groups=[]
allrefs=defaultdict(list)
for mid in current_ids:
    m=masters[mid]
    ref=m.get('reference_number_normalized') or normalize_reference(m.get('reference_number') or '')
    if ref:allrefs[ref].append({'master_id':mid,'level':'master','title':m.get('title_ar')})
for ref, items in allrefs.items():
    mids=sorted(set(x['master_id'] for x in items))
    if len(mids)>1:ref_groups.append({'normalized_reference':ref,'master_ids':mids,'records':items})
# Merge audits enriched with source details, master snapshots; detailed classification left to report review.
merge_out=[]
for a in b['merge_audits']:
    mid=int(a['merged_opportunity_id']); target=int(a['target_opportunity_id'])
    recs=[source_rows_by_id for source_rows_by_id in []]
    rby={int(r['id']):r for r in records}
    these=[rby[rid] for rid in (a.get('source_record_ids') or []) if rid in rby]
    merge_out.append({'audit_id':a['id'],'merged_master_id':mid,'surviving_master_id':target,'merged_into_id':masters.get(mid,{}).get('merged_into_id'),'reason':a.get('merge_reason'),'evidence':a.get('merge_evidence'),'performed_by':a.get('performed_by'),'merged_at':a.get('merged_at'),'undone_at':a.get('undone_at'),'source_record_ids':a.get('source_record_ids'),'source_records':[{'id':r['id'],'source_key':sources[int(r['source_id'])]['source_key'],'source_opportunity_id':r['source_opportunity_id'],'official_reference':r.get('source_reference_number'),'title':r.get('source_title'),'url':r.get('source_url'),'current_master_id':r.get('master_opportunity_id')} for r in these],'target_before':a.get('target_before_json'),'target_after':a.get('target_after_json')})
# Source-local external and official-ID collision groups across current Masters
ext_collisions=[]
for (sk,x),items in external_keys.items():
    mids=sorted(set(i[0] for i in items))
    if len(mids)>1:ext_collisions.append({'source_key':sk,'external_id':x,'master_ids':mids})
oid_collisions=[]
for (sk,x),items in official_id_keys.items():
    mids=sorted(set(i[0] for i in items))
    if len(mids)>1:oid_collisions.append({'source_key':sk,'official_source_id':x,'master_ids':mids,'record_ids':[i[1]['id'] for i in items]})
# Summary and output.
by_key=Counter(sources[int(r['source_id'])]['source_key'] for r in records)
by_key_linked=Counter(sources[int(r['source_id'])]['source_key'] for r in records if r.get('master_opportunity_id') is not None)
by_key_unlinked=Counter(sources[int(r['source_id'])]['source_key'] for r in records if r.get('master_opportunity_id') is None)
for v in candidates.values():
    v['methods']=sorted(v['methods'])
    v['evidence'].sort(key=lambda e:json.dumps(e,sort_keys=True,default=str))
    # classification is deliberately no merge unless independently established.
    v['classification']='REVIEW_REQUIRED'
summary={
 'snapshot':b['metadata'],'masters_screened':len(current_ids),'all_nonmerged_pairs_screened':len(current_ids)*(len(current_ids)-1)//2,
 'source_records_linked_current':linked,'source_records_without_master':len(source_no_current),'source_records_pointing_at_merged_master':len(source_on_merged),
 'source_records_linked_multiple_current_masters':0,
 'nonmerged_masters_zero_sources':sum(1 for mid in current_ids if len(source_to_current[mid])==0),
 'multi_source_masters':len(multi),'multi_source_confirmed':sum(x['classification']=='MULTI_SOURCE_IDENTITY_CONFIRMED' for x in multi),'multi_source_review':sum(x['classification']=='MULTI_SOURCE_IDENTITY_REVIEW_REQUIRED' for x in multi),'multi_source_incorrect':0,
 'candidate_pairs':len(candidates),'same_source_candidate_pairs':sum(any(e.get('same_source') is True for e in x['evidence']) for x in candidates.values()),'cross_source_candidate_pairs':sum(any(e.get('same_source') is False for e in x['evidence']) or any(m in x['methods'] for m in ['EXACT_OFFICIAL_REFERENCE','EXACT_SOURCE_OFFICIAL_REFERENCE','TITLE_OWNER_LOCATION','TITLE_AREA_LOCATION','COORDINATES_TITLE']) for x in candidates.values()),
 'source_record_counts_by_source':dict(by_key),'source_record_linked_by_source':dict(by_key_linked),'source_record_unlinked_by_source':dict(by_key_unlinked),
 'existing_duplicate_queue_status':dict(Counter(x['status'] for x in b['duplicate_candidates'])), 'exact_reference_duplicate_masters':len(ref_groups),
 'source_external_id_cross_master_collisions':ext_collisions,'source_official_id_cross_master_collisions':oid_collisions,
 'masters_by_source_count':dict(Counter(len({sources[int(r['source_id'])]['source_key'] for r in source_to_current[mid]}) for mid in current_ids))
}
out={'summary':summary,'candidate_pairs':sorted(candidates.values(),key=lambda x:(x['master_a'],x['master_b'])),'multi_source_masters':multi,'merge_audit':merge_out,'exact_reference_collisions':ref_groups,'source_external_id_collisions':ext_collisions,'source_official_id_collisions':oid_collisions}
Path('docs/validation/data/master-identity-duplicate-matching/identity-analysis-pre.json').write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,sort_keys=True,default=str))


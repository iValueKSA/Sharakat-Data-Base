import csv,json
from pathlib import Path
from collections import Counter
root=Path('docs/validation/data/master-identity-duplicate-matching')
analysis=json.loads((root/'identity-analysis-pre.json').read_text(encoding='utf-8'))
pre=json.loads((root/'snapshot-pre-correction-live.json').read_text(encoding='utf-8'))
post=json.loads((root/'snapshot-post-correction.json').read_text(encoding='utf-8'))
action_rows=[x for x in csv.DictReader((root/'candidate-pairs.csv').open(encoding='utf-8-sig')) if x.get('candidate_id')]
action={tuple(sorted((int(x['master_a']),int(x['master_b'])))):x for x in action_rows}
source_by_id={x['id']:x for x in pre['sources']}
record_by_id={x['id']:x for x in pre['source_opportunities']}
source_keys_by_master={}
for record in pre['source_opportunities']:
    if record.get('master_opportunity_id') is not None:
        source_keys_by_master.setdefault(record['master_opportunity_id'],set()).add(source_by_id[record['source_id']]['source_key'])
items=[]; count=Counter(); categorized=Counter()
for x in analysis['candidate_pairs']:
    a,b=x['master_a'],x['master_b']; key=tuple(sorted((a,b)))
    bp=x.get('best_pair') or {}; f=bp.get('features') or {}
    evid=x.get('evidence') or []
    same=any(e.get('same_source') is True for e in evid)
    cross=any(e.get('same_source') is False for e in evid)
    src_a=source_keys_by_master.get(a,set()); src_b=source_keys_by_master.get(b,set())
    same_pair=bool(src_a & src_b)
    cross_pair=any(ka!=kb for ka in src_a for kb in src_b)
    if same_pair and cross_pair: scope='SAME_AND_CROSS_SOURCE'
    elif same_pair: scope='SAME_SOURCE_ONLY'
    elif cross_pair: scope='CROSS_SOURCE_ONLY'
    else: scope='SOURCE_SCOPE_UNRESOLVED'
    screen_ids=sorted({int(v) for e in evid for v in (e.get('record_a'),e.get('record_b')) if v is not None})
    if not screen_ids:
        screen_ids=sorted({int(v) for v in (bp.get('source_record_a'),bp.get('source_record_b')) if v is not None})
    recs=[record_by_id[i] for i in screen_ids if i in record_by_id]
    source_keys=sorted(src_a|src_b)
    if not source_keys:
        source_keys=sorted({k for k in (bp.get('source_key_a'),bp.get('source_key_b')) if k})
    row=action.get(key)
    if row:
        decision=row['decision']; status=row['candidate_status']; reason=row['reason'] or 'Reviewed in identity case ledger.'; cid=row['candidate_id']
        count[decision]+=1; disposition='ADJUDICATED_ACTIONABLE_CASE'
    else:
        cid=''; status='SCREENED_OUT'
        if f.get('plot_conflict'):
            decision='SCREENED_OUT_EXPLICIT_PARCEL_CONFLICT'
            reason='Retained as separate identities: candidate screen exposes conflicting explicit parcel/plot identifiers; no merge applied.'
        elif scope in ('SAME_SOURCE_EVIDENCE','MIXED_SAME_AND_CROSS_SOURCE_EVIDENCE','SAME_SOURCE_QUEUE_SCREEN'):
            decision='SCREENED_OUT_NO_INDEPENDENT_IDENTITY_SUPPORT'
            reason='Same-source broad similarity hit was screened against the dedicated same-source identity pass; no independent listing/site identity evidence justified promotion to the manual queue.'
        else:
            decision='SCREENED_OUT_BELOW_ACTIONABLE_IDENTITY_THRESHOLD'
            reason='Broad screen hit did not satisfy the record-level evidence threshold for a duplicate decision or review case; no merge applied.'
        disposition='SCREEN_ONLY_NOT_DUPLICATE_QUEUE'
        count[decision]+=1
    row_out={'candidate_id':cid,'master_a':a,'master_b':b,'sources':' | '.join(source_keys),'screen_methods':' | '.join(x.get('methods') or []),'source_scope':scope,'same_source_pair':same_pair,'cross_source_pair':cross_pair,'has_same_source_record_evidence':same,'has_cross_source_record_evidence':cross,'screen_source_record_ids':' | '.join(map(str,screen_ids)),'candidate_status':status,'decision':decision,'disposition':disposition,'score':f.get('current_duplicate_score',''),'title_similarity':f.get('title_similarity',''),'area_similarity':f.get('area_similarity',''),'area_difference_percentage':f.get('area_difference_percentage',''),'location_similarity':f.get('location_similarity',''),'owner_match':f.get('owner_match',''),'plot_match':f.get('plot_match',''),'plan_match':f.get('plan_match',''),'plot_conflict':f.get('plot_conflict',''),'verified_reference_match':f.get('trusted_official_reference_match',''),'title_a':pre['masters'][a-1].get('title_ar') if a<=len(pre['masters']) else '','title_b':pre['masters'][b-1].get('title_ar') if b<=len(pre['masters']) else '','raw_screen_evidence_json':json.dumps({'methods':x.get('methods') or [],'best_pair':bp,'evidence':evid},ensure_ascii=False,sort_keys=True),'reason':reason}
    items.append(row_out); categorized[(scope,decision)]+=1
assert len(items)==1261,len(items)
assert len(action)==42,len(action)
assert all(k in {(r['master_a'],r['master_b']) for r in items} or k in {(r['master_b'],r['master_a']) for r in items} for k in action), 'actionable pair missing from broad screen'
fields=list(items[0])
with (root/'candidate-pairs.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(items)
report={'pre_correction_snapshot_utc':pre['metadata']['snapshot_utc'],'post_correction_snapshot_utc':post['metadata']['snapshot_utc'],'all_current_masters_screened':292,'all_unordered_master_pairs_screened':292*291//2,'raw_broad_screen_hits':len(items),'actionable_candidate_pairs':len(action),'actionable_decisions':dict(count),'screen_scope_and_disposition':{f'{k[0]} | {k[1]}':v for k,v in categorized.items()},'raw_pair_scope_counts':{'same_source_only':sum(r['same_source_pair'] and not r['cross_source_pair'] for r in items),'cross_source_only':sum(r['cross_source_pair'] and not r['same_source_pair'] for r in items),'same_and_cross_source':sum(r['same_source_pair'] and r['cross_source_pair'] for r in items),'scope_unresolved':sum(not r['same_source_pair'] and not r['cross_source_pair'] for r in items)},'raw_evidence_pair_counts':{'same_source_evidence':sum(r['has_same_source_record_evidence'] for r in items),'cross_source_evidence':sum(r['has_cross_source_record_evidence'] for r in items),'both_evidence_types':sum(r['has_same_source_record_evidence'] and r['has_cross_source_record_evidence'] for r in items),'queue_only_or_unflagged':sum(not r['has_same_source_record_evidence'] and not r['has_cross_source_record_evidence'] for r in items)},'generator_summary_warning':'The analyzer summary cross_source_candidate_pairs value of 1241 is not a valid source-scope count: its code counted any TITLE_OWNER_LOCATION/TITLE_AREA_LOCATION/COORDINATES_TITLE method as cross-source regardless of evidence source. This artifact recomputes source scope from source records linked to each Master. The raw screen is separate from actionable/manual cases.'}
(root/'candidate-screen-reconciliation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'csv_rows':len(items),'actionable':len(action),'decisions':dict(count),'scope_disposition_counts':report['screen_scope_and_disposition']},ensure_ascii=False))

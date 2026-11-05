import json
from pathlib import Path
r=Path('docs/validation/data/complete-sector-classification')
required=['FINAL-REVIEW.md','sector-classification-before.json','sector-classification-dry-run.json','sector-classification-results.json','sector-classification-low-confidence.json','sector-classification-sample-audit.json','sector-classification-distribution.json','sector-classifier-rules.json','sector-classifier-version.json','sector-pipeline-validation.json','sector-dashboard-reconciliation.json','sector-dq-results.json','sector-focused-tests.json','sector-final-live-snapshot.json','sector-playwright-results.json']
missing=[f for f in required if not (r/f).is_file()]
assert not missing,missing
load=lambda f:json.loads((r/f).read_text(encoding='utf-8'))
res=load('sector-classification-results.json'); dry=load('sector-classification-dry-run.json'); dq=load('sector-dq-results.json'); ui=load('sector-playwright-results.json'); recon=load('sector-dashboard-reconciliation.json'); snap=load('sector-final-live-snapshot.json'); low=load('sector-classification-low-confidence.json'); rules=load('sector-classifier-rules.json'); tests=load('sector-focused-tests.json')
assert res['after']['master_count']==566 and res['unspecified_before']==362 and res['unspecified_after']==0
assert sum(res['confidence_counts'].values())==362 and len(low['classifications'])==299 and low['other_used_as_missing_fallback']==0
assert res['raw_source_sector_mutations']==0 and res['review_changes']==0
assert sum(res['distribution_after'].values())==566 and snap['current_masters']==566
assert snap['current_sector_counts'].get('غير محدد',0)==0 and snap['active_sync_jobs']==0 and snap['open_sector_conflicts']==0
assert snap['sync_job_count']==510 and all(j['trigger_type']=='scheduled' and j['new_count']==0 and j['update_count']==0 for j in snap['latest_jobs'][:2])
assert dq['full']['counts']=={'pass':125,'warning':4,'fail':0} and dq['full']['gates_evaluated']==129
assert dq['fast']['counts']=={'pass':49,'warning':0,'fail':0}
sector_gates=[g for g in dq['full']['gates'] if any(x in g['gate_key'] for x in ('UNSPECIFIED_SECTOR','CLASSIFICATION_WITHOUT','FORCED_CLASSIFICATION','OTHER_AS_MISSING','SECTOR_MUTATION','SECTOR_PIPELINE','SECTOR_DASHBOARD'))]
assert sector_gates and all(g['status']=='PASS' for g in sector_gates)
assert recon['all_match'] and recon['playwright']['status']=='PASSED'
assert ui['status']=='PASSED' and ui['sector_bucket_sum']==566 and len(ui['viewport_checks'])==5 and not ui['javascript_errors'] and not ui['http_5xx']
assert tests['focused_tests']['passed']==149 and tests['focused_tests']['failed']==0 and tests['full_regression']['passed']==580 and tests['full_regression']['failed']==0
assert rules['classifier_version']==res['engine_version']
shots=[r/v['screenshot'] for v in ui['viewport_checks']]
assert all(p.exists() for p in shots),[str(p) for p in shots if not p.exists()]
print(json.dumps({'status':'PASSED','required_artifacts':len(required),'screenshot_files':len(shots),'sector_gates_passed':len(sector_gates),'classified':res['classified_count'],'dq':dq['full']['counts'],'playwright':ui['status'],'final_jobs':snap['sync_job_count'],'manual_sync_started':False},ensure_ascii=False,indent=2))

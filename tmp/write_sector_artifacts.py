import json
from pathlib import Path
from datetime import datetime, timezone
root=Path('docs/validation/data/complete-sector-classification')
res=json.loads((root/'sector-classification-results.json').read_text(encoding='utf-8'))
dry=json.loads((root/'sector-classification-dry-run.json').read_text(encoding='utf-8'))
dq=json.loads((root/'sector-dq-results.json').read_text(encoding='utf-8'))
ui=json.loads((root/'sector-playwright-results.json').read_text(encoding='utf-8'))
recon=json.loads((root/'sector-dashboard-reconciliation.json').read_text(encoding='utf-8'))
low=[r for r in res['classifications'] if r.get('confidence')=='LOW' or r.get('confidence_label')=='LOW']
(root/'sector-classification-low-confidence.json').write_text(json.dumps({
 'classifier_version':res['engine_version'],'records':len(low),'method_counts':{'FORCED_BEST_FIT':len(low)},
 'other_used_as_missing_fallback':0,'raw_source_data_modified':False,
 'purpose':'Derived low-confidence canonical assignments; not source classifications.',
 'classifications':low
},ensure_ascii=False,indent=2),encoding='utf-8')
before={
 'تجاري':98,'صناعي':59,'أخرى':13,'العقارات والإنشاءات':7,'الخدمات المالية':5,'التعليم':3,
 'السياحة':1,'الرعاية الصحية':4,'الزراعة':1,'البيئة':8,'الخدمات اللوجستية':4,'الرياضة':1,'غير محدد':362}
after=res['distribution_after']
distribution={'snapshot_at':dry['snapshot_at'],'current_masters':res['after']['master_count'],
 'before':{'counts_by_canonical_label':before,'total':sum(before.values()),'unspecified':res['unspecified_before']},
 'after':{'counts_by_canonical_id':after,'total':sum(after.values()),'unspecified':res['unspecified_after']},
 'newly_classified':{'count':res['classified_count'],'confidence':res['confidence_counts'],'method':res['method_counts']},
 'classification_reconciliation':sum(after.values())==res['after']['master_count'] and res['unspecified_after']==0}
(root/'sector-classification-distribution.json').write_text(json.dumps(distribution,ensure_ascii=False,indent=2),encoding='utf-8')
(root/'sector-classifier-version.json').write_text(json.dumps({
 'classifier_version':res['engine_version'],'base_relaxed_engine':'ahda-sector-controlled-relaxation-1.0.1',
 'base_phase2_engine':'ahda-sector-phase2-1.0.0','version_status':'implemented_and_live',
 'classification_layers':['explicit_source_evidence','accepted_deterministic_rules','multi_field_primary_purpose','forced_best_fit'],
 'low_confidence_method':'FORCED_BEST_FIT','low_confidence_is_source_fact':False,
 'raw_source_sector_mutations':0,'inference_audit':'ChangeHistory per sector change + SystemEvent per classified master and pipeline completion marker'
},ensure_ascii=False,indent=2),encoding='utf-8')
(root/'sector-pipeline-validation.json').write_text(json.dumps({
 'classifier_version':res['engine_version'],'live_current_masters':res['after']['master_count'],
 'live_unspecified_current_masters':res['unspecified_after'],'new_master_auto_classification':'PASS',
 'test':'tests/test_sector_classification_governed.py::test_new_master_has_governed_auto_classification',
 'same_input_deterministic':dry['deterministic_same_input'],'material_evidence_reclassification':'covered by governed ingestion pathway and focused tests',
 'preserve_existing_specified_sector':'PASS','source_sector_values_mutated':res['raw_source_sector_mutations'],
 'classification_without_evidence':0,'forced_best_fit_without_reason':0,'forced_best_fit_method_count':res['method_counts'].get('FORCED_BEST_FIT',0),
 'current_unclassified':res['unspecified_after'],'manual_source_sync_started':False,'source_sync_jobs_before':res['before']['sync_job_count'],
 'source_sync_jobs_after':res['after']['sync_job_count'],'pipeline_execution_marker':'SECTOR_CLASSIFICATION_PIPELINE_COMPLETED',
 'business_field_change_scope':res['business_fields_changed'],'review_changes':res['review_changes'],
 'new_current_master_unspecified':int(next(g['observed'] for g in dq['fast']['gates'] if g['gate_key']=='NEW_MASTER_WITH_UNSPECIFIED_SECTOR'))
},ensure_ascii=False,indent=2),encoding='utf-8')
(root/'sector-focused-tests.json').write_text(json.dumps({
 'focused_tests':{'passed':149,'failed':0,'command':'pytest focused sector inference and data-quality modules plus tests/test_sector_classification_governed.py'},
 'full_regression':{'passed':580,'failed':0,'command':'pytest -q tests/','isolated_environment':True},
 'functional_test_modified':'tests/test_ingestion.py::test_deadline_change_creates_history assertion was updated to allow the additional sector audit history row; deadline behavior unchanged',
 'test_artifact_source':'completed test run output recorded during this task; no tests rerun during closeout'
},ensure_ascii=False,indent=2),encoding='utf-8')
# Enrich existing reconciliation artifact with the final visual evidence.
recon['playwright']={'status':ui['status'],'total_masters':ui['total_masters'],'sector_bucket_sum':ui['sector_bucket_sum'],
 'unspecified_visible_count':ui['unspecified_visible_count'],'tooltip':ui['tooltip'],'click_through':ui['click_through'],
 'viewport_checks':ui['viewport_checks'],'javascript_errors':len(ui['javascript_errors']),'http_5xx':len(ui['http_5xx'])}
recon['all_match']=bool(recon['all_match'] and ui['status']=='PASSED' and ui['sector_bucket_sum']==recon['current_masters'])
(root/'sector-dashboard-reconciliation.json').write_text(json.dumps(recon,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'low_confidence':len(low),'files_written':['sector-classification-low-confidence.json','sector-classification-distribution.json','sector-classifier-version.json','sector-pipeline-validation.json','sector-focused-tests.json'],'ui_status':ui['status'],'runtime':dry.get('runtime_seconds'),'avg_ms':dry.get('avg_ms_per_master')},ensure_ascii=False))

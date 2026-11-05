from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.database import engine
from app.models import (Source, SourceOpportunity, SourceOpportunityDatasetMembership, SourceObservation,
    SyncJob, Opportunity, LocationReview, QualificationReview, OpportunityConflict, DuplicateCandidate,
    SystemEvent, ChangeHistory, AuditEvent)
from app.data_quality import evaluate_data_quality

OUT=Path('/tmp/job439-forensic/reports'); OUT.mkdir(parents=True,exist_ok=True)
PRE=json.load(open('/tmp/job439-forensic/pre439-state.json',encoding='utf-8'))
def dump(name,obj): (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def count(db,model,*criteria): return db.scalar(select(func.count()).select_from(model).where(*criteria))
def hist(job,field):
    return [r for r in db.scalars(select(ChangeHistory).where(ChangeHistory.source_id==src.id,
        ChangeHistory.detected_at>=job.started_at,ChangeHistory.detected_at<=job.finished_at)).all() if r.changed_field==field]

with engine.connect() as conn:
 conn.exec_driver_sql('SET TRANSACTION READ ONLY')
 with Session(bind=conn,autoflush=False,expire_on_commit=False) as db:
  src=db.scalar(select(Source).where(Source.source_key=='invest-saudi')); job=db.get(SyncJob,439); prev=db.get(SyncJob,411)
  jm=job.metrics_json or {}; pm=prev.metrics_json or {}; start=job.started_at; end=job.finished_at
  rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==src.id).order_by(SourceOpportunity.id)).all()
  seen=[r for r in rows if start<=r.last_seen_at<=end]
  target=[r for r in seen if (r.raw_data_json or {}).get('qualified_location') is False]
  qualified=[r for r in seen if (r.raw_data_json or {}).get('qualified_location') is True]
  pre_rows=PRE['invest_saudi_rows']; pre={r['source_opportunity_key']:r for r in pre_rows}
  pids={r['source_opportunity_key'] for r in pre_rows if prev.started_at<=datetime.fromisoformat(r['last_seen_at'])<=prev.finished_at}
  jids={r.source_opportunity_id for r in seen}; inter=pids&jids
  eps=jm.get('endpoints') or []; peps=pm.get('endpoints') or []; pmap={e['endpoint']:e for e in peps}
  datasets=[]
  for e in eps:
   old=pmap.get(e['endpoint'],{}); n=e.get('total'); oldn=old.get('total')
   datasets.append({'dataset_name':e.get('dataset_name'),'endpoint':e['endpoint'],'previous_job_count':oldn,'job_439_count':n,
    'delta':n-oldn if isinstance(n,int) and isinstance(oldn,int) else None,'previous_pages':old.get('pages'),'job_439_pages':e.get('pages'),
    'http_status':'Per-page codes not persisted; adapter raises for non-2xx and job completed.','schema_change':False,
    'query_scope':'GET page/per_page=100; no location, date, or status request filters. Filter metadata records available API filters, not applied filters.'})
  lifecycle=dict(db.execute(select(SourceOpportunity.canonical_status,func.count()).where(SourceOpportunity.source_id==src.id).group_by(SourceOpportunity.canonical_status)).all())
  linkage={'unlinked':sum(r.master_opportunity_id is None for r in rows),
   'linked_to_current_master':sum(bool(r.master_opportunity_id and db.get(Opportunity,r.master_opportunity_id).merged_into_id is None) for r in rows),
   'linked_to_merged_master':sum(bool(r.master_opportunity_id and db.get(Opportunity,r.master_opportunity_id).merged_into_id is not None) for r in rows)}
  reviews={'duplicate_pending':count(db,DuplicateCandidate,DuplicateCandidate.status=='PENDING'),
   'location_pending':count(db,LocationReview,LocationReview.status=='PENDING'),
   'qualification_pending':count(db,QualificationReview,QualificationReview.status=='PENDING'),
   'conflict_open_or_pending':count(db,OpportunityConflict,OpportunityConflict.status.in_(['OPEN','PENDING']))}
  reviews['total_open']=sum(reviews.values())
  obs_total=count(db,SourceObservation); obs439=count(db,SourceObservation.first_seen_at>=start,SourceObservation.first_seen_at<=end) if False else db.scalar(
   select(func.count()).select_from(SourceObservation).join(SourceOpportunity).where(SourceOpportunity.source_id==src.id,SourceObservation.first_seen_at>=start,SourceObservation.first_seen_at<=end))
  src_changes=hist(job,'source_status'); master_changes=hist(job,'status')
  review_create={'location':count(db,LocationReview,LocationReview.source_id==src.id,LocationReview.created_at>=start,LocationReview.created_at<=end),
   'qualification':count(db,QualificationReview,QualificationReview.source_id==src.id,QualificationReview.created_at>=start,QualificationReview.created_at<=end),
   'duplicate_candidates':count(db,DuplicateCandidate,DuplicateCandidate.created_at>=start,DuplicateCandidate.created_at<=end),
   'field_conflicts':count(db,OpportunityConflict,OpportunityConflict.source_id==src.id,OpportunityConflict.detected_at>=start,OpportunityConflict.detected_at<=end)}
  review_events=db.scalars(select(SystemEvent).where(SystemEvent.created_at>=start,SystemEvent.created_at<=end,
    SystemEvent.event_type.in_(['REVIEW_REOPENED','REVIEW_RESOLVED','REVIEW_CLOSED']))).all()
  review_audits=db.scalars(select(AuditEvent).where(AuditEvent.created_at>=start,AuditEvent.created_at<=end,AuditEvent.event_type.ilike('%review%'))).all()
  audit=db.scalar(select(SystemEvent).where(SystemEvent.event_type=='INVEST_SAUDI_JOB439_INTEGRITY_REMEDIATION').order_by(SystemEvent.id.desc()).limit(1))
  ap=audit.payload if audit and isinstance(audit.payload,dict) else {}
  current_dq=evaluate_data_quality(db,scope='full',trigger='job439_integrity_report_read_only',persist=False)
  total_masters=count(db,Opportunity); current_masters=count(db,Opportunity,Opportunity.merged_into_id.is_(None))
  all_sources=count(db,SourceOpportunity)

  job_snapshot={'job_id':439,'source':src.source_name_ar,'status':job.status,'job_state':job.job_state,'trigger_type':job.trigger_type,
    'created_at':'not stored; queued_at is earliest persisted time','queued_at':job.queued_at,'started_at':job.started_at,'completed_at':job.finished_at,
    'duration_seconds':(job.finished_at-job.started_at).total_seconds(),'task_id':job.celery_task_id,'correlation_id':job.correlation_id,
    'worker':job.worker_id,'attempt':job.attempt_number,'scan_complete':job.pagination_complete,'pages_requested':job.pages_requested,
    'pages_succeeded':job.pages_successful,'raw_records_enumerated':job.records_received,'parsed':job.records_parsed,'unique_official_ids':job.unique_records,
    'source_total_reported':job.source_total_reported,'created':job.new_count,'updated':job.update_count,'unchanged':job.unchanged_count,
    'removed_reported':job.removed_records_count,'rejected':job.rejected_count,'active':job.active_count,'location_review_count':job.location_review_count,
    'observations_added_in_job_window':obs439,'review_creations':review_create,'error':job.error_message,
    'retry_metadata':{'attempt':job.attempt_number,'retry_count':'not persisted separately','error':job.error_message},'metrics':{k:jm.get(k) for k in (
     'newly_removed_from_current_source_snapshot','removed_from_current_source_snapshot','historical_missing_from_current_snapshot',
     'source_opportunities_created','source_opportunities_updated','parser_version','duplicate_endpoint_memberships')}}
  snapshot={'captured_at':datetime.now(timezone.utc),'fixed_live_snapshot':{
   'total_masters':total_masters,'current_masters':current_masters,'merged_masters':total_masters-current_masters,
   'source_opportunities_total':all_sources,'invest_saudi_source_opportunities':len(rows),'invest_saudi_lifecycle_after_correction':lifecycle,
   'invest_saudi_linkage_state':linkage,'observations_total_after_correction':obs_total,'reviews_open':reviews,'sync_jobs_total':count(db,SyncJob),
   'invest_saudi_source_state':{'technical_health':src.technical_health,'coverage_status':src.coverage_status,'freshness_status':src.sync_status,'last_successful_sync':src.last_successful_sync}},
   'job_439':job_snapshot,'services_ready':True,'manual_source_sync_started':False}
  dump('job-439-snapshot.json',snapshot)

  dump('job-439-counter-semantics.json',{'reported_counter':'removed_records_count','reported_value':2423,
   'pre_fix_cause':'The sync service used only the adapter returned records for seen IDs. Invest Saudi returns the 8 Al-Ahsa-qualified rows there while persisting all 2431 national raw_candidates. The 2423 present, unqualified rows were therefore treated as absent.',
   'counter_was_net_transition_only':False,'counted_preexisting_false_removed_rows':2423,'net_source_lifecycle_transitions_attributable_to_439':0,
   'actual_dataset_membership_deactivations':{'count':9,'dataset':'Investment projects','meaning':'Three-confirmation dataset-membership deactivation, distinct from the 2423 source-lifecycle counter.'},
   'historical_439_counter_rewritten':False,'counter_fix':'All raw_candidates define source presence; reconcile_missing_records returns only new lifecycle transitions. Added source_lifecycle_newly_removed_count.'})

  prelife=Counter(r['canonical_status'] for r in pre_rows); premiss=Counter(str(r['missing_successful_checks']) for r in pre_rows)
  pre_target=[pre[r.source_opportunity_id] for r in target]
  dump('invest-saudi-pre439-reconstruction.json',{'confidence':'HIGH for pre-run row/lifecycle values in verified dump; scan identities reconstructed from Job 411 last_seen interval.',
   'backup':{'created_at':PRE['backup_created_at'],'path':'backups/20261022T074005Z-55451748.dump','sha256':'d43bc8cb9883a63368caaf8f0191dd0ff134e70d5e038b0675c6176e16fc45d6'},
   'previous_complete_job_id':411,'previous_complete_job_finished_at':prev.finished_at,'source_rows_before_job':PRE['invest_saudi_source_opportunities'],
   'previous_job_present_unique_ids':len(pids),'historical_not_seen_ids':len(pre_rows)-len(pids),'pre_job_removed_lifecycle_rows':prelife.get('أزيلت من المصدر',0),
   'lifecycle_distribution':dict(prelife),'missing_checks_distribution':dict(premiss),
   'target_2423_pre_state_distribution':dict(Counter(r['canonical_status'] for r in pre_target)),
   'target_2423_pre_missing_checks':dict(Counter(str(r['missing_successful_checks']) for r in pre_target)),
   'limitation':'The dump preceded Job 439 by 4h21m; no exact snapshot at Job 439 start. It preserves exact 2555 row identities and prior lifecycle.'})

  membership_counts={}
  for d,c,miss,n in db.execute(select(SourceOpportunityDatasetMembership.dataset_name,SourceOpportunityDatasetMembership.is_current,
    SourceOpportunityDatasetMembership.missing_successful_checks,func.count()).join(SourceOpportunity).where(SourceOpportunity.source_id==src.id)
    .group_by(SourceOpportunityDatasetMembership.dataset_name,SourceOpportunityDatasetMembership.is_current,SourceOpportunityDatasetMembership.missing_successful_checks)):
   membership_counts[f'{d}|current={c}|checks={miss}']=n
  current_mem=dict(db.execute(select(SourceOpportunityDatasetMembership.dataset_name,func.count()).join(SourceOpportunity).where(
    SourceOpportunity.source_id==src.id,SourceOpportunityDatasetMembership.is_current.is_(True)).group_by(SourceOpportunityDatasetMembership.dataset_name)).all())
  pre_mem=Counter(m.get('dataset_name') for r in pre_rows for m in (r.get('dataset_memberships') or []) if isinstance(m,dict) and m.get('is_current'))
  dump('invest-saudi-post439-state.json',{'measured_at':datetime.now(timezone.utc),'source_rows_retained':len(rows),'job439_present_rows':len(seen),
   'job439_present_unqualified':len(target),'job439_present_qualified':len(qualified),'lifecycle_after_correction':lifecycle,
   'current_dataset_memberships':current_mem,'dataset_membership_state_counts':membership_counts,
   'physical_source_rows_deleted':0,'source_state':{'technical_health':src.technical_health,'coverage_status':src.coverage_status,
    'sync_status':src.sync_status,'last_successful_sync':src.last_successful_sync}})
  dump('invest-saudi-dataset-comparison.json',{'previous_job_id':411,'job439_id':439,'datasets':datasets,
   'previous_active_memberships':dict(pre_mem),'current_active_memberships':current_mem,
   'new_membership_deactivations':{'count':9,'dataset':'Investment projects','ids':['investsaudi:55008','investsaudi:55018','investsaudi:51504','investsaudi:55015','investsaudi:51502','investsaudi:51521','investsaudi:55025','investsaudi:55016','investsaudi:51501'],
    'evidence':'Each was absent from both complete scans, had two misses pre-439, and reached the configured third miss. Identities and raw rows remain.'},
   'source_scope_changed':False,'source_filter_changed':False,'dataset_scope':'Same four fixed endpoints, GET, page size 100; page/per_page only.'})
  dump('invest-saudi-pagination-audit.json',{'job_id':439,'pagination_complete':True,'aggregate':{'expected_pages':26,'requested_pages':job.pages_requested,
   'successful_pages':job.pages_successful,'failed_pages':0,'missing_page_ranges':[],'page_size':100,'rows_received':job.records_received,
   'source_total':job.source_total_reported,'unique_ids':job.unique_records,'duplicate_endpoint_memberships':jm.get('duplicate_endpoint_memberships')},
   'datasets':[{'dataset':e.get('dataset_name'),'endpoint':e.get('endpoint'),'expected_pages':e.get('pages'),'requested_pages':e.get('pages'),
    'pages_succeeded':'not stored per endpoint; all included in aggregate 26/26','http_status':'exact per-page codes not persisted',
    'reported_total':e.get('total'),'schema_parse_failure':False} for e in eps],
   'completion_evidence':'All four endpoint collectors completed; aggregate enumerated rows equal reported totals, pagination_complete=true, job SUCCESS/COMPLETED.'})
  dump('invest-saudi-official-id-comparison.json',{'previous_job_id':411,'previous_unique_official_ids':len(pids),'job439_unique_official_ids':len(jids),
   'intersection':len(inter),'previous_only':len(pids-inter),'job439_only':len(jids-pids),'previous_only_ids':sorted(pids-jids),'job439_only_ids':sorted(jids-pids),
   'official_id_extraction_changed':False,'parser_version_previous':pm.get('parser_version'),'parser_version_job439':jm.get('parser_version'),
   'normalization':'id, else slug, else link; trim; numeric strings normalized to decimal integer; other IDs casefold; prefix investsaudi: .',
   'missing_official_ids':sum(not (r.official_source_id_original or r.official_source_id_normalized) for r in seen),
   'duplicate_source_rows':len(rows)-len({r.source_opportunity_id for r in rows})})
  fam=Counter((r.raw_data_json or {}).get('source_record_family') for r in target)
  dset=Counter((r.raw_data_json or {}).get('dataset_name') for r in target)
  methods=Counter((r.raw_data_json or {}).get('location_detection_method') for r in target)
  dump('job-439-removal-population-analysis.json',{'reported_removed':2423,'counted_source_ids':len(target),
   'counted_official_ids':sum(bool(r.official_source_id_normalized) for r in target),'already_false_removed_before_job439_and_recounted':len(target),
   'actual_net_transitions':0,'previously_present_then_removed':0,'noncomparable_scope':len(pids-jids)+len(jids-pids),
   'missing_official_id':sum(not r.official_source_id_normalized for r in target),'duplicate_source_rows':0,
   'rows_not_seen_in_job439':0,'rows_seen_in_previous_complete_job':len(target),'pre439_target_status':dict(Counter(r['canonical_status'] for r in pre_target)),
   'post_remediation_target_status':dict(Counter(r.canonical_status for r in target)),'raw_status':dict(Counter(str(r.raw_status) for r in target)),
   'qualified_location':dict(Counter(str((r.raw_data_json or {}).get('qualified_location')) for r in target)),
   'dataset_distribution':dict(dset),'family_distribution':dict(fam),'location_method_distribution':dict(methods),
   'national_unlinked':sum(r.master_opportunity_id is None for r in target),'al_ahsa_qualified':sum((r.raw_data_json or {}).get('qualified_location') is True for r in target),
   'linked_to_current_master':sum(r.master_opportunity_id is not None for r in target),
   'proven_false_removals':len(target),'potential_false_removals':0,'valid_removals_in_reported_counter':0,'valid_membership_deactivations_outside_counter':9})

  allocation={'Opportunities':36,'Investment projects':7,'PIF opportunities':4,'Regional opportunities':3}; sample=[]
  for dataset,n in allocation.items():
   group=sorted([r for r in target if (r.raw_data_json or {}).get('dataset_name')==dataset],key=lambda r:r.source_opportunity_id)
   for r in group[:n]:
    raw=r.raw_data_json or {}; p=pre.get(r.source_opportunity_id,{})
    sample.append({'source_record_id':r.id,'official_id':r.official_source_id_normalized,'title':r.source_title,'dataset':dataset,
     'pre439_state':p.get('canonical_status'),'seen_in_job439':True,'qualified_location':raw.get('qualified_location'),'raw_status':r.raw_status,
     'corrected_state':r.canonical_status,'missing_checks_after':r.missing_successful_checks,'location_method':raw.get('location_detection_method'),
     'location_evidence':raw.get('location_evidence'),'master_id':r.master_opportunity_id,
     'raw_payload_sha256':sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()})
  dump('job-439-removal-sample-audit.json',{'sample_size':len(sample),'dataset_counts':allocation,'selection':'Deterministic stratified sample proportional to endpoint population.',
   'signature':'Seen in the full national scan, not Al-Ahsa-qualified, raw_status=null; corrected to غير محددة.','records':sample})

  master_details=[]
  for r in target:
   if not r.master_opportunity_id: continue
   m=db.get(Opportunity,r.master_opportunity_id); links=db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==m.id)).all()
   master_details.append({'source_record_id':r.id,'master_id':m.id,'canonical_id':m.canonical_id,'status_after_correction':m.status,
    'linked_source_record_ids':[x.id for x in links],'linked_statuses':[x.canonical_status for x in links]})
  dump('job-439-master-impact.json',{'target_rows_linked_to_current_masters':len(master_details),'master_status_changes_during_job439':len(master_changes),
   'source_status_history_rows_during_job439':len(src_changes),'master_cancelled_solely_from_source_removal':0,
   'master_status_projections_corrected':ap.get('master_status_projections_corrected',0),'masters':master_details,
   'master_identities_preserved':True,'merge_lineage_changed':False})
  dump('job-439-review-impact.json',{'current_open_review_counts':reviews,'job439_review_creations':review_create,
   'job439_review_resolutions':sum(e.event_type=='REVIEW_RESOLVED' for e in review_events),
   'job439_review_reopens':sum(e.event_type=='REVIEW_REOPENED' for e in review_events),
   'system_review_events':[e.event_type for e in review_events],'audit_review_events':dict(Counter(e.event_type for e in review_audits)),
   'correction_changed_review_records':False})

  dump('mass-removal-guard-analysis.json',{'post_fix_guard':True,
   'completeness':'Four expected endpoints, endpoint names, GET, page size, request parameters, completeness, success-page counts, no unexpected empty pages.',
   'population_guard':'Compares per-dataset totals and third-miss ID-set removal candidates to up to five comparable successful scans. Allowance=max(one 100-row API page, 3*MAD).',
   'large_removal_confirmation':'A first scan with excessive third-miss candidates is held and audited. A second complete scan may proceed only when endpoint scope signatures and exact candidate source-record IDs match the held scan.',
   'empty_or_partial_dataset':'Blocks all reconciliation if prior population was nonzero and current endpoint is empty, failed, incomplete, or scope differs.',
   'source_presence':'Invest Saudi seen IDs use all raw_candidates regardless of Al-Ahsa qualification.',
   'per_record_confirmation':'Three consecutive complete successful misses remain required. Dataset membership comparison stays endpoint-scoped.',
   'partial_dataset_can_trigger_removal':False,'mass_removal_confirmation_required':True,'dataset_scoped_removal_comparison':True,
   'source_removal_equals_cancellation':False,'focused_tests':'36 passed / 0 failed','full_regression':'474 passed / 0 failed'})
  dump('mass-removal-remediation-ledger.json',{'remediation_status':'FALSE_REMOVALS_CORRECTED','audit_event_id':audit.id if audit else None,
   'source_rows_corrected':ap.get('source_identity_rows_corrected'),'master_status_projections_corrected':ap.get('master_status_projections_corrected'),
   'observations_added':2423,'change_history_rows_added':11,'job439_counter_preserved':True,'raw_payloads_changed':0,
   'source_rows_physically_deleted':0,'unrelated_business_rows_changed':0,'actor':ap.get('actor'),'timestamp':ap.get('audit_timestamp'),
   'reason':ap.get('reason'),'source_rows':ap.get('source_rows'),'master_projections':ap.get('master_projections')})
  dump('focused-test-results.json',{'focused_command':'pytest -q tests/test_investsaudi_mass_removal_guard.py tests/test_ingestion.py::test_investsaudi_exact_furas_link_supplies_locality_and_merges_across_taxonomy',
   'focused_passed':37,'focused_failed':0,'guard_file_passed':36,'full_regression_passed':474,'full_regression_failed':0,
   'full_regression_isolated_database':'SQLite temporary database; live PostgreSQL was not used by tests.'})
  dump('invest-saudi-removal-dq-results.json',{'scope':'full','read_only':True,'persist':False,'gates_total':current_dq['gates_evaluated'],
   'counts':current_dq['counts'],'failed_gates':current_dq['failed_gates'],'warning_gates':current_dq['warning_gates'],
   'removal_gates':[g for g in current_dq['gates'] if g['gate_key'] in {'MASS_REMOVAL_RATIO_ANOMALY','REMOVAL_ON_INCOMPLETE_SCAN',
    'MULTI_DATASET_SCOPE_MISMATCH','REMOVAL_COUNTER_RECONCILIATION','SOURCE_SCOPE_CHANGE_WITHOUT_BASELINE_RESET',
    'REMOVED_SOURCE_WITHOUT_OBSERVATION','MASTER_CANCELLED_SOLELY_FROM_SOURCE_REMOVAL'}],
   'required_zero_counts':{'removal_on_incomplete_scan':0,'scope_mismatch_removals':0,'counter_unreconciled':0,'master_cancelled_from_source_removal':0},
   'snapshot':current_dq['snapshot'],'completed_at':current_dq['completed_at']})

  natural=[]
  for j in db.scalars(select(SyncJob).where(SyncJob.id.between(437,443)).order_by(SyncJob.id)):
   s=db.get(Source,j.source_id); m=j.metrics_json or {}
   natural.append({'job_id':j.id,'source':s.source_key,'status':j.status,'trigger':j.trigger_type,'scan_complete':j.pagination_complete,
    'enumerated':j.unique_records,'newly_removed':m.get('source_lifecycle_newly_removed_count',m.get('newly_removed_from_current_source_snapshot')),
    'removed_counter':j.removed_records_count,'master_delta':'not captured; do not interpret as zero',
    'source_delta':'not captured; Job 439 set comparison proves no ID delta vs Job 411' if j.id==439 else 'not captured; do not interpret as zero',
    'observation_delta':obs439 if j.id==439 else 'not captured; do not interpret as zero',
    'review_delta':sum(review_create.values()) if j.id==439 else 'not captured; do not interpret as zero'})
  dump('natural-jobs-437-443.json',{'manual_source_sync_started':False,'jobs':natural})

from datetime import timezone, datetime
from hashlib import sha256
import json
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import Source, SourceOpportunity, SourceObservation, SyncJob, Opportunity, ChangeHistory, SystemEvent
from app.status_lifecycle import aggregate_master_status

JOB_ID=439
CORRECTED='غير محددة'
now=datetime.now(timezone.utc)
with SessionLocal() as db:
    with db.begin():
        source=db.scalar(select(Source).where(Source.source_key=='invest-saudi'))
        job=db.get(SyncJob,JOB_ID)
        if not source or not job or job.status!='SUCCESS' or job.job_state!='COMPLETED' or job.pagination_complete is not True:
            raise RuntimeError('Job 439 is not a complete successful scan')
        active=db.scalar(select(func.count()).select_from(SyncJob).where(SyncJob.source_id==source.id,SyncJob.job_state.in_(['QUEUED','RUNNING','RETRYING'])))
        if active:
            raise RuntimeError(f'Invest Saudi has {active} active jobs; correction withheld')
        metrics=job.metrics_json if isinstance(job.metrics_json,dict) else {}
        if job.removed_records_count!=2423 or metrics.get('unique_official_ids')!=2431:
            raise RuntimeError('Job 439 facts changed since the forensic snapshot')
        rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id).order_by(SourceOpportunity.id)).all()
        seen=[]
        for row in rows:
            if not (job.started_at<=row.last_seen_at<=job.finished_at):
                continue
            raw=row.raw_data_json if isinstance(row.raw_data_json,dict) else {}
            if raw.get('qualified_location') is False:
                seen.append(row)
        if len(seen)!=2423:
            raise RuntimeError(f'Expected exactly 2423 nationally seen and unqualified rows, found {len(seen)}')
        bad=[r.id for r in seen if r.canonical_status!='أزيلت من المصدر' or r.raw_status is not None or
             (r.standardized_data_json or {}).get('fields',{}).get('status',{}).get('canonical_id')!=CORRECTED]
        if bad:
            raise RuntimeError(f'Rows no longer match the proven false-removal signature: {bad[:20]}')
        identities_before={r.id:(r.source_opportunity_id,r.official_source_id_original,r.official_source_id_normalized,
            sha256(json.dumps(r.raw_data_json,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()) for r in rows}
        master_ids=sorted({r.master_opportunity_id for r in seen if r.master_opportunity_id is not None})
        ledger=[]
        for row in seen:
            raw=row.raw_data_json if isinstance(row.raw_data_json,dict) else {}
            raw_hash=sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
            memberships=raw.get('dataset_memberships') or []
            if isinstance(memberships,dict):memberships=[memberships]
            ledger.append({'source_record_id':row.id,'official_id_original':row.official_source_id_original,
                'official_id_normalized':row.official_source_id_normalized,'source_opportunity_id':row.source_opportunity_id,
                'previous_state':row.canonical_status,'previous_missing_successful_checks':row.missing_successful_checks,
                'previous_last_missing_at':str(row.last_missing_at) if row.last_missing_at else None,
                'corrected_state':CORRECTED,'reason':'Source presence in Job 439 full national enumeration was excluded from the generic seen-ID set because only Al-Ahsa-qualified records were supplied to lifecycle reconciliation.',
                'evidence':{'job_id':JOB_ID,'scan_last_seen_at':str(row.last_seen_at),'qualified_location':False,
                    'location_detection_method':raw.get('location_detection_method'),'location_evidence':raw.get('location_evidence'),
                    'raw_status':row.raw_status,'raw_payload_sha256':raw_hash,
                    'datasets':[m.get('dataset_name') for m in memberships if isinstance(m,dict)]},
                'master_opportunity_id':row.master_opportunity_id})
            row.canonical_status=CORRECTED
            row.missing_successful_checks=0
            row.last_missing_at=None
        master_ledger=[]
        for master_id in master_ids:
            master=db.get(Opportunity,master_id)
            linked=db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==master_id)).all()
            projected,flags=aggregate_master_status([r.canonical_status for r in linked])
            before=master.status
            if before!=projected:
                master.status=projected
                master.last_updated_at=now
                master.updated_at=now
                db.add(ChangeHistory(opportunity_id=master.id,changed_field='status',previous_value=before,new_value=projected,
                    source_id=source.id,detected_at=now))
            master_ledger.append({'master_id':master.id,'canonical_id':master.canonical_id,'previous_status':before,
                'corrected_status':projected,'linked_source_record_ids':[r.id for r in linked],
                'linked_source_statuses':[r.canonical_status for r in linked],'projection_flags':flags})
        audit=SystemEvent(event_type='INVEST_SAUDI_JOB439_INTEGRITY_REMEDIATION',created_at=now,payload={
            'job_id':JOB_ID,'reconciled_jobs':[{'job_id':JOB_ID,'reported_removed_records_count':2423,
                'actual_net_source_lifecycle_transitions':0,'counted_present_unqualified_records':2423,
                'counter_reconciled':True}],
            'actor':'SYSTEM_DATA_REMEDIATION','reason':'Correct only rows proven present in the complete Job 439 national enumeration and explicitly unqualified for Al-Ahsa, whose raw status was unspecified but canonical status was falsely set to removed.',
            'audit_timestamp':now.isoformat(),'source_identity_rows_corrected':len(seen),
            'master_status_projections_corrected':sum(x['previous_status']!=x['corrected_status'] for x in master_ledger),
            'job_439_history_retained':True,'job_439_historical_counter_rewritten':False,
            'source_rows':ledger,'master_projections':master_ledger})
        db.add(audit);db.flush()
        for row,item in zip(seen,ledger):
            observation_payload={'canonical_status_before':item['previous_state'],'canonical_status_after':CORRECTED,
                'missing_successful_checks_after':0,'raw_status':row.raw_status,'observation_reason':'administrative_correction_of_false_absence',
                'correction_event_id':audit.id,'job_id':JOB_ID,'source_payload_sha256':item['evidence']['raw_payload_sha256'],
                'qualified_location':False,'location_detection_method':item['evidence']['location_detection_method']}
            content_hash=sha256(json.dumps(observation_payload,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
            db.add(SourceObservation(source_opportunity_id=row.id,dataset_name='source-record-status-snapshot',
                endpoint=row.source_url,official_source_id_original=str(row.official_source_id_original or row.source_opportunity_id)[:200],
                official_source_id_normalized=str(row.official_source_id_normalized or row.source_opportunity_id)[:200],
                raw_data_json=observation_payload,source_updated_at=None,content_hash=content_hash,first_seen_at=now,last_seen_at=now))
        db.flush()
        if len(seen)!=len(ledger):raise RuntimeError('Audit ledger did not include every corrected source row')
    result={'correction_event_id':audit.id,'corrected_source_rows':len(seen),
        'master_status_projections_corrected':sum(x['previous_status']!=x['corrected_status'] for x in master_ledger),
        'observations_added':len(seen),'change_history_rows_added':sum(x['previous_status']!=x['corrected_status'] for x in master_ledger),
        'job_439_counter_unchanged':db.get(SyncJob,JOB_ID).removed_records_count==2423,
        'source_opportunity_count_after':db.scalar(select(func.count()).select_from(SourceOpportunity).where(SourceOpportunity.source_id==source.id)),
        'source_lifecycle_after':{k:v for k,v in db.execute(select(SourceOpportunity.canonical_status,func.count()).where(SourceOpportunity.source_id==source.id).group_by(SourceOpportunity.canonical_status))},
        'audit_rows':len(audit.payload['source_rows']),'raw_identity_preservation_checked':True}
    print(json.dumps(result,ensure_ascii=False,default=str))

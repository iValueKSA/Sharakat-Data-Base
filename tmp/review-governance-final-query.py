import json
from datetime import datetime, timezone
from collections import Counter
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import (Opportunity, SourceOpportunity, SourceObservation, DuplicateCandidate, LocationReview,
    QualificationReview, OpportunityConflict, Source, SyncJob, MergeAudit, AuditEvent, SourceOpportunityDatasetMembership)
now=datetime.now(timezone.utc)
def iso(x): return x.isoformat() if x else None
def age(x):
 if not x:return None
 if x.tzinfo is None:x=x.replace(tzinfo=timezone.utc)
 return max(0,(now-x).days)
s=SessionLocal()
try:
 allm=s.scalars(select(Opportunity).order_by(Opportunity.id)).all(); masters={m.id:m for m in allm}
 srcs={x.id:x for x in s.scalars(select(Source)).all()}
 records={x.id:x for x in s.scalars(select(SourceOpportunity)).all()}
 def obs_count(rid): return s.scalar(select(func.count(SourceObservation.id)).where(SourceObservation.source_opportunity_id==rid)) or 0
 dup=s.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status=='PENDING').order_by(DuplicateCandidate.id)).all()
 loc=s.scalars(select(LocationReview).where(LocationReview.status=='PENDING').order_by(LocationReview.id)).all()
 qual=s.scalars(select(QualificationReview).where(QualificationReview.status=='PENDING').order_by(QualificationReview.id)).all()
 conf=s.scalars(select(OpportunityConflict).where(OpportunityConflict.status=='OPEN').order_by(OpportunityConflict.id)).all()
 items=[]
 for x in dup:
  ids=[x.left_opportunity_id,x.right_opportunity_id]; mr=[masters.get(i) for i in ids]; recids=[r.id for m in mr if m for r in m.source_records]
  items.append({'queue':'duplicate','review_id':x.id,'reason_key':'DUPLICATE_IDENTITY_AMBIGUITY','master_ids':ids,'master_states':[{'id':m.id,'merged_into_id':m.merged_into_id,'status':m.status} if m else {'id':i,'missing':True} for i,m in zip(ids,mr)],'source_record_ids':recids,'observation_count':sum(obs_count(rid) for rid in recids),'created_at':iso(x.created_at),'age_days':age(x.created_at),'evidence':x.explanation_json or {}})
 for x in loc:
  r=records.get(x.source_record_id);m=masters.get(r.master_opportunity_id) if r and r.master_opportunity_id else None
  items.append({'queue':'location','review_id':x.id,'reason_key':'LOCATION_EVIDENCE_AMBIGUITY','master_ids':[m.id] if m else [],'master_states':[{'id':m.id,'merged_into_id':m.merged_into_id,'status':m.status}] if m else [],'source_id':x.source_id,'source_key':srcs[x.source_id].source_key if x.source_id in srcs else None,'source_record_id':x.source_record_id,'source_url':r.source_url if r else None,'observation_count':obs_count(r.id) if r else 0,'created_at':iso(x.created_at),'age_days':age(x.created_at),'reason':x.reason,'evidence':x.evidence})
 for x in qual:
  r=records.get(x.source_record_id) if x.source_record_id else None;m=masters.get(r.master_opportunity_id) if r and r.master_opportunity_id else None
  items.append({'queue':'qualification','review_id':x.id,'reason_key':'INVESTMENT_ELIGIBILITY_AMBIGUITY','master_ids':[m.id] if m else [],'master_states':[{'id':m.id,'merged_into_id':m.merged_into_id,'status':m.status}] if m else [],'source_id':x.source_id,'source_record_id':x.source_record_id,'source_url':r.source_url if r else x.source_url,'observation_count':obs_count(r.id) if r else 0,'created_at':iso(x.created_at),'age_days':age(x.created_at),'reason':x.reason})
 for x in conf:
  m=masters.get(x.opportunity_id);r=records.get(x.source_record_id);src=srcs.get(x.source_id)
  key={'contract_duration_years':'DURATION_UNIT_OR_SEMANTICS_UNVERIFIED','investment_value':'INVESTMENT_VALUE_ZERO_WITHOUT_UNIT_OR_MEANING'}.get(x.field_name,'STANDARDIZATION_EVIDENCE_REVIEW') if x.conflict_type=='STANDARDIZATION_REVIEW' else 'FIELD_CONFLICT:'+x.field_name
  items.append({'queue':'conflict','review_id':x.id,'reason_key':key,'conflict_type':x.conflict_type,'field':x.field_name,'master_ids':[x.opportunity_id],'master_states':[{'id':m.id,'merged_into_id':m.merged_into_id,'status':m.status}] if m else [{'id':x.opportunity_id,'missing':True}], 'source_id':x.source_id,'source_key':src.source_key if src else None,'source_record_id':x.source_record_id,'source_url':r.source_url if r else None,'observation_count':obs_count(r.id) if r else 0,'created_at':iso(x.detected_at),'age_days':age(x.detected_at),'selected_value':x.selected_value,'source_value':x.conflicting_value})
 open_by_queue=dict(Counter(x['queue'] for x in items))
 by_reason=dict(Counter(x['reason_key'] for x in items))
 pairgroups=Counter(tuple(sorted([x.left_opportunity_id,x.right_opportunity_id])) for x in dup)
 conflictgroups=Counter((x.opportunity_id,x.field_name,x.selected_value,x.conflicting_value,x.source_id,x.source_record_id) for x in conf)
 locations_key=Counter((x.source_id,x.external_id) for x in loc)
 qualifications_key=Counter((x.source_id,x.external_id) for x in qual)
 broken=[]; merged_open=[]; evidence_missing=[]
 for item in items:
  if item['queue']=='duplicate':
   if any(sid not in masters for sid in item['master_ids']):broken.append(item['review_id'])
   if any(masters[sid].merged_into_id is not None for sid in item['master_ids'] if sid in masters):merged_open.append(item['review_id'])
  else:
   if any(sid not in masters for sid in item['master_ids']):broken.append(item['review_id'])
   if any(masters[sid].merged_into_id is not None for sid in item['master_ids'] if sid in masters):merged_open.append(item['review_id'])
  if not item['observation_count']: evidence_missing.append({'queue':item['queue'],'review_id':item['review_id']})
 status_counts={}
 for label,model in [('duplicate',DuplicateCandidate),('location',LocationReview),('qualification',QualificationReview),('conflict',OpportunityConflict)]:
  status_counts[label]={str(status):count for status,count in s.execute(select(model.status,func.count(model.id)).group_by(model.status)).all()}
 memberships=s.scalars(select(SourceOpportunityDatasetMembership).where(SourceOpportunityDatasetMembership.is_current.is_(True),SourceOpportunityDatasetMembership.missing_successful_checks>0).order_by(SourceOpportunityDatasetMembership.id)).all()
 jobs=s.scalars(select(SyncJob).order_by(SyncJob.id.desc()).limit(10)).all()
 job_rows=[{'id':j.id,'source_key':srcs[j.source_id].source_key if j.source_id in srcs else None,'started_at':iso(j.started_at),'finished_at':iso(j.finished_at),'status':j.status,'trigger_type':j.trigger_type,'new_count':j.new_count,'update_count':j.update_count,'unchanged_count':j.unchanged_count,'records_received':j.records_received,'records_parsed':j.records_parsed,'metrics':j.metrics_json or {}} for j in jobs]
 result={'snapshot_at':iso(now),'masters':{'total_rows':len(allm),'current_nonmerged':sum(m.merged_into_id is None for m in allm),'merged':sum(m.merged_into_id is not None for m in allm)},'source_opportunities':len(records),'observations':s.scalar(select(func.count(SourceObservation.id))),'open_reviews_total':len(items),'open_by_queue':open_by_queue,'open_by_reason_key':by_reason,'items':items,'status_counts':status_counts,'duplicate_logical_pairs':[{ 'pair':list(pair),'count':count} for pair,count in pairgroups.items()],'duplicate_logical_case_duplicates':sum(count-1 for count in pairgroups.values() if count>1),'conflict_logical_case_duplicates':sum(count-1 for count in conflictgroups.values() if count>1),'location_logical_case_duplicates':sum(count-1 for count in locations_key.values() if count>1),'qualification_logical_case_duplicates':sum(count-1 for count in qualifications_key.values() if count>1),'broken_open_review_ids':broken,'open_on_merged_review_ids':merged_open,'open_without_observation':evidence_missing,'source_coverage_candidates':[{'source_record_id':m.source_opportunity_id,'missing_successful_checks':m.missing_successful_checks,'dataset_name':m.dataset_name,'endpoint':m.endpoint} for m in memberships],'recent_sync_jobs':job_rows,'merge_audit_count':s.scalar(select(func.count(MergeAudit.id))),'audit_event_count':s.scalar(select(func.count(AuditEvent.id)))}
 print(json.dumps(result,ensure_ascii=False,default=str))
finally:s.close()


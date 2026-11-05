from datetime import timezone
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.database import engine
from app.models import Source,SourceOpportunity,SourceOpportunityDatasetMembership,SourceObservation,SyncJob,Opportunity,LocationReview,QualificationReview,OpportunityConflict,SystemEvent,ChangeHistory
import json
with engine.connect() as conn:
 conn.exec_driver_sql('SET TRANSACTION READ ONLY')
 with Session(bind=conn,autoflush=False,expire_on_commit=False) as db:
  s=db.scalar(select(Source).where(Source.source_key=='invest-saudi')); j=db.get(SyncJob,439); start=j.started_at;end=j.finished_at
  rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==s.id)).all()
  life={status:count for status,count in db.execute(select(SourceOpportunity.canonical_status,func.count()).where(SourceOpportunity.source_id==s.id).group_by(SourceOpportunity.canonical_status))}
  linked={"linked_to_current_master":0,"linked_to_merged_master":0,"unlinked":0}; target=[];masters=[]
  for r in rows:
   if r.master_opportunity_id is None:linked['unlinked']+=1
   else:
    m=db.get(Opportunity,r.master_opportunity_id)
    linked['linked_to_merged_master' if m and m.merged_into_id is not None else 'linked_to_current_master']+=1
  for r in rows:
   if not (start<=r.last_seen_at<=end):continue
   raw=r.raw_data_json if isinstance(r.raw_data_json,dict) else {}
   if raw.get('qualified_location') is not False:continue
   target.append(r)
   if r.master_opportunity_id:
    m=db.get(Opportunity,r.master_opportunity_id)
    if m:
     linked_rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==m.id)).all()
     masters.append({'source_record_id':r.id,'external_id':r.source_opportunity_id,'master_id':m.id,'canonical_id':m.canonical_id,'master_status':m.status,'merged_into_id':m.merged_into_id,'linked_source_ids':[x.id for x in linked_rows],'linked_statuses':[x.canonical_status for x in linked_rows]})
 reviews={}
 for model,name,state in ((LocationReview,'location','PENDING'),(QualificationReview,'qualification','PENDING'),(OpportunityConflict,'conflict','OPEN')):
  reviews[name]=db.scalar(select(func.count()).select_from(model).where(model.status==state))
 created={}
 for model,name in ((LocationReview,'location'),(QualificationReview,'qualification')):
  created[name]=db.scalar(select(func.count()).select_from(model).where(model.source_id==s.id,model.created_at>=start,model.created_at<=end))
  events=db.scalars(select(SystemEvent).where(SystemEvent.created_at>=start,SystemEvent.created_at<=end).order_by(SystemEvent.id)).all()
  job439_obs=db.scalar(select(func.count()).select_from(SourceObservation).join(SourceOpportunity).where(SourceOpportunity.source_id==s.id,SourceObservation.first_seen_at>=start,SourceObservation.first_seen_at<=end))
  changes={field:db.scalar(select(func.count()).select_from(ChangeHistory).where(ChangeHistory.source_id==s.id,ChangeHistory.detected_at>=start,ChangeHistory.detected_at<=end,ChangeHistory.changed_field==field)) for field in ('status','source_status')}
  result={'snapshot':{'masters_total':db.scalar(select(func.count()).select_from(Opportunity)),'masters_current':db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_(None))),'masters_merged':db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_not(None))),'source_opportunities_total':db.scalar(select(func.count()).select_from(SourceOpportunity)),'invest_saudi_source_opportunities':len(rows),'invest_saudi_lifecycle':life,'invest_saudi_linkage':linked,'observations_total':db.scalar(select(func.count()).select_from(SourceObservation)),'reviews_open':reviews,'sync_jobs_total':db.scalar(select(func.count()).select_from(SyncJob)),'source_health':{'technical':s.technical_health,'coverage':s.coverage_status,'freshness':s.sync_status,'last_successful_sync':str(s.last_successful_sync)}},'job439':{'observations_added_window':job439_obs,'review_creations':created,'review_related_system_events':[{'type':e.event_type,'payload':e.payload} for e in events if 'REVIEW' in e.event_type],'master_status_changes':changes['status'],'master_source_status_changes':changes['source_status'],'events':[e.event_type for e in events]},'target':{'count':len(target),'lifecycle':{x:sum(r.canonical_status==x for r in target) for x in set(r.canonical_status for r in target)},'missing_checks':{str(x):sum(r.missing_successful_checks==x for r in target) for x in set(r.missing_successful_checks for r in target)},'raw_status_nonnull':sum(r.raw_status is not None for r in target),'linked_count':sum(r.master_opportunity_id is not None for r in target),'linked_master_details':masters},'source_status_snapshot_observations_missing':sum(1 for r in rows if r.canonical_status=='أزيلت من المصدر' and not db.scalar(select(SourceObservation.id).where(SourceObservation.source_opportunity_id==r.id,SourceObservation.dataset_name=='source-record-status-snapshot').limit(1)))}
  print(json.dumps(result,ensure_ascii=False,default=str))

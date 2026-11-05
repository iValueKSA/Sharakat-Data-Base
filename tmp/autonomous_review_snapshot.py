import json
from collections import Counter
from datetime import datetime, timezone
from app.database import SessionLocal
from app.main import review_queue
from app.models import (Opportunity, SourceOpportunity, SourceObservation, MergeAudit, DuplicateCandidate, LocationReview, QualificationReview, OpportunityConflict, Source, FieldProvenance, SyncJob, AuditEvent)
from sqlalchemy import select, func

s=SessionLocal()
items=review_queue(None,'all','OPEN',1000,disposition='ALL')
raw_keys=('title','description','project_location','location','city','region','governorate','owner','publisher','platform','source_scope','source_taxonomy','sector','activity','sub_activity','opportunity_type','investment_model','asset_type','facility_type','investmentSize','area','areaUnit','currency','contractDuration','submission_deadline','status','lifecycle_status','official_id','id','project_id','reference_number')
def source_item(record):
    if not record:return None
    source=s.get(Source,record.source_id); raw=record.raw_data_json if isinstance(record.raw_data_json,dict) else {}; std=record.standardized_data_json if isinstance(record.standardized_data_json,dict) else {}
    return {'id':record.id,'source_id':record.source_id,'source_key':source.source_key if source else None,'source_name':source.source_name_ar if source else None,'source_priority':source.priority if source else None,'master_id':record.master_opportunity_id,'source_opportunity_id':record.source_opportunity_id,'official_source_id_original':record.official_source_id_original,'official_source_id_normalized':record.official_source_id_normalized,'source_title':record.source_title,'source_owner':record.source_owner,'raw_location':record.raw_location,'raw_status':record.raw_status,'source_reference_number':record.source_reference_number,'source_url':record.source_url,'content_hash':record.content_hash,'last_seen_at':record.last_seen_at.isoformat() if record.last_seen_at else None,'raw_selected':{k:raw.get(k) for k in raw_keys if k in raw},'standardized_fields':std.get('fields',{}),'observation_count':s.scalar(select(func.count(SourceObservation.id)).where(SourceObservation.source_opportunity_id==record.id)) or 0}
def mastersource(m):
    return {'id':m.id,'title_ar':m.title_ar,'owner':m.opportunity_owner,'sector':m.sector,'activity':m.activity,'sub_activity':m.sub_activity,'opportunity_type':m.opportunity_type,'investment_model':m.investment_model,'status':m.status,'city':m.city,'location_description':m.location_description,'latitude':m.latitude,'longitude':m.longitude,'land_area_sqm':m.land_area_sqm,'investment_value':m.investment_value,'currency':m.currency,'contract_duration_years':m.contract_duration_years,'submission_deadline':m.submission_deadline,'merged_into_id':m.merged_into_id,'updated_at':m.updated_at.isoformat() if m.updated_at else None}
full=[]
for item in items:
    d={**item}
    domain=item['domain']; rid=int(item['id'])
    if domain in ('field_conflict','taxonomy_conflict'):
        r=s.get(OpportunityConflict,rid); m=s.get(Opportunity,r.opportunity_id) if r else None; rec=s.get(SourceOpportunity,r.source_record_id) if r and r.source_record_id else None
        d['record']={'status':r.status,'field_name':r.field_name,'conflict_type':r.conflict_type,'selected_value':r.selected_value,'conflicting_value':r.conflicting_value,'master':mastersource(m) if m else None,'source':source_item(rec),'source_provenance':[{'selected_value':p.selected_value,'source_id':p.source_id,'source_record_id':p.source_record_id,'captured_at':p.captured_at.isoformat() if p.captured_at else None,'confidence':p.confidence,'source_priority':s.get(Source,p.source_id).priority if s.get(Source,p.source_id) else None} for p in s.scalars(select(FieldProvenance).where(FieldProvenance.opportunity_id==r.opportunity_id,FieldProvenance.field_name==r.field_name).order_by(FieldProvenance.captured_at.desc()).limit(20)).all()] if r else []}
    elif domain=='duplicate':
        r=s.get(DuplicateCandidate,rid); ms=[]; recs=[]
        if r:
            for mid in (r.left_opportunity_id,r.right_opportunity_id):
                m=s.get(Opportunity,mid); ms.append(mastersource(m) if m else {'id':mid,'missing':True})
                for rec in s.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==mid).order_by(SourceOpportunity.id)).all(): recs.append(source_item(rec))
        d['record']={'status':r.status,'confidence_score':r.confidence_score,'explanation':r.explanation_json,'masters':ms,'source_records':recs} if r else None
    elif domain=='location':
        r=s.get(LocationReview,rid); rec=s.get(SourceOpportunity,r.source_record_id) if r and r.source_record_id else None
        d['record']={'status':r.status,'source_id':r.source_id,'external_id':r.external_id,'source_record_id':r.source_record_id,'sector':r.sector,'source_location':r.source_location,'description':r.description,'latitude':r.latitude,'longitude':r.longitude,'evidence':r.evidence,'reason':r.reason,'confidence_score':r.confidence_score,'source':source_item(rec)} if r else None
    full.append(d)
source_names=Counter()
for x in full:
    if x.get('source'): source_names[x['source']]+=1
    elif x['domain']=='duplicate':
        for sr in (x.get('record') or {}).get('source_records',[]):
            if sr and sr.get('source_name'):source_names[sr['source_name']]+=1
summary={'captured_at':datetime.now(timezone.utc).isoformat(),'open_reviews_total':len(items),'human_review_required':sum(x['disposition']!='SOURCE_RECHECK_REQUIRED' for x in items),'source_recheck_required':sum(x['disposition']=='SOURCE_RECHECK_REQUIRED' for x in items),'open_by_type':dict(Counter(x['domain'] for x in items)),'open_by_subtype':dict(Counter(x.get('field') or x.get('reason_key') or 'UNSPECIFIED' for x in items)),'open_by_priority':dict(Counter(x['priority'] for x in items)),'open_by_source':dict(source_names),'current_masters':s.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))),'source_opportunities':s.scalar(select(func.count(SourceOpportunity.id))),'observations':s.scalar(select(func.count(SourceObservation.id))),'merged_masters':s.scalar(select(func.count(MergeAudit.id)).where(MergeAudit.undone_at.is_(None))),'sync_jobs_total':s.scalar(select(func.count(SyncJob.id))),'sync_jobs_max_id':s.scalar(select(func.max(SyncJob.id))),'active_sync_jobs':s.scalar(select(func.count(SyncJob.id)).where(SyncJob.job_state.in_(['QUEUED','RUNNING','RETRYING']))),'audit_events':s.scalar(select(func.count(AuditEvent.id)))}
with open('/tmp/autonomous-review-pre-snapshot.json','w',encoding='utf-8') as f:json.dump({'summary':summary,'reviews':full},f,ensure_ascii=False,indent=2,default=str)
print(json.dumps(summary,ensure_ascii=False))
s.close()

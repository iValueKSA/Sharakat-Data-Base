import sys,json
sys.path.insert(0,'/app')
from sqlalchemy import select,func,text
from app.database import engine,SessionLocal
from app.models import Source,SourceOpportunity,SourceObservation,Opportunity,SourceOpportunityDatasetMembership,LocationReview,QualificationReview,SyncJob
with engine.connect() as conn:
 conn.execute(text('SET TRANSACTION READ ONLY'))
 with SessionLocal(bind=conn) as db:
  sources=db.scalars(select(Source).order_by(Source.priority)).all()
  out={'masters':{'total':db.scalar(select(func.count(Opportunity.id))),'current':db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))),'merged':db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_not(None)))},'sources':{},'observations':db.scalar(select(func.count(SourceObservation.id))),'jobs':db.scalar(select(func.count(SyncJob.id)))}
  for s in sources:
   rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==s.id).order_by(SourceOpportunity.id)).all()
   item={'source_id':s.id,'name':s.source_name_ar,'key':s.source_key,'enabled':s.enabled,'interval':s.polling_frequency_minutes,'technical_health':s.technical_health,'coverage':s.coverage_status,'sync_status':s.sync_status,'last_success':s.last_successful_sync.isoformat() if s.last_successful_sync else None,'last_attempt':s.last_attempted_sync.isoformat() if s.last_attempted_sync else None,'retained_count':len(rows),'records':[]}
   for r in rows:
    item['records'].append({'id':r.id,'external_id':r.source_opportunity_id,'official_id':r.official_source_id_normalized,'master_id':r.master_opportunity_id,'status':r.canonical_status,'missing_checks':r.missing_successful_checks,'raw_family':(r.raw_data_json or {}).get('source_record_family'),'qualified_location':(r.raw_data_json or {}).get('qualified_location'),'location_method':(r.raw_data_json or {}).get('location_detection_method'),'dataset_name':(r.raw_data_json or {}).get('dataset_name'),'raw_current':(r.raw_data_json or {}).get('is_current')})
   out['sources'][s.source_key]=item
  out['reviews']={'location_pending':db.scalar(select(func.count(LocationReview.id)).where(LocationReview.status=='PENDING')),'qualification_pending':db.scalar(select(func.count(QualificationReview.id)).where(QualificationReview.status=='PENDING'))}
  print(json.dumps(out,ensure_ascii=False,separators=(',',':'),default=str))

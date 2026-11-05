import json
from app.database import SessionLocal
from app.models import SourceOpportunity,SourceObservation,SyncJob,Source
from sqlalchemy import select
with SessionLocal() as db:
 s=db.scalar(select(SourceOpportunity).where(SourceOpportunity.id==2926))
 obs=db.scalars(select(SourceObservation).where(SourceObservation.source_opportunity_id==2926).order_by(SourceObservation.id)).all()
 jobs=db.execute(select(SyncJob,Source.source_key).join(Source,Source.id==SyncJob.source_id).where(SyncJob.id>=349).order_by(SyncJob.id)).all()
 print(json.dumps({"target":{"id":s.id,"master_id":s.master_opportunity_id,"source_key":s.source.source_key,"external_id":s.source_opportunity_id,"reference":s.source_reference_number,"url":s.source_url,"first_seen_at":str(s.first_seen_at),"last_seen_at":str(s.last_seen_at),"canonical_status":s.canonical_status,"raw_status":s.raw_status,"missing_successful_checks":s.missing_successful_checks,"last_missing_at":str(s.last_missing_at),"raw_url_fields":{k:v for k,v in (s.raw_data_json or {}).items() if "url" in k.casefold() or "link" in k.casefold()},"observations":[{"id":o.id,"dataset":o.dataset_name,"endpoint":o.endpoint,"first_seen_at":str(o.first_seen_at),"last_seen_at":str(o.last_seen_at),"payload_has_url":any("url" in str(k).casefold() or "link" in str(k).casefold() for k in (o.raw_data_json or {}).keys())} for o in obs]},"scheduled_jobs":[{"id":j.id,"source_key":key,"trigger_type":j.trigger_type,"job_state":j.job_state,"status":j.status,"started_at":str(j.started_at),"finished_at":str(j.finished_at),"new_count":j.new_count,"update_count":j.update_count,"unchanged_count":j.unchanged_count,"raw_count":j.raw_count,"records_received":j.records_received,"source_total_reported":j.source_total_reported} for j,key in jobs]},ensure_ascii=False))

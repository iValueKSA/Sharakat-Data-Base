import json
from app.database import SessionLocal
from app.models import SyncJob, SourceObservation, Source
from sqlalchemy import select, func
with SessionLocal() as db:
 jobs=db.execute(select(SyncJob,Source.source_key).join(Source,Source.id==SyncJob.source_id).order_by(SyncJob.id.desc()).limit(15)).all()
 out=[]
 for j,k in jobs:
  out.append({"id":j.id,"source_key":k,"trigger_type":j.trigger_type,"status":j.status,"job_state":j.job_state,"started_at":str(j.started_at),"finished_at":str(j.finished_at),"raw_count":j.raw_count,"new_count":j.new_count,"update_count":j.update_count,"unchanged_count":j.unchanged_count,"records_received":j.records_received,"unique_records":j.unique_records,"observation_delta":(j.metrics_json or {}).get("observations_created")})
 obs=db.execute(select(SourceObservation.id,SourceObservation.source_opportunity_id,SourceObservation.dataset_name,SourceObservation.first_seen_at).order_by(SourceObservation.id.desc()).limit(20)).all()
 print(json.dumps({"recent_jobs":out,"recent_observations":[{"id":x[0],"source_id":x[1],"dataset":x[2],"first_seen_at":str(x[3])} for x in obs]},ensure_ascii=False))

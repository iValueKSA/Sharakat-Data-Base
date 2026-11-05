import json
from sqlalchemy import event,select
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import SyncJob,Source
@event.listens_for(Session,"after_begin")
def ro(session,transaction,connection):
 if connection.dialect.name=="postgresql": connection.exec_driver_sql("SET TRANSACTION READ ONLY")
with SessionLocal() as db:
 rows=db.execute(select(SyncJob.id,Source.source_key,SyncJob.status,SyncJob.trigger_type,SyncJob.started_at,SyncJob.finished_at,SyncJob.new_count,SyncJob.update_count,SyncJob.removed_records_count).join(Source,Source.id==SyncJob.source_id).where(SyncJob.id>=433).order_by(SyncJob.id)).all()
 print(json.dumps([{"job_id":r.id,"source":r.source_key,"status":r.status,"trigger_type":r.trigger_type,"started_at":str(r.started_at),"finished_at":str(r.finished_at),"master_new_delta":r.new_count,"master_update_delta":r.update_count,"source_removed_records_reported":r.removed_records_count,"source_net_delta":"NOT_CAPTURED_AT_EXECUTION","observation_delta":"NOT_CAPTURED_AT_EXECUTION","review_delta":"NOT_CAPTURED_AT_EXECUTION"} for r in rows],ensure_ascii=False))

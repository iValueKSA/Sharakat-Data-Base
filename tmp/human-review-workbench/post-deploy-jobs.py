import json
from sqlalchemy import event,select
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import SyncJob,Source
@event.listens_for(Session,"after_begin")
def ro(session,transaction,connection):
 if connection.dialect.name=="postgresql": connection.exec_driver_sql("SET TRANSACTION READ ONLY")
with SessionLocal() as db:
 rows=db.execute(select(SyncJob,Source.source_key).join(Source,Source.id==SyncJob.source_id).where(SyncJob.id>=435).order_by(SyncJob.id)).all()
 out=[]
 for j,key in rows: out.append({"job_id":j.id,"source":key,"status":j.status,"trigger_type":j.trigger_type,"started_at":str(j.started_at),"finished_at":str(j.finished_at),"master_new_delta":j.new_count,"master_update_delta":j.update_count,"source_removed_delta":j.removed_records_count,"observations_delta":None,"reviews_delta":None,"metrics":j.metrics_json or {}})
 print(json.dumps(out,ensure_ascii=False,default=str))

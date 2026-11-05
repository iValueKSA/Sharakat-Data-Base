import json
from sqlalchemy import select,func,text
from app.database import SessionLocal
from app.models import OpportunityConflict,SyncJob
s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY'))
q=s.execute(select(OpportunityConflict.field_name,OpportunityConflict.status,func.count()).group_by(OpportunityConflict.field_name,OpportunityConflict.status)).all()
j=s.execute(select(SyncJob.id,SyncJob.status,SyncJob.job_state,SyncJob.trigger_type,SyncJob.source_id).where(SyncJob.job_state.notin_(['COMPLETED','COMPLETED_WITH_WARNINGS','FAILED','CANCELLED'])).order_by(SyncJob.id)).all()
print(json.dumps({'conflicts':q,'active_jobs':j},ensure_ascii=False,default=str))
s.close()

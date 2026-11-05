from sqlalchemy import func,select,text
from app.database import SessionLocal
from app.models import *
with SessionLocal() as d:
 print('sources',d.execute(select(Source.id,Source.source_key,Source.source_name_ar).order_by(Source.id)).all())
 for model in [DuplicateCandidate,LocationReview,QualificationReview,OpportunityConflict]:
  datecol=getattr(model,'created_at',getattr(model,'detected_at',None))
  print(model.__tablename__,d.execute(select(model.id,model.status,datecol).where(model.status.in_(['OPEN','PENDING']))).all())
 print('jobs',d.execute(select(SyncJob.id,SyncJob.source_id,SyncJob.status,SyncJob.job_state,SyncJob.started_at,SyncJob.finished_at,SyncJob.heartbeat_at,SyncJob.celery_task_id,SyncJob.error_message).where(SyncJob.id.in_([692,694,745,746,747])).order_by(SyncJob.id)).all())

from sqlalchemy import func,select,text
from app.database import SessionLocal
from app.models import *
with SessionLocal() as d:
 print('counts', { 'TOTAL_MASTERS':d.scalar(select(func.count()).select_from(Opportunity)), 'CURRENT_MASTERS':d.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_(None))), 'SOURCEOPPORTUNITIES':d.scalar(select(func.count()).select_from(SourceOpportunity)), 'JOBS':d.scalar(select(func.count()).select_from(SyncJob)), 'ACTIVE_JOBS':d.scalar(select(func.count()).select_from(SyncJob).where(SyncJob.job_state.in_(['QUEUED','RUNNING']))), 'ALEMBIC_HEAD':d.scalar(text('select version_num from alembic_version'))})
 print('rcjy',d.execute(select(Source.id,func.count(SourceOpportunity.id),func.count(func.distinct(SourceOpportunity.master_opportunity_id))).outerjoin(SourceOpportunity,SourceOpportunity.source_id==Source.id).where(Source.source_key=='rcjy').group_by(Source.id)).all())
 print('furas_rows',d.scalar(select(func.count()).select_from(SourceOpportunity).join(Source,Source.id==SourceOpportunity.source_id).where(Source.source_key=='furas')))
 for model in [DuplicateCandidate,LocationReview,QualificationReview,OpportunityConflict]: print(model.__tablename__,d.execute(select(model.id,model.status,model.created_at).where(model.status.in_(['OPEN','PENDING']))).all())
 print('jobs',d.execute(select(SyncJob.id,SyncJob.source_id,SyncJob.status,SyncJob.job_state,SyncJob.started_at,SyncJob.finished_at,SyncJob.heartbeat_at,SyncJob.celery_task_id,SyncJob.error_message).where(SyncJob.id.in_([692,694,745,746,747])).order_by(SyncJob.id)).all())

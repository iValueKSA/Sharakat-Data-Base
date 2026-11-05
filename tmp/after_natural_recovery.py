from sqlalchemy import select,func
from app.database import SessionLocal
from app.models import *
from app.tasks import flag_enabled
with SessionLocal() as d:
 print('feature_flag_furas_national=',flag_enabled('FURAS_NATIONAL_ENUMERATION_ENABLED'))
 print('job_state_745_750=',d.execute(select(SyncJob.id,SyncJob.source_id,SyncJob.status,SyncJob.job_state,SyncJob.started_at,SyncJob.finished_at,SyncJob.heartbeat_at,SyncJob.celery_task_id,SyncJob.error_message).where(SyncJob.id.between(745,750)).order_by(SyncJob.id)).all())
 rcjy=d.scalar(select(Source.id).where(Source.source_key=='rcjy-investment-opportunities'))
 print('rcjy_counts=',d.execute(select(func.count(SourceOpportunity.id),func.count(func.distinct(SourceOpportunity.master_opportunity_id))).where(SourceOpportunity.source_id==rcjy)).one())
 print('rcjy_records=',d.execute(select(SourceOpportunity.id,SourceOpportunity.source_opportunity_id,SourceOpportunity.master_opportunity_id,SourceOpportunity.content_hash).where(SourceOpportunity.source_id==rcjy).order_by(SourceOpportunity.id)).all())
 print('counts=',d.execute(select(func.count()).select_from(Opportunity)).scalar_one(),d.execute(select(func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_(None))).scalar_one(),d.execute(select(func.count()).select_from(SourceOpportunity)).scalar_one(),d.execute(select(func.count()).select_from(SyncJob)).scalar_one(),d.execute(select(func.count()).select_from(SyncJob).where(SyncJob.job_state.in_(['QUEUED','RUNNING','RETRYING']))).scalar_one())

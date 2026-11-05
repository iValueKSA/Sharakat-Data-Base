import json
from sqlalchemy import func, select, text
from app.database import SessionLocal, engine
from app.models import Opportunity, SourceOpportunity, Source, SyncJob, DuplicateCandidate, LocationReview, QualificationReview, OpportunityConflict
from app.data_quality import evaluate_data_quality
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
out={}
with SessionLocal() as db:
    out['counts']={
      'TOTAL_MASTERS':db.scalar(select(func.count()).select_from(Opportunity)) or 0,
      'CURRENT_MASTERS':db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_(None))) or 0,
      'SOURCEOPPORTUNITIES':db.scalar(select(func.count()).select_from(SourceOpportunity)) or 0,
      'FURAS_ROWS':db.scalar(select(func.count()).select_from(SourceOpportunity).join(Source,Source.id==SourceOpportunity.source_id).where(Source.source_key=='furas')) or 0,
      'REVIEWS':sum(db.scalar(select(func.count()).select_from(m).where(m.status.in_(['OPEN','PENDING']))) or 0 for m in [DuplicateCandidate,LocationReview,QualificationReview,OpportunityConflict]),
      'JOBS':db.scalar(select(func.count()).select_from(SyncJob)) or 0,
      'ACTIVE_JOBS':db.scalar(select(func.count()).select_from(SyncJob).where(SyncJob.job_state.in_(['QUEUED','RUNNING']))) or 0,
    }
    rcjy=db.scalar(select(Source.id).where(Source.source_key=='rcjy'))
    out['counts']['RCJY_SOURCE_ROWS']=db.scalar(select(func.count()).select_from(SourceOpportunity).where(SourceOpportunity.source_id==rcjy)) if rcjy else 0
    out['counts']['RCJY_MASTERS']=db.scalar(select(func.count(func.distinct(SourceOpportunity.master_opportunity_id))).where(SourceOpportunity.source_id==rcjy,SourceOpportunity.master_opportunity_id.is_not(None))) if rcjy else 0
    out['sources']=[{'id':s.id,'key':s.source_key,'enabled':s.enabled} for s in db.scalars(select(Source).order_by(Source.id)).all()]
    out['jobs_recent']=[{'id':j.id,'source_id':j.source_id,'status':j.status,'job_state':j.job_state,'started_at':str(j.started_at),'finished_at':str(j.finished_at),'heartbeat_at':str(j.heartbeat_at),'task_id':j.celery_task_id,'error':j.error_message} for j in db.scalars(select(SyncJob).order_by(SyncJob.id.desc()).limit(15)).all()]
    out['alembic_head']=db.scalar(text('select version_num from alembic_version'))
    out['dq']=evaluate_data_quality(db,scope='full',trigger='baseline_readonly_20261103',persist=False)
print(json.dumps(out,default=str,ensure_ascii=False))

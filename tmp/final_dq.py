import json
from sqlalchemy import func,select,text
from app.database import SessionLocal
from app.models import Opportunity,SourceOpportunity,Source,SyncJob,DuplicateCandidate,LocationReview,QualificationReview,OpportunityConflict
from app.data_quality import evaluate_data_quality
from app.geography_flags import flag_enabled
with SessionLocal() as db:
 result=evaluate_data_quality(db,scope='full',trigger='final_readonly_20261103',persist=False)
 rcjy_id=db.scalar(select(Source.id).where(Source.source_key=='rcjy-investment-opportunities'))
 rcjy=db.execute(select(SourceOpportunity.id,SourceOpportunity.source_opportunity_id,SourceOpportunity.master_opportunity_id).where(SourceOpportunity.source_id==rcjy_id).order_by(SourceOpportunity.id)).all()
 out={'run_id':result['run_id'],'started_at':result['started_at'],'completed_at':result['completed_at'],'counts':result['counts'],'snapshot':result['snapshot'],'failed_gates':[g for g in result['gates'] if g['status']=='FAIL'],'warning_gates':[{'gate_key':g['gate_key'],'observed':g['observed'],'sample_ids':g['sample_ids']} for g in result['gates'] if g['status']=='WARNING'],'furas_feature_enabled':flag_enabled('FURAS_NATIONAL_ENUMERATION_ENABLED'),'furas_schedule_evidence':next((r for r in next(g for g in result['gates'] if g['gate_key']=='UNEXPLAINED_MISSED_SCHEDULE_EXECUTIONS')['evidence'] if r['source']=='furas'),None),'furas_freshness':next((r for r in next(g for g in result['gates'] if g['gate_key']=='SOURCE_LAST_SUCCESS_TOO_OLD')['evidence'] if r['source']=='furas'),None),'rcjy_rows':rcjy,'active_jobs':db.execute(select(SyncJob.id,SyncJob.source_id,SyncJob.status,SyncJob.job_state).where(SyncJob.job_state.in_(['QUEUED','RUNNING','RETRYING']))).all(),'alembic_head':db.scalar(text('select version_num from alembic_version'))}
 print(json.dumps(out,default=str,ensure_ascii=False))

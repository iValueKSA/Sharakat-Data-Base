from datetime import datetime, timezone
from sqlalchemy import select, func, text
from app.database import SessionLocal
from app.models import Source, SyncJob, SourceOpportunity, SourceObservation

now=datetime.now(timezone.utc)
with SessionLocal() as db:
    db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
    sources=db.execute(select(Source.id,Source.source_key,Source.enabled,Source.technical_health,Source.coverage_status,Source.source_type,Source.polling_frequency_minutes,Source.last_attempted_sync,Source.last_successful_sync,Source.last_pagination_complete)).all()
    rows=[]
    for sid,key,enabled,health,cov,mode,poll,last_attempt,last_success,last_pag in sources:
        complete=db.execute(select(SyncJob.id,SyncJob.finished_at).where(SyncJob.source_id==sid,SyncJob.status=='SUCCESS',SyncJob.pagination_complete.is_(True)).order_by(SyncJob.finished_at.desc()).limit(1)).first()
        content_change=db.execute(select(func.max(SourceObservation.first_seen_at)).join(SourceOpportunity,SourceObservation.source_opportunity_id==SourceOpportunity.id).where(SourceOpportunity.source_id==sid)).scalar()
        last_failure=db.execute(select(SyncJob.id,SyncJob.finished_at,SyncJob.status,SyncJob.error_message).where(SyncJob.source_id==sid,SyncJob.status.in_(['FAILED','BLOCKED','PARSER_WARNING','INCOMPLETE_COLLECTION_WARNING','WARNING'])).order_by(SyncJob.started_at.desc()).limit(1)).first()
        jobs=db.execute(select(SyncJob.id,SyncJob.status,SyncJob.job_state,SyncJob.trigger_type,SyncJob.started_at,SyncJob.finished_at,SyncJob.pagination_complete,SyncJob.pages_scanned,SyncJob.new_count,SyncJob.update_count,SyncJob.error_message,SyncJob.metrics_json).where(SyncJob.source_id==sid).order_by(SyncJob.started_at.desc()).limit(8)).all()
        rows.append({'source_id':sid,'key':key,'enabled':enabled,'technical_health':health,'coverage_status':cov,'sync_mode':mode,'polling_minutes':poll,'last_attempt':last_attempt.isoformat() if last_attempt else None,'last_success':last_success.isoformat() if last_success else None,'source_last_pagination_complete':last_pag,'last_complete_job':{'id':complete.id,'finished_at':complete.finished_at.isoformat() if complete.finished_at else None} if complete else None,'last_content_change':content_change.isoformat() if content_change else None,'last_failure':{'id':last_failure.id,'finished_at':last_failure.finished_at.isoformat() if last_failure.finished_at else None,'status':last_failure.status,'error':(last_failure.error_message or '')[:120]} if last_failure else None,'latest_jobs':[{'id':j.id,'status':j.status,'state':j.job_state,'trigger':j.trigger_type,'start':j.started_at.isoformat() if j.started_at else None,'finish':j.finished_at.isoformat() if j.finished_at else None,'complete':j.pagination_complete,'pages':j.pages_scanned,'new':j.new_count,'updated':j.update_count,'error':(j.error_message or '')[:150],'metrics':{k:(j.metrics_json or {}).get(k) for k in ('public_scope_complete','technical_health','coverage_status','pagination_complete','pages_requested','pages_successful','page_errors','public_surface_errors','source_limitations')}} for j in reversed(jobs)]})
    import json
    print(json.dumps({'captured_at':now.isoformat(),'sources':rows},default=str,ensure_ascii=False))
    db.rollback()

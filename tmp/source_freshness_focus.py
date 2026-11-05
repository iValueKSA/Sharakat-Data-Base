from datetime import datetime, timezone
from sqlalchemy import select,text
from app.database import SessionLocal
from app.models import Source,SyncJob
import json
with SessionLocal() as d:
 d.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
 out=[]
 for sid in (6,7,8,10):
  s=d.execute(select(Source.id,Source.source_key,Source.polling_frequency_minutes,Source.technical_health,Source.coverage_status,Source.last_attempted_sync,Source.last_successful_sync,Source.last_pagination_complete).where(Source.id==sid)).first()
  jobs=d.execute(select(SyncJob.id,SyncJob.status,SyncJob.job_state,SyncJob.trigger_type,SyncJob.started_at,SyncJob.finished_at,SyncJob.pagination_complete,SyncJob.pages_scanned,SyncJob.metrics_json,SyncJob.error_message).where(SyncJob.source_id==sid).order_by(SyncJob.started_at.desc()).limit(12)).all()
  out.append({'source':{'id':s.id,'key':s.source_key,'polling_minutes':s.polling_frequency_minutes,'technical_health':s.technical_health,'coverage_status':s.coverage_status,'last_attempt':s.last_attempted_sync.isoformat() if s.last_attempted_sync else None,'last_success':s.last_successful_sync.isoformat() if s.last_successful_sync else None,'source_last_pagination_complete':s.last_pagination_complete},'jobs':[{'id':j.id,'status':j.status,'state':j.job_state,'trigger':j.trigger_type,'start':j.started_at.isoformat() if j.started_at else None,'finish':j.finished_at.isoformat() if j.finished_at else None,'complete':j.pagination_complete,'pages':j.pages_scanned,'public_scope_complete':(j.metrics_json or {}).get('public_scope_complete'),'technical_health':(j.metrics_json or {}).get('technical_health'),'coverage_status':(j.metrics_json or {}).get('coverage_status'),'error':(j.error_message or '')[:140]} for j in reversed(jobs)]})
 print(json.dumps({'captured_at':datetime.now(timezone.utc).isoformat(),'sources':out},ensure_ascii=False))
 d.rollback()

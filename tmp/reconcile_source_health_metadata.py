import json
import sys
sys.path.insert(0,'/app')
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Source,SyncJob,SystemEvent
from app.service import NOW

targets={'ahda','invest-saudi','modon','mwan'}
changed=[]
with SessionLocal() as db:
 for key in sorted(targets):
  source=db.scalar(select(Source).where(Source.source_key==key))
  latest=db.scalar(select(SyncJob).where(SyncJob.source_id==source.id).order_by(SyncJob.id.desc()).limit(1)) if source else None
  if not source or not latest or latest.status!='FAILED' or source.sync_status!='FAILED' or source.technical_health!='HEALTHY':
   continue
  before=source.technical_health
  source.technical_health='WARNING'
  changed.append({'source_key':key,'source_id':source.id,'job_id':latest.id,'before':before,'after':'WARNING'})
  db.add(SystemEvent(event_type='SOURCE_TECHNICAL_HEALTH_RECONCILED',created_at=NOW(),payload={
   'source_key':key,'source_id':source.id,'latest_failed_job_id':latest.id,
   'before':'HEALTHY','after':'WARNING',
   'reason':'A failed transport attempt without an HTTP status was incorrectly classified as HEALTHY; technical-health fallback is now WARNING. No source listing, Master, observation, or opportunity data was changed.'}))
 db.commit()
print(json.dumps({'changed':changed,'count':len(changed)},separators=(',',':')))


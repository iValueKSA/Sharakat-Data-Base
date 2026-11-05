import sys; sys.path.insert(0,"/app")
from datetime import datetime, timezone
import json
from sqlalchemy import select, func
from app.database import SessionLocal, engine
from app.models import Opportunity, SourceOpportunity, Source, SourceObservation, SyncJob
with SessionLocal() as db:
  print('snapshot_utc', db.execute(select(func.now())).scalar())
  f=db.scalar(select(Source).where(Source.source_key=='furas'))
  rows=db.execute(select(SourceOpportunity,Opportunity).join(Opportunity,Opportunity.id==SourceOpportunity.master_opportunity_id).where(SourceOpportunity.source_id==f.id).order_by(SourceOpportunity.id)).all()
  print('furas_source_records_linked',len(rows))
  records=[]
  for so,o in rows:
    raw=so.raw_data_json or {}; a=raw.get('attributes') or {}
    records.append({'source_id':so.id,'master_id':o.id,'ext':so.source_opportunity_id,'ref':so.source_reference_number,'title':so.source_title,'url':so.source_url,'raw_status':so.raw_status,'canonical_status':o.status,'merged':o.merged_into_id is not None,'type':a.get('OPPORTUNITYTYPE'),'activity_type':a.get('ACTIVITYTYPE'),'start':a.get('STARTDATE'),'end':a.get('ENDDATE'),'sell':a.get('LASTRFPSELLDATE'),'bid':a.get('LASTBIDATE'),'open':a.get('ENVELOPESOPENDATE'),'canonical_deadline':o.submission_deadline,'canonical_pub':o.publication_date})
  print('date_presence_stats',json.dumps({str((r['start'] is not None,r['end'] is not None,r['sell'] is not None,r['bid'] is not None,r['open'] is not None)):sum(1 for x in records if (x['start'] is not None,x['end'] is not None,x['sell'] is not None,x['bid'] is not None,x['open'] is not None)==(r['start'] is not None,r['end'] is not None,r['sell'] is not None,r['bid'] is not None,r['open'] is not None)) for r in records},ensure_ascii=False)); print('records_ref',json.dumps([{k:r[k] for k in ('master_id','ref','title','url','raw_status','canonical_status','type','start','end','sell','bid','open','canonical_deadline','canonical_pub')} for r in records if r['master_id']>100],ensure_ascii=False))
  print('sync_jobs_after_prev', db.execute(select(SyncJob.id,SyncJob.source_id,SyncJob.status,SyncJob.job_state,SyncJob.trigger_type,SyncJob.queued_at,SyncJob.started_at,SyncJob.finished_at,SyncJob.observation_count if hasattr(SyncJob,'observation_count') else SyncJob.id).where(SyncJob.queued_at>=datetime(2026,10,19,13,9,21,tzinfo=timezone.utc)).order_by(SyncJob.id)).all())



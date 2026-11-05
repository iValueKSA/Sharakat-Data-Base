from sqlalchemy import select
from app.database import SessionLocal
from app.models import Source,SourceOpportunity,Opportunity,GeographicReferenceUnit,AuditEvent,OpportunityConflict,SyncJob
with SessionLocal() as db:
 src=db.scalar(select(Source).where(Source.source_key=='rcjy-investment-opportunities'))
 rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==src.id).order_by(SourceOpportunity.id)).all()
 for r in rows:
  m=db.get(Opportunity,r.master_opportunity_id)
  u=db.get(GeographicReferenceUnit,m.geography_reference_unit_id) if m and m.geography_reference_unit_id else None
  p=db.get(GeographicReferenceUnit,u.parent_id) if u and u.parent_id else None
  print('RCJY_GEO',r.id,r.source_opportunity_id,r.master_opportunity_id,m.geographic_scope if m else None,u.id if u else None,u.name_ar if u else None,p.id if p else None,p.name_ar if p else None)
 print('REVIEW_STATUS',db.execute(select(OpportunityConflict.id,OpportunityConflict.status).where(OpportunityConflict.id.between(1303,1312)).order_by(OpportunityConflict.id)).all())
 print('REVIEW_AUDITS',db.execute(select(AuditEvent.entity_id,AuditEvent.id,AuditEvent.event_type).where(AuditEvent.event_type=='REVIEW_STALE_CONDITION_RESOLVED',AuditEvent.entity_id.in_([str(i) for i in range(1303,1313)])).order_by(AuditEvent.entity_id)).all())
 print('FURAS_JOBS',db.execute(select(SyncJob.id,SyncJob.status,SyncJob.job_state,SyncJob.finished_at).where(SyncJob.id.in_([692,694])).order_by(SyncJob.id)).all())

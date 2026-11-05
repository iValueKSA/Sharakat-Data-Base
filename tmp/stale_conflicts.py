from sqlalchemy import select
from app.database import SessionLocal
from app.models import *
from app.review_lifecycle import stale_conflict_evidence
with SessionLocal() as db:
 for c in db.scalars(select(OpportunityConflict).where(OpportunityConflict.status=='OPEN').order_by(OpportunityConflict.id)).all():
  e=stale_conflict_evidence(db,c)
  r=db.get(SourceOpportunity,c.source_record_id); m=db.get(Opportunity,c.opportunity_id)
  linked=db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==m.id).order_by(SourceOpportunity.id)).all()
  print(c.id, 'evidence_rule=',e.get('rule') if e else None,'master_status=',m.status,'record_status=',r.canonical_status,'missing=',r.missing_successful_checks,'record_last_seen=',r.last_seen_at,'linked=',[(x.id,x.source_id,x.canonical_status,x.missing_successful_checks,x.last_seen_at) for x in linked])

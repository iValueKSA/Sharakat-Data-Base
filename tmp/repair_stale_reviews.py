import json
from sqlalchemy import select
from app.database import SessionLocal
from app.models import OpportunityConflict,AuditEvent
from app.review_lifecycle import stale_conflict_evidence,apply_review_triage_candidates
with SessionLocal() as db:
 rows=db.scalars(select(OpportunityConflict).where(OpportunityConflict.status=='OPEN').order_by(OpportunityConflict.id)).all()
 ids=[row.id for row in rows]
 assert ids==list(range(1303,1313)),f'unexpected open conflict set: {ids}'
 evidence={row.id:stale_conflict_evidence(db,row) for row in rows}
 assert all(evidence.values()),{key:value for key,value in evidence.items() if value is None}
 receipt=apply_review_triage_candidates(db,ids)
 assert [row['review_id'] for row in receipt]==ids,receipt
 db.commit()
 for row in receipt:
  event=db.scalar(select(AuditEvent).where(AuditEvent.event_type=='REVIEW_STALE_CONDITION_RESOLVED',AuditEvent.entity_id==str(row['review_id'])).order_by(AuditEvent.id.desc()))
  row['audit_event_id']=event.id if event else None
  row['audit_event_type']=event.event_type if event else None
  row['audit_created_at']=event.created_at.isoformat() if event and event.created_at else None
  row['source_scope']=row['evidence'].get('source_key')
 print(json.dumps({'resolved_count':len(receipt),'repairs':receipt},ensure_ascii=False,default=str))

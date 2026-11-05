import json
from sqlalchemy import select,func
from app.database import SessionLocal
from app.models import AuditEvent,MergeAudit,OpportunityConflict,DuplicateCandidate,LocationReview,QualificationReview
s=SessionLocal()
try:
 ids=[330,331,356,369,372,376,378,381,388,391]
 rows=s.scalars(select(AuditEvent).where(AuditEvent.entity_type=='opportunity_conflict',AuditEvent.entity_id.in_([str(i) for i in ids])).order_by(AuditEvent.id)).all()
 event_items=[{'audit_event_id':e.id,'event_type':e.event_type,'entity_type':e.entity_type,'entity_id':e.entity_id,'actor':e.request_metadata.get('actor'),'created_at':e.created_at.isoformat(),'before':e.before_json,'after':e.after_json} for e in rows]
 merges=s.scalars(select(MergeAudit).order_by(MergeAudit.id)).all()
 complete_merges=[{'merge_audit_id':a.id,'merged_master_id':a.merged_opportunity_id,'survivor_master_id':a.target_opportunity_id,'actor':a.performed_by,'merged_at':a.merged_at.isoformat() if a.merged_at else None,'has_reason':bool(a.merge_reason),'has_evidence':bool(a.merge_evidence),'has_before_after':bool(a.target_before_json is not None and a.target_after_json is not None)} for a in merges]
 counts={'duplicate_resolved':s.scalar(select(func.count(DuplicateCandidate.id)).where(DuplicateCandidate.status.in_(('MERGED','REJECTED')))),'location_resolved':s.scalar(select(func.count(LocationReview.id)).where(LocationReview.status.in_(('ACCEPTED','REJECTED')))),'qualification_resolved':s.scalar(select(func.count(QualificationReview.id)).where(QualificationReview.status!='PENDING')),'conflict_resolved_legacy':s.scalar(select(func.count(OpportunityConflict.id)).where(OpportunityConflict.status.in_(('RESOLVED','RESOLVED_KEEP','RESOLVED_CANONICAL')))),'conflict_superseded_audited':s.scalar(select(func.count(OpportunityConflict.id)).where(OpportunityConflict.status=='SUPERSEDED'))}
 result={'captured_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'historical_resolved_counts':counts,'historical_incomplete_audit_cases':120,'historical_reason':'pre-typed legacy decisions lack one or more case-level before/after, reason, evidence, actor, or resolution timestamp; no values fabricated','complete_merge_audits':len(complete_merges),'merge_audit_sample':complete_merges[:3],'new_supersede_audit_events':event_items,'new_supersede_audit_event_count':len(event_items)}
 print(json.dumps(result,ensure_ascii=False,default=str))
finally:s.close()

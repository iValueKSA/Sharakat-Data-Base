import json
from collections import Counter
from datetime import datetime, timezone
from sqlalchemy import select, func, text
from app.database import SessionLocal
from app.models import Opportunity, SourceOpportunity, SourceObservation, DuplicateCandidate, LocationReview, QualificationReview, OpportunityConflict, AuditEvent, MergeAudit, SystemEvent, Source
from app.data_quality import evaluate_data_quality

def iso(v): return v.isoformat() if hasattr(v,"isoformat") else v

db=SessionLocal(); db.execute(text("SET TRANSACTION READ ONLY"))
models=[(DuplicateCandidate,"duplicate_candidate",("PENDING","OPEN")),(LocationReview,"location_review",("PENDING","OPEN")),(QualificationReview,"qualification_review",("PENDING","OPEN")),(OpportunityConflict,"opportunity_conflict",("PENDING","OPEN"))]
counts={"current_masters":db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))) or 0,"total_masters":db.scalar(select(func.count(Opportunity.id))) or 0,"merged_masters":db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_not(None))) or 0,"source_opportunities":db.scalar(select(func.count(SourceOpportunity.id))) or 0,"observations":db.scalar(select(func.count(SourceObservation.id))) or 0}
status_counts={}; resolved=[]
for model,kind,opens in models:
    rows=db.scalars(select(model).order_by(model.id)).all(); c=Counter(r.status for r in rows); status_counts[kind]={"total":len(rows),"by_status":dict(c)}
    for r in rows:
        if r.status in opens: continue
        rid=str(r.id); ev=db.scalars(select(AuditEvent).where(AuditEvent.entity_type==kind,AuditEvent.entity_id==rid).order_by(AuditEvent.created_at,AuditEvent.id)).all()
        item={"review_id":r.id,"review_type":kind,"status":r.status,"created_at":iso(getattr(r,"created_at",None) or getattr(r,"detected_at",None)),"review_record_fields":{k:iso(v) for k,v in {c.name:getattr(r,c.name) for c in r.__table__.columns}.items()},"audit_events":[{"id":e.id,"event_type":e.event_type,"user_id":e.user_id,"actor":(e.request_metadata or {}).get("actor"),"decision":(e.after_json or {}).get("decision"),"after":e.after_json,"metadata":e.request_metadata,"created_at":iso(e.created_at)} for e in ev],"current_entity_valid":None}
        if model is DuplicateCandidate:
            left=db.get(Opportunity,r.left_opportunity_id); right=db.get(Opportunity,r.right_opportunity_id)
            item["entities"]={"left":({"id":left.id,"canonical_id":left.canonical_id,"title":left.title_ar,"reference":left.reference_number,"merged_into_id":left.merged_into_id} if left else None),"right":({"id":right.id,"canonical_id":right.canonical_id,"title":right.title_ar,"reference":right.reference_number,"merged_into_id":right.merged_into_id} if right else None)}
            ma=db.scalars(select(MergeAudit).where(MergeAudit.merged_opportunity_id==r.right_opportunity_id,MergeAudit.target_opportunity_id==r.left_opportunity_id).order_by(MergeAudit.created_at)).all()
            item["merge_audits"]=[{"id":m.id,"created_at":iso(m.created_at),"merged_at":iso(m.merged_at),"undone_at":iso(m.undone_at),"performed_by":m.performed_by,"merge_reason":m.merge_reason,"merge_evidence":m.merge_evidence} for m in ma]
            item["system_merge_events"]=[{"id":x.id,"created_at":iso(x.created_at),"payload":x.payload} for x in db.scalars(select(SystemEvent).where(SystemEvent.event_type=="MASTER_DUPLICATE_MERGED").order_by(SystemEvent.id)).all() if (x.payload or {}).get("audit_id") in {m.id for m in ma}]
            item["current_entity_valid"]=bool(left and right)
        elif model is OpportunityConflict:
            master=db.get(Opportunity,r.opportunity_id); src=db.get(SourceOpportunity,r.source_record_id); source=db.get(Source,r.source_id)
            item["entities"]={"master_id":r.opportunity_id,"source_record_id":r.source_record_id,"master_exists":bool(master),"master_merged_into":master.merged_into_id if master else None,"source_record_exists":bool(src),"source_id_exists":bool(source)}
            item["current_entity_valid"]=bool(master and src and source)
        elif model is LocationReview:
            src=db.get(SourceOpportunity,r.source_record_id) if r.source_record_id else None; source=db.get(Source,r.source_id); master=db.get(Opportunity,src.master_opportunity_id) if src and src.master_opportunity_id else None
            item["entities"]={"source_record_id":r.source_record_id,"source_record_exists":bool(src),"source_id_exists":bool(source),"master_id":src.master_opportunity_id if src else None,"master_exists":bool(master)}; item["current_entity_valid"]=bool(source and (src is None or src is not None))
        else:
            src=db.get(SourceOpportunity,r.source_record_id) if r.source_record_id else None; source=db.get(Source,r.source_id)
            item["entities"]={"source_record_id":r.source_record_id,"source_record_exists":bool(src),"source_id_exists":bool(source)}; item["current_entity_valid"]=bool(source and src)
        resolved.append(item)
all_review_total=sum(v["total"] for v in status_counts.values()); open_reviews=sum(sum(v for s,v in x["by_status"].items() if s in ("PENDING","OPEN")) for x in status_counts.values()); superseded=sum(i["status"] in ("SUPERSEDED","STALE","OBSOLETE") for i in resolved)
invalid_actions=[]
valid={"FIELD_KEEP","FIELD_USE_SOURCE","SECTOR_INFERENCE_ACCEPTED","DUPLICATE_MERGED","DUPLICATE_REJECTED","DUPLICATE_UNDONE","LOCATION_ACCEPTED","LOCATION_REJECTED","QUALIFICATION_ACCEPTED","QUALIFICATION_REJECTED"}
for e in db.scalars(select(AuditEvent).where(AuditEvent.event_type.like("REVIEW_%")).order_by(AuditEvent.id)).all():
 d=(e.after_json or {}).get("decision")
 if isinstance(d,str) and d not in valid and (e.request_metadata or {}).get("actor")!="SYSTEM": invalid_actions.append({"event_id":e.id,"event_type":e.event_type,"entity_type":e.entity_type,"entity_id":e.entity_id,"user_id":e.user_id,"actor":(e.request_metadata or {}).get("actor"),"decision":d,"before":e.before_json,"after":e.after_json,"metadata":e.request_metadata,"created_at":iso(e.created_at)})
r=evaluate_data_quality(db,scope="full",trigger="focused_dq_root_cause_read_only",persist=False)
out={"captured_at":datetime.now(timezone.utc).isoformat(),"counts":counts,"review_counts":status_counts,"total_reviews":all_review_total,"open_reviews":open_reviews,"resolved_reviews":all_review_total-open_reviews-superseded,"superseded_reviews":superseded,"resolved_review_records_without_linked_review_audit":len(resolved),"resolved_review_records":resolved,"invalid_action_event_count":len(invalid_actions),"invalid_action_events":invalid_actions,"dq":{"total":r["gates_evaluated"],"counts":r["counts"],"failed_gates":r["failed_gates"],"warnings":r["warning_gates"]}}
print(json.dumps(out,ensure_ascii=False,default=str))
db.close()

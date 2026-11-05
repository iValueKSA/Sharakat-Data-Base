import json
from sqlalchemy import text, select
from app.database import SessionLocal, engine
from app.data_quality import evaluate_data_quality
from app.models import AuditEvent
with engine.connect() as connection: connection.execute(text("SET TRANSACTION READ ONLY"))
with SessionLocal() as db:
    result=evaluate_data_quality(db,scope="full",trigger="workbench_readonly_acceptance",persist=False)
    gate=next(g for g in result["gates"] if g["gate_key"]=="REVIEW_DECISION_WITH_INVALID_ACTION")
    events=db.scalars(select(AuditEvent).where(AuditEvent.id.in_(gate.get("sample_ids",[])))).all()
    print(json.dumps({"count":gate["observed"],"samples":[{"id":e.id,"type":e.event_type,"entity":e.entity_type,"entity_id":e.entity_id,"actor":(e.request_metadata or {}).get("actor"),"kind":(e.request_metadata or {}).get("decision_kind"),"decision":(e.after_json or {}).get("decision"),"before_status":(e.before_json or {}).get("status"),"after_status":(e.after_json or {}).get("status")} for e in events]},ensure_ascii=False))

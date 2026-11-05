import json
from collections import Counter
from datetime import datetime, timezone
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import SyncJob, Source
from app.data_quality import evaluate_data_quality
import app.main as main

@event.listens_for(Session, "after_begin")
def _readonly(session, transaction, connection):
    if connection.dialect.name == "postgresql": connection.exec_driver_sql("SET TRANSACTION READ ONLY")

def snapshot():
    token=main.request_context.set({"user":{"id":0,"role":"admin"},"path":"/api/admin/review-queue","method":"GET"})
    try: items=main.review_queue(None,"all","OPEN",1000)
    finally: main.request_context.reset(token)
    with SessionLocal() as db:
        total,max_id=db.execute(select(func.count(SyncJob.id),func.max(SyncJob.id))).one()
        jobs=db.execute(select(SyncJob.id,Source.source_key,SyncJob.status,SyncJob.trigger_type,SyncJob.new_count,SyncJob.update_count,SyncJob.removed_records_count,SyncJob.metrics_json).join(Source,Source.id==SyncJob.source_id).where(SyncJob.id>432).order_by(SyncJob.id)).all()
    return {"open_reviews":len(items),"human_review_required":sum(x.get("disposition")=="HUMAN_REVIEW_REQUIRED" for x in items),"source_recheck_required":sum(x.get("disposition")=="SOURCE_RECHECK_REQUIRED" for x in items),"disposition_counts":dict(sorted(Counter(str(x.get("disposition")) for x in items).items())),"open_by_priority":dict(sorted(Counter(x.get("priority") for x in items).items())),"open_by_type":dict(sorted(Counter(x.get("domain") for x in items).items())),"sync_jobs_total":int(total),"sync_jobs_max_id":int(max_id or 0),"jobs_since_previous_accepted_snapshot_id_432":[{"job_id":r.id,"source":r.source_key,"status":r.status,"trigger_type":r.trigger_type,"master_delta_new":r.new_count,"master_delta_update":r.update_count,"removed_records":r.removed_records_count,"metrics":r.metrics_json or {}} for r in jobs]}

captured_at=datetime.now(timezone.utc).isoformat()
before=snapshot()
with SessionLocal() as db: report=evaluate_data_quality(db,scope="full",trigger="manual",persist=False)
after=snapshot()
result={"captured_at":captured_at,"environment":"live local PostgreSQL; separate ephemeral container; SQL transactions enforced READ ONLY","scope":"full","persist":False,"snapshot_before":before,"snapshot_after":after,"dq_report":report}
print(json.dumps(result,ensure_ascii=False,default=str,separators=(",",":")))

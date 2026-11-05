"""Read current queue and sync-job counts without writing to the live database."""
import json
from sqlalchemy import event, func, select
from app.database import SessionLocal, engine
from app.models import SyncJob
from app.models import Source
from app import main as api

if engine.dialect.name != "postgresql":
    raise RuntimeError("This snapshot is intended for the configured live PostgreSQL database.")

@event.listens_for(engine, "connect")
def force_read_only(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET default_transaction_read_only = on")
    cursor.close()

api.request_context.set({"user":{"id":-1,"role":"admin","display_name":"read-only closeout"},
    "path":"/api/admin/review-queue","method":"GET"})
rows = api.review_queue(None, "all", "OPEN", 1000, exclude_source_recheck=False)
source_recheck = [row for row in rows if row.get("disposition") == "SOURCE_RECHECK_REQUIRED"]
with SessionLocal() as db:
    jobs = db.scalar(select(func.count(SyncJob.id))) or 0
    max_job_id = db.scalar(select(func.max(SyncJob.id)))
    recent_jobs = db.scalars(select(SyncJob).order_by(SyncJob.id.desc()).limit(5)).all()
    job_rows = [{"id":job.id,"source":(db.get(Source,job.source_id).source_key if db.get(Source,job.source_id) else None),
        "status":job.status,"trigger_type":job.trigger_type,"new":job.new_count,"updated":job.update_count,
        "unchanged":job.unchanged_count,"removed":job.removed_records_count} for job in recent_jobs]
print(json.dumps({"open_reviews":len(rows),"human_review_required":len(rows)-len(source_recheck),
    "source_recheck_required":len(source_recheck),"sync_jobs":jobs,"sync_jobs_max_id":max_job_id,
    "recent_jobs":job_rows,"read_only":True},ensure_ascii=False))

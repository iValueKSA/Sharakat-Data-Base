import json
from collections import Counter
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import SyncJob
import app.main as main
@event.listens_for(Session,"after_begin")
def ro(session,transaction,connection):
 if connection.dialect.name=="postgresql": connection.exec_driver_sql("SET TRANSACTION READ ONLY")
t=main.request_context.set({"user":{"id":0,"role":"admin"},"path":"/api/admin/review-queue","method":"GET"})
try: items=main.review_queue(None,"all","OPEN",1000)
finally: main.request_context.reset(t)
with SessionLocal() as db: jobs,maxid=db.execute(select(func.count(SyncJob.id),func.max(SyncJob.id))).one()
print(json.dumps({"open_reviews":len(items),"human_review_required":sum(x.get("disposition")!="SOURCE_RECHECK_REQUIRED" for x in items),"source_recheck_required":sum(x.get("disposition")=="SOURCE_RECHECK_REQUIRED" for x in items),"sync_jobs_total":jobs,"sync_jobs_max_id":maxid},ensure_ascii=False))

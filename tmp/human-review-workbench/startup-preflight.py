import json, os
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Source, User
from app.service import DEFAULT_SOURCES
@event.listens_for(Session,"after_begin")
def ro(session,transaction,connection):
 if connection.dialect.name=="postgresql": connection.exec_driver_sql("SET TRANSACTION READ ONLY")
with SessionLocal() as db:
 rows={x.source_key:x for x in db.scalars(select(Source)).all()}
 diffs=[]
 for seed in DEFAULT_SOURCES:
  row=rows.get(seed["source_key"])
  if row is None: diffs.append({"source_key":seed["source_key"],"missing":True}); continue
  for key,value in seed.items():
   if key in ("notes","polling_frequency_minutes"): continue
   if getattr(row,key)!=value: diffs.append({"source_key":seed["source_key"],"field":key,"diff":True})
 print(json.dumps({"seed_source_diffs":diffs,"seed_source_differences":len(diffs),"bootstrap_user_exists":bool(db.scalar(select(User.id).where(User.email==os.environ.get("BOOTSTRAP_ADMIN_EMAIL","").lower()))),"sync_on_startup":os.getenv("SYNC_ON_STARTUP","false")},ensure_ascii=False))

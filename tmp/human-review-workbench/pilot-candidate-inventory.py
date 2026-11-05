import json
from collections import Counter
from sqlalchemy import event
from sqlalchemy.orm import Session
import app.main as main
@event.listens_for(Session,"after_begin")
def ro(session,transaction,connection):
 if connection.dialect.name=="postgresql": connection.exec_driver_sql("SET TRANSACTION READ ONLY")
t=main.request_context.set({"user":{"id":0,"role":"admin"},"path":"/api/admin/review-queue","method":"GET"})
try: rows=main.review_queue(None,"all","OPEN",1000)
finally: main.request_context.reset(t)
open_rows=[r for r in rows if r.get("status")=="OPEN"]
actionable=[r for r in open_rows if r.get("disposition")!="SOURCE_RECHECK_REQUIRED"]
subtypes=Counter((r.get("domain"),r.get("field") or r.get("reason_key")) for r in actionable)
out={"open_total":len(open_rows),"actionable_total":len(actionable),"source_recheck":len(open_rows)-len(actionable),"by_type":dict(Counter(r.get("domain") for r in open_rows)),"by_subtype":[{"type":k[0],"subtype":k[1],"count":n} for k,n in subtypes.items()],"by_priority":dict(Counter(r.get("priority") for r in open_rows)),"by_source":dict(Counter(r.get("source") or "UNSPECIFIED" for r in actionable)),"source_recheck_in_actionable":sum(r.get("disposition")=="SOURCE_RECHECK_REQUIRED" for r in actionable),"records":[{"review_id":r["id"],"priority":r.get("priority"),"type":r.get("domain"),"subtype":r.get("field") or r.get("reason_key"),"master_id":(r.get("master_ids") or [None])[0],"master_ids":r.get("master_ids",[]),"title":r.get("title"),"source":r.get("source"),"source_key":r.get("source_key"),"source_record_id":r.get("source_record_id"),"disposition":r.get("disposition"),"evidence_status":r.get("evidence_status"),"created_at":r.get("created_at"),"reason_label":r.get("reason_label"),"has_source_url":bool(r.get("url") or (r.get("evidence") or {}).get("source_url")),"guarded_standardization":(r.get("evidence") or {}).get("guarded_standardization")} for r in actionable]}
print(json.dumps(out,ensure_ascii=False,separators=(",",":"),default=str))

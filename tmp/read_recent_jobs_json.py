import json
from datetime import date,datetime
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
 c.exec_driver_sql('SET TRANSACTION READ ONLY')
 rows=c.execute(text('select id,source_id,trigger_type,status,job_state,started_at,finished_at,new_count,update_count from source_sync_jobs order by id desc limit 4')).mappings().all()
 def conv(v): return v.isoformat() if isinstance(v,(date,datetime)) else v
 print(json.dumps([{k:conv(v) for k,v in row.items()} for row in rows],ensure_ascii=False,indent=2))

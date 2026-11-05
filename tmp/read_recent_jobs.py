from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
 c.exec_driver_sql('SET TRANSACTION READ ONLY')
 for row in c.execute(text('select id,source_id,trigger_type,status,job_state,started_at,finished_at,new_count,update_count from source_sync_jobs order by id desc limit 4')).mappings():
  print(dict(row))

import json
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
 c.exec_driver_sql('SET TRANSACTION READ ONLY')
 counts={k:c.execute(text(sql)).scalar_one() for k,sql in {
  'master_rows':'select count(*) from opportunities',
  'current_masters':'select count(*) from opportunities where merged_into_id is null',
  'source_opportunities':'select count(*) from source_opportunities',
  'change_history_rows':'select count(*) from opportunity_change_history',
  'jobs_total':'select count(*) from source_sync_jobs',
  'jobs_max_id':'select coalesce(max(id),0) from source_sync_jobs'}.items()}
 jobs=[dict(r) for r in c.execute(text('select id,trigger_type,status,job_state,new_count,update_count,started_at from source_sync_jobs where id>510 order by id')).mappings().all()]
 print(json.dumps({'read_only':True,'counts':counts,'jobs_after_baseline_510':jobs},ensure_ascii=False,default=str,indent=2))

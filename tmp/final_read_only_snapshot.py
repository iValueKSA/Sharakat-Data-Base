import json
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
 c.exec_driver_sql('SET TRANSACTION READ ONLY')
 total=c.execute(text('select count(*) from opportunities')).scalar_one()
 current=c.execute(text('select count(*) from opportunities where merged_into_id is null')).scalar_one()
 counts={r[0]:r[1] for r in c.execute(text('select coalesce(sector,\'NULL\'),count(*) from opportunities where merged_into_id is null group by coalesce(sector,\'NULL\') order by 1')).all()}
 sources=c.execute(text('select count(*) from source_opportunities')).scalar_one()
 jobs=c.execute(text('select count(*),coalesce(max(id),0) from source_sync_jobs')).one()
 states={r[0]:r[1] for r in c.execute(text('select job_state,count(*) from source_sync_jobs group by job_state order by job_state')).all()}
 active=c.execute(text("select count(*) from source_sync_jobs where upper(coalesce(job_state,'')) in ('QUEUED','RUNNING','PENDING') or upper(coalesce(status,'')) in ('QUEUED','RUNNING','PENDING')")).scalar_one()
 sector_open=c.execute(text("select count(*) from opportunity_data_conflicts where lower(field_name) like '%sector%' and upper(status)='OPEN'")).scalar_one()
 ch=c.execute(text("select count(*) from opportunity_change_history where changed_field='sector'")).scalar_one()
 obj={'read_only':True,'total_master_rows':total,'current_masters':current,'current_sector_counts':counts,'source_opportunities':sources,'sync_job_count':jobs[0],'sync_job_max_id':jobs[1],'sync_job_states':states,'active_sync_jobs':active,'open_sector_conflicts':sector_open,'sector_change_history_rows':ch}
 print(json.dumps(obj,ensure_ascii=False,indent=2))

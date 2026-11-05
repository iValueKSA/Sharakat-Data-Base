import json
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
 c.exec_driver_sql('SET TRANSACTION READ ONLY')
 rows=c.execute(text("select id,user_id,event_type,entity_type,entity_id,created_at,before_json,after_json,request_metadata from audit_events where entity_type='user' and entity_id='1' and event_type='PASSWORD_RESET' order by created_at desc limit 3")).mappings().all()
 safe=[]
 for r in rows:
  safe.append({'id':r['id'],'actor_user_id':r['user_id'],'event_type':r['event_type'],'entity_type':r['entity_type'],'entity_id':r['entity_id'],'created_at':r['created_at'].isoformat() if r['created_at'] else None,'before_keys':sorted((r['before_json'] or {}).keys()),'after_keys':sorted((r['after_json'] or {}).keys()),'metadata_keys':sorted((r['request_metadata'] or {}).keys()),'credentials_or_hash_in_audit':False})
 print(json.dumps({'latest_password_reset_audit':safe[0] if safe else None,'count_found':len(rows)},ensure_ascii=False,indent=2))

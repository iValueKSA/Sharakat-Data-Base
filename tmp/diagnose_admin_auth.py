import json,os,sys,hashlib
from datetime import datetime,timezone,timedelta
from sqlalchemy import text
from app.database import engine
from app.security import verify_password
email='admin@local'
raw=sys.stdin.read()
fields={}
for line in raw.splitlines():
 key,sep,val=line.partition(':')
 if sep: fields[key.strip().lower()]=val.strip()
file_email=fields.get('email','').lower()
file_password=fields.get('password')
now=datetime.now(timezone.utc)
with engine.connect() as c:
 c.exec_driver_sql('SET TRANSACTION READ ONLY')
 dbname=c.execute(text('select current_database()')).scalar_one()
 row=c.execute(text('select id,email,role,is_active,failed_login_count,locked_until,last_login_at,created_at,password_hash from users where lower(email)=:email'),{'email':email}).mappings().first()
 if not row:
  print(json.dumps({'account_exists':False,'database_name':dbname,'environment':os.getenv('ENVIRONMENT'),'redis_configured':bool(os.getenv('REDIS_URL')),'credential_file_email_matches':file_email==email,'credential_file_has_password':bool(file_password)}));sys.exit(0)
 uid=row['id']; lock=row['locked_until']; lock_norm=lock.replace(tzinfo=timezone.utc) if lock and lock.tzinfo is None else lock
 events=c.execute(text('select event_type,created_at,request_metadata from audit_events where user_id=:uid order by created_at desc limit 100'),{'uid':uid}).mappings().all()
 safe_events=[{'type':e['event_type'],'at':e['created_at'].isoformat() if e['created_at'] else None,'ip':(e['request_metadata'] or {}).get('ip')} for e in events if any(x in (e['event_type'] or '').upper() for x in ('LOGIN','PASSWORD','USER_'))]
 active_sessions=c.execute(text('select count(*) from user_sessions where user_id=:uid and expires_at>:now'),{'uid':uid,'now':now}).scalar_one()
 file_matches=bool(file_password and verify_password(file_password,row['password_hash']))
 bootstrap_email=os.getenv('BOOTSTRAP_ADMIN_EMAIL','').lower()
 recent_ips={'172.31.240.10'}
 recent_ips.update(e['ip'] for e in safe_events if e.get('ip'))
 throttle=[]
 redis_configured=bool(os.getenv('REDIS_URL'))
 redis_healthy=False
 if redis_configured:
  try:
   import redis
   client=redis.Redis.from_url(os.environ['REDIS_URL'],socket_connect_timeout=1,socket_timeout=1)
   redis_healthy=bool(client.ping())
   for ip in recent_ips:
    key='rate:login:'+hashlib.sha256(f'{ip}:{email}'.encode()).hexdigest()
    value=client.get(key);ttl=client.ttl(key)
    count=int(value) if value else 0
    throttle.append({'count':count,'ttl_seconds':ttl,'active':bool(ttl>0 and count>=8)})
  except Exception:
   redis_healthy=False
 pwd_reset=[e for e in safe_events if e['type'].upper()=='PASSWORD_RESET']
 login_failed=[e for e in safe_events if e['type'].upper()=='LOGIN_FAILED']
 login_success=[e for e in safe_events if e['type'].upper()=='LOGIN']
 out={
  'account_exists':True,'user_id':uid,'email':row['email'],'role':row['role'],'active':bool(row['is_active']),
  'failed_login_count':row['failed_login_count'] or 0,'locked_until':lock_norm.isoformat() if lock_norm else None,
  'account_locked_now':bool(lock_norm and lock_norm>now),'last_login_at':row['last_login_at'].isoformat() if row['last_login_at'] else None,
  'created_at':row['created_at'].isoformat() if row['created_at'] else None,'active_sessions':int(active_sessions),
  'database_name':dbname,'environment':os.getenv('ENVIRONMENT'),'bootstrap_email_matches':bool(bootstrap_email and bootstrap_email==email),
  'credential_file_email_matches':file_email==email,'credential_file_password_matches_current_hash':file_matches,
  'audit_password_reset_count':len(pwd_reset),'latest_password_reset_at':pwd_reset[0]['at'] if pwd_reset else None,
  'recent_login_failed_count':len(login_failed),'latest_login_failed_at':login_failed[0]['at'] if login_failed else None,
  'latest_login_failed_ip':login_failed[0].get('ip') if login_failed else None,
  'latest_login_success_at':login_success[0]['at'] if login_success else None,
  'latest_login_success_ip':login_success[0].get('ip') if login_success else None,
  'redis_configured':redis_configured,'redis_healthy':redis_healthy,'redis_candidate_throttle_states':throttle,
  'login_throttled':any(x['active'] for x in throttle),
  'password_hash_returned':False
 }
 print(json.dumps(out,ensure_ascii=False,indent=2))

import json,sys
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User
from app.security import hash_password,audit,utcnow
payload=json.load(sys.stdin)
password=payload.get('password','')
if not isinstance(password,str) or len(password)<24:
 print(json.dumps({'ok':False,'reason':'credential policy'}));sys.exit(2)
with SessionLocal() as db:
 with db.begin():
  user=db.scalar(select(User).where(User.email=='admin@local').with_for_update())
  if not user:
   print(json.dumps({'ok':False,'reason':'existing account missing'}));sys.exit(3)
  if not user.is_active or (user.role or '').lower()!='admin':
   print(json.dumps({'ok':False,'reason':'existing account is not active admin'}));sys.exit(4)
  before={'is_active':bool(user.is_active),'role':user.role,'failed_login_count':int(user.failed_login_count or 0),'account_locked':bool(user.locked_until and user.locked_until>utcnow())}
  user.password_hash=hash_password(password)
  user.failed_login_count=0
  user.locked_until=None
  audit(db,'PASSWORD_RESET',None,'user',str(user.id),before=before,after={'password_reset':True,'is_active':True,'role':user.role,'failed_login_count':0,'locked_until':None},metadata={'method':'authorized_local_operator_reset','scope':'authentication_credentials_only','credential_material_recorded':False,'password_hash_recorded':False})
  db.flush()
  print(json.dumps({'ok':True,'user_id':user.id,'email':user.email,'role':user.role,'is_active':bool(user.is_active),'password_reset_audit_written':True,'failed_login_count_reset':True,'lock_cleared':True,'password_material_recorded':False,'password_hash_returned':False}))

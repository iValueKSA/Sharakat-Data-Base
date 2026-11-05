import json
from app.database import SessionLocal
from app.data_quality import evaluate_data_quality
with SessionLocal() as db:
 result=evaluate_data_quality(db,scope='full',trigger='baseline_readonly_20261103',persist=False)
 print(json.dumps({k:result[k] for k in ['run_id','started_at','completed_at','counts','snapshot']},default=str,ensure_ascii=False))
 print('FAIL_GATES='+json.dumps([g for g in result['gates'] if g['status']=='FAIL'],default=str,ensure_ascii=False))
 print('WARNING_GATES='+json.dumps([g for g in result['gates'] if g['status']=='WARNING'],default=str,ensure_ascii=False))

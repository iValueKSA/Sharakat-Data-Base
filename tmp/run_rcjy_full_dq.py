import json
from app.database import SessionLocal
from app.data_quality import evaluate_data_quality
with SessionLocal() as db:
 result=evaluate_data_quality(db,scope='full',trigger='rcjy_post_promotion',persist=True)
 db.commit()
 print(json.dumps({'run_id':result.get('run_id'),'counts':result.get('counts'),'failed_gates':result.get('failed_gates'),'snapshot':result.get('snapshot')},ensure_ascii=False,default=str))

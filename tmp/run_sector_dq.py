import json
from sqlalchemy import text
from app.database import SessionLocal
from app.data_quality import evaluate_data_quality
out={}
for scope in ('fast','full'):
    db=SessionLocal()
    try:
        db.execute(text('SET TRANSACTION READ ONLY'))
        run=evaluate_data_quality(db,scope=scope,trigger='sector_classification_validation',persist=False)
        out[scope]=run
    finally: db.close()
with open('/tmp/sector-dq-results.json','w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=2,default=str)
print(json.dumps({scope:{'gates_evaluated':r['gates_evaluated'],'counts':r['counts'],'failed_gates':[x['key'] for x in r['failed_gates']],'warning_gates':[x['key'] for x in r['warning_gates']]} for scope,r in out.items()},ensure_ascii=False,indent=2))

import json
import app.main as m
from app.database import SessionLocal
m.admin_auth=lambda token:{'id':None,'role':'admin'}
with open('/tmp/pilot-sample.json',encoding='utf-8') as f: pilot=json.load(f)
rows=m.review_queue('pilot-readonly','all','ALL',1000)
by_key={f"{row.get('domain')}:{row.get('id')}":row for row in rows}
result=[]
for case in pilot['cases']:
 item=by_key.get(case['review_id_key'])
 if not item: result.append({'review_id_key':case['review_id_key'],'available':False}); continue
 with SessionLocal() as db:
  detail=m._workbench_detail(db,item)
 result.append({'review_id_key':case['review_id_key'],'available':True,'current_status':detail.get('status'),
  'current_disposition':detail.get('disposition'),'current_priority':detail.get('priority'),
  'master_titles':[master.get('title') for master in detail.get('masters',[])],
  'source_names':sorted({source.get('source') for source in detail.get('sources',[]) if source.get('source')}),
  'recommendation_available':bool((detail.get('recommendation') or {}).get('action')),
  'recommendation_confidence':(detail.get('recommendation') or {}).get('confidence') or 'NONE',
  'recommendation_action':(detail.get('recommendation') or {}).get('action')})
print(json.dumps(result,ensure_ascii=False))

from app.database import SessionLocal
from app.main import review_queue,_workbench_recommendation
from collections import Counter
s=SessionLocal()
items=review_queue(None,'all','OPEN',1000,disposition='ALL')
counts=Counter(); picks=[]
for item in items:
    if item['domain'] in ('field_conflict','taxonomy_conflict'):
        rec=_workbench_recommendation(s,item)
        counts[(rec.get('action') or 'none',rec.get('confidence'))]+=1
        if rec.get('action')=='use_source' and rec.get('confidence')=='HIGH':
            picks.append({'id':item['id'],'domain':item['domain'],'field':item.get('field'),'title':item['title'],'source':item.get('source'),'selected':item['evidence'].get('selected'),'conflicting':item['evidence'].get('conflicting'),'rule':rec.get('rule'),'recommendation':rec})
print({'recommendations':{str(k):v for k,v in counts.items()},'high_use_source':picks})
s.close()

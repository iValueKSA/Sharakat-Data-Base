import json
from sqlalchemy import select,text
from app.database import SessionLocal
from app.models import Opportunity,SourceOpportunity,Source
s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY'))
ss={x.id:x.source_key for x in s.scalars(select(Source)).all()}
rows=s.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None),Opportunity.opportunity_type=='تأجير مؤقت',Opportunity.sector!='غير محدد').order_by(Opportunity.id)).all()
out=[]
for m in rows:
    srcs=s.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==m.id)).all()
    out.append({'id':m.id,'sector':m.sector,'title':m.title_ar,'activity':m.activity,'sub_activity':m.sub_activity,'subsector':m.subsector,'asset':m.opportunity_type,'short_description':m.short_description,'source_facts':[{'source':ss.get(x.source_id),'sector':x.source_sector,'activity':x.source_activity,'sub_activity':x.source_sub_activity,'raw':x.raw_data_json} for x in srcs]})
print(json.dumps({'count':len(out),'examples':out[:40]},ensure_ascii=False,indent=2,default=str))
s.close()

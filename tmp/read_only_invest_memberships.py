import sys,json
sys.path.insert(0,'/app')
from sqlalchemy import select,text
from app.database import engine,SessionLocal
from app.models import Source,SourceOpportunity,SourceOpportunityDatasetMembership
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 with SessionLocal(bind=c) as db:
  s=db.scalar(select(Source).where(Source.source_key=='invest-saudi'))
  rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==s.id).order_by(SourceOpportunity.id)).all()
  out=[]
  for r in rows:
   ms=db.scalars(select(SourceOpportunityDatasetMembership).where(SourceOpportunityDatasetMembership.source_opportunity_id==r.id)).all()
   out.append({'external_id':r.source_opportunity_id,'official_id':r.official_source_id_normalized,'source_status':r.canonical_status,'missing_checks':r.missing_successful_checks,'raw_family':(r.raw_data_json or {}).get('source_record_family'),'raw_dataset':(r.raw_data_json or {}).get('dataset_name'),'memberships':[{'dataset':m.dataset_name,'current':m.is_current,'missing_checks':m.missing_successful_checks} for m in ms]})
  print(json.dumps(out,ensure_ascii=False,separators=(',',':')))

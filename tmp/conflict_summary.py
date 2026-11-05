import sys,json
sys.path.insert(0,"/app")
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Opportunity,Source,SourceOpportunity,OpportunityConflict,SourceObservation
with SessionLocal() as db:
 out=[]
 for c in db.scalars(select(OpportunityConflict).where(OpportunityConflict.id.in_([1158,1159,1160,1161])).order_by(OpportunityConflict.id)):
  m=db.get(Opportunity,c.opportunity_id);s=db.get(SourceOpportunity,c.source_record_id);src=db.get(Source,c.source_id)
  linked=db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==m.id,SourceOpportunity.id!=s.id)).all()
  others=[]
  for r in linked:
   so=db.get(Source,r.source_id); others.append({'source':so.source_key if so else None,'id':r.id,'status':r.canonical_status,'raw_status':r.raw_status,'missing':r.missing_successful_checks,'seen':str(r.last_seen_at),'url':r.source_url})
  obs=db.scalars(select(SourceObservation).where(SourceObservation.source_opportunity_id==s.id).order_by(SourceObservation.last_seen_at.desc())).all()
  statuses=[]
  for o in obs:
   d=o.raw_data_json or {}; raw=d.get('raw_payload') or d
   statuses.append({'seen':str(o.last_seen_at),'dataset':o.dataset_name,'status':raw.get('status'),'id':raw.get('id'),'url':raw.get('furas_link')})
  out.append({'conflict_id':c.id,'status':c.status,'master_id':m.id,'master_status':m.status,'master_title':m.title_ar,'conflicting':c.conflicting_value,'source':src.source_key,'record_id':s.id,'external':s.source_opportunity_id,'canonical':s.canonical_status,'raw_status':s.raw_status,'missing':s.missing_successful_checks,'source_seen':str(s.last_seen_at),'obs_count':len(obs),'obs_statuses':statuses[:4],'other_linked':others})
 print(json.dumps(out,ensure_ascii=False,default=str))
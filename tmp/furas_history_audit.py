import sys,json
sys.path.insert(0,'/app')
from collections import Counter,defaultdict
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Source,SourceOpportunity,SourceObservation
with SessionLocal() as db:
 s=db.scalar(select(Source).where(Source.source_key=='furas'))
 ids=set(db.scalars(select(SourceOpportunity.id).where(SourceOpportunity.source_id==s.id)).all())
 obs=db.scalars(select(SourceObservation).where(SourceObservation.source_opportunity_id.in_(ids)).order_by(SourceObservation.id)).all()
 patterns=Counter(); equality={'equal':0,'different':0}; firstdiff=[]
 for o in obs:
  p=o.raw_data_json or {}; raw=p.get('raw_payload') or p; a=raw.get('attributes') or {}
  if not a:continue
  patterns[tuple(a.get(k) not in (None,'') for k in ('STARTDATE','ENDDATE','LASTRFPSELLDATE','LASTBIDATE','ENVELOPESOPENDATE'))]+=1
  if a.get('ENDDATE') is not None and a.get('LASTRFPSELLDATE') is not None:
   if a.get('ENDDATE')==a.get('LASTRFPSELLDATE'):equality['equal']+=1
   else:
    equality['different']+=1
    if len(firstdiff)<5:firstdiff.append({'observation_id':o.id,'source_id':o.source_opportunity_id,'end':a.get('ENDDATE'),'sell':a.get('LASTRFPSELLDATE'),'seen':o.first_seen_at.isoformat() if o.first_seen_at else None})
 print(json.dumps({'observations':len(obs),'attribute_snapshots':sum(patterns.values()),'patterns':{str(k):v for k,v in patterns.items()},'end_sell_comparison':equality,'different_examples':firstdiff},ensure_ascii=False))

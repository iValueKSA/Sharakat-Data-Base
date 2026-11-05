import json
from collections import defaultdict, Counter
from pathlib import Path
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Opportunity, SourceOpportunity, Source
from app.standardization import standardize_text
with SessionLocal() as db:
 masters=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
 sources=db.execute(select(SourceOpportunity,Source.source_key).join(Source,Source.id==SourceOpportunity.source_id)).all()
 groups=defaultdict(lambda:{"count":0,"ids":[],"sources":set(),"raw_source_sector":Counter(),"raw_source_subsector":Counter(),"activities":Counter(),"payload_category":Counter(),"types":Counter()})
 for m in masters:
  key="<NULL>" if m.sector is None else "<BLANK>" if not standardize_text(m.sector) else m.sector
  g=groups[key];g["count"]+=1;g["ids"].append(m.id)
  for r,source_key in sources:
   if r.master_opportunity_id!=m.id: continue
   g["sources"].add(source_key)
   if r.source_sector is not None:g["raw_source_sector"][r.source_sector]+=1
   if r.source_subsector is not None:g["raw_source_subsector"][r.source_subsector]+=1
   payload=r.raw_data_json or {};details=payload.get("details") or {}
   for value in [payload.get("activity"),details.get("نوع النشاط"),payload.get("normalized_taxonomy",{}).get("sector")]:
    if value is not None:g["activities"][str(value)]+=1
   for value in [payload.get("category"),payload.get("opportunity_category"),payload.get("content_type")]:
    if value is not None:g["payload_category"][str(value)]+=1
   if payload.get("opportunity_type") is not None:g["types"][str(payload["opportunity_type"])]+=1
 out=[]
 for k,g in groups.items():out.append({"sector":k,"count":g["count"],"ids":g["ids"],"sources":sorted(g["sources"]),"raw_source_sector":dict(g["raw_source_sector"]),"raw_source_subsector":dict(g["raw_source_subsector"]),"activities":dict(g["activities"]),"payload_category":dict(g["payload_category"]),"types":dict(g["types"])})
 Path('/tmp/sector-master-evidence.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps([{k:v for k,v in row.items() if k!='ids'} for row in out],ensure_ascii=False))

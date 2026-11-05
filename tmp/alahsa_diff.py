import sys,json
sys.path.insert(0,'/app')
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Opportunity,SourceOpportunity,Source
from app.main import _opportunity_filter_conditions
with SessionLocal() as db:
 legacy=set(db.scalars(select(Opportunity.id).where(*_opportunity_filter_conditions(db,location='al_ahsa_governorate'))).all())
 gov=set(db.scalars(select(Opportunity.id).where(*_opportunity_filter_conditions(db,governorate_id='501'))).all())
 extras=sorted(legacy-gov);missing=sorted(gov-legacy);samples=[]
 for mid in extras[:25]:
  m=db.get(Opportunity,mid); rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==mid)).all(); srcs=[]
  for r in rows:
   src=db.get(Source,r.source_id); raw=r.raw_data_json or {};a=raw.get('attributes') or {}
   srcs.append({'source':src.source_key if src else None,'record_id':r.id,'raw_location':r.raw_location,'city':a.get('CITYNAME'),'city_id':a.get('CITY_ID'),'region':a.get('REGIONNAME'),'region_id':a.get('REGION_ID'),'amana':a.get('AMANA'),'baladya':a.get('BALADYA')})
  samples.append({'master_id':mid,'city':m.city,'district':m.district,'location_description':m.location_description,'geo_scope':m.geographic_scope,'reference_id':m.geography_reference_unit_id,'sources':srcs})
 print(json.dumps({'legacy_count':len(legacy),'official_governorate_count':len(gov),'legacy_only':len(extras),'official_only':len(missing),'official_only_ids':missing[:20],'legacy_only_samples':samples},ensure_ascii=False,default=str))
from app.database import SessionLocal
from app.models import *
from sqlalchemy import select
from app.adapters import LOCATION_ACCEPTANCE_THRESHOLD
import json,re
out=[]
with SessionLocal() as db:
 for m in db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)):
  records=db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==m.id).order_by(SourceOpportunity.id)).all()
  source_items=[]
  for r in records:
   s=db.get(Source,r.source_id); raw=r.raw_data_json or {}
   source_items.append({'source_key':s.source_key,'source_record_id':r.id,'external_id':r.source_opportunity_id,'raw_location':r.raw_location,'method':raw.get('location_detection_method'),'source_scope':raw.get('source_scope'),'location_evidence':raw.get('location_evidence'),'raw_places':raw.get('opportunity_locations') or [],'raw_scope':raw.get('location_scope'),'raw_source_filter':raw.get('source_filter_where')})
  keys={x['source_key'] for x in source_items}
  if 'ahda' in keys:
   if m.title_ar=='تطوير فنادق 5 نجوم في المنطقة الشرقية': state,reason='LOCATION_REVIEW_REQUIRED','REGION_ONLY: Eastern Province stated; project-level Al-Ahsa location not stated.'
   else: state,reason='LOCATION_UNSPECIFIED','No project-level locality, governorate field, or coordinates; current location value is synthetic publisher scope.'
  elif any(x['external_id']=='02-26-017704-1001' for x in source_items): state,reason='LOCATION_REVIEW_REQUIRED','COORDINATE_TEXT_CONFLICT: explicit Salwa title and official Furas city-filter row (CITY_ID=104) lie outside local reference polygon; boundary is non-official and cannot overrule source row.'
  elif any(x['external_id']=='ncp:foodsafetylabs' for x in source_items): state,reason='MULTI_LOCATION_WITH_AL_AHSA','Official NCP source explicitly lists Al-Ahsa among five municipalities; other locations retained.'
  else: state,reason='AL_AHSA_CONFIRMED','Supported by Al-Ahsa-specific official source scope or explicit official locality/campus evidence.'
  out.append({'master_id':m.id,'canonical_id':m.canonical_id,'title':m.title_ar,'classification':state,'reason':reason,'city_projection':m.city,'district_projection':m.district,'master_location_description':m.location_description,'latitude':m.latitude,'longitude':m.longitude,'confidence':m.location_confidence_score,'method':m.location_detection_method,'master_evidence':m.location_evidence,'manual_review_required':m.manual_review_required,'sources':source_items})
print(json.dumps(out,ensure_ascii=False,default=str))

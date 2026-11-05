from app.database import SessionLocal
from app.models import *
from sqlalchemy import select,func
import json,re
rx=re.compile(r'al[\s-]?ahsa|al\s*hasa|alahsa|alhasaa|ahsa|الأحساء|الاحساء|الهفوف|المبرز|العقير|العيون|سلوى',re.I)
with SessionLocal() as db:
 queue=[]
 for q in db.scalars(select(LocationReview).where(LocationReview.status=='PENDING').order_by(LocationReview.id)):
  src=db.get(Source,q.source_id);r=db.get(SourceOpportunity,q.source_record_id) if q.source_record_id else None;raw=(r.raw_data_json or {}) if r else {}
  master_id=r.master_opportunity_id if r else None
  if master_id is not None:
   classification='MASTER_GEOGRAPHY_REVIEW'
   reason=q.reason
  else:
   localized=q.id in {1,2,3,4,5,10,11,12,13,14,15,16,17}
   classification='EXPLICIT_AL_AHSA_CANDIDATE_IDENTITY_CHECK_REQUIRED' if localized else 'CONTRADICTORY_OR_MULTIREGION_EVIDENCE_RETAINED'
   reason=('Official source title/description identifies an Al-Ahsa site or asset; preserve candidate for identity/status/multiplicity review before linking a Master.' if localized else 'Source text also mentions Al-Ahsa but names a different system/route/location; preserve contradictory evidence for human review.')
  queue.append({'review_id':q.id,'status':q.status,'source_key':src.source_key,'external_id':q.external_id,'source_record_id':q.source_record_id,'existing_master_id':master_id,'title':q.title,'source_location':q.source_location,'latitude':q.latitude,'longitude':q.longitude,'evidence':q.evidence,'queue_reason':q.reason,'review_classification':classification,'review_note':reason,'raw_method':raw.get('location_detection_method')})
 summaries=[]
 for src in db.scalars(select(Source).order_by(Source.source_key)):
  rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==src.id)).all(); linked=[r for r in rows if r.master_opportunity_id is not None]
  location_present=sum(bool((r.raw_location or '').strip()) for r in rows)
  explicit=0
  for r in rows:
   raw=r.raw_data_json or {}
   geo_text=' '.join([r.raw_location or '',str(raw.get('location') or ''),str(raw.get('region') or ''),str(raw.get('city') or '')])
   explicit += bool(rx.search(geo_text))
  coords=0
  for r in rows:
   raw=r.raw_data_json or {};g=raw.get('geometry') or {};c=raw.get('coordinates') or {}
   if isinstance(g,dict) and g.get('x') is not None and g.get('y') is not None:coords+=1
   elif isinstance(c,dict) and c.get('latitude') is not None and c.get('longitude') is not None:coords+=1
  summaries.append({'source':src.source_key,'official_name':src.source_name_ar,'records':len(rows),'linked_master_records':len(linked),'raw_location_present':location_present,'explicit_al_ahsa_in_location_fields':explicit,'source_coordinate_records':coords,'health':src.technical_health,'coverage':src.coverage_status,'last_successful_sync':src.last_successful_sync.isoformat() if src.last_successful_sync else None})
 ncp=db.scalar(select(Source).where(Source.source_key=='ncp'))
 candidates=[]
 for r in db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==ncp.id,SourceOpportunity.master_opportunity_id.is_(None))):
  raw=r.raw_data_json or {}
  if any('Al-Ahsa' in str(x) or 'الأحساء' in str(x) for x in (raw.get('opportunity_locations') or [])):
   candidates.append({'source_record_id':r.id,'external_id':r.source_opportunity_id,'title':r.source_title,'raw_location':r.raw_location,'opportunity_locations':raw.get('opportunity_locations'),'location_scope':raw.get('location_scope'),'qualification_reason':raw.get('qualification_reason')})
 print(json.dumps({'captured_at_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'pending_location_reviews':queue,'source_coverage':summaries,'unlinked_ncp_explicit_al_ahsa':candidates},ensure_ascii=False,default=str))


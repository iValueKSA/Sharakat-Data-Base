from app.database import SessionLocal
from app.models import *
from app.main import ACTIVE_EXCLUDED_STATUSES,HISTORICAL_STATUSES
from sqlalchemy import select,func
from collections import Counter
from datetime import datetime,timezone
import hashlib,json

def digest(rows):
 return hashlib.sha256('\n'.join(json.dumps(row,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':')) for row in rows).encode('utf-8')).hexdigest()
with SessionLocal() as db:
 masters=db.scalars(select(Opportunity).order_by(Opportunity.id)).all();eligible=[m for m in masters if m.merged_into_id is None]
 sr=db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all();obs=db.scalars(select(SourceObservation).order_by(SourceObservation.id)).all()
 identity=digest([(m.id,m.canonical_id,m.merged_into_id) for m in masters])
 links=digest([(r.id,r.source_id,r.master_opportunity_id,r.source_opportunity_id) for r in sr])
 raw_source=digest([(r.id,r.content_hash,hashlib.sha256(json.dumps(r.raw_data_json or {},ensure_ascii=False,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()) for r in sr])
 raw_obs=digest([(r.id,r.content_hash,hashlib.sha256(json.dumps(r.raw_data_json or {},ensure_ascii=False,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()) for r in obs])
 status_counts=Counter(m.status for m in eligible)
 coords=[m for m in eligible if m.latitude is not None and m.longitude is not None]
 invalid=[m.id for m in coords if not (-90<=m.latitude<=90 and -180<=m.longitude<=180)]
 result={'captured_at_utc':datetime.now(timezone.utc).isoformat(),'counts':{'masters_total':len(masters),'masters_eligible_nonmerged':len(eligible),'masters_merged':len(masters)-len(eligible),'masters_active':sum(1 for m in eligible if m.status not in ACTIVE_EXCLUDED_STATUSES),'masters_historical':sum(1 for m in eligible if m.status in HISTORICAL_STATUSES),'master_status_counts':dict(status_counts),'source_opportunities':len(sr),'source_observations':len(obs),'change_history':db.scalar(select(func.count(ChangeHistory.id))),'pending_location_reviews':db.scalar(select(func.count(LocationReview.id)).where(LocationReview.status=='PENDING')),'open_location_reviews_all_statuses':db.execute(select(LocationReview.status,func.count(LocationReview.id)).group_by(LocationReview.status)).all(),'opportunity_location_rows':db.scalar(select(func.count(OpportunityLocation.id))),'masters_with_coordinates':len(coords),'coordinates_missing_both':sum(m.latitude is None and m.longitude is None for m in eligible),'coordinates_partial':sum((m.latitude is None)!=(m.longitude is None) for m in eligible),'coordinates_invalid_wgs84':len(invalid)},'fingerprints':{'master_identities_sha256':identity,'master_source_links_sha256':links,'raw_source_payloads_sha256':raw_source,'raw_observation_payloads_sha256':raw_obs}}
 print(json.dumps(result,ensure_ascii=False,indent=2,default=str))


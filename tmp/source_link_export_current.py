import json
from app.database import SessionLocal
from app.models import Opportunity, SourceOpportunity
with SessionLocal() as db:
 rows=[]
 for s in db.query(SourceOpportunity).join(Opportunity,SourceOpportunity.master_opportunity_id==Opportunity.id).filter(Opportunity.merged_into_id.is_(None)).order_by(SourceOpportunity.id).all():
  rows.append({"source_record_id":s.id,"master_id":s.master_opportunity_id,"source_key":s.source.source_key,"source_name":s.source.source_name_ar,"external_id":s.source_opportunity_id,"reference":s.source_reference_number or s.official_source_id_original or "","title":s.source_title,"owner":s.source_owner or "","location":s.raw_location or "","url":s.source_url or "","source_status":s.canonical_status,"missing_checks":s.missing_successful_checks or 0,"master_status":s.master.status if s.master else "","raw":s.raw_data_json or {}})
 print(json.dumps(rows,ensure_ascii=False,separators=(",",":")))

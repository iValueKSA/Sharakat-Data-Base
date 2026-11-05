from sqlalchemy import select,func
from sqlalchemy.orm import joinedload
from app.database import SessionLocal
from app.models import Source,SourceOpportunity,OpportunityLocation,GeographicReferenceUnit,SyncJob,Opportunity
with SessionLocal() as db:
 s=db.scalar(select(Source).where(Source.source_key=='rcjy-investment-opportunities'))
 rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==s.id).options(joinedload(SourceOpportunity.opportunity_locations))).unique().all()
 print('source_rows',len(rows),'masters',db.scalar(select(func.count(Opportunity.id)).where(Opportunity.primary_publication_platform==s.source_name_ar)))
 for row in rows:
  print(row.source_opportunity_id, row.source_title, row.raw_location, row.master_opportunity_id, row.raw_data_json.get('source_actionability_status'), [(p.location_name,p.geography_reference_unit_id,p.source_evidence_json) for p in row.opportunity_locations])
 job=db.scalar(select(SyncJob).where(SyncJob.source_id==s.id).order_by(SyncJob.id.desc()).limit(1))
 print('job',job.id,job.status,job.raw_count,job.removed_records_count,job.error_message)


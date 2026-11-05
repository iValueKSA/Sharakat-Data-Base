import sys,json
sys.path.insert(0,"/app")
from sqlalchemy import select,func
from app.database import SessionLocal
from app.models import Opportunity,GeographicReferenceDataset,GeographicReferenceUnit,OpportunityConflict,SourceOpportunity,Source
with SessionLocal() as db:
 current=db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None)))
 ds=db.scalar(select(GeographicReferenceDataset).where(GeographicReferenceDataset.is_current.is_(True)))
 refs={level:db.scalar(select(func.count(GeographicReferenceUnit.id)).where(GeographicReferenceUnit.dataset_id==ds.id,GeographicReferenceUnit.level==level)) or 0 for level in ('country','region','governorate','city')}
 assigned=db.execute(select(GeographicReferenceUnit.level,func.count(Opportunity.id)).join(Opportunity,Opportunity.geography_reference_unit_id==GeographicReferenceUnit.id).where(Opportunity.merged_into_id.is_(None),GeographicReferenceUnit.dataset_id==ds.id).group_by(GeographicReferenceUnit.level)).all()
 scopes=db.execute(select(Opportunity.geographic_scope,func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None)).group_by(Opportunity.geographic_scope)).all()
 rows=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None),Opportunity.coordinate_provenance_json.is_not(None))).all()
 verified=sum(1 for x in rows if (x.coordinate_provenance_json or {}).get('verified') is True)
 outside=sum(1 for x in rows if (x.coordinate_provenance_json or {}).get('boundary_validation',{}).get('status')=='SOURCE_COORDINATE_OUTSIDE_SAUDI_REVIEW')
 openconf=db.scalar(select(func.count(OpportunityConflict.id)).where(OpportunityConflict.id.in_([1158,1159,1160,1161]),OpportunityConflict.status=='OPEN'))
 out={'current_masters':current,'reference_version':ds.version,'reference_sha256':ds.content_sha256,'reference_counts':refs,'assigned_by_level':dict(assigned),'scopes':dict(scopes),'provenance_rows':len(rows),'verified_provenance':verified,'outside_review':outside,'conflicts_open_of_four':openconf}
 print(json.dumps(out,ensure_ascii=False,default=str))
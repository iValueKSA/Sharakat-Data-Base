import json
from sqlalchemy import func,select
from app.database import SessionLocal
from app.models import *
with SessionLocal() as d:
 src=d.scalar(select(Source).where(Source.source_key=='rcjy-investment-opportunities'))
 rows=d.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==src.id)).all()
 print('RCJY',src.id,len(rows),[(r.id,r.master_opportunity_id,r.source_opportunity_id,r.official_source_id_normalized,r.source_title,r.raw_status) for r in rows])
 for c in d.scalars(select(OpportunityConflict).where(OpportunityConflict.status=='OPEN').order_by(OpportunityConflict.id)).all():
  m=d.get(Opportunity,c.opportunity_id); s=d.get(Source,c.source_id); r=d.get(SourceOpportunity,c.source_record_id)
  audit=d.scalars(select(AuditEvent).where(AuditEvent.entity_type=='opportunity_conflict',AuditEvent.entity_id==str(c.id)).order_by(AuditEvent.id)).all()
  print('CONFLICT',c.id,{'master':c.opportunity_id,'title':m.title_ar if m else None,'source':s.source_key if s else None,'record':c.source_record_id,'record_title':r.source_title if r else None,'field':c.field_name,'type':c.conflict_type,'selected':c.selected_value,'other':c.conflicting_value,'detected_at':str(c.detected_at),'audit':[(a.id,a.event_type,a.before_json,a.after_json,a.request_metadata) for a in audit]})

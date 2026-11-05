from sqlalchemy import select,func,text
from app.database import SessionLocal
from app.models import Opportunity,SourceOpportunity,Source
s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY'))
q=s.execute(select(Opportunity.opportunity_type,Opportunity.sector,func.count()).where(Opportunity.merged_into_id.is_(None),Opportunity.sector!='غير محدد').group_by(Opportunity.opportunity_type,Opportunity.sector).order_by(Opportunity.opportunity_type,func.count().desc())).all()
print('\n'.join(f'{a or "(null)"}\t{b}\t{c}' for a,b,c in q))
s.close()

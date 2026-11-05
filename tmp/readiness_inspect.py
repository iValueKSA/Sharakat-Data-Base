import json,sys
sys.path.insert(0,"/app")
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity, OpportunityConflict, SourceObservation
with SessionLocal() as db:
    f=db.scalar(select(Source).where(Source.source_key=='furas'))
    q=db.execute(select(SourceOpportunity,Opportunity).join(Opportunity,Opportunity.id==SourceOpportunity.master_opportunity_id).where(SourceOpportunity.source_id==f.id,Opportunity.merged_into_id.is_(None)))
    rows=q.all()
    coord=[]
    for s,m in rows:
        if s.raw_data_json and (m.latitude is not None or m.longitude is not None):
            coord.append({'source_id':s.id,'external_id':s.source_opportunity_id,'raw_url':s.source_url,'master_id':m.id,'master_coords':[m.latitude,m.longitude],'prov':m.coordinate_provenance_json,'raw_keys':list(s.raw_data_json.keys()),'raw':s.raw_data_json,'standardized':s.standardized_data_json})
            if len(coord)>=3:break
    print('FURAS_SAMPLE',json.dumps(coord,ensure_ascii=False,default=str)[:12000])
    cnt=db.execute(select(func.count()).select_from(SourceOpportunity).where(SourceOpportunity.source_id==f.id,SourceOpportunity.master_opportunity_id.is_not(None))).scalar()
    coords=db.execute(select(func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_(None),Opportunity.latitude.is_not(None),Opportunity.longitude.is_not(None))).scalar()
    print('LINKED_FURAS',cnt,'CURRENT_COORDS',coords)
    c=db.scalars(select(OpportunityConflict).where(OpportunityConflict.status=='OPEN',OpportunityConflict.field_name=='status')).all()
    out=[]
    for x in c:
        src=db.get(Source,x.source_id);s=db.get(SourceOpportunity,x.source_record_id);m=db.get(Opportunity,x.opportunity_id)
        if src and src.source_key=='invest-saudi':
            obs=db.scalars(select(SourceObservation).where(SourceObservation.source_opportunity_id==s.id).order_by(SourceObservation.last_seen_at.desc())).all()
            out.append({'conflict_id':x.id,'master_id':m.id,'master_title':m.title_ar,'master_status':m.status,'source_id':s.id,'external_id':s.source_opportunity_id,'raw_status':s.raw_status,'canonical_status':s.canonical_status,'selected':x.selected_value,'conflicting':x.conflicting_value,'source_url':s.source_url,'raw':s.raw_data_json,'standardized':s.standardized_data_json,'obs_count':len(obs),'obs':[{'seen':o.last_seen_at,'data':o.raw_data_json} for o in obs[:5]]})
    print('INVEST_CONFLICTS',json.dumps(out,ensure_ascii=False,default=str)[:20000])
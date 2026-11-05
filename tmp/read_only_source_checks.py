import sys,json
sys.path.insert(0,'/app')
from sqlalchemy import select,func,text
from app.database import engine,SessionLocal
from app.models import Source,SourceOpportunity,SourceObservation,Opportunity,SourceOpportunityDatasetMembership,LocationReview
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 with SessionLocal(bind=c) as db:
  out={'masters':{},'observation_count':db.scalar(select(func.count(SourceObservation.id))),'source_rows':{},'url_duplicate_groups':[],'active_rows_without_observations':0,'orphaned_observations':0,'master_source_distribution':{},'invest_memberships':{},'location_reviews':[]}
  out['masters']={'total':db.scalar(select(func.count(Opportunity.id))),'current':db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))),'merged':db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_not(None)))}
  rows=db.scalars(select(SourceOpportunity)).all();obs_counts=dict(db.execute(select(SourceObservation.source_opportunity_id,func.count(SourceObservation.id)).group_by(SourceObservation.source_opportunity_id)).all())
  sources=db.scalars(select(Source)).all();source_by_id={s.id:s for s in sources}
  for s in sources:
   rs=[r for r in rows if r.source_id==s.id]
   linked=sum(r.master_opportunity_id is not None for r in rs)
   active=[r for r in rs if r.missing_successful_checks < max(1,s.missing_confirmation_threshold) and r.canonical_status!='أزيلت من المصدر']
   dup_ext=db.execute(select(SourceOpportunity.source_opportunity_id,func.count(SourceOpportunity.id)).where(SourceOpportunity.source_id==s.id).group_by(SourceOpportunity.source_opportunity_id).having(func.count(SourceOpportunity.id)>1)).all()
   urlgroups=db.execute(select(SourceOpportunity.source_url,func.count(SourceOpportunity.id)).where(SourceOpportunity.source_id==s.id,SourceOpportunity.source_url!='').group_by(SourceOpportunity.source_url).having(func.count(SourceOpportunity.id)>1)).all()
   out['url_duplicate_groups'] += [{'source':s.source_key,'url':u,'count':n} for u,n in urlgroups]
   out['source_rows'][s.source_key]={'total':len(rs),'linked':linked,'unlinked':len(rs)-linked,'active_by_missing_threshold':len(active),'historical_by_missing_threshold':len(rs)-len(active),'status_counts':dict(db.execute(select(SourceOpportunity.canonical_status,func.count(SourceOpportunity.id)).where(SourceOpportunity.source_id==s.id).group_by(SourceOpportunity.canonical_status)).all()),'external_id_duplicates':len(dup_ext),'records_without_observation':sum(obs_counts.get(r.id,0)==0 for r in active)}
  linked_counts={}
  for r in rows:
   if r.master_opportunity_id is None:continue
   master=db.get(Opportunity,r.master_opportunity_id)
   if master and master.merged_into_id is None:linked_counts.setdefault(master.id,set()).add(r.source_id)
  dist={'1':0,'2':0,'3_plus':0,'0':0}
  for mid in db.scalars(select(Opportunity.id).where(Opportunity.merged_into_id.is_(None))):
   n=len(linked_counts.get(mid,set()));dist['0' if n==0 else '1' if n==1 else '2' if n==2 else '3_plus']+=1
  out['master_source_distribution']=dist
  ms=db.scalars(select(SourceOpportunityDatasetMembership).join(SourceOpportunity).where(SourceOpportunity.source_id==next(s.id for s in sources if s.source_key=='invest-saudi'))).all()
  by={}
  for m in ms:
   z=by.setdefault(m.dataset_name,{'total':0,'current':0,'noncurrent':0,'missing_checks':{}});z['total']+=1;z['current' if m.is_current else 'noncurrent']+=1;z['missing_checks'][str(m.missing_successful_checks)]=z['missing_checks'].get(str(m.missing_successful_checks),0)+1
  out['invest_memberships']=by
  for r in db.scalars(select(LocationReview).where(LocationReview.status=='PENDING')):
   if source_by_id.get(r.source_id) and source_by_id[r.source_id].source_key=='invest-saudi':out['location_reviews'].append({'id':r.id,'external_id':r.external_id,'confidence':r.confidence_score,'reason':r.reason})
  print(json.dumps(out,ensure_ascii=False,separators=(',',':'),default=str))

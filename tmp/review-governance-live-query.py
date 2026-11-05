import json
from collections import Counter
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import (OpportunityConflict, DuplicateCandidate, LocationReview, QualificationReview, Opportunity,
                        SourceOpportunity, SourceObservation, SourceOpportunityDatasetMembership, Source, SyncJob,
                        AuditEvent, MergeAudit, User)
with SessionLocal() as db:
    out={}
    out['as_of_db_utc']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
    conflicts=db.scalars(select(OpportunityConflict).where(OpportunityConflict.status=='OPEN')).all()
    obs=[]; broken=[]; merged=[]
    for c in conflicts:
        master=db.get(Opportunity,c.opportunity_id); rec=db.get(SourceOpportunity,c.source_record_id)
        n=db.scalar(select(func.count(SourceObservation.id)).where(SourceObservation.source_opportunity_id==c.source_record_id)) or 0
        obs.append(n)
        if not master or not rec or db.get(Source,c.source_id) is None: broken.append(c.id)
        if master and master.merged_into_id is not None: merged.append(c.id)
    out['open_conflicts']=len(conflicts);out['conflicts_no_observations']=sum(n==0 for n in obs);out['conflict_observation_min']=min(obs) if obs else None;out['broken_conflict_ids']=broken;out['merged_conflict_ids']=merged
    duplicates=db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status=='PENDING')).all()
    pair_counts=Counter(tuple(sorted((d.left_opportunity_id,d.right_opportunity_id))) for d in duplicates)
    out['open_duplicate_ids']=[d.id for d in duplicates];out['duplicate_logical_pairs']=[list(p) for p in pair_counts];out['duplicate_duplicate_pair_count']=sum(n-1 for n in pair_counts.values())
    out['duplicate_broken_or_merged_ids']=[d.id for d in duplicates if not db.get(Opportunity,d.left_opportunity_id) or not db.get(Opportunity,d.right_opportunity_id) or db.get(Opportunity,d.left_opportunity_id).merged_into_id is not None or db.get(Opportunity,d.right_opportunity_id).merged_into_id is not None]
    locations=db.scalars(select(LocationReview).where(LocationReview.status=='PENDING')).all()
    out['open_location_ids']=[r.id for r in locations]
    out['location_without_reason_or_evidence']=[r.id for r in locations if not r.reason or not r.evidence]
    out['location_broken_ids']=[r.id for r in locations if db.get(Source,r.source_id) is None or (r.source_record_id and db.get(SourceOpportunity,r.source_record_id) is None)]
    out['location_observation_zero_ids']=[r.id for r in locations if not r.source_record_id or (db.scalar(select(func.count(SourceObservation.id)).where(SourceObservation.source_opportunity_id==r.source_record_id)) or 0)==0]
    qs=db.scalars(select(QualificationReview).where(QualificationReview.status=='PENDING')).all();out['open_qualification_ids']=[q.id for q in qs]
    out['source_coverage_pending_ids']=[]
    invest=db.scalar(select(Source).where(Source.source_key=='invest-saudi'))
    if invest:
        out['source_coverage_pending_ids']=sorted(set(db.scalars(select(SourceOpportunity.id).join(SourceOpportunityDatasetMembership,SourceOpportunityDatasetMembership.source_opportunity_id==SourceOpportunity.id).where(SourceOpportunity.source_id==invest.id,SourceOpportunityDatasetMembership.is_current.is_(True),SourceOpportunityDatasetMembership.missing_successful_checks>0)).all()))
    out['jobs']=[{'id':j.id,'source_id':j.source_id,'job_state':j.job_state,'trigger_type':j.trigger_type,'started_at':j.started_at.isoformat() if j.started_at else None,'raw_count':j.raw_count,'new_count':j.new_count,'update_count':j.update_count,'unchanged_count':j.unchanged_count,'location_review_count':j.location_review_count,'metrics_json':j.metrics_json} for j in db.scalars(select(SyncJob).order_by(SyncJob.id.desc()).limit(10)).all()]
    out['observations_total']=db.scalar(select(func.count(SourceObservation.id))) or 0
    out['audit_total']=db.scalar(select(func.count(AuditEvent.id))) or 0
    out['merge_audit_total']=db.scalar(select(func.count(MergeAudit.id))) or 0
    out['active_users']={role:db.scalar(select(func.count(User.id)).where(User.role==role,User.is_active.is_(True))) or 0 for role in ('admin','analyst','viewer')}
    print(json.dumps(out,ensure_ascii=False,default=str))

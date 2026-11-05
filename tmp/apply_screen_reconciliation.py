from datetime import datetime, timezone
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import Opportunity, SourceOpportunity, Source, DuplicateCandidate, MergeAudit, SystemEvent
from app.merge import merge_candidate

SNAPSHOT='2026-10-20T09:27:35.377973Z'
MERGES=[
    (234,236,2837,0.9867,'Furas and Al-Ahsa records independently state plot 484, plan 14/16, 653.74 m², the same warehouse description and Al-Uyun industrial locality. Source text resolves a parser plot-conflict flag as formatting-only. Furas ref 01-26-017001-26003 is retained on the survivor; Al-Ahsa supplies no propagated reference.'),
    (237,252,2853,0.9265,'Both source records describe commercial plot B1, plan 15/28 at Jawatha, 2,000 m², with the same normalized opportunity description and locality. Furas ref 01-26-017001-30001 is retained on the survivor; Al-Ahsa supplies no propagated reference.'),
    (239,247,2848,0.9894,'Both source records describe factory/workshop plot 214, plan 14/16, 464.52 m², with the same normalized opportunity description and Al-Uyun industrial site. Furas ref 01-26-017001-34002 is retained on the survivor; Al-Ahsa supplies no propagated reference.'),
    (240,243,2844,0.9892,'Both source records describe factory/workshop plot 54, plan 14/16, 538.72 m², with the same normalized opportunity description and Al-Uyun industrial site. Furas ref 01-26-017001-34005 is retained on the survivor; Al-Ahsa supplies no propagated reference.'),
    (241,244,2845,0.9754,'Both source records describe mixed-use building plot 2030, plan 187 at Al-Saifa/Hofuf, 2,513.16 m², with matching normalized title and locality. Furas ref 01-26-017001-40001 is retained on the survivor; Al-Ahsa supplies no propagated reference.'),
    (253,261,2862,1.0,'Both source records describe mixed-use building plot 12, plan 4/253 in the second education district/Hofuf, 1,991 m², with matching normalized title and site. Furas ref 01-26-017001-1 is retained on the survivor; Al-Ahsa supplies no propagated reference.'),
]
PENDING=[
    (107,186,107,189,0.8194,'Furas and Al-Ahsa listings both describe a 15 m² smart-gym kiosk on a King Faisal University promenade and have highly similar titles. Al-Ahsa has no official reference or owner, and its location is only Hawfuf while Furas includes a more specific street. Keep separate pending source-detail confirmation.'),
    (107,187,107,190,0.7743,'Furas lists a 15 m² smart-gym kiosk on a King Faisal University walkway; the Al-Ahsa listing says Diyar Al-Ahsa promenade opposite the university. The shared area and nearby locality are insufficient to establish the same exact site; keep separate pending source-detail confirmation.'),
]
with SessionLocal() as db:
    counts=(db.scalar(select(func.count(Opportunity.id))),db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))),db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_not(None))),db.scalar(select(func.count(SourceOpportunity.id))),db.scalar(select(func.count()).select_from(DuplicateCandidate).where(DuplicateCandidate.status=='PENDING')),db.scalar(select(func.count()).select_from(MergeAudit).where(MergeAudit.undone_at.is_(None))))
    assert counts==(297,282,15,2899,8,15), counts
    existing_pairs={tuple(sorted((c.left_opportunity_id,c.right_opportunity_id))) for c in db.scalars(select(DuplicateCandidate)).all()}
    now=datetime.now(timezone.utc)
    actions=[]
    for a,b,record_id,score,reason in MERGES:
        assert tuple(sorted((a,b))) not in existing_pairs,(a,b)
        left=db.get(Opportunity,a); right=db.get(Opportunity,b); record=db.get(SourceOpportunity,record_id)
        assert left and right and left.merged_into_id is None and right.merged_into_id is None
        assert record and record.master_opportunity_id==b
        assert record.source_id not in {r.source_id for r in left.source_records}
        left_before={k:getattr(left,k) for k in ('title_ar','opportunity_owner','reference_number','location_description','land_area_sqm','submission_deadline')}
        right_before={k:getattr(right,k) for k in ('title_ar','opportunity_owner','reference_number','location_description','land_area_sqm','submission_deadline')}
        evidence={'identity_review_decision':{'decision':'CONFIRMED_FALSE_SPLIT','reviewed_at':now.isoformat(),'basis':reason,'fuzzy_title_alone_used':False,'same_source':False,'reversible':True,'review_snapshot':SNAPSHOT,'generator':'broad-title-area-location-screen; record-level plot/plan/site review','owner_evidence':'UNAVAILABLE_ON_AL_AHSA_SOURCE_RECORD'},'features':{'title_similarity':score,'area_similarity':1.0,'owner_match':False,'owner_comparison':'UNAVAILABLE_ON_AL_AHSA_SOURCE_RECORD','plot_or_plan_match':True,'official_reference_support':'Furas source-specific reference retained on survivor; no cross-source equal reference asserted','auto_merge_safe':False,'contradicting_evidence':[]}}
        candidate=DuplicateCandidate(left_opportunity_id=a,right_opportunity_id=b,confidence_score=score,status='PENDING',created_at=now,explanation_json=evidence)
        db.add(candidate); db.flush()
        audit=merge_candidate(db,candidate,performed_by='identity-deep-review')
        actions.append({'candidate_id':candidate.id,'survivor':a,'merged':b,'audit_id':audit.id,'source_record_id':record_id,'before':{'survivor':left_before,'merged':right_before},'reason':reason})
        existing_pairs.add(tuple(sorted((a,b))))
    pending_ids=[]
    for a,b,ra,rb,score,reason in PENDING:
        assert tuple(sorted((a,b))) not in existing_pairs,(a,b)
        left_record=db.get(SourceOpportunity,ra); right_record=db.get(SourceOpportunity,rb)
        assert left_record and right_record and left_record.master_opportunity_id==a and right_record.master_opportunity_id==b
        assert left_record.source_id != right_record.source_id
        src_left=db.get(Source,left_record.source_id); src_right=db.get(Source,right_record.source_id)
        candidate=DuplicateCandidate(left_opportunity_id=a,right_opportunity_id=b,confidence_score=score,status='PENDING',created_at=now,explanation_json={'identity_review_decision':{'decision':'REVIEW_REQUIRED','reviewed_at':now.isoformat(),'basis':reason,'same_source':False,'source_record_ids':[ra,rb],'source_keys':[src_left.source_key,src_right.source_key],'auto_merge_safe':False,'review_snapshot':SNAPSHOT,'generator':'broad-title-area-location-screen'}})
        db.add(candidate); db.flush(); pending_ids.append(candidate.id); existing_pairs.add(tuple(sorted((a,b))))
    db.add(SystemEvent(event_type='MASTER_IDENTITY_ADDITIONAL_RECONCILIATION',created_at=now,payload={'merge_pairs':[[x[0],x[1]] for x in MERGES],'pending_review_pairs':[[x[0],x[1]] for x in PENDING],'reason':'Record-level reconciliation of broad identity-screen hits omitted from the initial actionable candidate ledger. Six exact cross-source site/parcel/area duplicates were merged reversibly; two weaker campus-kiosk matches remain pending.'}))
    db.commit()
    final=(db.scalar(select(func.count(Opportunity.id))),db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))),db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_not(None))),db.scalar(select(func.count(SourceOpportunity.id))),db.scalar(select(func.count()).select_from(DuplicateCandidate).where(DuplicateCandidate.status=='PENDING')),db.scalar(select(func.count()).select_from(MergeAudit).where(MergeAudit.undone_at.is_(None))),db.scalar(select(func.count()).select_from(DuplicateCandidate)))
    assert final==(297,276,21,2899,10,21,47),final
    print({'before':counts,'after':final,'additional_merges':actions,'new_pending_candidate_ids':pending_ids})


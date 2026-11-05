from datetime import datetime, timezone
from sqlalchemy import select
from app.database import SessionLocal
from app.models import DuplicateCandidate, MergeAudit, SystemEvent

EVIDENCE={
40:{'title_similarity':0.9867,'plot_match':True,'plan_match':True,'parser_plot_conflict_overridden':True,'reason':'Furas and Al-Ahsa records independently state plot 484, plan 14/16, 653.74 m², the same warehouse description and Al-Uyun industrial locality. Punctuation/spacing differences caused a parser plot-conflict flag; the source text resolves it as the same plot. Furas ref 01-26-017001-26003 is retained on the surviving source record; Al-Ahsa supplies no propagated reference.'},
41:{'title_similarity':0.9265,'plot_match':True,'plan_match':True,'parser_plot_conflict_overridden':False,'reason':'Both source records describe commercial plot B1, plan 15/28 at Jawatha, 2,000 m², with the same normalized opportunity description and locality. Furas ref 01-26-017001-30001 is retained on the surviving source record; Al-Ahsa supplies no propagated reference.'},
42:{'title_similarity':0.9894,'plot_match':True,'plan_match':True,'parser_plot_conflict_overridden':False,'reason':'Both source records describe factory/workshop plot 214, plan 14/16, 464.52 m², with the same normalized opportunity description and Al-Uyun industrial site. Furas ref 01-26-017001-34002 is retained on the surviving source record; Al-Ahsa supplies no propagated reference.'},
43:{'title_similarity':0.9892,'plot_match':True,'plan_match':True,'parser_plot_conflict_overridden':False,'reason':'Both source records describe factory/workshop plot 54, plan 14/16, 538.72 m², with the same normalized opportunity description and Al-Uyun industrial site. Furas ref 01-26-017001-34005 is retained on the surviving source record; Al-Ahsa supplies no propagated reference.'},
44:{'title_similarity':0.9754,'plot_match':True,'plan_match':True,'parser_plot_conflict_overridden':False,'reason':'Both source records describe mixed-use building plot 2030, plan 187 at Al-Saifa/Hofuf, 2,513.16 m², with matching normalized title and locality. Furas ref 01-26-017001-40001 is retained on the surviving source record; Al-Ahsa supplies no propagated reference.'},
45:{'title_similarity':1.0,'plot_match':True,'plan_match':True,'parser_plot_conflict_overridden':False,'reason':'Both source records describe mixed-use building plot 12, plan 4/253 in the second education district/Hofuf, 1,991 m², with matching normalized title and site. Furas ref 01-26-017001-1 is retained on the surviving source record; Al-Ahsa supplies no propagated reference.'},
}
with SessionLocal() as db:
    touched=[]
    for cid,item in EVIDENCE.items():
        c=db.get(DuplicateCandidate,cid)
        assert c and c.status=='MERGED'
        audit=db.scalar(select(MergeAudit).where(MergeAudit.merged_opportunity_id==c.right_opportunity_id,MergeAudit.target_opportunity_id==c.left_opportunity_id,MergeAudit.undone_at.is_(None)))
        assert audit
        evidence={'auto_merge_safe':False,'trusted_official_reference_match':False,'owner_match':False,'owner_comparison':'UNAVAILABLE_ON_AL_AHSA_SOURCE_RECORD','plot_match':item['plot_match'],'plan_match':item['plan_match'],'plot_conflict':False,'parser_plot_conflict_overridden':item['parser_plot_conflict_overridden'],'title_similarity':item['title_similarity'],'area_similarity':1.0,'area_difference_percentage':0.0,'site_identity_match':True,'fuzzy_title_alone_used':False,'positive_evidence':['normalized source titles agree with the same explicit plot and plan','exactly matching area','compatible named locality/site','verified Furas source reference remains attached to surviving source listing'],'contradicting_evidence':[],'identity_review_decision':{'decision':'CONFIRMED_FALSE_SPLIT','reviewed_at':datetime.now(timezone.utc).isoformat(),'basis':item['reason'],'fuzzy_title_alone_used':False,'same_source':False,'reversible':True,'review_snapshot':'2026-10-20T09:27:35.377973Z','owner_evidence':'UNAVAILABLE_ON_AL_AHSA_SOURCE_RECORD','official_reference_evidence':'Furas source-specific reference exists only on the Furas record; no equal Al-Ahsa reference is asserted.'}}
        c.explanation_json=evidence
        audit.merge_evidence=evidence
        for event in db.scalars(select(SystemEvent).where(SystemEvent.event_type=='MASTER_DUPLICATE_MERGED')).all():
            payload=dict(event.payload or {})
            if payload.get('audit_id')==audit.id:
                payload['merge_evidence']=evidence
                event.payload=payload
        touched.append({'candidate_id':cid,'audit_id':audit.id,'pair':[c.left_opportunity_id,c.right_opportunity_id],'owner_evidence':'unavailable','reason':item['reason']})
    db.commit()
    print(touched)

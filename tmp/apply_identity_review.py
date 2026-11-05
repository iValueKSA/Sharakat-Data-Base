from datetime import datetime, timezone
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import Opportunity, SourceOpportunity, Source, DuplicateCandidate, MergeAudit, SystemEvent
from app.merge import merge_candidate
MERGES = {7:(163,233,"AL-Ahsa lot 5 / plan 19/149 matches Furas lot 5 / plan 19/149; exact 11,099 m², same title/site; same official asset."),20:(231,265,"Furas and Al-Ahsa titles identify plot T20, plan 4/1082, same 2,448.7 m²; same owner/site and exact asset description."),21:(248,266,"Same drive-through kiosk on King Fahd Road in Al-Mubarraz; exact title/site and 16 m²; Furas official reference maps to Al-Ahsa listing."),22:(251,267,"Same drive-through kiosk on Gulf Road in Hofuf; exact title/site and 16 m²; Furas official reference maps to Al-Ahsa listing."),23:(258,268,"Same drive-through kiosk at King Abdullah Road / Al-Amer Mall extension; exact title/site and 8 m²; Furas official reference maps to Al-Ahsa listing."),24:(246,269,"Same numbered (2) drive-through kiosk on Prince Abdullah bin Jalawi Road; exact title/site and 16 m²; reference and source content align."),25:(242,270,"Same numbered (1) drive-through kiosk on Prince Abdullah bin Jalawi Road; exact title/site and 16 m²; reference and source content align."),28:(262,273,"Same salvage-yard asset, plot 67/1, plan 518/4, 5,223 m², owner and site. Raw titles agree; parser tokenization created a false plot conflict."),29:(260,274,"Same salvage-yard asset, plot 60, plan 518/4, 9,982 m², owner and site; exact cross-source asset match."),30:(235,276,"Same warehouse, plot 485, plan 14/16, 712 m², same site and owner; Furas and Al-Ahsa records describe the identical asset.")}
REJECTS = {6:"Different assets and parcels: Master 165 lists multi-plot group 71/1,71/2,73/1,73/2 (893.06 m²); Master 232 is factory plot 524 (800 m²).",8:"Different plot and asset: Master 193 plot 471 light-industry site vs Master 234 warehouse plot 484 (653.74 m²).",9:"Different plot and asset: Master 193 plot 471 vs Master 235 warehouse plot 485 (712 m²).",10:"Different plot and asset: Master 193 plot 471 vs Master 236 warehouse plot 484 (653.74 m²).",11:"Different plot and asset: Master 193 plot 471 vs Master 238 warehouse plot 483 (705.75 m²).",12:"Different plot and asset: Master 193 plot 471 vs Master 239 factory/workshop plot 214 (464.52 m²).",13:"Different plot and asset: Master 193 plot 471 vs Master 240 factory/workshop plot 54 (538.72 m²).",14:"Different plot and asset: Master 193 plot 471 vs Master 243 factory/workshop plot 54 (538.72 m²).",15:"Different plot and asset: Master 193 plot 471 vs Master 245 factory/workshop plot 524 (800 m²).",16:"Different plot and asset: Master 193 plot 471 vs Master 247 factory/workshop plot 214 (464.52 m²).",17:"Different shopping-center lots: Master 191 identifies lot 11 (6,525 m²); Master 249 identifies lot 12 (6,683.14 m²).",18:"Different plot and asset: Master 193 plot 471 vs Master 250 factory/workshop plot 122 (558.79 m²).",19:"Different plot and asset: Master 193 plot 471 vs Master 255 warehouse plot 483 (705.75 m²).",26:"Different parcel/use: Furas salvage-yard plot 67/1, plan 518/4, vs Al-Ahsa equipment/office site plot T84, plan 41082, 5,008 m².",27:"Different parcel/use: Furas salvage-yard plot 67/1, plan 518/4, vs Al-Ahsa equipment/office site plot T82, plan 41082, 5,008 m².",31:"Different parcel/use: Furas salvage-yard plot 67/1, plan 518/4, vs Al-Ahsa equipment/office site plot T85, plan 41082, 5,008 m²."}
SAME_SOURCE = [(155,156,155,156,"484","483"),(155,159,155,159,"484","480"),(156,159,156,159,"483","480"),(157,160,157,160,"482","479"),(158,161,158,161,"481","478"),(163,254,163,2855,"476","527"),(197,198,200,201,"439","438"),(263,264,2864,2865,"523","522")]
with SessionLocal() as db:
    counts=(db.scalar(select(func.count(Opportunity.id))),db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))),db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_not(None))),db.scalar(select(func.count(SourceOpportunity.id))),db.scalar(select(func.count()).select_from(DuplicateCandidate).where(DuplicateCandidate.status=="PENDING")))
    assert counts==(297,292,5,2899,26), f"Unexpected baseline {counts}"
    existing={c.id:c for c in db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.id.in_(list(MERGES)+list(REJECTS)))).all()}
    assert set(existing)==set(MERGES)|set(REJECTS)
    assert all(existing[i].status=="PENDING" for i in existing)
    actions=[]
    for cid,(left,right,reason) in MERGES.items():
        c=existing[cid]
        assert (c.left_opportunity_id,c.right_opportunity_id)==(left,right), f"candidate {cid} pair changed"
        evidence=dict(c.explanation_json or {})
        evidence["identity_review_decision"]={"decision":"CONFIRMED_FALSE_SPLIT","reviewed_at":datetime.now(timezone.utc).isoformat(),"basis":reason,"fuzzy_title_alone_used":False,"same_source":False,"reversible":True,"review_snapshot":"2026-10-20T09:27:35.377973Z"}
        c.explanation_json=evidence
        audit=merge_candidate(db,c,performed_by="identity-deep-review")
        actions.append({"candidate_id":cid,"survivor":left,"merged":right,"audit_id":audit.id,"source_record_ids":audit.source_record_ids,"reason":reason})
    for cid,reason in REJECTS.items():
        c=existing[cid]
        evidence=dict(c.explanation_json or {})
        evidence["identity_review_decision"]={"decision":"CONFIRMED_DISTINCT","reviewed_at":datetime.now(timezone.utc).isoformat(),"basis":reason,"merge_applied":False,"review_snapshot":"2026-10-20T09:27:35.377973Z"}
        c.explanation_json=evidence;c.status="REJECTED"
        db.add(SystemEvent(event_type="DUPLICATE_CANDIDATE_REJECTED",created_at=datetime.now(timezone.utc),payload={"candidate_id":cid,"master_ids":[c.left_opportunity_id,c.right_opportunity_id],"reason":reason,"performed_by":"identity-deep-review"}))
    now=datetime.now(timezone.utc)
    existing_pairs={(min(c.left_opportunity_id,c.right_opportunity_id),max(c.left_opportunity_id,c.right_opportunity_id)) for c in db.scalars(select(DuplicateCandidate)).all()}
    for a,b,ra,rb,exa,exb in SAME_SOURCE:
        assert tuple(sorted((a,b))) not in existing_pairs
        left=next(r for r in db.scalars(select(SourceOpportunity).where(SourceOpportunity.id==ra)).all())
        right=next(r for r in db.scalars(select(SourceOpportunity).where(SourceOpportunity.id==rb)).all())
        assert left.master_opportunity_id==a and right.master_opportunity_id==b
        assert left.source_id==right.source_id
        source=db.get(Source,left.source_id)
        reason={"decision":"REVIEW_REQUIRED","review_reason":"Same-source listings can be reissues or distinct tenders; identical title plus matching plot/plan is not sufficient to merge without source detail/publication-history evidence.","same_source":True,"source_key":source.source_key,"source_record_ids":[ra,rb],"external_ids":[exa,exb],"master_ids":[a,b],"source_urls":[left.source_url,right.source_url],"source_titles":[left.source_title,right.source_title],"same_plot_plan_screen":True,"auto_merge_safe":False,"reviewed_at":now.isoformat()}
        c=DuplicateCandidate(left_opportunity_id=a,right_opportunity_id=b,confidence_score=0.75,status="PENDING",created_at=now,explanation_json={"identity_review_decision":reason})
        db.add(c)
    db.flush()
    db.add(SystemEvent(event_type="SAME_SOURCE_IDENTITY_REVIEW_QUEUED",created_at=now,payload={"master_pairs":[[a,b] for a,b,*_ in SAME_SOURCE],"source_record_ids":[[ra,rb] for _,_,ra,rb,_,_ in SAME_SOURCE],"reason":"same-source exact-title / plot-plan screen; conservatively retained for manual source-history review"}))
    db.commit()
    final=(db.scalar(select(func.count(Opportunity.id))),db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))),db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_not(None))),db.scalar(select(func.count(SourceOpportunity.id))),db.scalar(select(func.count()).select_from(DuplicateCandidate).where(DuplicateCandidate.status=="PENDING")),db.scalar(select(func.count()).select_from(MergeAudit).where(MergeAudit.undone_at.is_(None))))
    assert final==(297,282,15,2899,8,15), f"Unexpected final counts {final}"
    assert db.scalar(select(func.count(SourceOpportunity.id)).where(SourceOpportunity.master_opportunity_id.is_(None)))==0
    print({"baseline":counts,"final":final,"merges":actions,"rejected":len(REJECTS),"new_same_source_reviews":len(SAME_SOURCE)})



import hashlib, json, time
from collections import Counter
from datetime import datetime, timezone
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import (Opportunity, Source, SourceOpportunity, SourceObservation,
    OpportunityAssetFacilityType, ChangeHistory, SystemEvent, OpportunityConflict,
    QualificationReview, LocationReview, SyncJob)
from app.standardization import canonical_id
from app.sector_classification import ENGINE_VERSION, classify_governed, evidence_fingerprint

DRYRUN_PATH="/tmp/sector-classification-dry-run.json"
dry=json.load(open(DRYRUN_PATH,encoding="utf-8"))
expected={int(x["master_id"]):x for x in dry["dry_run_records"]}
started=time.perf_counter()

def json_hash(value):
    packed=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()

def signatures(db,prespecified_ids=None):
    source_rows=db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
    source_sig=[(r.id,r.master_opportunity_id,r.source_sector,r.source_activity,r.source_sub_activity,
                 r.raw_data_json,r.standardized_data_json,r.official_source_id_original) for r in source_rows]
    masters=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
    master_columns=[c.name for c in Opportunity.__table__.columns if c.name not in {"sector","updated_at","last_updated_at"}]
    master_sig=[{name:getattr(r,name) for name in master_columns} for r in masters]
    conflicts=db.scalars(select(OpportunityConflict).order_by(OpportunityConflict.id)).all()
    conflict_sig=[(r.id,r.opportunity_id,r.field_name,r.status,r.selected_value,r.conflicting_value) for r in conflicts]
    qualification=db.scalars(select(QualificationReview).order_by(QualificationReview.id)).all()
    qualification_sig=[(r.id,r.status,r.reason,r.source_id,r.external_id) for r in qualification]
    locations=db.scalars(select(LocationReview).order_by(LocationReview.id)).all()
    location_sig=[(r.id,r.status,r.source_id,r.source_record_id) for r in locations]
    jobs=db.scalars(select(SyncJob).order_by(SyncJob.id)).all()
    job_sig=[(r.id,r.status,r.job_state,r.trigger_type) for r in jobs]
    current=[r for r in masters if canonical_id("sector",r.sector)!="sector:unspecified"]
    preexisting_sector_sig=[(r.id,r.sector) for r in masters if prespecified_ids is not None and r.id in prespecified_ids]
    return {"source_count":len(source_rows),"raw_source_hash":json_hash(source_sig),
        "master_count":len(masters),"master_business_hash":json_hash(master_sig),
        "specified_sector_hash":json_hash([(r.id,r.sector) for r in current]),
        "prespecified_sector_hash":json_hash(preexisting_sector_sig),
        "conflict_count":len(conflicts),"conflict_hash":json_hash(conflict_sig),
        "qualification_review_count":len(qualification),"qualification_review_hash":json_hash(qualification_sig),
        "location_review_count":len(locations),"location_review_hash":json_hash(location_sig),
        "sync_job_count":len(jobs),"sync_job_max_id":max((r.id for r in jobs),default=None),"sync_job_hash":json_hash(job_sig),
        "history_sector_count":db.scalar(select(func.count(ChangeHistory.id)).where(ChangeHistory.changed_field=="sector")) or 0}

def record_for(db,master,source_map):
    srcs=db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==master.id).order_by(SourceOpportunity.id)).all()
    source_ids=[r.id for r in srcs]
    observations=db.scalars(select(SourceObservation).where(SourceObservation.source_opportunity_id.in_(source_ids))
        .order_by(SourceObservation.last_seen_at.desc(),SourceObservation.id.desc())).all() if source_ids else []
    obs_by={}
    for o in observations:
        obs_by.setdefault(o.source_opportunity_id,[])
        if len(obs_by[o.source_opportunity_id])<3:
            obs_by[o.source_opportunity_id].append({"last_seen_at":o.last_seen_at.isoformat() if o.last_seen_at else None,
                                                    "raw_data_json":o.raw_data_json})
    assets=db.execute(select(OpportunityAssetFacilityType.raw_value).where(
        OpportunityAssetFacilityType.opportunity_id==master.id)).scalars().all()
    source_facts=[]
    for r in srcs:
        source=source_map.get(r.source_id)
        assigned=db.execute(select(OpportunityAssetFacilityType.raw_value).where(
            OpportunityAssetFacilityType.source_record_id==r.id)).scalars().all()
        source_facts.append({"source_key":source.source_key if source else "","source_record_id":r.id,
            "source_opportunity_id":r.source_opportunity_id,"official_source_id_original":r.official_source_id_original,
            "source_title":r.source_title,"source_sector":r.source_sector,"normalized_sector":r.normalized_sector,
            "source_activity":r.source_activity,"source_sub_activity":r.source_sub_activity,
            "source_subsector":r.source_subsector,"source_owner":r.source_owner,"raw_location":r.raw_location,
            "raw_area":r.raw_area,"raw_value":r.raw_value,"raw_dates":r.raw_dates,"raw_data_json":r.raw_data_json,
            "standardized_data_json":r.standardized_data_json,"assets":assigned,
            "observations":obs_by.get(r.id,[])})
    return {"id":master.id,"canonical_id":master.canonical_id,"sector":master.sector,
        "title_ar":master.title_ar,"title_en":master.title_en,"normalized_title":master.normalized_title,
        "reference_number":master.reference_number,"opportunity_owner":master.opportunity_owner,
        "primary_publication_platform":master.primary_publication_platform,"activity":master.activity,
        "sub_activity":master.sub_activity,"subsector":master.subsector,"opportunity_type":master.opportunity_type,
        "investment_model":master.investment_model,"city":master.city,"district":master.district,
        "location_description":master.location_description,"latitude":master.latitude,"longitude":master.longitude,
        "land_area_sqm":master.land_area_sqm,"plot_number":master.plot_number,"investment_value":master.investment_value,
        "contract_duration_years":master.contract_duration_years,"publication_date":master.publication_date,
        "submission_deadline":master.submission_deadline,"short_description":master.short_description,
        "full_description":master.full_description,"asset_facility_type":" | ".join(sorted(set(assets))),"sources":source_facts}

db=SessionLocal()
try:
    with db.begin():
        masters=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id).with_for_update()).all()
        current=[m for m in masters if canonical_id("sector",m.sector)=="sector:unspecified"]
        ids={m.id for m in current}
        if ids!=set(expected):
            raise RuntimeError(f"Current unspecified cohort changed: expected {len(expected)} ids, found {len(ids)}")
        source_map={r.id:r for r in db.scalars(select(Source)).all()}
        prespecified_ids={m.id for m in masters if m.id not in ids}
        before=signatures(db,prespecified_ids)
        decisions=[]
        for master in current:
            record=record_for(db,master,source_map)
            result=classify_governed(record)
            fingerprint=evidence_fingerprint(record,result)
            prior=expected[master.id]
            if result["sector_id"]!=prior["sector_id"] or result["classification"]!=prior["classification_result"]["classification"]:
                raise RuntimeError(f"Dry-run drift for Master {master.id}")
            if not result.get("positive_evidence") or not result.get("rule_key"):
                raise RuntimeError(f"Missing classification evidence for Master {master.id}")
            if result["sector_id"]=="sector:other" and result["classification"]=="FORCED_BEST_FIT":
                if not any(float(ev.get("weight") or 0)>0 and not str(ev.get("rule_key") or "").startswith("FORCED_BEST_FIT")
                           for ev in result.get("positive_evidence",[])):
                    raise RuntimeError(f"Other would be a missing fallback for Master {master.id}")
            decisions.append((master,record,result,fingerprint))
        if len(decisions)!=len(expected):
            raise RuntimeError("Classification coverage mismatch")
        now=datetime.now(timezone.utc)
        event_items=[]
        for master,record,result,fingerprint in decisions:
            previous=master.sector
            master.sector=result["sector"]
            master.updated_at=now
            master.last_updated_at=now
            db.add(ChangeHistory(opportunity_id=master.id,changed_field="sector",previous_value=previous,
                new_value=master.sector,source_id=record["sources"][0]["source_record_id"] and
                    next((s.id for s in source_map.values() if s.source_key==record["sources"][0]["source_key"]),None),
                detected_at=now))
            event_items.append({"master_id":master.id,"sector":master.sector,
                "sector_id":result["sector_id"],"classification_origin":result["classification_origin"],
                "classification_method":result.get("method",result["classification"]),
                "confidence":result["confidence"],"confidence_label":result.get("confidence_label"),
                "confidence_score":result.get("confidence_score",result["confidence"]),
                "total_score":result.get("total_score",result.get("top_score")),
                "top_sector_id":result.get("top_sector_id",result["sector_id"]),"top_score":result.get("top_score"),
                "second_sector_id":result.get("second_sector_id"),"second_score":result.get("second_score"),
                "confidence_margin":result.get("confidence_margin"),"rule_key":result["rule_key"],
                "rule_keys":result.get("rule_keys",[result["rule_key"]]),
                "positive_evidence":result["positive_evidence"],"negative_evidence":result.get("negative_evidence",[]),
                "evidence_fields":result.get("evidence_fields",[]),"reason":result["reason"],
                "engine_version":result.get("engine_version",ENGINE_VERSION),"evidence_fingerprint":fingerprint,
                "previous_sector":previous,"sector_changed":True,"raw_source_sector_values_preserved":True,
                "inference_timestamp":now.isoformat()})
        db.add(SystemEvent(event_type="SECTOR_GOVERNED_CLASSIFICATION_APPLIED",created_at=now,
            payload={"engine_version":ENGINE_VERSION,"scope":"current_unspecified_masters",
                     "classification_count":len(event_items),"classifications":event_items}))
        db.add(SystemEvent(event_type="SECTOR_CLASSIFICATION_PIPELINE_COMPLETED",created_at=now,
            payload={"engine_version":ENGINE_VERSION,"master_count":len(masters),"classified_count":len(event_items),
                "unspecified_after":0,"source_sync_started":False,"dry_run_snapshot_at":dry["snapshot_at"],
                "completed_at":now.isoformat()}))
        db.flush()
        after=signatures(db,prespecified_ids)
        post_counts=Counter(canonical_id("sector",m.sector) for m in db.scalars(
            select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all())
        unspecified_after=post_counts.get("sector:unspecified",0)
        if unspecified_after!=0: raise RuntimeError(f"Unspecified count after apply is {unspecified_after}")
        if after["master_count"]!=before["master_count"] or after["source_count"]!=before["source_count"]:
            raise RuntimeError("Master or source row count changed during apply")
        if after["raw_source_hash"]!=before["raw_source_hash"]:
            raise RuntimeError("Raw source provenance changed during apply")
        if after["conflict_hash"]!=before["conflict_hash"] or after["qualification_review_hash"]!=before["qualification_review_hash"] or after["location_review_hash"]!=before["location_review_hash"]:
            raise RuntimeError("A review row changed during apply")
        if after["sync_job_hash"]!=before["sync_job_hash"]:
            raise RuntimeError("A sync job changed during apply")
        if after["master_business_hash"]!=before["master_business_hash"]:
            raise RuntimeError("A non-sector business field changed during apply")
        if after["prespecified_sector_hash"]!=before["prespecified_sector_hash"]:
            raise RuntimeError("A previously specified sector changed during apply")
        if after["specified_sector_hash"]==before["specified_sector_hash"]:
            raise RuntimeError("Sector distribution did not change")
        if after["history_sector_count"]-before["history_sector_count"]!=len(decisions):
            raise RuntimeError("Sector ChangeHistory count mismatch")
        output={"completed_at":now.isoformat(),"engine_version":ENGINE_VERSION,"before":before,
            "after":after,"unspecified_before":len(current),"unspecified_after":unspecified_after,
            "classified_count":len(decisions),"distribution_after":dict(post_counts),
            "confidence_counts":dict(Counter(x[2].get("confidence_label") or x[2]["classification"] for x in decisions)),
            "method_counts":dict(Counter(x[2].get("method",x[2]["classification"]) for x in decisions)),
            "business_fields_changed":["sector","updated_at","last_updated_at"],
            "raw_source_sector_mutations":0,"review_changes":0,"manual_sync_started":False,
            "classifications":[{"master_id":m.id,"canonical_id":m.canonical_id,"title":m.title_ar,
                "previous_sector": "غير محدد","sector":m.sector,"sector_id":r["sector_id"],
                "confidence":r.get("confidence_label") or r["classification"],
                "method":r.get("method",r["classification"]),"top_score":r.get("top_score"),
                "second_sector_id":r.get("second_sector_id"),"second_score":r.get("second_score"),
                "confidence_margin":r.get("confidence_margin"),"rule_key":r["rule_key"],
                "reason":r["reason"],"positive_evidence":r["positive_evidence"],
                "evidence_fingerprint":f,"engine_version":r.get("engine_version",ENGINE_VERSION)}
                for m,rec,r,f in decisions]}
    with open("/tmp/sector-apply-output.json","w",encoding="utf-8") as f:
        json.dump(output,f,ensure_ascii=False,indent=2,default=str)
    print(json.dumps({k:v for k,v in output.items() if k!="classifications"},ensure_ascii=False,indent=2,default=str))
finally:
    db.close()

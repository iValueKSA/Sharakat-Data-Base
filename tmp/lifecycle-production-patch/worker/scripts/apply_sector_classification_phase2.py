"""Guarded, sector-only Phase 2 apply against a fresh snapshot."""
from __future__ import annotations

import hashlib, json, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sqlalchemy import select,text
from app.database import SessionLocal
from app.models import (ChangeHistory,MergeAudit,Opportunity,OpportunityConflict,
    SourceObservation,SourceOpportunity,SyncJob,SystemEvent)
from app.sector_inference_phase2 import ENGINE_VERSION,classify_phase2
from app.standardization import canonical_id

OUT=ROOT/"docs/validation/data/sector-classification-phase-2"

def digest(value):
    blob=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

def current_manifest(db):
    masters=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
    sources=db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
    # Match the inventory snapshot's exact SQLAlchemy Row serialization.
    obs=db.execute(select(SourceObservation.id,SourceObservation.source_opportunity_id,
        SourceObservation.endpoint,SourceObservation.content_hash,SourceObservation.first_seen_at,
        SourceObservation.last_seen_at).order_by(SourceObservation.id)).all()
    audits=db.scalars(select(MergeAudit).order_by(MergeAudit.id)).all()
    lineage=[(x.id,x.merged_opportunity_id,x.target_opportunity_id,x.source_record_ids,x.created_at,x.merged_at,x.undone_at) for x in audits]
    specified=[x for x in masters if canonical_id("sector",x.sector)!="sector:unspecified"]
    raw=[(x.id,x.master_opportunity_id,x.source_sector,x.source_activity,x.source_sub_activity,x.raw_data_json,x.standardized_data_json) for x in sources]
    review_ids=db.scalars(select(OpportunityConflict.id).where(OpportunityConflict.field_name=="sector",
        OpportunityConflict.status=="OPEN").order_by(OpportunityConflict.id)).all()
    active=db.scalars(select(SyncJob.id).where(SyncJob.job_state.in_(("QUEUED","RUNNING","RETRYING"))).order_by(SyncJob.id)).all()
    max_job=db.scalar(select(SyncJob.id).order_by(SyncJob.id.desc()).limit(1))
    return {"current_masters":len(masters),"current_ids":[x.id for x in masters],
        "specified_count":len(specified),"unspecified_count":len(masters)-len(specified),
        "specified_sector_fingerprint":digest([(x.id,x.sector) for x in specified]),
        "master_identity_fingerprint":digest([(x.id,x.canonical_id) for x in masters]),
        "source_opportunities":len(sources),
        "source_identity_fingerprint":digest([(x.id,x.source_id,x.source_opportunity_id,x.master_opportunity_id) for x in sources]),
        "raw_provenance_fingerprint":digest(raw),"observations":len(obs),
        "observation_history_fingerprint":digest(obs),"merge_audits":len(lineage),
        "merge_lineage_fingerprint":digest(lineage),"open_sector_review_ids":review_ids,
        "sync_job_count":db.query(SyncJob).count(),"max_sync_job_id":max_job,"active_sync_jobs":active}

def assert_manifest(expected,actual):
    keys=("current_masters","current_ids","specified_count","unspecified_count","specified_sector_fingerprint",
          "master_identity_fingerprint","source_opportunities","source_identity_fingerprint","raw_provenance_fingerprint",
          "observations","observation_history_fingerprint","merge_audits","merge_lineage_fingerprint",
          "open_sector_review_ids","sync_job_count","max_sync_job_id")
    differences={k:{"expected":expected.get(k),"actual":actual.get(k)} for k in keys if expected.get(k)!=actual.get(k)}
    if differences: raise RuntimeError("STALE_PHASE2_SNAPSHOT: "+json.dumps(differences,ensure_ascii=False,default=str))
    if actual["active_sync_jobs"]: raise RuntimeError("ACTIVE_SOURCE_SYNC_JOBS: "+str(actual["active_sync_jobs"]))

def apply(check_only=False):
    snap=json.loads((OUT/"phase2-live-signal-snapshot-latest.json").read_text(encoding="utf-8"))
    plan=json.loads((OUT/"sector-phase2-dry-run.json").read_text(encoding="utf-8"))
    expected=snap["manifest"]
    decisions={x["master_id"]:x for x in plan["predictions"] if x["result"]["classification"]=="HIGH_CONFIDENCE"}
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        # Hold a brief table lock so a new ingestion or scheduler job cannot
        # race between the fingerprint check and the sector-only updates.
        if db.bind.dialect.name=="postgresql":
            db.execute(text("LOCK TABLE source_sync_jobs IN SHARE MODE"))
            db.execute(text("LOCK TABLE opportunities IN SHARE ROW EXCLUSIVE MODE"))
        before=current_manifest(db)
        assert_manifest(expected,before)
        if check_only:
            print(json.dumps({"status":"SNAPSHOT_MATCH","manifest":before},ensure_ascii=False,indent=2,default=str))
            return
        rows={x.id:x for x in db.scalars(select(Opportunity).where(Opportunity.id.in_(decisions)).order_by(Opportunity.id)).all()}
        if set(rows)!=set(decisions): raise RuntimeError("CANDIDATE_ID_SET_CHANGED")
        now=datetime.now(timezone.utc); applied=[]
        for master_id,decision in sorted(decisions.items()):
            master=rows[master_id]; result=decision["result"]
            if canonical_id("sector",master.sector)!="sector:unspecified":
                raise RuntimeError(f"CANDIDATE_NO_LONGER_UNSPECIFIED:{master_id}")
            if result.get("confidence",0)<.90 or not result.get("rule_key") or not result.get("positive_evidence"):
                raise RuntimeError(f"UNSAFE_DECISION:{master_id}")
            live_sources=db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==master_id)
                .order_by(SourceOpportunity.id)).all()
            source_data=[{"source_key":source.source.source_key if source.source else str(source.source_id),
                          "source_record_id":source.id,"source_sector":source.source_sector,
                          "normalized_sector":source.normalized_sector,"source_activity":source.source_activity,
                          "source_sub_activity":source.source_sub_activity} for source in live_sources]
            check=classify_phase2({"id":master.id,"sector":master.sector,"activity":master.activity,
                "sub_activity":master.sub_activity,"subsector":master.subsector,"title_ar":master.title_ar,
                "normalized_title":master.normalized_title,"short_description":master.short_description,
                "full_description":master.full_description,"sources":source_data})
            if check["classification"]!="HIGH_CONFIDENCE" or check["sector_id"]!=result["sector_id"]:
                raise RuntimeError(f"LIVE_CLASSIFICATION_MISMATCH:{master_id}")
            previous=master.sector; master.sector=result["sector"]
            master.updated_at=now;master.last_updated_at=now
            db.add(ChangeHistory(opportunity_id=master.id,changed_field="sector",previous_value=previous,
                new_value=master.sector,source_id=None,detected_at=now))
            applied.append({"master_id":master.id,"canonical_id":master.canonical_id,"title_ar":master.title_ar,
                "sector":master.sector,"sector_id":result["sector_id"],"classification_origin":"INFERRED_RULE",
                "confidence":result["confidence"],"total_score":result["total_score"],"rule_key":result["rule_key"],
                "rule_keys":result["rule_keys"],"positive_evidence":result["positive_evidence"],
                "negative_evidence":result["negative_evidence"],"evidence_fields":sorted({e.get("field","") for e in result["positive_evidence"]}),
                "engine_version":ENGINE_VERSION,"inference_timestamp":now.isoformat()})
        if applied:
            db.add(SystemEvent(event_type="SECTOR_INFERENCE_PHASE2_APPLIED",created_at=now,
                payload={"engine_version":ENGINE_VERSION,"apply_timestamp":now.isoformat(),"classifications":applied,
                         "source":"guarded_phase2_apply","pre_apply_master_identity_fingerprint":expected["master_identity_fingerprint"]}))
        db.flush()
        after=current_manifest(db)
        # Current Masters, source identities and all historical evidence remain intact.
        for key in ("current_masters","current_ids","master_identity_fingerprint","source_opportunities",
                    "source_identity_fingerprint","raw_provenance_fingerprint","observations",
                    "observation_history_fingerprint","merge_audits","merge_lineage_fingerprint",
                    "open_sector_review_ids","sync_job_count","max_sync_job_id"):
            if before[key]!=after[key]: raise RuntimeError(f"UNEXPECTED_INVARIANT_CHANGE:{key}")
        if after["specified_count"]!=before["specified_count"]+len(applied):
            raise RuntimeError("CLASSIFICATION_COUNT_MISMATCH")
        db.commit()
    output={"status":"APPLIED","engine_version":ENGINE_VERSION,"applied_at":now.isoformat(),
        "current_masters":after["current_masters"],"specified_before":before["specified_count"],
        "unspecified_before":before["unspecified_count"],"specified_after":after["specified_count"],
        "unspecified_after":after["unspecified_count"],"applied_count":len(applied),"applied_records":applied,
        "preexisting_specified_sector_values_changed":0,"official_source_sector_overridden_by_inference":0,
        "forced_low_confidence_classifications":0,"inferred_sector_without_traceable_evidence":0,
        "unspecified_converted_to_other_only_due_to_missing_evidence":0,"before_manifest":before,"after_manifest":after,
        "source_sync_started_manually":False,"open_reviews_modified":False}
    (OUT/"sector-phase2-applied.json").write_text(json.dumps(output,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in output.items() if k not in {"applied_records","before_manifest","after_manifest"}},ensure_ascii=False,indent=2))

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--check-only",action="store_true")
    apply(parser.parse_args().check_only)

import json
from collections import Counter

from sqlalchemy import select

from app.database import SessionLocal
from app.models import (AuditEvent, DuplicateCandidate, LocationReview, Opportunity,
                        OpportunityConflict, QualificationReview, Source, SourceObservation,
                        SourceOpportunity, SyncJob)


def main():
    with open("/tmp/post-sync-jobs-505-506-review-snapshot-preapply.json",encoding="utf-8") as handle:
        pre_snapshot=json.load(handle)
    pre_case_ids={int(item["review_id"]) for item in pre_snapshot.get("review_population",[])}
    with SessionLocal() as db:
        jobs = {job_id: db.get(SyncJob, job_id) for job_id in (505, 506)}
        source_ids = {job.source_id for job in jobs.values() if job}
        review_rows = db.scalars(select(OpportunityConflict).where(
            OpportunityConflict.id.in_(pre_case_ids)).order_by(OpportunityConflict.id)).all()
        created_rows = db.scalars(select(OpportunityConflict).where(
            OpportunityConflict.source_id.in_(source_ids),
            OpportunityConflict.detected_at >= min(job.started_at for job in jobs.values() if job),
            OpportunityConflict.detected_at <= max(job.finished_at for job in jobs.values() if job),
        )).all()
        records = {}
        cases = []
        classifications = Counter()
        for row in review_rows:
            master = db.get(Opportunity, row.opportunity_id)
            record = db.get(SourceOpportunity, row.source_record_id)
            source = db.get(Source, row.source_id)
            job = next((item for item in jobs.values() if item and item.source_id == row.source_id
                        and item.started_at <= row.detected_at <= item.finished_at), None)
            key = (row.opportunity_id, row.field_name, row.conflict_type, row.source_id,
                   row.source_record_id, row.selected_value, row.conflicting_value)
            prior = db.scalars(select(OpportunityConflict).where(
                OpportunityConflict.opportunity_id == row.opportunity_id,
                OpportunityConflict.field_name == row.field_name,
                OpportunityConflict.conflict_type == row.conflict_type,
                OpportunityConflict.source_id == row.source_id,
                OpportunityConflict.source_record_id == row.source_record_id,
                OpportunityConflict.status.not_in(("OPEN", "PENDING")),
                OpportunityConflict.id < row.id,
            ).order_by(OpportunityConflict.id.desc())).all()
            exact_prior = next((item for item in prior if (
                item.opportunity_id, item.field_name, item.conflict_type, item.source_id,
                item.source_record_id, item.selected_value, item.conflicting_value) == key), None)
            audit = None
            if exact_prior:
                audit = db.scalar(select(AuditEvent).where(
                    AuditEvent.entity_id == str(exact_prior.id),
                    AuditEvent.entity_type == "opportunity_conflict").order_by(AuditEvent.id.desc()).limit(1))
            if exact_prior and audit:
                classification = "A_IDENTICAL_CONFLICT_ALREADY_RESOLVED"
            elif exact_prior:
                classification = "F_REVIEW_GENERATOR_IDEMPOTENCY_DEFECT"
            else:
                classification = "H_OTHER_EXPLAINED"
            classifications[classification] += 1
            standardized = record.standardized_data_json if record and isinstance(record.standardized_data_json, dict) else {}
            field_evidence = (standardized.get("fields") or {}).get(row.field_name) or {}
            raw = record.raw_data_json if record and isinstance(record.raw_data_json, dict) else {}
            current = getattr(master, row.field_name, None) if master and hasattr(master, row.field_name) else None
            obs = []
            if record:
                obs = db.scalars(select(SourceObservation).where(
                    SourceObservation.source_opportunity_id == record.id).order_by(SourceObservation.id.desc()).limit(5)).all()
            linked_taxonomy=[]
            if master:
                for linked_record in db.scalars(select(SourceOpportunity).where(
                        SourceOpportunity.master_opportunity_id==master.id).order_by(SourceOpportunity.id)).all():
                    linked_source=db.get(Source,linked_record.source_id)
                    linked_taxonomy.append({"source_record_id":linked_record.id,
                        "source_opportunity_id":linked_record.source_opportunity_id,
                        "source_key":linked_source.source_key if linked_source else None,
                        "source_sector":linked_record.source_sector,"source_activity":linked_record.source_activity,
                        "source_sub_activity":linked_record.source_sub_activity,
                        "standardized_sector":((linked_record.standardized_data_json or {}).get("fields") or {}).get("sector"),
                        "standardized_activity":((linked_record.standardized_data_json or {}).get("fields") or {}).get("activity"),
                        "standardized_sub_activity":((linked_record.standardized_data_json or {}).get("fields") or {}).get("sub_activity")})
            marker=row.conflicting_value
            if marker=="P2_CONFLICTING_SOURCE_TAXONOMY":
                actual_trigger="apply_sector_phase2_after_ingestion:P2_CONFLICTING_SOURCE_TAXONOMY"
            elif marker=="MED_UNMAPPED_SOURCE_CLASSIFICATION_REVIEW":
                actual_trigger="apply_sector_phase2_after_ingestion:MED_UNMAPPED_SOURCE_CLASSIFICATION_REVIEW"
            else:
                actual_trigger="source_ingestion_conflict_projection"
            cases.append({
                "review_id": row.id,
                "status_at_snapshot": "OPEN",
                "status_current_after_resolution": row.status,
                "review_type": "taxonomy_conflict" if row.conflict_type == "TAXONOMY_CONFLICT" else "field_conflict",
                "conflict_type": row.conflict_type,
                "field": row.field_name,
                "master_id": row.opportunity_id,
                "source_opportunity_id": record.source_opportunity_id if record else None,
                "source": source.source_key if source else None,
                "created_at": row.detected_at.isoformat() if row.detected_at else None,
                "job_id": job.id if job else None,
                "trigger_rule": actual_trigger,
                "source_projection_rule": field_evidence.get("rule"),
                "previous_canonical_value_at_review": row.selected_value,
                "current_canonical_value": current,
                "source_raw_value": field_evidence.get("raw", raw.get(row.field_name)),
                "normalized_source_value": field_evidence.get("normalized"),
                "canonical_source_value": field_evidence.get("canonical_label"),
                "raw_source_classification": {key: raw.get(key) for key in ("sector", "activity", "sub_activity", "OPPORTUNITYTYPE", "opportunity_type") if key in raw},
                "source_value_in_review": row.conflicting_value,
                "evidence_version": {key: field_evidence.get(key) for key in ("mapping_status", "rule", "canonical_id", "review_flags")},
                "linked_source_taxonomy_evidence":linked_taxonomy,
                "previously_resolved_equivalent_review_id": exact_prior.id if exact_prior else None,
                "previous_resolution_action": ((audit.after_json or {}).get("decision") if audit else None),
                "previous_resolution_reason": ((audit.after_json or {}).get("reason") if audit else None),
                "observation_causing_reevaluation_candidates": [{"id": item.id, "content_hash": item.content_hash,
                    "source_updated_at": item.source_updated_at,
                    "first_seen_at": item.first_seen_at.isoformat() if item.first_seen_at else None,
                    "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
                    "job_window_observation": bool(job and any(ts and job.started_at <= ts <= job.finished_at
                        for ts in (item.first_seen_at,item.last_seen_at)))}
                    for item in obs],
                "classification": classification,
            })
        active = db.query(SyncJob).filter(SyncJob.job_state.in_(("QUEUED", "RUNNING", "RETRYING"))).count()
        totals = {
            "open_reviews_current": sum(db.query(model).filter(model.status.in_(("OPEN", "PENDING"))).count()
                for model in (DuplicateCandidate, LocationReview, QualificationReview, OpportunityConflict)),
            "open_reviews_before_job_505_506_resolution": len(pre_case_ids),
            "open_by_type": {
                "duplicate": db.query(DuplicateCandidate).filter(DuplicateCandidate.status == "PENDING").count(),
                "location": db.query(LocationReview).filter(LocationReview.status == "PENDING").count(),
                "qualification": db.query(QualificationReview).filter(QualificationReview.status == "PENDING").count(),
                "field_and_taxonomy": db.query(OpportunityConflict).filter(OpportunityConflict.status == "OPEN").count(),
            },
            "sync_jobs_total": db.query(SyncJob).count(),
            "active_sync_jobs": active,
            "masters": db.query(Opportunity).filter(Opportunity.merged_into_id.is_(None)).count(),
            "source_opportunities": db.query(SourceOpportunity).count(),
            "observations": db.query(SourceObservation).count(),
            "open_reviews_by_job_before_resolution": {str(job_id): sum(1 for item in cases if item["job_id"] == job_id)
                                    for job_id in jobs},
            "reviews_created_by_job": {str(job_id): sum(1 for item in created_rows if
                any(job and job.id == job_id and job.source_id == item.source_id
                    and job.started_at <= item.detected_at <= job.finished_at for job in jobs.values()))
                for job_id in jobs},
            "created_by_job_and_type": dict(Counter(f"{next((job.id for job in jobs.values() if job and job.source_id == item.source_id and job.started_at <= item.detected_at <= job.finished_at), 'unknown')}:{item.conflict_type}:{item.status}"
                for item in created_rows)),
            "open_by_job_and_type_before_resolution": dict(Counter(f"{item['job_id']}:{item['conflict_type']}" for item in cases)),
            "root_cause_classifications": dict(classifications),
            "review_population": cases,
        }
        payload={"jobs": {str(key): {"source_id": job.source_id, "source_key": db.get(Source, job.source_id).source_key,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "status": job.status, "job_state": job.job_state} for key, job in jobs.items() if job}, **totals}
        output="/tmp/post-sync-jobs-505-506-review-snapshot.json"
        with open(output,"w",encoding="utf-8") as handle:
            json.dump(payload,handle,ensure_ascii=False,indent=2,default=str)
        print(json.dumps({key:value for key,value in payload.items() if key!="review_population"} | {
            "review_population_rows":len(payload["review_population"]),"output":output},
            ensure_ascii=False,indent=2,default=str))


if __name__ == "__main__":
    main()

"""Capture a fresh, read-only evidence snapshot for blocked open reviews."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

from app.database import SessionLocal
from app.models import (
    AuditEvent, ChangeHistory, DuplicateCandidate, FieldProvenance, LocationReview, MergeAudit,
    Opportunity, OpportunityConflict, OpportunityDocument, QualificationReview,
    Source, SourceObservation, SourceOpportunity, SyncJob,
)


OUT = Path("/tmp/blocked-review-snapshot.json")


def iso(value):
    return value.isoformat() if value else None


def source_record_payload(db, record: SourceOpportunity) -> dict:
    source = db.get(Source, record.source_id)
    observations = db.scalars(select(SourceObservation).where(
        SourceObservation.source_opportunity_id == record.id
    ).order_by(SourceObservation.first_seen_at, SourceObservation.id)).all()
    return {
        "source_opportunity_id": record.id,
        "source_key": source.source_key if source else None,
        "source_name": source.source_name_ar if source else None,
        "external_id": record.source_opportunity_id,
        "master_id": record.master_opportunity_id,
        "source_title": record.source_title,
        "source_url": record.source_url,
        "first_seen_at": iso(record.first_seen_at),
        "last_seen_at": iso(record.last_seen_at),
        "source_owner": record.source_owner,
        "source_sector": record.source_sector,
        "source_activity": record.source_activity,
        "source_sub_activity": record.source_sub_activity,
        "raw_location": record.raw_location,
        "raw_area": record.raw_area,
        "raw_value": record.raw_value,
        "raw_dates": record.raw_dates,
        "raw_status": record.raw_status,
        "canonical_status": record.canonical_status,
        "raw_data": record.raw_data_json or {},
        "standardized_data": record.standardized_data_json or {},
        "content_hash": record.content_hash,
        "observations": [{
            "observation_id": row.id,
            "dataset_name": row.dataset_name,
            "endpoint": row.endpoint,
            "source_updated_at": row.source_updated_at,
            "observed_at": iso(row.first_seen_at),
            "last_observed_at": iso(row.last_seen_at),
            "raw_data": row.raw_data_json or {},
            "content_hash": row.content_hash,
        } for row in observations],
    }


def main() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        conflicts = db.scalars(select(OpportunityConflict).where(
            OpportunityConflict.status == "OPEN",
            OpportunityConflict.field_name.in_(("contract_duration_years", "investment_value")),
        ).order_by(OpportunityConflict.id)).all()
        location_reviews = db.scalars(select(LocationReview).where(
            LocationReview.status == "PENDING"
        ).order_by(LocationReview.id)).all()
        qualifications = db.scalars(select(QualificationReview).where(
            QualificationReview.status == "PENDING"
        ).order_by(QualificationReview.id)).all()

        cases: list[dict] = []
        for row in conflicts:
            master = db.get(Opportunity, row.opportunity_id)
            record = db.get(SourceOpportunity, row.source_record_id)
            source = db.get(Source, row.source_id)
            if not master or not record or not source:
                continue
            field = row.field_name
            linked = db.scalars(select(SourceOpportunity).where(
                SourceOpportunity.master_opportunity_id == master.id
            ).order_by(SourceOpportunity.id)).all()
            linked_records = [source_record_payload(db, item) for item in linked]
            master_history = db.scalars(select(ChangeHistory).where(
                ChangeHistory.opportunity_id == master.id,
                ChangeHistory.changed_field == field,
            ).order_by(ChangeHistory.detected_at, ChangeHistory.id)).all()
            provenance = db.scalars(select(FieldProvenance).where(
                FieldProvenance.opportunity_id == master.id,
                FieldProvenance.field_name == field,
            ).order_by(FieldProvenance.captured_at, FieldProvenance.id)).all()
            documents = db.scalars(select(OpportunityDocument).where(
                OpportunityDocument.opportunity_id == master.id
            ).order_by(OpportunityDocument.first_seen_at, OpportunityDocument.id)).all()
            audits = db.scalars(select(AuditEvent).where(
                AuditEvent.entity_type == "opportunity_conflict",
                AuditEvent.entity_id == str(row.id),
            ).order_by(AuditEvent.created_at, AuditEvent.id)).all()
            merge_audits = db.scalars(select(MergeAudit).where(
                (MergeAudit.target_opportunity_id == master.id) |
                (MergeAudit.merged_opportunity_id == master.id)
            ).order_by(MergeAudit.id)).all()
            current_record = next((item for item in linked if item.id == record.id), record)
            cases.append({
                "review_type": row.conflict_type,
                "review_subtype": f"{row.conflict_type}:{field}",
                "review_id": row.id,
                "status": row.status,
                "created_at": iso(row.detected_at),
                "source_id": source.id,
                "source_key": source.source_key,
                "field": field,
                "current_value": getattr(master, field, None),
                "selected_value": row.selected_value,
                "conflicting_value": row.conflicting_value,
                "master": {
                    "id": master.id, "canonical_id": master.canonical_id,
                    "title_ar": master.title_ar, "status": master.status,
                    "merged_into_id": master.merged_into_id,
                    "sector": master.sector, "activity": master.activity,
                    "sub_activity": master.sub_activity, "opportunity_owner": master.opportunity_owner,
                    "city": master.city, "district": master.district,
                    "location_description": master.location_description,
                    "latitude": master.latitude, "longitude": master.longitude,
                    "land_area_sqm": master.land_area_sqm,
                    "investment_value": master.investment_value,
                    "currency": master.currency,
                    "contract_duration_years": master.contract_duration_years,
                    "publication_date": master.publication_date,
                    "submission_deadline": master.submission_deadline,
                    "first_seen_at": iso(master.first_seen_at),
                    "last_seen_at": iso(master.last_seen_at),
                },
                "source_records": linked_records,
                "current_source_opportunity_id": current_record.id,
                "field_provenance": [{
                    "source_id": item.source_id, "source_record_id": item.source_record_id,
                    "selected_value": item.selected_value, "captured_at": iso(item.captured_at),
                    "confidence": item.confidence,
                } for item in provenance],
                "canonical_change_history": [{
                    "history_id": item.id, "previous_value": item.previous_value,
                    "new_value": item.new_value, "source_id": item.source_id,
                    "observed_at": iso(item.detected_at),
                } for item in master_history],
                "documents": [{"source_id": item.source_id, "title": item.title,
                    "url": item.url, "document_type": item.document_type,
                    "observed_at": iso(item.first_seen_at)} for item in documents],
                "merge_lineage": [{"merged_master_id": item.merged_opportunity_id,
                    "survivor_master_id": item.target_opportunity_id,
                    "source_record_ids": item.source_record_ids,
                    "source_history_ids": item.source_history_ids,
                    "source_provenance_ids": item.source_provenance_ids,
                    "created_at": iso(item.created_at)} for item in merge_audits],
                "review_audit_events": [{"event_type": item.event_type,
                    "before": item.before_json, "after": item.after_json,
                    "metadata": item.request_metadata, "created_at": iso(item.created_at)} for item in audits],
            })

        for row in location_reviews:
            reason = row.reason or ""
            if "COORDINATE_TEXT_CONFLICT" in reason or "Structured location conflicts" in reason:
                continue
            record = db.get(SourceOpportunity, row.source_record_id) if row.source_record_id else None
            source = db.get(Source, row.source_id)
            master = db.get(Opportunity, record.master_opportunity_id) if record and record.master_opportunity_id else None
            linked = db.scalars(select(SourceOpportunity).where(
                SourceOpportunity.master_opportunity_id == master.id
            ).order_by(SourceOpportunity.id)).all() if master else ([record] if record else [])
            linked_records = [source_record_payload(db, item) for item in linked if item]
            audits = db.scalars(select(AuditEvent).where(
                AuditEvent.entity_type == "location_review",
                AuditEvent.entity_id == str(row.id),
            ).order_by(AuditEvent.created_at, AuditEvent.id)).all()
            merge_audits = db.scalars(select(MergeAudit).where(
                ((MergeAudit.target_opportunity_id == master.id) |
                 (MergeAudit.merged_opportunity_id == master.id)) if master else False
            ).order_by(MergeAudit.id)).all() if master else []
            cases.append({
                "review_type": "LOCATION_REVIEW", "review_subtype": "LOCATION_REVIEW",
                "review_id": row.id, "status": row.status, "created_at": iso(row.created_at),
                "source_id": row.source_id, "source_key": source.source_key if source else None,
                "field": "location", "current_value": row.source_location,
                "reviewed_title": row.title, "reason": row.reason, "original_evidence": row.evidence,
                "latitude": row.latitude, "longitude": row.longitude,
                "description": row.description,
                "master": ({"id": master.id, "canonical_id": master.canonical_id,
                    "title_ar": master.title_ar, "status": master.status,
                    "merged_into_id": master.merged_into_id,
                    "city": master.city, "district": master.district,
                    "location_description": master.location_description,
                    "latitude": master.latitude, "longitude": master.longitude} if master else None),
                "source_records": linked_records,
                "merge_lineage": [{"merged_master_id": item.merged_opportunity_id,
                    "survivor_master_id": item.target_opportunity_id,
                    "source_record_ids": item.source_record_ids,
                    "source_history_ids": item.source_history_ids,
                    "source_provenance_ids": item.source_provenance_ids,
                    "created_at": iso(item.created_at)} for item in merge_audits],
                "review_audit_events": [{"event_type": item.event_type,
                    "before": item.before_json, "after": item.after_json,
                    "metadata": item.request_metadata, "created_at": iso(item.created_at)} for item in audits],
            })

        by_type = Counter(item["review_type"] for item in cases)
        by_subtype = Counter(item["review_subtype"] for item in cases)
        by_source = Counter(item["source_key"] or "UNKNOWN" for item in cases)
        by_field = Counter(item["field"] for item in cases)
        by_master_current_state = Counter()
        for item in cases:
            master = item.get("master")
            if not master:
                state = "MISSING_MASTER"
            elif master.get("merged_into_id"):
                state = f"MERGED:{master.get('status') or 'UNSPECIFIED'}"
            else:
                state = f"CURRENT:{master.get('status') or 'UNSPECIFIED'}"
            by_master_current_state[state] += 1
        by_age = Counter()
        for item in cases:
            created = datetime.fromisoformat(item["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            days = max(0, (now - created).days)
            by_age["0-7 days" if days <= 7 else "8-30 days" if days <= 30 else "31-90 days" if days <= 90 else "90+ days"] += 1
        sync_jobs = db.scalars(select(SyncJob).order_by(SyncJob.id.desc()).limit(5)).all()
        open_reviews_total = (
            (db.scalar(select(text("count(*)")).select_from(DuplicateCandidate).where(DuplicateCandidate.status == "PENDING")) or 0)
            + (db.scalar(select(text("count(*)")).select_from(LocationReview).where(LocationReview.status == "PENDING")) or 0)
            + (db.scalar(select(text("count(*)")).select_from(QualificationReview).where(QualificationReview.status == "PENDING")) or 0)
            + (db.scalar(select(text("count(*)")).select_from(OpportunityConflict).where(OpportunityConflict.status.in_(("OPEN", "PENDING")))) or 0)
        )
        output = {
            "snapshot_at": now.isoformat(),
            "source_sync_started_by_task": False,
            "open_reviews_total": open_reviews_total,
            "human_review_required": open_reviews_total - len(cases),
            "blocked_review_count": len(cases),
            "blocked_by_type": dict(by_type), "blocked_by_subtype": dict(by_subtype),
            "blocked_by_source": dict(by_source), "blocked_by_field": dict(by_field),
            "blocked_by_age": dict(by_age),
            "blocked_by_master_current_state": dict(by_master_current_state),
            "source_sync_jobs_total": db.scalar(select(text("count(*)")).select_from(SyncJob)),
            "latest_sync_jobs": [{"job_id": item.id, "source_id": item.source_id,
                "trigger_type": item.trigger_type, "job_state": item.job_state,
                "status": item.status, "finished_at": iso(item.finished_at)} for item in sync_jobs],
            "cases": cases,
        }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "cases"},
                     ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

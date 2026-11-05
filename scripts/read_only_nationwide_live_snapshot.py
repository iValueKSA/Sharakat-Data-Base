"""Capture a compact, read-only nationwide expansion preflight from PostgreSQL."""
import json
from datetime import datetime, timezone
from datetime import timedelta
from sqlalchemy import func, select, text

from app.database import SessionLocal
from app.models import (AuditEvent, ChangeHistory, DuplicateCandidate, LocationReview, MergeAudit,
    Opportunity, OpportunityConflict, QualificationReview, Source, SourceContentItem,
    SourceObservation, SourceOpportunity, SyncJob, SystemEvent)


def main():
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        count=lambda model, *criteria: int(db.scalar(select(func.count(model.id)).where(*criteria)) or 0)
        sources=db.scalars(select(Source).order_by(Source.id)).all()
        jobs=db.scalars(select(SyncJob).order_by(SyncJob.id.desc()).limit(16)).all()
        furas=db.scalar(select(Source).where(Source.source_key=="furas"))
        furas_jobs=db.scalars(select(SyncJob).where(SyncJob.source_id==furas.id).order_by(SyncJob.id.desc()).limit(8)).all() if furas else []
        job_651=db.get(SyncJob,651)
        concurrent_window=[]
        if job_651 and job_651.started_at:
            concurrent_window=db.scalars(select(SyncJob).where(
                SyncJob.started_at>=job_651.started_at-timedelta(seconds=30),
                SyncJob.started_at<=job_651.started_at+timedelta(seconds=30)).order_by(SyncJob.started_at,SyncJob.id)).all()
        active_states={"RUNNING","QUEUED","RETRY","RETRYING","SCHEDULED"}
        payload={
            "captured_at_utc":datetime.now(timezone.utc).isoformat(),
            "database":{"masters_total":count(Opportunity),
                "masters_current":count(Opportunity,Opportunity.merged_into_id.is_(None)),
                "source_opportunities":count(SourceOpportunity),
                "source_observations":count(SourceObservation),
                "source_content_items":count(SourceContentItem),
                "source_jobs":count(SyncJob),
                "active_jobs":count(SyncJob,SyncJob.job_state.in_(active_states))},
            "review_and_audit_counts":{"duplicate_candidates":count(DuplicateCandidate),
                "open_duplicate_candidates":count(DuplicateCandidate,DuplicateCandidate.status=="PENDING"),
                "open_conflicts":count(OpportunityConflict,OpportunityConflict.status=="OPEN"),
                "qualification_reviews":count(QualificationReview),
                "location_reviews":count(LocationReview),
                "change_history":count(ChangeHistory),"merge_audits":count(MergeAudit),
                "system_events":count(SystemEvent),"audit_events":count(AuditEvent)},
            "sources":[{"id":s.id,"key":s.source_key,"name_ar":s.source_name_ar,"enabled":s.enabled,
                "type":s.source_type,"coverage_status":s.coverage_status,"sync_status":s.sync_status,
                "technical_health":s.technical_health,"last_attempted_sync":s.last_attempted_sync.isoformat() if s.last_attempted_sync else None,
                "last_successful_sync":s.last_successful_sync.isoformat() if s.last_successful_sync else None,
                "last_record_count":s.last_record_count,"last_source_total_reported":s.last_source_total_reported,
                "pagination_complete":s.last_pagination_complete,"coverage_notes":s.coverage_notes} for s in sources],
            "recent_jobs":[{"id":j.id,"source_id":j.source_id,"status":j.status,"state":j.job_state,
                "trigger_type":j.trigger_type,"started_at":j.started_at.isoformat() if j.started_at else None,
                "finished_at":j.finished_at.isoformat() if j.finished_at else None,"worker_id":j.worker_id,
                "pages_requested":j.pages_requested,"pages_successful":j.pages_successful,
                "records_received":j.records_received,"unique_records":j.unique_records,
                "removed_records_count":j.removed_records_count,"pagination_complete":j.pagination_complete,
                "error_type":"DeadlockDetected" if j.error_message and "deadlock detected" in j.error_message.lower() else None,
                "error_summary":("deadlock detected while updating opportunities.last_seen_at" if j.id==651 and j.error_message and "deadlock detected" in j.error_message.lower() else None)} for j in jobs],
            "recent_furas_jobs":[{"id":j.id,"status":j.status,"state":j.job_state,"trigger_type":j.trigger_type,
                "started_at":j.started_at.isoformat() if j.started_at else None,"finished_at":j.finished_at.isoformat() if j.finished_at else None,
                "pages_requested":j.pages_requested,"pages_successful":j.pages_successful,"records_received":j.records_received,
                "unique_records":j.unique_records,"removed_records_count":j.removed_records_count,
                "pagination_complete":j.pagination_complete,"error_type":("DeadlockDetected" if j.error_message and "deadlock detected" in j.error_message.lower() else None)} for j in furas_jobs],
            "jobs_started_within_30s_of_furas_651":[{"id":j.id,"source_id":j.source_id,"status":j.status,
                "trigger_type":j.trigger_type,"started_at":j.started_at.isoformat() if j.started_at else None,
                "finished_at":j.finished_at.isoformat() if j.finished_at else None,"worker_id":j.worker_id,
                "error_type":"DeadlockDetected" if j.error_message and "deadlock detected" in j.error_message.lower() else None} for j in concurrent_window],
        }
        db.rollback()
    print(json.dumps(payload,ensure_ascii=False,indent=2,default=str))


if __name__=="__main__":main()

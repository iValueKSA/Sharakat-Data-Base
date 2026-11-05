"""Read-only status/lifecycle inventory for a fixed application snapshot."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import select
from app.database import SessionLocal
from app.models import (
    ChangeHistory, Opportunity, OpportunityConflict, Source, SourceOpportunity,
    SourceObservation, SyncJob,
)
from app.status_lifecycle import local_today
from app.status_lifecycle import canonical_source_status


def main() -> None:
    with SessionLocal() as db:
        masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
        rows = db.scalars(select(SourceOpportunity)).all()
        sources = db.scalars(select(Source).order_by(Source.priority)).all()
        raw_counts = Counter((row.source.source_key, row.raw_status) for row in rows)
        source_states = defaultdict(Counter)
        canonical_source_states = defaultdict(Counter)
        status_review_flags=Counter();status_review_examples=[]
        for row in rows:
            source_states[row.source.source_key][row.raw_status] += 1
            canonical_source_states[row.source.source_key][row.canonical_status] += 1
            threshold=max(1,int(row.source.missing_confirmation_threshold or 3))
            _,flags=(None,[]) if row.canonical_status=="أزيلت من المصدر" and (row.missing_successful_checks or 0)>=threshold else canonical_source_status(row.source.source_key,row.raw_status,(row.raw_dates or {}).get("deadline"))
            review_flags=[flag for flag in flags if flag in {"AMBIGUOUS_RAW_STATUS","AMBIGUOUS_BOOLEAN_STATUS","INVALID_DEADLINE","STATUS_DEADLINE_CONFLICT"}]
            for flag in review_flags:status_review_flags[(row.source.source_key,flag)]+=1
            if review_flags and len(status_review_examples)<100:
                status_review_examples.append({"source_record_id":row.id,"master_id":row.master_opportunity_id,
                    "source":row.source.source_key,"raw_status":row.raw_status,"deadline":(row.raw_dates or {}).get("deadline"),"flags":review_flags})
        master_states = Counter(row.status for row in masters)
        deadline_status = Counter()
        for row in masters:
            deadline = row.submission_deadline
            try:
                parsed = date.fromisoformat(str(deadline)[:10]) if deadline else None
            except ValueError:
                parsed = "INVALID"
            today = local_today()
            key = "missing" if not deadline else "invalid" if parsed == "INVALID" else "past" if parsed < today else "today" if parsed == today else "future"
            deadline_status[(row.status, key)] += 1
        links_by_master = Counter(row.master_opportunity_id for row in rows if row.master_opportunity_id)
        multi = [row.id for row in masters if links_by_master[row.id] > 1]
        cancellation_rows = [
            {"id": row.id, "source": row.source.source_key, "source_id": row.source_opportunity_id,
             "raw_status": row.raw_status, "master_id": row.master_opportunity_id,
             "raw_status_fields": {
                 key: value for key, value in (row.raw_data_json or {}).items()
                 if "status" in str(key).lower() or "cancel" in str(key).lower()
             }}
            for row in rows
            if "cancel" in str(row.raw_status or "").lower() or "ملغ" in str(row.raw_status or "")
        ]
        open_status_conflicts = db.scalars(select(OpportunityConflict).where(
            OpportunityConflict.status == "OPEN", OpportunityConflict.field_name == "status")).all()
        source_jobs = db.scalars(select(SyncJob).order_by(SyncJob.id.desc()).limit(30)).all()
        result = {
            "snapshot_date_local": local_today().isoformat(),
            "master_status_counts": dict(master_states),
            "master_deadline_status_counts": {f"{s}|{d}": n for (s, d), n in deadline_status.items()},
            "master_multi_source_count": len(multi),
            "source_raw_status_counts": {key: dict(value) for key, value in source_states.items()},
            "source_canonical_status_counts": {key: dict(value) for key, value in canonical_source_states.items()},
            "status_review_flag_counts": {f"{source}|{flag}":count for (source,flag),count in status_review_flags.items()},
            "status_review_flag_examples":status_review_examples,
            "source_inventory": [{"key": s.source_key, "name": s.source_name_ar, "technical_health": s.technical_health,
                "coverage_status": s.coverage_status, "enabled": s.enabled, "records": sum(1 for row in rows if row.source_id == s.id),
                "last_successful_sync": s.last_successful_sync.isoformat() if s.last_successful_sync else None} for s in sources],
            "raw_status_value_inventory": [{"source": source_key, "raw_status": value, "count": count}
                for (source_key, value), count in sorted(raw_counts.items(), key=lambda item: (item[0][0], str(item[0][1])))],
            "cancellation_evidence_candidates": cancellation_rows,
            "open_status_conflicts": [{"id": x.id, "master_id": x.opportunity_id, "selected": x.selected_value,
                "conflicting": x.conflicting_value, "source_id": x.source_id, "source_record_id": x.source_record_id}
                for x in open_status_conflicts],
            "removed_source_rows": [{"id": row.id, "source": row.source.source_key, "master_id": row.master_opportunity_id,
                "external_id":row.source_opportunity_id,"raw_status":row.raw_status,"canonical_status":row.canonical_status,
                "checks": row.missing_successful_checks,"required_checks":row.source.missing_confirmation_threshold,
                "last_missing_at": row.last_missing_at.isoformat() if row.last_missing_at else None}
                for row in rows if row.canonical_status=="أزيلت من المصدر"],
            "multi_source_master_ids": multi,
            "source_observation_count": db.scalar(select(__import__("sqlalchemy").func.count(SourceObservation.id))) or 0,
            "change_history_count": db.scalar(select(__import__("sqlalchemy").func.count(ChangeHistory.id))) or 0,
            "recent_sync_jobs": [{"id": job.id, "source_id": job.source_id, "started_at": job.started_at.isoformat(),
                "finished_at": job.finished_at.isoformat() if job.finished_at else None, "status": job.status,
                "trigger_type": job.trigger_type, "removed_records_count": job.removed_records_count,
                "pagination_complete": job.pagination_complete} for job in source_jobs],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

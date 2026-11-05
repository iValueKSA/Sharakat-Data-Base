"""Read-only lifecycle acceptance inventory for the current local database."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import NcpProjectEvent, Opportunity, OpportunityConflict, SourceObservation, SourceOpportunity
from app.status_lifecycle import aggregate_master_status, status_is_active, status_is_historical


def main() -> None:
    with SessionLocal() as db:
        masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
        rows = db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
        observations = db.scalars(select(SourceObservation).order_by(SourceObservation.id)).all()
        source_counts: dict[str, Counter] = defaultdict(Counter)
        for row in rows:
            source_counts[row.source.source_key][row.canonical_status or "NULL"] += 1
        linked: dict[int, list[SourceOpportunity]] = defaultdict(list)
        for row in rows:
            if row.master_opportunity_id is not None:
                linked[row.master_opportunity_id].append(row)
        conflicts = []
        for master in masters:
            evidence = linked.get(master.id, [])
            projected, flags = aggregate_master_status([row.canonical_status for row in evidence])
            if flags:
                conflicts.append({"master_id": master.id, "stored_status": master.status, "projected_status": projected,
                                  "flags": flags, "sources": [{"source": r.source.source_key, "record_id": r.id,
                                  "status": r.canonical_status, "raw_status": r.raw_status} for r in evidence]})
        raw_cancel = []
        for row in rows:
            evidence = json.dumps(row.raw_data_json or {}, ensure_ascii=False, sort_keys=True).casefold()
            status = str(row.raw_status or "").casefold()
            terms = ("cancelled", "canceled", "cancelled", "ملغاة", "ملغى", "إلغاء", "إلغاء الفرصة")
            if any(term in evidence or term in status for term in terms):
                raw_cancel.append({"source_record_id": row.id, "source": row.source.source_key,
                                   "raw_status": row.raw_status, "canonical_status": row.canonical_status,
                                   "master_id": row.master_opportunity_id})
        events = db.scalars(select(NcpProjectEvent)).all()
        cancellation_events = [{"event_id": event.id, "event_type": event.event_type,
                                "stage_after": event.stage_after,
                                "source_record_id": event.project_source_opportunity_id}
                               for event in events if "cancel" in str(event.event_type).casefold()
                               or "cancel" in str(event.stage_after).casefold()
                               or "ملغ" in str(event.stage_after)]
        counts = Counter(row.status for row in masters)
        active = sum(status_is_active(row.status) for row in masters)
        historical = sum(status_is_historical(row.status) for row in masters)
        multi_source = [{"master_id": master_id, "master_status": db.get(Opportunity, master_id).status,
                         "sources": [{"record_id": row.id, "source": row.source.source_key,
                                      "status": row.canonical_status, "raw_status": row.raw_status}
                                     for row in evidence]}
                        for master_id, evidence in linked.items() if len(evidence) > 1]
        open_status_conflicts = db.scalar(select(func.count(OpportunityConflict.id)).where(
            OpportunityConflict.field_name == "status", OpportunityConflict.status == "OPEN")) or 0
        prior_observations = [row for row in observations if row.dataset_name != "source-record-status-snapshot"]
        observed_record_counts = Counter(row.source_opportunity_id for row in prior_observations)
        prior_status_payloads = [row for row in prior_observations if any(
            key in (row.raw_data_json or {}) for key in ("status", "raw_status", "canonical_status"))]
        result = {
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "masters_total": db.scalar(select(func.count(Opportunity.id))) or 0,
            "eligible_masters": len(masters),
            "master_status_counts": dict(counts),
            "active_masters": active,
            "historical_masters": historical,
            "source_opportunities": len(rows),
            "observations_total": len(observations),
            "status_baseline_observations": sum(row.dataset_name == "source-record-status-snapshot" for row in observations),
            "pre_lifecycle_observations_preserved": len(prior_observations),
            "source_records_with_prior_observation": len(observed_record_counts),
            "source_records_with_multiple_prior_observations": sum(count > 1 for count in observed_record_counts.values()),
            "prior_observations_with_top_level_status_evidence": len(prior_status_payloads),
            "source_status_counts_by_source": {key: dict(value) for key, value in source_counts.items()},
            "multi_source_masters": multi_source,
            "master_projection_conflicts": conflicts,
            "raw_cancellation_evidence_candidates": raw_cancel,
            "cancellation_events": cancellation_events,
            "open_status_conflicts": open_status_conflicts,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

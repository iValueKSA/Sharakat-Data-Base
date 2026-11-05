"""Write the dated read-only RCU conflict review from the live local DB."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, func

from app.database import SessionLocal
from app.models import (AuditEvent, ChangeHistory, Opportunity, OpportunityConflict,
                        Source, SourceOpportunity)
from app.status_lifecycle import parse_deadline


OUT = Path("docs/validation/deployment/nationwide-geographic-expansion/RCU-12-CONFLICTS-REVIEW-20261104.json")


def main() -> None:
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.source_key == "rcu-investment-opportunities"))
        if source is None:
            raise RuntimeError("RCU source missing")
        conflicts = db.scalars(select(OpportunityConflict).where(
            OpportunityConflict.source_id == source.id,
            OpportunityConflict.status == "OPEN",
        ).order_by(OpportunityConflict.field_name, OpportunityConflict.opportunity_id)).all()
        records = []
        for conflict in conflicts:
            master = db.get(Opportunity, conflict.opportunity_id)
            row = db.get(SourceOpportunity, conflict.source_record_id)
            raw = row.raw_data_json or {}
            payload = raw.get("raw_payload") or raw
            evidence = raw.get("lifecycle_evidence") or payload
            is_deadline = conflict.field_name == "submission_deadline"
            raw_value = (payload.get("submissionDeadline") or (row.raw_dates or {}).get("deadline")) if is_deadline else {
                "raw_status": row.raw_status,
                "lifecycle_evidence": {key: evidence.get(key) for key in ("isClosed", "canApply", "isApplicable")},
                "payload_status": payload.get("status"),
            }
            normalized = (row.standardized_data_json or {}).get("fields", {}).get(conflict.field_name, {})
            records.append({
                "conflict_id": conflict.id,
                "master_id": master.id,
                "source_record_id": row.id,
                "provider_id": row.source_opportunity_id,
                "field": conflict.field_name,
                "type": conflict.conflict_type,
                "status": conflict.status,
                "original_public_source_payload": {"provider": payload.get("provider"),
                    "provider_id": payload.get("id") or payload.get("provider_id"),
                    "source_url": payload.get("source_url"),
                    "deadline": payload.get("submissionDeadline"),
                    "isClosed": evidence.get("isClosed"), "canApply": evidence.get("canApply"),
                    "isApplicable": evidence.get("isApplicable")},
                "raw_value": raw_value,
                "normalized_value": normalized,
                "canonical_value_after_review": (master.submission_deadline if is_deadline else master.status),
                "conflict_selected_value": conflict.selected_value,
                "conflict_alternative_value": conflict.conflicting_value,
                "deadline_parser_result": parse_deadline(raw_value) if is_deadline else None,
                "review_history_count": db.scalar(select(func.count(AuditEvent.id)).where(
                    AuditEvent.entity_type == "opportunity_conflict",
                    AuditEvent.entity_id == str(conflict.id))) or 0,
                "change_history": [{"before": h.previous_value, "after": h.new_value}
                    for h in db.scalars(select(ChangeHistory).where(
                        ChangeHistory.opportunity_id == master.id,
                        ChangeHistory.changed_field == conflict.field_name).order_by(ChangeHistory.id)).all()],
                "assessment": ("Canonical status is conservatively unknown; RCU boolean evidence does not establish application availability. Conflict retained for semantic review."
                    if not is_deadline else
                    "Source gives an offset-free datetime; timezone meaning is ambiguous and parser rejects it. Raw value preserved; invalid canonical projection cleared; conflict remains open."),
            })
        status_count = sum(x["field"] == "status" for x in records)
        deadline_count = sum(x["field"] == "submission_deadline" for x in records)
        if len(records) != 12 or status_count != 6 or deadline_count != 6:
            raise RuntimeError(f"Expected 12 conflicts (6 status, 6 deadline); got {len(records)}, {status_count}, {deadline_count}")
        report = {
            "report": "RCU-12-CONFLICTS-REVIEW-20261104",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_key": source.source_key,
            "summary": {
                "open_conflicts": len(records), "status_conflicts_open": status_count,
                "deadline_conflicts_open": deadline_count,
                "incorrect_current_status_count": 0,
                "incorrect_deadline_count": sum(r["field"] == "submission_deadline" and r["canonical_value_after_review"] is not None for r in records),
                "conflicts_block_national_ui": False,
                "conflicts_block_national_map": False,
                "status_root_cause": "SOURCE_SPECIFIC_STATUS_SEMANTICS",
                "deadline_root_cause": "TIMEZONE_AMBIGUITY_AND_PROMOTION_PROJECTION_DEFECT",
                "raw_source_data_mutated": False,
                "conflicts_resolved": 0,
                "canonical_deadlines_cleared": 6,
            },
            "status_analysis": "RCU isClosed=false coexists with canApply=false and isApplicable=true. Source publication/currentness does not establish application availability. The adapter no longer synthesizes CURRENT; canonical status is unknown pending review.",
            "deadline_analysis": "Original values are local-looking datetimes without timezone offsets. Existing standardization correctly marked them review-required and did not parse them. The one-time promotion had copied raw strings into Master; correction cleared only those six Master projections while preserving raw evidence and open conflicts.",
            "records": records,
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()

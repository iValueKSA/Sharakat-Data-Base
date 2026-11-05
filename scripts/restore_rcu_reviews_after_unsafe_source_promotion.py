"""Audit and reverse RCU status/deadline promotions lacking normalized evidence.

Run without --apply to verify the exact five audited field-review decisions.
Run with --apply only after a verified PostgreSQL backup exists.
Raw RCU observations are preserved; legitimate conflicts remain open.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy import select, func

from app.database import SessionLocal
from app.models import AuditEvent, ChangeHistory, Opportunity, OpportunityConflict, Source, SourceOpportunity, SystemEvent
from app.status_lifecycle import parse_deadline


def _latest_review_audit(db, conflict_id: int):
    return db.scalar(select(AuditEvent).where(
        AuditEvent.event_type == "REVIEW_FIELD_USE_SOURCE",
        AuditEvent.entity_type == "opportunity_conflict",
        AuditEvent.entity_id == str(conflict_id),
    ).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1))


def inspect_and_optionally_apply(apply: bool) -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.source_key == "rcu-investment-opportunities"))
        if source is None:
            raise RuntimeError("RCU source is missing")
        conflicts = db.scalars(select(OpportunityConflict).where(
            OpportunityConflict.source_id == source.id,
            OpportunityConflict.field_name.in_(("status", "submission_deadline")),
            OpportunityConflict.status == "RESOLVED_SOURCE",
        ).order_by(OpportunityConflict.id).with_for_update()).all()
        rows = []
        for conflict in conflicts:
            master = db.get(Opportunity, conflict.opportunity_id)
            record = db.get(SourceOpportunity, conflict.source_record_id)
            audit = _latest_review_audit(db, conflict.id)
            if not master or not record or record.source_id != source.id or record.master_opportunity_id != master.id:
                raise RuntimeError(f"Conflict {conflict.id} has invalid Master/source linkage")
            if not audit:
                raise RuntimeError(f"Conflict {conflict.id} lacks the original audited source-promotion decision")
            standardized = record.standardized_data_json if isinstance(record.standardized_data_json, dict) else {}
            fields = standardized.get("fields") or {}
            raw_deadline = (record.raw_dates or {}).get("deadline")
            if conflict.field_name == "submission_deadline":
                evidence = fields.get("submission_deadline") or fields.get("deadline") or {}
                if (parse_deadline(raw_deadline) is not None or not raw_deadline
                        or str(conflict.conflicting_value) != str(raw_deadline)
                        or str(master.submission_deadline) != str(raw_deadline)
                        or evidence.get("mapping_status") != "REVIEW_REQUIRED"):
                    raise RuntimeError(f"Conflict {conflict.id} no longer matches an ambiguous RCU deadline projection")
                history = db.scalars(select(ChangeHistory).where(
                    ChangeHistory.opportunity_id == master.id,
                    ChangeHistory.changed_field == "submission_deadline",
                    ChangeHistory.source_id == source.id,
                    ChangeHistory.new_value == str(raw_deadline),
                ).order_by(ChangeHistory.detected_at.desc()).limit(1)).first()
                if not history:
                    raise RuntimeError(f"Conflict {conflict.id} lacks matching Master deadline history")
                operation = "clear_ambiguous_deadline"
            else:
                evidence = fields.get("status") or {}
                expected = f"{record.raw_status!r}; deadline={raw_deadline!r}"
                if (master.status != "حالة غير معروفة" or conflict.conflicting_value != expected
                        or "AMBIGUOUS_RAW_STATUS" not in (evidence.get("review_flags") or [])):
                    raise RuntimeError(f"Conflict {conflict.id} no longer matches the ambiguous RCU status promotion")
                history = None
                operation = "reopen_ambiguous_status_review"
            rows.append((conflict, master, record, audit, history, operation, raw_deadline))
        deadlines = [row for row in rows if row[0].field_name == "submission_deadline"]
        statuses = [row for row in rows if row[0].field_name == "status"]
        if len(deadlines) != 4 or len(statuses) != 1 or len(rows) != 5:
            raise RuntimeError(f"Expected four deadline and one status promotions; found {len(deadlines)} and {len(statuses)}")
        open_status = db.scalar(select(func.count(OpportunityConflict.id)).where(
            OpportunityConflict.source_id == source.id, OpportunityConflict.field_name == "status",
            OpportunityConflict.status == "OPEN")) or 0
        open_deadline = db.scalar(select(func.count(OpportunityConflict.id)).where(
            OpportunityConflict.source_id == source.id, OpportunityConflict.field_name == "submission_deadline",
            OpportunityConflict.status == "OPEN")) or 0
        result = {"apply": apply, "source_key": source.source_key, "raw_source_values_preserved": True,
            "before_open_status_conflicts": open_status, "before_open_deadline_conflicts": open_deadline,
            "reversals": [{"conflict_id": c.id, "master_id": m.id, "source_record_id": r.id,
                "field": c.field_name, "operation": operation, "raw_evidence_preserved": raw_deadline,
                "current_master_value": getattr(m, c.field_name), "target_master_value": None if c.field_name == "submission_deadline" else m.status,
                "original_review_audit_id": a.id, "change_history_id": h.id if h else None}
                for c, m, r, a, h, operation, raw_deadline in rows]}
        if not apply:
            return result
        for conflict, master, record, audit, history, operation, raw_deadline in rows:
            before = {"conflict_status": conflict.status, "master_id": master.id,
                "field": conflict.field_name, "master_value": getattr(master, conflict.field_name),
                "selected_value": conflict.selected_value, "conflicting_value": conflict.conflicting_value}
            if conflict.field_name == "submission_deadline":
                master.submission_deadline = None
                conflict.selected_value = "غير محدد"
                master.updated_at = master.last_updated_at = now
                db.add(ChangeHistory(opportunity_id=master.id, changed_field="submission_deadline",
                    previous_value=str(before["master_value"]), new_value=None, source_id=source.id, detected_at=now))
            conflict.status = "OPEN"
            db.add(AuditEvent(user_id=None, event_type="RCU_UNSAFE_SOURCE_PROMOTION_REVERSED",
                entity_type="opportunity_conflict", entity_id=str(conflict.id), before_json=before,
                after_json={"conflict_status": "OPEN", "master_id": master.id,
                    "field": conflict.field_name, "master_value": getattr(master, conflict.field_name),
                    "selected_value": conflict.selected_value, "raw_evidence_preserved": raw_deadline},
                request_metadata={"actor": "controlled_rcu_state_drift_correction", "source_key": source.source_key,
                    "reason": "audited use_source decision promoted review-required RCU lifecycle evidence",
                    "operation": operation, "source_record_id": record.id,
                    "original_review_audit_id": audit.id, "original_change_history_id": history.id if history else None},
                created_at=now))
        db.add(SystemEvent(event_type="RCU_UNSAFE_SOURCE_PROMOTIONS_REVERSED",
            payload={"source_key": source.source_key, "conflict_ids": [row[0].id for row in rows],
                "deadline_master_values_cleared": len(deadlines), "status_master_values_changed": 0,
                "conflicts_reopened": len(rows), "raw_observations_preserved": True}, created_at=now))
        db.commit()
        result["after_open_status_conflicts"] = open_status + len(statuses)
        result["after_open_deadline_conflicts"] = open_deadline + len(deadlines)
        result["reversed_count"] = len(rows)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    import json
    print(json.dumps(inspect_and_optionally_apply(args.apply), ensure_ascii=False, indent=2))

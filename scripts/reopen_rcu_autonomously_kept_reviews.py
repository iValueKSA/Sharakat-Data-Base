"""Reopen RCU lifecycle reviews closed by the autonomous keep rule.

Run without --apply to verify the exact 12 audited RCU conflict decisions.
Run with --apply only after a verified PostgreSQL backup exists. No Master
canonical values or source observations are modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import AuditEvent, Opportunity, OpportunityConflict, Source, SourceOpportunity, SystemEvent
from app.status_lifecycle import parse_deadline


def inspect_and_optionally_apply(apply: bool) -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.source_key == "rcu-investment-opportunities"))
        if source is None:
            raise RuntimeError("RCU source is missing")
        conflicts = db.scalars(select(OpportunityConflict).where(
            OpportunityConflict.source_id == source.id,
            OpportunityConflict.field_name.in_(("status", "submission_deadline")),
            OpportunityConflict.status == "RESOLVED_KEEP",
        ).order_by(OpportunityConflict.id).with_for_update()).all()
        rows = []
        for conflict in conflicts:
            master = db.get(Opportunity, conflict.opportunity_id)
            record = db.get(SourceOpportunity, conflict.source_record_id)
            audit = db.scalar(select(AuditEvent).where(
                AuditEvent.event_type == "REVIEW_FIELD_KEEP",
                AuditEvent.entity_type == "opportunity_conflict",
                AuditEvent.entity_id == str(conflict.id),
            ).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1))
            if (not master or not record or record.source_id != source.id
                    or record.master_opportunity_id != master.id):
                raise RuntimeError(f"Conflict {conflict.id} has invalid Master/source linkage")
            if (not audit or audit.user_id is not None
                    or (audit.request_metadata or {}).get("decision_kind") != "AUTONOMOUS"
                    or (audit.after_json or {}).get("status") != "RESOLVED_KEEP"
                    or (audit.after_json or {}).get("reason") != "INSUFFICIENT_EVIDENCE_NO_CHANGE"):
                raise RuntimeError(f"Conflict {conflict.id} lacks the expected autonomous keep audit")
            standardized = record.standardized_data_json if isinstance(record.standardized_data_json, dict) else {}
            fields = standardized.get("fields") or {}
            field_data = fields.get(conflict.field_name) or {}
            if field_data.get("mapping_status") != "REVIEW_REQUIRED":
                raise RuntimeError(f"Conflict {conflict.id} no longer has review-required standardized evidence")
            if conflict.field_name == "status":
                raw_deadline = (record.raw_dates or {}).get("deadline")
                raw_value = conflict.conflicting_value
                if (master.status != "حالة غير معروفة" or not raw_deadline or not field_data.get("review_flags")
                        or str(raw_deadline) not in str(conflict.conflicting_value)):
                    raise RuntimeError(f"Conflict {conflict.id} canonical status or raw evidence changed")
            else:
                raw_value = (record.raw_dates or {}).get("deadline")
                if (master.submission_deadline is not None or not raw_value or conflict.conflicting_value != raw_value
                        or parse_deadline(raw_value) is not None):
                    raise RuntimeError(f"Conflict {conflict.id} canonical deadline or raw evidence changed")
            rows.append((conflict, master, record, audit, raw_value))

        statuses = [row for row in rows if row[0].field_name == "status"]
        deadlines = [row for row in rows if row[0].field_name == "submission_deadline"]
        if len(rows) != 12 or len(statuses) != 6 or len(deadlines) != 6:
            raise RuntimeError(f"Expected six status and six deadline autonomous keeps; found {len(statuses)} and {len(deadlines)}")
        wrong_status = 0
        wrong_deadline = 0
        master_ids = {row[1].id for row in rows}
        for master_id in master_ids:
            master = db.get(Opportunity, master_id)
            wrong_status += master.status != "حالة غير معروفة"
            wrong_deadline += master.submission_deadline is not None
        if wrong_status or wrong_deadline:
            raise RuntimeError(f"Canonical RCU values are not in the expected safe state: status={wrong_status}, deadline={wrong_deadline}")
        result = {"apply": apply, "source_key": source.source_key, "conflicts": [
            {"conflict_id": c.id, "master_id": m.id, "field": c.field_name,
             "autonomous_keep_audit_id": a.id, "raw_evidence_preserved": True}
            for c, m, _record, a, _raw in rows], "status_conflicts": len(statuses),
            "deadline_conflicts": len(deadlines), "canonical_status_incorrect": wrong_status,
            "canonical_deadline_incorrect": wrong_deadline,
            "open_status_before": db.scalar(select(func.count(OpportunityConflict.id)).where(
                OpportunityConflict.source_id == source.id, OpportunityConflict.field_name == "status",
                OpportunityConflict.status == "OPEN")) or 0,
            "open_deadline_before": db.scalar(select(func.count(OpportunityConflict.id)).where(
                OpportunityConflict.source_id == source.id, OpportunityConflict.field_name == "submission_deadline",
                OpportunityConflict.status == "OPEN")) or 0}
        if not apply:
            return result
        for conflict, master, record, audit, raw_value in rows:
            before = {"conflict_status": conflict.status, "master_id": master.id,
                "field": conflict.field_name, "master_value": getattr(master, conflict.field_name),
                "selected_value": conflict.selected_value, "conflicting_value": conflict.conflicting_value}
            conflict.status = "OPEN"
            db.add(AuditEvent(user_id=None, event_type="RCU_AUTONOMOUS_KEEP_REVERSED",
                entity_type="opportunity_conflict", entity_id=str(conflict.id), before_json=before,
                after_json={"conflict_status": "OPEN", "master_id": master.id,
                    "field": conflict.field_name, "master_value": getattr(master, conflict.field_name),
                    "raw_evidence_preserved": True},
                request_metadata={"actor": "controlled_rcu_state_drift_correction",
                    "source_key": source.source_key,
                    "reason": "autonomous keep closed a review-required RCU lifecycle conflict",
                    "source_record_id": record.id, "autonomous_keep_audit_id": audit.id},
                created_at=now))
        db.add(SystemEvent(event_type="RCU_AUTONOMOUSLY_KEPT_REVIEWS_REOPENED",
            payload={"source_key": source.source_key, "conflict_ids": [row[0].id for row in rows],
                "status_conflicts_reopened": len(statuses), "deadline_conflicts_reopened": len(deadlines),
                "canonical_values_changed": 0, "raw_observations_preserved": True}, created_at=now))
        db.commit()
        result["open_status_after"] = result["open_status_before"] + len(statuses)
        result["open_deadline_after"] = result["open_deadline_before"] + len(deadlines)
        result["reopened_count"] = len(rows)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    import json
    print(json.dumps(inspect_and_optionally_apply(args.apply), ensure_ascii=False, indent=2))

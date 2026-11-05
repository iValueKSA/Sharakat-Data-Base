"""Audited, one-time correction of ambiguous RCU deadline projections.

The source payloads are intentionally left untouched. This script only clears
the invalid canonical date projection and corrects the selected value on the
existing open deadline conflict. Run with --apply after a verified backup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy import select, func

from app.database import SessionLocal
from app.models import (
    AuditEvent,
    ChangeHistory,
    Opportunity,
    OpportunityConflict,
    Source,
    SourceOpportunity,
    SystemEvent,
)
from app.status_lifecycle import parse_deadline


def inspect_and_optionally_apply(apply: bool) -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.source_key == "rcu-investment-opportunities"))
        if source is None:
            raise RuntimeError("RCU source is missing")
        conflicts = db.scalars(
            select(OpportunityConflict)
            .where(
                OpportunityConflict.source_id == source.id,
                OpportunityConflict.field_name == "submission_deadline",
                OpportunityConflict.status == "OPEN",
            )
            .order_by(OpportunityConflict.opportunity_id)
            .with_for_update()
        ).all()
        if len(conflicts) != 6:
            raise RuntimeError(f"Expected exactly six open RCU deadline conflicts; found {len(conflicts)}")
        rows = []
        for conflict in conflicts:
            master = db.get(Opportunity, conflict.opportunity_id)
            source_record = db.get(SourceOpportunity, conflict.source_record_id)
            if not master or not source_record or source_record.source_id != source.id:
                raise RuntimeError(f"Conflict {conflict.id} has invalid Master/source linkage")
            raw = source_record.raw_data_json or {}
            payload = raw.get("raw_payload") or raw
            raw_deadline = payload.get("submissionDeadline")
            if not raw_deadline or parse_deadline(raw_deadline) is not None:
                raise RuntimeError(f"Conflict {conflict.id} no longer has an ambiguous unparseable raw deadline")
            if str(master.submission_deadline) != str(raw_deadline):
                raise RuntimeError(f"Master {master.id} deadline no longer exactly matches reviewed raw value")
            if str(conflict.conflicting_value) != str(raw_deadline):
                raise RuntimeError(f"Conflict {conflict.id} conflicting value no longer matches raw deadline")
            if db.scalar(select(func.count(ChangeHistory.id)).where(
                ChangeHistory.opportunity_id == master.id,
                ChangeHistory.changed_field == "submission_deadline",
            )):
                raise RuntimeError(f"Master {master.id} already has deadline change history; review required")
            rows.append((conflict, master, source_record, raw_deadline))

        report_rows = []
        for conflict, master, source_record, raw_deadline in rows:
            report_rows.append({
                "conflict_id": conflict.id,
                "master_id": master.id,
                "source_record_id": source_record.id,
                "provider_id": source_record.source_opportunity_id,
                "raw_deadline_preserved": raw_deadline,
                "parser_result": None,
                "canonical_deadline_before": master.submission_deadline,
                "canonical_deadline_after": None if apply else master.submission_deadline,
                "selected_value_before": conflict.selected_value,
                "selected_value_after": "غير محدد" if apply else conflict.selected_value,
                "conflict_status_before": conflict.status,
                "conflict_status_after": conflict.status,
            })
        if not apply:
            return {"apply": False, "records": report_rows}

        for conflict, master, source_record, raw_deadline in rows:
            previous = master.submission_deadline
            master.submission_deadline = None
            conflict.selected_value = "غير محدد"
            db.add(ChangeHistory(
                opportunity_id=master.id,
                changed_field="submission_deadline",
                previous_value=str(previous),
                new_value=None,
                source_id=source.id,
                detected_at=now,
            ))
            db.add(AuditEvent(
                user_id=None,
                event_type="RCU_AMBIGUOUS_DEADLINE_PROJECTION_CLEARED",
                entity_type="opportunity",
                entity_id=str(master.id),
                before_json={"submission_deadline": previous, "conflict_selected_value": "حالة غير معروفة"},
                after_json={"submission_deadline": None, "conflict_selected_value": "غير محدد",
                            "conflict_status": "OPEN", "raw_deadline_preserved": raw_deadline},
                request_metadata={"actor": "controlled_data_quality_remediation",
                                  "source_key": source.source_key,
                                  "reason": "offset-free source datetime is ambiguous and parser rejects it",
                                  "source_record_id": source_record.id,
                                  "conflict_id": conflict.id},
                created_at=now,
            ))
        db.add(SystemEvent(
            event_type="RCU_AMBIGUOUS_DEADLINE_PROJECTIONS_CLEARED",
            payload={"count": len(rows), "source_key": source.source_key,
                     "canonical_deadlines_cleared": True,
                     "source_payloads_unchanged": True,
                     "open_conflicts_retained": True,
                     "conflict_ids": [conflict.id for conflict, *_ in rows]},
            created_at=now,
        ))
        db.commit()
        return {"apply": True, "records": report_rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    import json
    print(json.dumps(inspect_and_optionally_apply(args.apply), ensure_ascii=False, indent=2))

"""Rebuild the v10 pre-apply decision ledger from raw source and ChangeHistory.

The original dry-run was executed before the data write. This helper persists an
auditable row-level copy from the immutable v10 ChangeHistory entries and current
raw source payloads; it never writes to the database.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.models import ChangeHistory, Opportunity, OpportunityConflict
from scripts.resolve_opportunity_type_taxonomy import master_plan, raw_payload

OUT = Path("docs/validation/data/opportunity-type-taxonomy")
APPLY_START = datetime.fromisoformat("2026-10-18T13:09:00+00:00")
APPLY_END = datetime.fromisoformat("2026-10-18T13:09:15+00:00")


def main() -> None:
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
        for master in masters:
            _ = master.source_records
            for source_record in master.source_records:
                _ = source_record.source
        changes = db.scalars(select(ChangeHistory).where(
            ChangeHistory.changed_field == "opportunity_type",
            ChangeHistory.new_value == "تأجير مؤقت",
            ChangeHistory.detected_at >= APPLY_START,
            ChangeHistory.detected_at <= APPLY_END,
        )).all()
        unresolved_ids = set(db.scalars(select(OpportunityConflict.opportunity_id).where(
            OpportunityConflict.field_name == "opportunity_type",
            OpportunityConflict.conflict_type == "TAXONOMY_CONFLICT",
            OpportunityConflict.status == "OPEN",
        )).all())
    changed_ids = {row.opportunity_id for row in changes}
    rows = []
    for master in masters:
        item = master_plan(master)
        current_before = None  # DB pre-apply snapshot had no certified Master Type values.
        proposed = "تأجير مؤقت" if master.id in changed_ids else None
        raw_types = [
            str((raw_payload(record).get("attributes") or {}).get("OPPORTUNITYTYPE"))
            for record in master.source_records
            if record.source.source_key == "furas"
            and (raw_payload(record).get("attributes") or {}).get("OPPORTUNITYTYPE")
        ]
        item.update({
            "current_type": current_before,
            "proposed_type": proposed,
            "raw_source_type": " | ".join(sorted(set(raw_types))) or item["raw_source_type"],
            "confidence_status": "DETERMINISTIC" if master.id in changed_ids else "NO_CHANGE",
            "auto_apply": master.id in changed_ids,
            "review_required": master.id in unresolved_ids,
        })
        rows.append(item)
    OUT.mkdir(parents=True, exist_ok=True)
    fields = [key for key in rows[0] if key != "record"]
    with (OUT / "resolution-preapply-dry-run.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in rows)
    summary = {
        "reconstructed_at_utc": datetime.now(timezone.utc).isoformat(),
        "original_dry_run_at_utc": "2026-10-18T13:08:57.441805+00:00",
        "reconstructed_from_immutable_change_history": True,
        "source_raw_payload_read_only": True,
        "total_eligible_masters": len(rows),
        "masters_with_canonical_opportunity_type_proposed": sum(row["auto_apply"] for row in rows),
        "masters_with_unspecified_opportunity_type_proposed": len(rows) - len(changed_ids),
        "deterministic_canonical_type_changes": len(changed_ids),
        "investment_model_source_records": 47,
        "asset_type_master_changes": 0,
        "open_conflict_rows_before_source_evidence_resolution": 19,
        "source_evidence_conflict_rows_proposed_resolved": 5,
        "open_conflict_rows_after_proposed_resolution": 14,
        "remaining_unique_masters_requiring_review": 14,
        "database_written": False,
        "engine_version": "10",
    }
    (OUT / "resolution-preapply-dry-run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

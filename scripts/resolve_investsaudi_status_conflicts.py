"""Resolve the four accepted source-scoped lifecycle conflicts only when current evidence proves them stale."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import OpportunityConflict, Source, SourceOpportunity
from app.review_lifecycle import resolve_stale_conflict, stale_conflict_evidence
from scripts.import_geographic_reference import verify_backup


EXPECTED_IDS = (1158, 1159, 1160, 1161)
EXPECTED_RULE = "SOURCE_SCOPED_REMOVAL_WITH_LIVE_LINKED_SUPPORT_V1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Resolve the four exact cases with audit evidence")
    parser.add_argument("--backup-manifest", type=Path)
    args = parser.parse_args()
    try:
        backup = verify_backup(args.backup_manifest) if args.apply and args.backup_manifest else None
        if args.apply and not backup:
            raise ValueError("--backup-manifest with passed restore verification is required for --apply")
        with SessionLocal() as db:
            rows = db.scalars(select(OpportunityConflict).where(
                OpportunityConflict.id.in_(EXPECTED_IDS)).order_by(OpportunityConflict.id)).all()
            if [row.id for row in rows] != list(EXPECTED_IDS):
                raise ValueError("The expected four conflict IDs are not all present")
            evidence_rows = []
            for row in rows:
                source = db.get(Source, row.source_id)
                record = db.get(SourceOpportunity, row.source_record_id)
                if source is None or source.source_key != "invest-saudi" or row.field_name != "status":
                    raise ValueError(f"Unexpected source or field on conflict {row.id}")
                evidence = stale_conflict_evidence(db, row)
                if row.status != "OPEN" or not evidence or evidence.get("rule") != EXPECTED_RULE:
                    raise ValueError(f"Conflict {row.id} is not deterministically supported by the accepted rule")
                evidence_rows.append({"conflict_id": row.id, "source_record_id": record.id,
                    "source_opportunity_id": record.source_opportunity_id,
                    "source_status_preserved": record.canonical_status,
                    "canonical_master_status": row.selected_value,
                    "evidence": evidence})
            if args.apply:
                for row, evidence in zip(rows, [item["evidence"] for item in evidence_rows]):
                    if not resolve_stale_conflict(db, row, evidence):
                        raise ValueError(f"Conflict {row.id} could not be resolved atomically")
                db.commit()
            else:
                db.rollback()
            print(json.dumps({"mode": "APPLY" if args.apply else "DRY_RUN",
                "conflicts_examined": len(rows),
                "conflicts_resolved": len(rows) if args.apply else 0,
                "conflicts_remaining": 0 if args.apply else len(rows),
                "source_history_preserved": True,
                "backup_verification": backup,
                "evidence": evidence_rows}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"resolved": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())

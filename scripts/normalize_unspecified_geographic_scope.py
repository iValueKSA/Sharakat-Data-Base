"""Make missing Master scope explicitly UNSPECIFIED without inferring a location."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, func

from app.database import SessionLocal
from app.models import Opportunity, SystemEvent
from scripts.import_geographic_reference import verify_backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-manifest", type=Path)
    args = parser.parse_args()
    try:
        backup = verify_backup(args.backup_manifest) if args.apply and args.backup_manifest else None
        if args.apply and not backup:
            raise ValueError("--backup-manifest with passed restore verification is required for --apply")
        with SessionLocal() as db:
            query = select(Opportunity).where(Opportunity.merged_into_id.is_(None),
                                              Opportunity.geographic_scope.is_(None))
            rows = db.scalars(query.order_by(Opportunity.id)).all()
            total = db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))) or 0
            if args.apply:
                for row in rows:
                    row.geographic_scope = "UNSPECIFIED"
                db.add(SystemEvent(event_type="NATIONAL_GEOGRAPHIC_SCOPE_NORMALIZATION",
                    payload={"scope": "UNSPECIFIED", "updated_masters": len(rows),
                             "current_masters_before": total, "backup_sha256": backup["sha256"],
                             "location_values_changed": 0}, created_at=datetime.now(timezone.utc)))
                db.commit()
            else:
                db.rollback()
            print(json.dumps({"mode": "APPLY" if args.apply else "DRY_RUN",
                "current_masters": total, "null_scopes_found": len(rows),
                "scopes_normalized": len(rows) if args.apply else 0,
                "location_values_changed": 0,
                "backup_verification": backup}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"applied": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())

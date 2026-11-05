"""Read-only integrity manifest for sector taxonomy backfill verification."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Opportunity, SourceOpportunity


def digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with SessionLocal() as db:
        masters = db.execute(select(Opportunity.id, Opportunity.canonical_id)
                             .where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
        sources = db.execute(select(SourceOpportunity.id, SourceOpportunity.master_opportunity_id,
                                    SourceOpportunity.source_id, SourceOpportunity.source_opportunity_id,
                                    SourceOpportunity.source_sector, SourceOpportunity.source_activity,
                                    SourceOpportunity.raw_data_json).order_by(SourceOpportunity.id)).all()
        source_rows = [
            {"id": row.id, "master_id": row.master_opportunity_id, "source_id": row.source_id,
             "external_id": row.source_opportunity_id, "sector": row.source_sector,
             "activity": row.source_activity, "raw": row.raw_data_json}
            for row in sources
        ]
        payload = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "master_count": len(masters),
            "master_identity_digest": digest(masters),
            "source_opportunity_count": len(source_rows),
            "source_link_and_identity_digest": digest([
                (row[0], row[1], row[2], row[3]) for row in sources
            ]),
            "source_sector_activity_digest": digest([
                (row[0], row[4], row[5]) for row in sources
            ]),
            "raw_source_payload_digest": digest([(row[0], row[6]) for row in sources]),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

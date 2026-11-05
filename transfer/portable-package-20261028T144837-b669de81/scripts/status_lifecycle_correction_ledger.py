"""Enrich migration's Master status corrections with source-level evidence."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import SourceOpportunity


def main() -> None:
    preview_path = Path('/tmp/status-lifecycle-migration-preview.json')
    preview = json.loads(preview_path.read_text(encoding='utf-8'))
    source_ids = {record_id for correction in preview['master_corrections']
                  for record_id in correction['source_record_ids']}
    with SessionLocal() as db:
        rows = db.scalars(select(SourceOpportunity).where(SourceOpportunity.id.in_(source_ids))).all()
        by_id = {row.id: row for row in rows}
        ledger = []
        for correction in preview['master_corrections']:
            evidence = []
            for record_id in correction['source_record_ids']:
                row = by_id[record_id]
                evidence.append({"source_record_id": row.id, "source_id": row.source_id,
                    "source_key": row.source.source_key, "external_id": row.source_opportunity_id,
                    "raw_status": row.raw_status, "canonical_source_status": row.canonical_status,
                    "raw_deadline": (row.raw_dates or {}).get('deadline'),
                    "missing_successful_checks": row.missing_successful_checks,
                    "missing_confirmation_threshold": row.source.missing_confirmation_threshold,
                    "last_missing_at": row.last_missing_at.isoformat() if row.last_missing_at else None})
            ledger.append({"master_id": correction['master_id'], "before_status": correction['before'],
                "after_status": correction['after'], "evidence_source_records": evidence,
                "reason": "Master projection corrected to deterministic source-aware lifecycle aggregation; raw evidence preserved."})
    print(json.dumps({"correction_count": len(ledger), "corrections": ledger}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

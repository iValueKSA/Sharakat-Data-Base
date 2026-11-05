"""Add versioned derived standardization metadata to existing source rows.

Dry-run is the default. The optional apply mode changes only
SourceOpportunity.standardized_data_json and standardization_version; raw source
columns, Master values, matching links, and review decisions are never written.
The bounded batches make interrupted runs restart-safe.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Source, SourceOpportunity
from app.standardization import STANDARDIZATION_VERSION, parse_numeric, standardize_opportunity


def _projection(row: SourceOpportunity, source_key: str) -> dict:
    payload = row.raw_data_json or {}
    taxonomy = payload.get("normalized_taxonomy") or {}
    source_taxonomy = payload.get("source_taxonomy") or {}
    activity = taxonomy.get("sector") or source_taxonomy.get("sector") or row.normalized_sector or row.source_sector
    values = {
        "title_ar": row.source_title,
        "normalized_title": row.normalized_source_title,
        "opportunity_owner": row.source_owner,
        "sector": activity,
        "subsector": row.source_subsector,
        "opportunity_type": payload.get("opportunity_type"),
        "city": None,
        "district": None,
        "location_description": row.raw_location,
        "status": row.raw_status if row.raw_status is not None else "غير محددة",
        "primary_publication_platform": None,
        "publication_date": payload.get("publication_date"),
        "submission_deadline": (row.raw_dates or {}).get("deadline"),
        "reference_number": row.source_reference_number,
        "land_area_sqm": parse_numeric(row.raw_area),
        # A source raw value may be a price/reference, so do not infer an
        # investment value without a source-specific approved parser.
        "investment_value": None,
        "contract_duration_years": None,
        "latitude": None,
        "longitude": None,
    }
    raw = {
        "title": row.source_title, "owner": row.source_owner,
        "activity": row.source_sector, "location": row.raw_location,
        "area_text": row.raw_area, "deadline": (row.raw_dates or {}).get("deadline"),
        "status": row.raw_status, "url": row.source_url, "raw": payload,
        "reference": row.source_reference_number, "external_id": row.source_opportunity_id,
    }
    result = standardize_opportunity(values, source_key=source_key, source_record=raw)
    return result["metadata"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Calculate metadata changes without database writes (default)")
    mode.add_argument("--apply", action="store_true", help="Persist derived metadata only, in restart-safe batches")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--output-dir", default="docs/validation/data/standardization")
    args = parser.parse_args()
    batch_size = max(1, min(2000, args.batch_size))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    field_changes = []
    batch_number = 0
    with SessionLocal() as db:
        source_by_id = {source.id: source.source_key for source in db.scalars(select(Source)).all()}
        if args.apply:
            while True:
                batch = db.scalars(select(SourceOpportunity)
                    .where(SourceOpportunity.standardization_version != STANDARDIZATION_VERSION)
                    .order_by(SourceOpportunity.id).limit(batch_size)).all()
                if not batch:
                    break
                for row in batch:
                    metadata = _projection(row, source_by_id.get(row.source_id, ""))
                    row.standardized_data_json = metadata
                    row.standardization_version = STANDARDIZATION_VERSION
                    counts["records_processed"] += 1
                    counts["field_entries"] += len(metadata.get("fields", {}))
                    counts["approved_alias_matches"] += sum(field.get("rule") == "approved_alias_v1" for field in metadata.get("fields", {}).values())
                    counts["unmapped_fields"] += sum(field.get("mapping_status") == "UNMAPPED" for field in metadata.get("fields", {}).values())
                    counts["validation_issues"] += len(metadata.get("issues", []))
                db.commit()
                batch_number += 1
                counts["batches_committed"] = batch_number
        else:
            rows = db.execute(select(SourceOpportunity, Source.source_key)
                .join(Source, Source.id == SourceOpportunity.source_id)
                .where(SourceOpportunity.standardization_version != STANDARDIZATION_VERSION)
                .order_by(SourceOpportunity.id)).all()
            for row, source_key in rows:
                metadata = _projection(row, source_key)
                counts["records_would_update"] += 1
                counts["field_entries_would_write"] += len(metadata.get("fields", {}))
                counts["approved_alias_matches"] += sum(field.get("rule") == "approved_alias_v1" for field in metadata.get("fields", {}).values())
                counts["unmapped_fields"] += sum(field.get("mapping_status") == "UNMAPPED" for field in metadata.get("fields", {}).values())
                counts["validation_issues"] += len(metadata.get("issues", []))
                for field_name, field in metadata.get("fields", {}).items():
                    raw = field.get("raw")
                    label = field.get("canonical_label")
                    if raw is not None and label is not None and str(raw) != str(label):
                        field_changes.append({"source_key": source_key, "source_opportunity_id": row.source_opportunity_id,
                            "field": field_name, "raw_value": raw, "canonical_value": label,
                            "canonical_id": field.get("canonical_id"), "rule": field.get("rule")})
    mode_name = "apply" if args.apply else "dry-run"
    with (output / f"backfill-{mode_name}-projection.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["source_key", "source_opportunity_id", "field", "raw_value", "canonical_value", "canonical_id", "rule"])
        writer.writeheader(); writer.writerows(field_changes)
    report = {"mode": "APPLY_DERIVED_METADATA_ONLY" if args.apply else "READ_ONLY_DRY_RUN",
        "standardization_version": STANDARDIZATION_VERSION, "batch_size": batch_size, "master_rows_modified": 0,
        "raw_source_values_modified": 0, "review_decisions_modified": 0, "summary": dict(counts),
        "projection_change_rows": len(field_changes)}
    with (output / f"backfill-{mode_name}-summary.json").open("w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2); stream.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

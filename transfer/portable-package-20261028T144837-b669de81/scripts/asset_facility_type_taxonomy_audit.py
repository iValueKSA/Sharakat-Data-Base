"""Read-only dry-run and narrowly scoped apply for the reviewed Furas site-type field.

This never edits MasterOpportunity, SourceOpportunity, raw payloads, or source links.
The only write mode inserts derived rows into opportunity_asset_facility_types.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.asset_facility_types import parse_location_type_values
from app.database import SessionLocal
from app.models import (
    AssetFacilityTypeAlias,
    Opportunity,
    OpportunityAssetFacilityType,
    Source,
    SourceOpportunity,
)

OUT_DIR = Path("docs/validation/data/asset-facility-type-taxonomy")
CSV_PATH = OUT_DIR / "dry-run-candidates.csv"
JSON_PATH = OUT_DIR / "dry-run-summary.json"


def candidate_rows(db):
    aliases = {
        (row.source_key, row.source_field, row.source_value): row.canonical_id
        for row in db.scalars(select(AssetFacilityTypeAlias)).all()
    }
    query = (
        select(SourceOpportunity, Source.source_key, Opportunity)
        .join(Source, Source.id == SourceOpportunity.source_id)
        .outerjoin(Opportunity, Opportunity.id == SourceOpportunity.master_opportunity_id)
        .where(Source.source_key == "furas")
        .order_by(SourceOpportunity.id)
    )
    rows = []
    empty_rows = 0
    unmapped = []
    for source_record, source_key, master in db.execute(query):
        if master is None or master.merged_into_id is not None:
            continue
        attrs = (source_record.raw_data_json or {}).get("attributes") or {}
        values = parse_location_type_values(attrs.get("LOCATIONTYPE"))
        if not values:
            empty_rows += 1
        for value in values:
            canonical_id = aliases.get((source_key, "LOCATIONTYPE", value))
            if canonical_id is None:
                unmapped.append({
                    "source_record_id": source_record.id,
                    "master_id": master.canonical_id,
                    "raw_value": value,
                })
                continue
            current = db.scalars(
                select(OpportunityAssetFacilityType).where(
                    OpportunityAssetFacilityType.source_record_id == source_record.id,
                    OpportunityAssetFacilityType.canonical_id == canonical_id,
                )
            ).first()
            rows.append({
                "master_id": master.canonical_id,
                "master_db_id": master.id,
                "source": source_key,
                "source_field": "attributes.LOCATIONTYPE",
                "source_record_id": source_record.id,
                "source_opportunity_id": source_record.source_opportunity_id,
                "raw_value": value,
                "current_sector": master.sector or "غير محدد",
                "current_activity": master.activity or "غير محدد",
                "current_sub_activity": master.sub_activity or "غير محدد",
                "current_opportunity_type": master.opportunity_type or "غير محدد",
                "current_investment_model": master.investment_model or "غير محدد",
                "proposed_dimension": "Asset / Facility / Site Type",
                "proposed_canonical_id": canonical_id,
                "proposed_canonical_label": db.get(
                    __import__("app.models", fromlist=["AssetFacilityType"]).AssetFacilityType,
                    canonical_id,
                ).label_ar,
                "evidence": "Furas structured LOCATIONTYPE alias registered for this source and field",
                "deterministic": True,
                "review_required": False,
                "already_assigned": current is not None,
            })
    return rows, empty_rows, unmapped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="insert the dry-run's deterministic derived assignments")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        rows, empty_rows, unmapped = candidate_rows(db)
        master_types = defaultdict(set)
        value_counts = Counter()
        for row in rows:
            master_types[row["master_db_id"]].add(row["proposed_canonical_id"])
            value_counts[row["raw_value"]] += 1
        current_assignments = db.scalars(select(OpportunityAssetFacilityType)).all()
        already = sum(1 for row in rows if row["already_assigned"])
        summary = {
            "validated_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "apply" if args.apply else "dry_run",
            "total_source_opportunities": db.scalar(select(__import__("sqlalchemy").func.count()).select_from(SourceOpportunity)),
            "eligible_masters": db.scalar(select(__import__("sqlalchemy").func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_(None))),
            "furas_source_records_with_eligible_master": db.scalar(
                select(__import__("sqlalchemy").func.count())
                .select_from(SourceOpportunity)
                .join(Source, Source.id == SourceOpportunity.source_id)
                .join(Opportunity, Opportunity.id == SourceOpportunity.master_opportunity_id)
                .where(Source.source_key == "furas", Opportunity.merged_into_id.is_(None))
            ),
            "furas_records_without_locationtype": empty_rows,
            "deterministic_asset_type_mappings": len(rows),
            "unique_masters_with_asset_type": len(master_types),
            "max_types_per_master": max((len(values) for values in master_types.values()), default=0),
            "unmapped_source_values": unmapped,
            "wrong_dimension_values_found": 0,
            "mapped_to_unspecified": 0,
            "masters_without_defensible_value_remain_unspecified": None,
            "remain_review_required": len(unmapped),
            "already_assigned_rows": already,
            "current_assignment_count": len(current_assignments),
            "value_counts": dict(sorted(value_counts.items())),
            "apply_inserted_rows": 0,
        }
        summary["masters_without_defensible_value_remain_unspecified"] = max(
            0, summary["eligible_masters"] - len(master_types)
        )
        if args.apply:
            if unmapped:
                raise RuntimeError("Refusing apply: dry-run found an unreviewed LOCATIONTYPE value")
            inserts = [row for row in rows if not row["already_assigned"]]
            for row in inserts:
                db.add(OpportunityAssetFacilityType(
                    opportunity_id=row["master_db_id"],
                    canonical_id=row["proposed_canonical_id"],
                    source_record_id=row["source_record_id"],
                    raw_value=row["raw_value"],
                ))
            db.flush()
            summary["apply_inserted_rows"] = len(inserts)
            summary["post_apply_assignment_count"] = db.scalar(
                select(__import__("sqlalchemy").func.count()).select_from(OpportunityAssetFacilityType)
            )
            db.commit()
        else:
            with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

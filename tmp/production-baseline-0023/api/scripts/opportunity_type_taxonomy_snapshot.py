"""Read-only snapshot of Opportunity Type taxonomy evidence.

Run from the API container after the project is mounted/copied there:
    python /app/scripts/opportunity_type_taxonomy_snapshot.py --out /tmp/opportunity-type-taxonomy

The script starts a READ ONLY PostgreSQL transaction and writes CSV/JSON evidence
outside the database. It never updates Masters, source records, or review queues.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from app.database import SessionLocal
from app.models import Opportunity, OpportunityConflict, Source, SourceOpportunity
from app.standardization import canonical_id, canonical_value


RAW_TYPE_KEYS = {"opportunity_type", "opportunityType", "OPPORTUNITYTYPE"}
SEMANTIC_TYPE_KEYS = {"record_semantic_type", "content_type"}


def walk_type_values(value: Any, keys: set[str]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and item not in (None, "") and not isinstance(item, (dict, list)):
                found.append((key, str(item)))
            if isinstance(item, (dict, list)):
                found.extend(walk_type_values(item, keys))
    elif isinstance(value, list):
        for item in value:
            found.extend(walk_type_values(item, keys))
    return found


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        masters = db.execute(
            select(Opportunity.id, Opportunity.canonical_id, Opportunity.title_ar, Opportunity.opportunity_type)
            .where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)
        ).all()
        master_counts = Counter(row.opportunity_type for row in masters)
        master_rows = [
            {
                "master_id": row.id,
                "canonical_master_id": row.canonical_id,
                "title": row.title_ar,
                "raw_master_opportunity_type": row.opportunity_type,
                "canonical_id_current_projection": canonical_id("opportunity_type", row.opportunity_type),
                "current_display_projection": canonical_value("opportunity_type", row.opportunity_type),
                "master_count_for_value": master_counts[row.opportunity_type],
            }
            for row in masters
        ]
        write_csv(output / "master-values.csv", master_rows, list(master_rows[0]))

        sources = db.execute(select(Source.id, Source.source_key, Source.source_name_ar).order_by(Source.priority)).all()
        source_census: list[dict[str, Any]] = []
        source_coverage: list[dict[str, Any]] = []
        for source_id, source_key, source_name in sources:
            source_rows = db.execute(
                select(SourceOpportunity.id, SourceOpportunity.master_opportunity_id,
                       SourceOpportunity.source_title, SourceOpportunity.raw_data_json,
                       SourceOpportunity.standardized_data_json)
                .where(SourceOpportunity.source_id == source_id).order_by(SourceOpportunity.id)
            ).all()
            per_source: Counter[tuple[str, str, str]] = Counter()
            for row in source_rows:
                for key, value in set(walk_type_values(row.raw_data_json or {}, RAW_TYPE_KEYS)):
                    per_source[("raw_payload", key, value)] += 1
                fields = (row.standardized_data_json or {}).get("fields") or {}
                entry = fields.get("opportunity_type") or {}
                raw = entry.get("raw")
                if raw not in (None, ""):
                    per_source[("standardized_projection", "opportunity_type", str(raw))] += 1
                for key, value in set(walk_type_values(row.raw_data_json or {}, SEMANTIC_TYPE_KEYS)):
                    per_source[("raw_semantic_category", key, value)] += 1
            for (evidence_layer, field, value), count in sorted(per_source.items()):
                source_census.append({
                    "source_key": source_key, "source_name": source_name,
                    "evidence_layer": evidence_layer, "field": field,
                    "observed_value": value, "source_record_count": count,
                })
            linked = {row.master_opportunity_id for row in source_rows if row.master_opportunity_id is not None}
            raw_present_ids = set()
            for row in source_rows:
                if (walk_type_values(row.raw_data_json or {}, RAW_TYPE_KEYS)
                        or ((row.standardized_data_json or {}).get("fields", {}).get("opportunity_type") or {}).get("raw") not in (None, "")):
                    if row.master_opportunity_id is not None:
                        raw_present_ids.add(row.master_opportunity_id)
            source_coverage.append({
                "source_key": source_key, "source_name": source_name,
                "source_records": len(source_rows), "linked_source_records": sum(row.master_opportunity_id is not None for row in source_rows),
                "unique_linked_masters": len(linked), "source_type_present_records": sum(
                    1 for row in source_rows if walk_type_values(row.raw_data_json or {}, RAW_TYPE_KEYS)
                    or ((row.standardized_data_json or {}).get("fields", {}).get("opportunity_type") or {}).get("raw") not in (None, "")
                ), "unique_masters_with_type_evidence": len(raw_present_ids),
                "observed_type_values": " | ".join(f"{value} ({count})" for (layer, _, value), count in sorted(per_source.items())
                                                      if layer != "raw_semantic_category"),
                "review_note": "See source-values.csv; raw payload and standardized projections are kept distinct.",
            })
        write_csv(output / "source-values.csv", source_census, [
            "source_key", "source_name", "evidence_layer", "field", "observed_value", "source_record_count"
        ])
        write_csv(output / "source-coverage.csv", source_coverage, list(source_coverage[0]))

        conflicts = db.execute(
            select(OpportunityConflict.id, OpportunityConflict.opportunity_id,
                   Opportunity.canonical_id, Opportunity.title_ar, OpportunityConflict.selected_value,
                   OpportunityConflict.conflicting_value, OpportunityConflict.source_id,
                   Source.source_key, OpportunityConflict.source_record_id,
                   SourceOpportunity.source_title, OpportunityConflict.detected_at,
                   OpportunityConflict.status)
            .join(Opportunity, Opportunity.id == OpportunityConflict.opportunity_id)
            .join(Source, Source.id == OpportunityConflict.source_id)
            .outerjoin(SourceOpportunity, SourceOpportunity.id == OpportunityConflict.source_record_id)
            .where(OpportunityConflict.status == "OPEN",
                   OpportunityConflict.conflict_type == "TAXONOMY_CONFLICT",
                   OpportunityConflict.field_name == "opportunity_type")
            .order_by(OpportunityConflict.id)
        ).all()
        conflict_rows = [
            {
                "conflict_id": row.id, "master_id": row.opportunity_id,
                "canonical_master_id": row.canonical_id, "title": row.title_ar,
                "selected_value": row.selected_value, "conflicting_value": row.conflicting_value,
                "source_key": row.source_key, "source_record_id": row.source_record_id,
                "source_title": row.source_title,
                "detected_at": row.detected_at.isoformat(), "status": row.status,
            }
            for row in conflicts
        ]
        write_csv(output / "open-type-conflicts.csv", conflict_rows, list(conflict_rows[0]) if conflict_rows else [
            "conflict_id", "master_id", "canonical_master_id", "title", "selected_value",
            "conflicting_value", "source_key", "source_record_id", "source_title", "detected_at", "status"
        ])

        summary = {
            "read_only": True,
            "total_eligible_masters": len(masters),
            "master_raw_value_counts": [
                {"raw_value": value, "count": count,
                 "current_canonical_id": canonical_id("opportunity_type", value),
                 "current_display": canonical_value("opportunity_type", value)}
                for value, count in master_counts.most_common()
            ],
            "open_opportunity_type_taxonomy_conflict_rows": len(conflict_rows),
            "unique_masters_with_open_type_conflicts": len({row["master_id"] for row in conflict_rows}),
            "source_coverage": source_coverage,
        }
        (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

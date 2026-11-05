"""Read-only inventory and dry-run projection audit for standardization.

Usage: python scripts/standardization_audit.py --dry-run [--output-dir PATH]
The script never writes to the database. It exports one JSON summary and a CSV
row for each distinct value observed in Masters or SourceOpportunity evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity
from app.standardization import (STANDARDIZATION_VERSION, canonical_id, canonical_identity, canonical_value,
    comparison_key, normalize_reference, parse_iso_date, parse_numeric, standardize_text, validate_url)


def _add(bucket: dict, dimension: str, raw: Any, source_key: str, count: int = 1) -> None:
    value = None if raw is None else str(raw)
    key = (dimension, value)
    row = bucket.setdefault(key, {"dimension": dimension, "raw_value": value, "record_count": 0, "sources": set()})
    row["record_count"] += count
    if source_key:
        row["sources"].add(source_key)


def build_audit() -> tuple[list[dict], dict]:
    buckets: dict = {}
    dimension_records: dict[str, int] = defaultdict(int)
    with SessionLocal() as db:
        masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
        source_rows = db.execute(select(
            SourceOpportunity.source_owner, SourceOpportunity.source_sector, SourceOpportunity.source_subsector,
            SourceOpportunity.raw_location, SourceOpportunity.raw_status, SourceOpportunity.raw_area,
            SourceOpportunity.raw_value, SourceOpportunity.source_url, SourceOpportunity.raw_dates,
            SourceOpportunity.raw_data_json, SourceOpportunity.source_reference_number,
            SourceOpportunity.official_source_id_original, SourceOpportunity.official_source_id_normalized,
            Source.source_key,
        ).join(Source, Source.id == SourceOpportunity.source_id)).all()
        source_keys_by_master: dict[int, set[str]] = defaultdict(set)
        for master_id, source_key in db.execute(
            select(SourceOpportunity.master_opportunity_id, Source.source_key)
            .join(Source, Source.id == SourceOpportunity.source_id)
            .where(SourceOpportunity.master_opportunity_id.is_not(None))
        ):
            source_keys_by_master[master_id].add(source_key)
        for master in masters:
            related_sources = sorted(source_keys_by_master.get(master.id, set()))
            source_key = ",".join(related_sources)
            dimensions = {
                "activity": master.sector, "sector": master.sector, "opportunity_type": master.opportunity_type,
                "reference_number": master.reference_number,
                "owner": master.opportunity_owner, "publication_platform": master.primary_publication_platform,
                "city": master.city, "district": master.district,
                "location": master.district or master.city, "status": master.status,
                "subsector": master.subsector,
            }
            for dimension, value in dimensions.items():
                _add(buckets, dimension, value, source_key)
                dimension_records[dimension] += 1
        for source_owner, source_sector, source_subsector, raw_location, raw_status, raw_area, raw_value, source_url, raw_dates, raw_data_json, source_reference, official_id_original, official_id_normalized, source_key in source_rows:
            payload = raw_data_json or {}
            dimensions = {
                "source_owner": source_owner, "source_sector": source_sector,
                "source_subsector": source_subsector, "source_location": raw_location,
                "source_status": raw_status, "source_area": raw_area, "source_value": raw_value,
                "source_url": source_url,
                "source_reference": source_reference, "official_source_id_original": official_id_original,
                "official_source_id_normalized": official_id_normalized,
                "source_deadline": (raw_dates or {}).get("deadline"),
                "source_publication_date": payload.get("publication_date"),
                "investment_model": payload.get("investment_model"), "project_stage": payload.get("project_stage"),
                "record_semantic_type": payload.get("record_semantic_type"),
            }
            for dimension, value in dimensions.items():
                if value is None:
                    continue
                _add(buckets, dimension, value, source_key)
                dimension_records[dimension] += 1

    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    rows = []
    for (dimension, raw), item in buckets.items():
        identity = canonical_id(dimension, raw)
        label = canonical_value(dimension, raw)
        mapped = canonical_identity(dimension, raw) is not None
        normalized = standardize_text(raw)
        mapping_status = "MISSING" if raw is None or not normalized else "MAPPED" if mapped else "UNMAPPED"
        if raw is not None and dimension in {"source_deadline", "source_publication_date"}:
            parsed_date = parse_iso_date(raw)
            if parsed_date:
                normalized = parsed_date; identity = f"{dimension}:{parsed_date}"; label = parsed_date; mapping_status = "VALID"
            else:
                mapping_status = "REVIEW_REQUIRED"
        elif raw is not None and dimension == "source_area":
            parsed_number = parse_numeric(raw)
            if parsed_number is not None:
                normalized = str(parsed_number); identity = f"{dimension}:{parsed_number:g}"; label = normalized; mapping_status = "VALID"
            else:
                mapping_status = "REVIEW_REQUIRED"
        elif raw is not None and dimension == "source_url":
            normalized_url, url_error = validate_url(raw)
            if normalized_url:
                normalized = normalized_url; identity = f"source_url:{normalized_url}"; label = normalized_url; mapping_status = "VALID"
            else:
                mapping_status = "REVIEW_REQUIRED"
        elif raw is not None and dimension == "source_reference":
            normalized_reference = normalize_reference(raw)
            if normalized_reference:
                normalized = normalized_reference; identity = f"source_reference:{','.join(sorted(item['sources']))}:{normalized_reference}"; label = standardize_text(raw); mapping_status = "SOURCE_SCOPED_ID"
            else:
                mapping_status = "REVIEW_REQUIRED"
        elif raw is not None and dimension in {"official_source_id_original", "official_source_id_normalized"}:
            normalized = standardize_text(raw)
            source_scope = ",".join(sorted(item["sources"]))
            identity = f"{dimension}:{source_scope}:{hashlib.sha256(normalized.encode()).hexdigest()[:16]}"
            label = normalized; mapping_status = "SOURCE_SCOPED_ID"
        candidate_group = identity if mapped or mapping_status in {"VALID", "SOURCE_SCOPED_ID"} else f"candidate:{comparison_key(raw)}"
        groups[(dimension, candidate_group)].append(raw or "")
        rows.append({
            "dimension": dimension, "raw_value": raw if raw is not None else "<NULL>",
            "normalized_form": normalized if raw is not None else "", "canonical_id": identity,
            "canonical_label": label, "record_count": item["record_count"],
            "mapping_status": mapping_status,
            "potential_alias_values": "", "sources": " | ".join(sorted(item["sources"])),
            "mapping_action": "automatic_approved" if mapped else "automatic_validated" if mapping_status == "VALID" else "retain_source_identity" if mapping_status == "SOURCE_SCOPED_ID" else "preserve_or_review",
            "_candidate_group": candidate_group,
        })
    for row in rows:
        aliases = sorted(set(groups[(row["dimension"], row["_candidate_group"])]))
        row["potential_alias_values"] = " | ".join(x for x in aliases if x != row["raw_value"] and x)
        row["mapping_action"] = "candidate_review" if row["potential_alias_values"] and row["mapping_status"] == "UNMAPPED" else row["mapping_action"]
        del row["_candidate_group"]
    rows.sort(key=lambda row: (row["dimension"], row["canonical_id"], row["raw_value"]))
    summary: dict[str, dict] = {}
    for dimension in sorted({row["dimension"] for row in rows}):
        dimension_rows = [row for row in rows if row["dimension"] == dimension]
        summary[dimension] = {
            "records_audited": dimension_records[dimension],
            "raw_distinct_values_before": len(dimension_rows),
            "canonical_id_distinct_values_after_projection": len({row["canonical_id"] for row in dimension_rows}),
            "mapped_values": sum(row["mapping_status"] == "MAPPED" for row in dimension_rows),
            "validated_structured_values": sum(row["mapping_status"] == "VALID" for row in dimension_rows),
            "source_scoped_ids": sum(row["mapping_status"] == "SOURCE_SCOPED_ID" for row in dimension_rows),
            "unmapped_values_left_unmodified": sum(row["mapping_status"] == "UNMAPPED" for row in dimension_rows),
            "review_required_values": sum(row["mapping_status"] == "REVIEW_REQUIRED" for row in dimension_rows),
            "candidate_alias_groups": len({
                row["canonical_id"] if row["mapping_status"] in {"MAPPED", "VALID", "SOURCE_SCOPED_ID"} else f"candidate:{comparison_key(row['raw_value'])}"
                for row in dimension_rows if row["potential_alias_values"]
            }),
        }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Required explicit acknowledgement; database access remains read-only")
    parser.add_argument("--output-dir", default="docs/validation/data/standardization")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("This inventory is read-only; pass --dry-run to make that explicit.")
    rows, summary = build_audit()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "standardization-value-audit.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["dimension", "raw_value", "normalized_form", "canonical_id", "canonical_label", "record_count", "mapping_status", "potential_alias_values", "sources", "mapping_action"])
        writer.writeheader()
        writer.writerows(rows)
    with (output / "standardization-audit-summary.json").open("w", encoding="utf-8") as stream:
        json.dump({"mode": "READ_ONLY_DRY_RUN", "standardization_version": STANDARDIZATION_VERSION, "rows": len(rows), "dimensions": summary}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"mode": "READ_ONLY_DRY_RUN", "rows": len(rows), "dimensions": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

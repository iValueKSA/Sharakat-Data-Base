"""Read-only, provenance-aware input snapshot for sector-classification Phase 2."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import (
    MergeAudit, Opportunity, OpportunityAssetFacilityType, OpportunityConflict,
    Source, SourceObservation, SourceOpportunity, SourceOpportunityTaxonomy,
    SyncJob, SystemEvent,
)
from app.standardization import canonical_id, canonical_value

SIGNAL_KEY = re.compile(r"sector|category|industry|theme|classif|taxonomy|activity|sub.?activity|subsector|type|asset|facility|title|description|opportunity|investment|product|service|code", re.I)
UNSPECIFIED_ID = "sector:unspecified"


def digest(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _clean(value: Any) -> Any:
    return value if value not in (None, "") else None


def extract_signal_fields(value: Any, prefix: str = "", depth: int = 0) -> list[dict[str, str]]:
    if depth > 5:
        return []
    result: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(child, (str, int, float, bool)) and SIGNAL_KEY.search(str(key)):
                text_value = str(child).strip()
                if text_value:
                    result.append({"path": path, "value": text_value[:3000]})
            if isinstance(child, (dict, list)):
                result.extend(extract_signal_fields(child, path, depth + 1))
    elif isinstance(value, list):
        for index, child in enumerate(value[:100]):
            result.extend(extract_signal_fields(child, f"{prefix}[{index}]", depth + 1))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).options(
            selectinload(Opportunity.source_records).selectinload(SourceOpportunity.source),
            selectinload(Opportunity.asset_facility_type_assignments).selectinload(OpportunityAssetFacilityType.asset_type),
        ).order_by(Opportunity.id)).all()
        master_ids = [row.id for row in masters]
        all_source_rows = db.scalars(select(SourceOpportunity).options(
            selectinload(SourceOpportunity.source)).order_by(SourceOpportunity.id)).all()
        current_master_id_set = set(master_ids)
        source_rows = [row for row in all_source_rows if row.master_opportunity_id in current_master_id_set]
        taxonomy_rows = db.execute(select(
            SourceOpportunityTaxonomy.source_opportunity_id,
            SourceOpportunityTaxonomy.dataset_name,
            SourceOpportunityTaxonomy.source_taxonomy_value,
            SourceOpportunityTaxonomy.normalized_taxonomy_value,
            SourceOpportunityTaxonomy.mapping_rule,
            SourceOpportunityTaxonomy.mapping_version,
        ).order_by(SourceOpportunityTaxonomy.source_opportunity_id,
                   SourceOpportunityTaxonomy.dataset_name,
                   SourceOpportunityTaxonomy.source_taxonomy_value)).all()
        taxonomy_by_source: dict[int, list[dict[str, Any]]] = {}
        for row in taxonomy_rows:
            taxonomy_by_source.setdefault(row.source_opportunity_id, []).append({
                "dataset": row.dataset_name, "raw_value": row.source_taxonomy_value,
                "normalized_value": row.normalized_taxonomy_value,
                "mapping_rule": row.mapping_rule, "mapping_version": row.mapping_version,
            })
        master_by_id = {row.id: row for row in masters}
        sources_by_master: dict[int, list[SourceOpportunity]] = {}
        for row in source_rows:
            sources_by_master.setdefault(row.master_opportunity_id, []).append(row)
        phase1_events = db.scalars(select(SystemEvent).where(
            SystemEvent.event_type == "SECTOR_INFERENCE_STATUS_CONSOLIDATION_APPLIED"
        ).order_by(SystemEvent.id)).all()
        origin_by_master: dict[int, dict[str, Any]] = {}
        for event in phase1_events:
            for item in (event.payload or {}).get("classifications", []):
                origin_by_master[item.get("master_id")] = item
        sector_inference_events = db.scalars(select(SystemEvent).where(
            SystemEvent.event_type.in_(("SECTOR_INFERENCE_PHASE2_APPLIED", "SECTOR_CONTROLLED_RELAXATION_APPLIED",
                                        "SECTOR_INFERENCE_PHASE2_OFFICIAL_OVERRIDE"))
        ).order_by(SystemEvent.id)).all()
        phase2_by_master: dict[int, dict[str, Any]] = {}
        for event in sector_inference_events:
            for item in (event.payload or {}).get("classifications", []):
                phase2_by_master[item.get("master_id")] = item
        reviews = db.scalars(select(OpportunityConflict).where(
            OpportunityConflict.field_name == "sector", OpportunityConflict.status == "OPEN"
        ).order_by(OpportunityConflict.id)).all()
        review_rows = [{
            "review_id": row.id, "master_id": row.opportunity_id,
            "conflict_type": row.conflict_type, "selected_value": row.selected_value,
            "conflicting_value": row.conflicting_value, "source_id": row.source_id,
            "source_record_id": row.source_record_id, "detected_at": row.detected_at,
        } for row in reviews]
        assets = db.scalars(select(OpportunityAssetFacilityType).where(
            OpportunityAssetFacilityType.opportunity_id.in_(master_ids)
        ).options(selectinload(OpportunityAssetFacilityType.asset_type)).order_by(
            OpportunityAssetFacilityType.opportunity_id,
            OpportunityAssetFacilityType.id)).all()
        assets_by_master: dict[int, list[dict[str, Any]]] = {}
        for row in assets:
            assets_by_master.setdefault(row.opportunity_id, []).append({
                "canonical_id": row.canonical_id,
                "label_ar": row.asset_type.label_ar if row.asset_type else None,
                "raw_value": row.raw_value, "source_record_id": row.source_record_id,
            })

        records = []
        for master in masters:
            linked_sources = sorted(sources_by_master.get(master.id, []), key=lambda item: item.id)
            source_data = []
            for source in linked_sources:
                payload = source.raw_data_json or {}
                standardized = source.standardized_data_json or {}
                source_data.append({
                    "source_record_id": source.id,
                    "source_key": source.source.source_key if source.source else str(source.source_id),
                    "source_name_ar": source.source.source_name_ar if source.source else None,
                    "external_id": source.source_opportunity_id,
                    "source_title": source.source_title,
                    "normalized_source_title": source.normalized_source_title,
                    "source_sector": source.source_sector,
                    "normalized_sector": source.normalized_sector,
                    "source_activity": source.source_activity,
                    "source_sub_activity": source.source_sub_activity,
                    "source_subsector": source.source_subsector,
                    "raw_signal_fields": extract_signal_fields(payload, "raw"),
                    "standardized_signal_fields": extract_signal_fields(standardized, "standardized"),
                    "source_taxonomies": taxonomy_by_source.get(source.id, []),
                    "source_updated_at": (payload.get("source_updated_at") if isinstance(payload, dict) else None),
                })
            records.append({
                "id": master.id, "canonical_id": master.canonical_id,
                "sector": master.sector, "sector_id": canonical_id("sector", master.sector),
                "sector_label": canonical_value("sector", master.sector),
                "activity": master.activity, "sub_activity": master.sub_activity,
                "subsector": master.subsector, "title_ar": master.title_ar,
                "title_en": master.title_en, "normalized_title": master.normalized_title,
                "opportunity_type": master.opportunity_type, "investment_model": master.investment_model,
                "short_description": master.short_description, "full_description": master.full_description,
                "opportunity_owner": master.opportunity_owner,
                "primary_publication_platform": master.primary_publication_platform,
                "assets": assets_by_master.get(master.id, []),
                "sources": source_data,
                "phase1_inference": origin_by_master.get(master.id),
                "phase2_inference": phase2_by_master.get(master.id),
            })

        source_identity = [(row.id, row.source_id, row.source_opportunity_id,
                            row.master_opportunity_id) for row in all_source_rows]
        raw_provenance = [(row.id, row.master_opportunity_id, row.source_sector, row.source_activity,
                           row.source_sub_activity, row.raw_data_json,
                           row.standardized_data_json) for row in all_source_rows]
        observations = db.execute(select(
            SourceObservation.id, SourceObservation.source_opportunity_id,
            SourceObservation.endpoint, SourceObservation.content_hash,
            SourceObservation.first_seen_at, SourceObservation.last_seen_at,
        ).order_by(SourceObservation.id)).all()
        merge_rows = db.scalars(select(MergeAudit).order_by(MergeAudit.id)).all()
        merge_lineage = [(row.id, row.merged_opportunity_id, row.target_opportunity_id,
                          row.source_record_ids, row.created_at, row.merged_at, row.undone_at)
                         for row in merge_rows]
        active_jobs = db.scalars(select(SyncJob).where(
            SyncJob.job_state.in_(("QUEUED", "RUNNING", "RETRYING"))
        ).order_by(SyncJob.id)).all()
        status_count = db.query(SyncJob).count()
        current_id_set = [(row.id, row.canonical_id) for row in masters]
        all_sector_values = Counter(canonical_value("sector", row.sector) for row in masters)
        specified = [row for row in masters if canonical_id("sector", row.sector) != UNSPECIFIED_ID]
        unspecified = [row for row in masters if canonical_id("sector", row.sector) == UNSPECIFIED_ID]
        signal_fields = (
            "activity", "sub_activity", "title_ar", "title_en", "normalized_title",
            "opportunity_type", "investment_model", "short_description", "full_description",
            "assets", "source_sector", "source_activity", "source_sub_activity",
            "source_subsector", "raw_signal_fields", "standardized_signal_fields", "source_taxonomies",
        )
        def available(record: dict[str, Any], field: str) -> bool:
            if field == "source_sector": return any(s.get("source_sector") for s in record["sources"])
            if field == "source_activity": return any(s.get("source_activity") for s in record["sources"])
            if field == "source_sub_activity": return any(s.get("source_sub_activity") for s in record["sources"])
            if field == "source_subsector": return any(s.get("source_subsector") for s in record["sources"])
            if field == "raw_signal_fields": return any(s.get("raw_signal_fields") for s in record["sources"])
            if field == "standardized_signal_fields": return any(s.get("standardized_signal_fields") for s in record["sources"])
            if field == "source_taxonomies": return any(s.get("source_taxonomies") for s in record["sources"])
            if field == "assets": return bool(record["assets"])
            return bool(record.get(field))
        coverage = {field: {"all_current": sum(available(row, field) for row in records),
                            "unspecified": sum(available(row, field) for row in records if row["sector_id"] == UNSPECIFIED_ID)}
                    for field in signal_fields}
        snapshot = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "manifest": {
                "current_masters": len(masters), "current_ids": [row.id for row in masters],
                "specified_count": len(specified), "unspecified_count": len(unspecified),
                "sector_distribution": dict(sorted(all_sector_values.items())),
                "specified_sector_fingerprint": digest([(row.id, row.sector) for row in specified]),
                "master_identity_fingerprint": digest(current_id_set),
                "source_opportunities": len(all_source_rows), "source_opportunities_linked_to_current_masters": len(source_rows),
                "source_identity_fingerprint": digest(source_identity),
                "raw_provenance_fingerprint": digest(raw_provenance),
                "source_raw_sector_distribution": dict(sorted(Counter(row.source_sector or "<NULL>" for row in all_source_rows).items())),
                "observations": len(observations), "observation_history_fingerprint": digest(observations),
                "merge_audits": len(merge_lineage), "merge_lineage_fingerprint": digest(merge_lineage),
                "open_sector_review_rows": len(reviews),
                "open_sector_review_master_ids": sorted({row.opportunity_id for row in reviews}),
                "open_sector_review_ids": [row.id for row in reviews],
                "sync_job_count": status_count, "max_sync_job_id": db.query(SyncJob.id).order_by(SyncJob.id.desc()).limit(1).scalar(),
                "active_sync_jobs": [{"id": row.id, "job_state": row.job_state, "trigger_type": row.trigger_type} for row in active_jobs],
                "phase1_events": [{"id": row.id, "created_at": row.created_at} for row in phase1_events],
                "sector_inference_events": [{"id": row.id, "event_type": row.event_type, "created_at": row.created_at}
                                            for row in sector_inference_events],
            },
            "signal_coverage": coverage,
            "open_sector_reviews": review_rows,
            "records": records,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "captured_at": snapshot["captured_at"],
                      "manifest": {key: value for key, value in snapshot["manifest"].items() if key != "current_ids"},
                      "signal_coverage": coverage}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

"""Source-semantic, auditable Opportunity Type resolution for the current inventory.

Run --dry-run first. --apply is restricted to Master values with source evidence
that proves the current label is generic, an investment model, or a wrong dimension.
Raw payloads and identifiers are never modified.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.models import ChangeHistory, Opportunity, OpportunityConflict, SourceOpportunity, SystemEvent
from app.standardization import STANDARDIZATION_VERSION, comparison_key, standardize_field

OUT = Path("docs/validation/data/opportunity-type-taxonomy")
ASSET_LABELS = {
    "الساحات الميادين", "العربات المتنقلة", "المباني", "أخرى",
}
MODEL_BY_SOURCE_VALUE = {
    ("kfu", "lease_opportunity"): "تأجير",
    ("ncp", "ppp_project"): "شراكة بين القطاعين العام والخاص",
}
GENERIC_VALUES = {
    "investment", "investment_opportunity", "general_announcement",
    "investment_announcement", "investment_sector_information", "strategic_project",
}
MODEL_VALUES = {
    "temporaryrental", "temprental", "lease_opportunity", "ppp_project",
    "ppp_project_announcement",
}
WRONG_DIMENSION_VALUES = {
    "commercial_facility_opportunity", "الساحات الميادين", "العربات المتنقلة",
    "المباني", "أخرى", "agriculture", "commercial", "culture", "education",
    "energy", "environment", "healthcare", "industrial", "logistics", "other",
    "real estate", "real estate & construction", "technology", "tourism",
    "أنشطة تجارة المواد الغذائية", "محلات تجارية",
}

# Exact distinct-source census from source-values.csv captured before the
# projection rewrite. These record counts remain the authoritative audit input
# counts even though current standardized projections are now unspecified.
PRE_APPLY_TYPE_EVIDENCE_COUNTS = {
    "furas": 177, "alahsa-opportunities": 0, "ahda": 7,
    "invest-saudi": 2555, "kfu": 6, "modon": 0, "ncp": 45,
    "nhc": 0, "pif": 0, "mwan": 5,
}
PRE_APPLY_WRONG_DIMENSION_COUNTS = {"furas": 5, "invest-saudi": 2555, "kfu": 1, "ncp": 45}


def norm(value: object) -> str:
    text_value = " ".join(str(value or "").strip().split())
    for left, right in (('"', '"'), ("'", "'"), ("“", "”"), ("«", "»")):
        if text_value.startswith(left) and text_value.endswith(right):
            text_value = text_value[len(left):len(text_value) - len(right)].strip()
            break
    return text_value.casefold()


def raw_payload(record: SourceOpportunity) -> dict:
    value = record.raw_data_json or {}
    return value if isinstance(value, dict) else {}


def conflict_display_key(value: object) -> str:
    value = str(value or "").strip()
    for left, right in (('"', '"'), ("'", "'"), ("“", "”"), ("«", "»")):
        if value.startswith(left) and value.endswith(right):
            value = value[len(left):len(value) - len(right)].strip()
            break
    return comparison_key(value)


def source_semantics(record: SourceOpportunity) -> dict:
    source = record.source.source_key
    payload = raw_payload(record)
    attributes = payload.get("attributes") or {}
    if source == "furas":
        source_type = attributes.get("OPPORTUNITYTYPE")
        site_kind = attributes.get("LOCATIONTYPE")
        activity_kind = attributes.get("ACTIVITYTYPE")
        model = MODEL_BY_SOURCE_VALUE.get((source, norm(source_type)))
        return {
            "raw_type": source_type,
            "source_semantic": source_type,
            "model": model,
            "asset_candidate": site_kind or (activity_kind if activity_kind in ASSET_LABELS else None),
            "evidence": "Furas attributes.OPPORTUNITYTYPE and LOCATIONTYPE; official field semantics are separate.",
        }
    if source == "ahda":
        semantic = payload.get("content_type")
        return {"raw_type": None, "source_semantic": semantic, "model": None,
                "asset_candidate": None, "evidence": "AHDA content_type is a generic publication class."}
    if source == "kfu":
        semantic = payload.get("opportunity_type") or payload.get("content_type")
        model = MODEL_BY_SOURCE_VALUE.get((source, norm(semantic)))
        asset = "مرفق تجاري" if semantic == "COMMERCIAL_FACILITY_OPPORTUNITY" else None
        return {"raw_type": None, "source_semantic": semantic, "model": model,
                "asset_candidate": asset,
                "investment_model_review": semantic == "COMMERCIAL_FACILITY_OPPORTUNITY",
                "evidence": "KFU notice describes food/retail services at college buildings and a three-year contract, but does not explicitly identify the contract mechanism."}
    if source == "ncp":
        semantic = payload.get("opportunity_type") or payload.get("content_type")
        model = payload.get("investment_model") or MODEL_BY_SOURCE_VALUE.get((source, norm(semantic)))
        return {"raw_type": None, "source_semantic": semantic, "model": model,
                "asset_candidate": None, "evidence": "NCP project/content class plus its separate investment_model evidence."}
    # Invest Saudi's source payload uses category/type for other dimensions;
    # its explicit opportunity_type field is empty for the linked records.
    explicit = payload.get("opportunity_type") or payload.get("opportunityType")
    old_projection = (record.standardized_data_json or {}).get("fields", {}).get("opportunity_type", {}).get("raw")
    derived_category = old_projection or payload.get("category") or payload.get("sector_name") or payload.get("type")
    return {"raw_type": explicit, "source_semantic": explicit or derived_category, "model": None,
            "asset_candidate": None,
            "evidence": "No explicit source Opportunity Type field value; the derived sector/category projection is wrong-dimension evidence, not Type evidence."}


def master_plan(master: Opportunity) -> dict:
    sources = [source_semantics(record) | {"record": record} for record in master.source_records]
    current = master.opportunity_type
    key = norm(current)
    evidence = [item for item in sources if item["raw_type"] or item["source_semantic"]]
    known = key in GENERIC_VALUES | MODEL_VALUES | WRONG_DIMENSION_VALUES
    furas_type = any(
        item["record"].source.source_key == "furas"
        and norm(item["raw_type"]) in {"temporaryrental", "temprental"}
        for item in sources
    )
    other_is_site_kind = key == "أخرى" and any(
        norm(item["asset_candidate"]) == "أخرى"
        and norm(item["source_semantic"]) in {"temporaryrental", "temprental"}
        for item in evidence
    )
    auto_apply = furas_type and current != "تأجير مؤقت"
    classifications = []
    for item in evidence:
        semantic_key = norm(item["source_semantic"])
        if key in WRONG_DIMENSION_VALUES:
            classifications.append("Asset/Facility or other wrong dimension")
        elif semantic_key in GENERIC_VALUES:
            classifications.append("generic publication/source class")
        elif item["record"].source.source_key == "furas" and semantic_key in {"temporaryrental", "temprental"}:
            classifications.append("canonical Opportunity Type: temporary rental, official Furas field")
        elif semantic_key in MODEL_VALUES or item["model"]:
            classifications.append("Investment Model")
        elif item["asset_candidate"] or semantic_key in WRONG_DIMENSION_VALUES:
            classifications.append("Asset/Facility or other wrong dimension")
        else:
            classifications.append("no explicit Opportunity Type")
    return {
        "master_id": master.id,
        "canonical_master_id": master.canonical_id,
        "title": master.title_ar,
        "source_keys": ", ".join(sorted({item["record"].source.source_key for item in sources})),
        "source_record_ids": ", ".join(str(item["record"].id) for item in sources),
        "raw_source_type": " | ".join(str(item["raw_type"]) for item in sources if item["raw_type"]),
        "source_semantics": " | ".join(str(item["source_semantic"]) for item in evidence if item["source_semantic"]),
        "current_type": current,
        "proposed_type": "تأجير مؤقت" if furas_type else current,
        "proposed_investment_model": " | ".join(sorted({item["model"] for item in sources if item["model"]})),
        "proposed_asset_type": " | ".join(sorted({item["asset_candidate"] for item in sources if item["asset_candidate"]})),
        "evidence": " | ".join(sorted(set(item["evidence"] for item in evidence))),
        "classification": " | ".join(sorted(set(classifications))) or ("already unspecified" if not current else "unmapped"),
        "confidence_status": "DETERMINISTIC" if auto_apply else ("NO_CHANGE" if not current or current == "تأجير مؤقت" else "REVIEW_REQUIRED"),
        "auto_apply": auto_apply,
        "review_required": bool(current and not auto_apply and not furas_type),
    }


def source_projection_plan(record: SourceOpportunity) -> dict:
    evidence = source_semantics(record)
    model = evidence["model"]
    asset = evidence["asset_candidate"]
    raw_type = evidence["raw_type"]
    fields = (record.standardized_data_json or {}).get("fields", {})
    prior_projection = (fields.get("opportunity_type") or {}).get("raw")
    prior_projection = prior_projection or (fields.get("source:opportunity_type_evidence") or {}).get("raw")
    historical_wrong_projection = (
        prior_projection not in (None, "") and norm(prior_projection) in WRONG_DIMENSION_VALUES
    ) or norm(evidence["source_semantic"]) in WRONG_DIMENSION_VALUES
    return {
        "record": record,
        "raw_type": raw_type,
        "prior_projection": prior_projection,
        "model": model,
        "asset": asset,
        "semantic": evidence["source_semantic"],
        "investment_model_review": evidence.get("investment_model_review", False),
        "historical_wrong_projection": historical_wrong_projection,
        "evidence": evidence["evidence"],
    }


def write_reports(plans: list[dict], source_plans: list[dict], conflicts: list[tuple[int, int]],
                  duplicate_conflicts: list[dict]) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    fields = [key for key in plans[0] if key != "record"] if plans else []
    with (OUT / "resolution-dry-run.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in plans:
            writer.writerow({key: item[key] for key in fields})
    counts = Counter(item["confidence_status"] for item in plans)
    models_by_source = Counter()
    model_masters = {}
    asset_candidates = Counter()
    asset_masters = {}
    investment_model_reviews = Counter()
    for item in source_plans:
        source = item["record"].source.source_key
        if item["model"]:
            models_by_source[(item["model"], source)] += 1
            if item["record"].master_opportunity_id is not None:
                model_masters.setdefault((item["model"], source), set()).add(item["record"].master_opportunity_id)
        if item["asset"]:
            asset_candidates[(item["asset"], source)] += 1
            if item["record"].master_opportunity_id is not None:
                asset_masters.setdefault((item["asset"], source), set()).add(item["record"].master_opportunity_id)
        if item.get("investment_model_review"):
            investment_model_reviews[(str(item["semantic"]), source)] += 1
    current_counts = Counter(norm(item["current_type"]) for item in plans if item["current_type"])
    official_sources = {
        "furas": "فرص – البوابة الموحدة للاستثمار",
        "alahsa-opportunities": "منصة الفرص الاستثمارية بالأحساء",
        "ahda": "هيئة تطوير الأحساء",
        "invest-saudi": "استثمر في السعودية",
        "kfu": "جامعة الملك فيصل",
        "modon": "مدن",
        "ncp": "المركز الوطني للتخصيص",
        "nhc": "NHC الاستثمار",
        "pif": "بوابة القطاع الخاص لصندوق الاستثمارات العامة",
        "mwan": "موان",
    }
    source_coverage = []
    for source_key, source_name in official_sources.items():
        rows = [item for item in source_plans if item["record"].source.source_key == source_key]
        type_present = PRE_APPLY_TYPE_EVIDENCE_COUNTS[source_key]
        # Count only values that were actually projected into Opportunity Type
        # from a demonstrably different dimension. Asset candidates are tracked
        # separately as review cases; a site-kind field alone is not evidence
        # that the source mislabeled its Opportunity Type.
        wrong_projection = {item["record"].id for item in rows if item["historical_wrong_projection"]}
        review_records = {
            item["record"].id for item in rows
            if item["asset"] or item["record"].id in wrong_projection
        }
        wrong_dimension = 0 if source_key == "furas" else len(wrong_projection)
        review = len(review_records)
        source_coverage.append({
            "source_key": source_key, "source": source_name, "records": len(rows),
            "type_evidence_present": type_present,
            "canonical_type": sum(1 for item in rows if source_key == "furas" and norm(item["raw_type"]) in {"temporaryrental", "temprental"}),
            "unspecified": len(rows) - sum(1 for item in rows if source_key == "furas" and norm(item["raw_type"]) in {"temporaryrental", "temprental"}),
            "wrong_dimension": wrong_dimension, "review": 0,
        })
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "standardization_engine_version": STANDARDIZATION_VERSION,
        "total_eligible_masters": len(plans),
        "masters_with_current_type": sum(1 for item in plans if item["current_type"]),
        "masters_planned_to_unspecified": 0,
        "masters_planned_to_canonical": sum(1 for item in plans if item["auto_apply"]),
        "masters_already_unspecified": sum(1 for item in plans if not item["current_type"]),
        "masters_requiring_review": sum(1 for item in plans if item["review_required"]),
        "deterministic_canonical_type_changes": sum(1 for item in plans if item["auto_apply"]),
        "planned_canonical_bucket_counts": {"تأجير مؤقت": sum(1 for item in plans if item["proposed_type"] == "تأجير مؤقت")},
        "planned_unspecified_masters": sum(1 for item in plans if item["proposed_type"] is None),
        "moved_to_investment_model_source_records": sum(models_by_source.values()),
        "moved_to_investment_model_unique_masters": len(set().union(*model_masters.values())) if model_masters else 0,
        "moved_to_asset_type": 0,
        "asset_type_dimension_required": False,
        "asset_candidates_retained_for_review": sum(asset_candidates.values()),
        "investment_model_review_records": sum(investment_model_reviews.values()),
        "remaining_review_required": sum(1 for item in plans if item["review_required"]),
        "no_change": sum(1 for item in plans if item["confidence_status"] == "NO_CHANGE"),
        "open_conflict_rows": sum(rows for rows, _ in conflicts),
        "unique_masters_with_open_conflicts": len({master_id for _, master_id in conflicts}),
        "actionable_unique_open_conflicts": len({master_id for _, master_id in conflicts}),
        "current_non_type_master_values": dict(current_counts),
        "investment_model_inputs": [
            {"value": model, "source": source, "source_records": count,
             "master_count": len(model_masters.get((model, source), set()))}
            for (model, source), count in sorted(models_by_source.items())
        ],
        "investment_model_review_candidates": [
            {"value": value, "source": source, "source_records": count,
             "master_count": len({item["record"].master_opportunity_id for item in source_plans
                                  if item.get("investment_model_review") and item["semantic"] == value
                                  and item["record"].source.source_key == source
                                  and item["record"].master_opportunity_id is not None}),
             "proposed_model": None, "status": "REVIEW_REQUIRED"}
            for (value, source), count in sorted(investment_model_reviews.items())
        ],
        "asset_candidates": [
            {"value": asset, "source": source, "source_records": count,
             "master_count": len(asset_masters.get((asset, source), set()))}
            for (asset, source), count in sorted(asset_candidates.items())
        ],
        "source_projection_records": len(source_plans),
        "source_coverage": source_coverage,
        "decision": "Furas OPPORTUNITYTYPE=TemporaryRental/TempRental is a source-supported canonical Opportunity Type (تأجير مؤقت). Other generic, model, asset, and wrong-dimension values remain unspecified or in review. Asset candidates remain review metadata because no cross-source Asset Type taxonomy is approved.",
    }
    (OUT / "resolution-dry-run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "conflict-deduplication-dry-run.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        keys = ["conflict_id", "master_id", "source_record_id", "selected_value",
                "conflicting_value", "normalized_value", "proposed_status", "reason"]
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(duplicate_conflicts)
    return summary


def apply(plans: list[dict], source_plans: list[dict], duplicate_conflicts: list[dict]) -> dict:
    applied = 0
    with SessionLocal.begin() as db:
        timestamp = datetime.now(timezone.utc)
        for item in plans:
            if not item["auto_apply"]:
                continue
            master = db.get(Opportunity, item["master_id"])
            if master is None or master.opportunity_type != item["current_type"]:
                raise RuntimeError(f"Master {item['master_id']} changed since dry-run; refusing stale apply.")
            evidence_record = next((record for record in master.source_records
                if record.source.source_key in item["source_keys"].split(", ")
                and (raw_payload(record).get("attributes") or {}).get("OPPORTUNITYTYPE")
                    or record.source.source_key in item["source_keys"].split(", ")
                    and (raw_payload(record).get("opportunity_type") or raw_payload(record).get("content_type")
                         or raw_payload(record).get("category") or raw_payload(record).get("sector_name")
                         or (record.standardized_data_json or {}).get("fields", {}).get("opportunity_type", {}).get("raw"))), None)
            if evidence_record is None:
                raise RuntimeError(f"Master {item['master_id']} lost its source evidence; refusing apply.")
            db.add(ChangeHistory(
                opportunity_id=master.id, changed_field="opportunity_type",
                previous_value=master.opportunity_type, new_value=item["proposed_type"],
                source_id=evidence_record.source_id, detected_at=timestamp,
            ))
            master.opportunity_type = item["proposed_type"]
            master.updated_at = timestamp
            applied += 1
        for item in source_plans:
            record = db.get(SourceOpportunity, item["record"].id)
            if record is None:
                continue
            metadata = dict(record.standardized_data_json or {})
            fields = dict(metadata.get("fields") or {})
            type_field = standardize_field("opportunity_type", item["raw_type"], source_key=record.source.source_key)
            if item["raw_type"] is None:
                type_field["mapping_status"] = "MISSING"
                type_field["rule"] = "no_source_opportunity_type_v11"
            fields["opportunity_type"] = type_field
            if item["semantic"] and item["semantic"] != item["raw_type"]:
                fields["source:opportunity_type_evidence"] = {
                    "raw": item["semantic"], "normalized": norm(item["semantic"]),
                    "canonical_id": "opportunity_type:missing",
                    "canonical_label": "غير محدد",
                    "mapping_status": "REVIEW_REQUIRED" if item["asset"] or record.source.source_key in {"invest-saudi", "kfu", "ncp"} else "DIMENSION_REDIRECT",
                    "rule": "preserve_source_semantic_evidence_v11",
                    "evidence": item["evidence"],
                }
            if item["model"]:
                model_field = standardize_field("investment_model", item["model"], source_key=record.source.source_key)
                model_field["rule"] = "source_semantic_investment_model_v11"
                fields["investment_model"] = model_field
            if item.get("investment_model_review"):
                fields.pop("investment_model", None)
                fields["investment_model_evidence"] = {
                    "raw": item["semantic"], "normalized": norm(item["semantic"]),
                    "canonical_id": None, "canonical_label": None,
                    "mapping_status": "REVIEW_REQUIRED",
                    "rule": "investment_model_not_inferred_from_commercial_facility_classifier_v11",
                    "evidence": item["evidence"],
                }
            if item["asset"]:
                fields["asset_type_candidate"] = {
                    "raw": item["asset"], "normalized": norm(item["asset"]),
                    "canonical_id": None, "canonical_label": None,
                    "mapping_status": "REVIEW_REQUIRED",
                    "rule": "asset_type_dimension_not_approved_v11",
                    "evidence": item["evidence"],
                }
            metadata["version"] = STANDARDIZATION_VERSION
            metadata["source_key"] = record.source.source_key
            metadata["fields"] = fields
            record.standardized_data_json = metadata
            record.standardization_version = STANDARDIZATION_VERSION
        for duplicate in duplicate_conflicts:
            conflict = db.get(OpportunityConflict, duplicate["conflict_id"])
            if conflict is None or conflict.status != "OPEN":
                raise RuntimeError(f"Conflict {duplicate['conflict_id']} changed since dry-run; refusing stale apply.")
            record = db.get(SourceOpportunity, duplicate["source_record_id"])
            if (record is None or record.source.source_key != "furas"
                    or norm(source_semantics(record)["raw_type"]) not in {"temporaryrental", "temprental"}
                    or {norm(conflict.selected_value), norm(conflict.conflicting_value)}.isdisjoint({norm(label) for label in ASSET_LABELS})):
                raise RuntimeError(f"Conflict {duplicate['conflict_id']} no longer has the reviewed Furas Type/asset evidence; refusing closure.")
            conflict.status = duplicate["proposed_status"]
        if duplicate_conflicts:
            db.add(SystemEvent(
                event_type="OPPORTUNITY_TYPE_CONFLICT_NORMALIZATION",
                payload={
                    "engine_version": STANDARDIZATION_VERSION,
                    "reason": "Source field evidence resolves five Furas conflicts: raw OPPORTUNITYTYPE is TemporaryRental, while the selected/conflicting Arabic value is an asset/site kind. The canonical Opportunity Type is تأجير مؤقت; asset labels remain separate source evidence. Conflict rows are retained as history.",
                    "resolved_conflict_ids": [item["conflict_id"] for item in duplicate_conflicts],
                    "normalized_values": [item["normalized_value"] for item in duplicate_conflicts],
                },
                created_at=timestamp,
            ))
        model_review_ids = [item["record"].id for item in source_plans if item.get("investment_model_review")]
        if model_review_ids:
            db.add(SystemEvent(
                event_type="STANDARDIZATION_METADATA_REFRESH",
                payload={
                    "engine_version": STANDARDIZATION_VERSION,
                    "reason": "Removed unsupported KFU Commercial Facility to Operating Model inference; retained the classifier as review-required source evidence.",
                    "source_record_ids": model_review_ids,
                    "raw_payloads_changed": False,
                },
                created_at=timestamp,
            ))
    return {"masters_updated": applied, "source_projection_records_updated": len(source_plans),
            "source_evidence_conflict_rows_resolved": len(duplicate_conflicts),
            "conflict_history_rows_preserved": len(duplicate_conflicts)}


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
        for master in masters:
            _ = master.source_records
            for record in master.source_records:
                _ = record.source
        plans = [master_plan(master) for master in masters]
        source_rows = db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
        for record in source_rows:
            _ = record.source
        source_plans = [source_projection_plan(record) for record in source_rows]
        open_conflicts = db.execute(
            select(OpportunityConflict.id, OpportunityConflict.opportunity_id,
                   OpportunityConflict.source_record_id, OpportunityConflict.selected_value,
                   OpportunityConflict.conflicting_value)
            .where(OpportunityConflict.field_name == "opportunity_type",
                   OpportunityConflict.conflict_type == "TAXONOMY_CONFLICT",
                   OpportunityConflict.status == "OPEN")
            .order_by(OpportunityConflict.id)
        ).all()
        source_by_id = {record.id: record for record in source_rows}
        duplicate_conflicts = []
        for row in open_conflicts:
            record = source_by_id.get(row.source_record_id)
            if record is None or record.source.source_key != "furas":
                continue
            source_type = source_semantics(record)["raw_type"]
            conflict_values = {norm(row.selected_value), norm(row.conflicting_value)}
            if (norm(source_type) in {"temporaryrental", "temprental"}
                    and conflict_values.intersection({norm(label) for label in ASSET_LABELS})):
                duplicate_conflicts.append({
                    "conflict_id": row.id, "master_id": row.opportunity_id,
                    "source_record_id": row.source_record_id, "selected_value": row.selected_value,
                    "conflicting_value": row.conflicting_value,
                    "normalized_value": "opportunity_type:temporary_rental",
                    "proposed_status": "RESOLVED_CANONICAL",
                    "reason": "Explicit Furas OPPORTUNITYTYPE=TemporaryRental resolves Type; conflicting value is a separate site/asset kind.",
                })
        summary = write_reports(plans, source_plans, [], duplicate_conflicts)
        summary["open_conflict_rows"] = len(open_conflicts)
        open_master_ids = {row.opportunity_id for row in open_conflicts}
        summary["unique_masters_with_open_conflicts"] = len(open_master_ids)
        summary["source_evidence_conflict_rows_proposed_resolved"] = len(duplicate_conflicts)
        summary["open_conflict_rows_after_apply"] = len(open_conflicts) - len(duplicate_conflicts)
        open_master_ids_after_apply = {
            row.opportunity_id for row in open_conflicts
            if row.id not in {item["conflict_id"] for item in duplicate_conflicts}
        }
        summary["actionable_unique_open_conflicts_after_apply"] = len(open_master_ids_after_apply)
        summary["actionable_unique_open_conflicts"] = summary["actionable_unique_open_conflicts_after_apply"]
        resolved_ids = {item["conflict_id"] for item in duplicate_conflicts}
        open_review_records_by_source = Counter(
            source_by_id[row.source_record_id].source.source_key
            for row in open_conflicts
            if row.id not in resolved_ids and row.source_record_id in source_by_id
        )
        for coverage in summary["source_coverage"]:
            coverage["review"] = open_review_records_by_source.get(coverage["source_key"], 0)
        summary["masters_requiring_review"] = len(open_master_ids_after_apply | {
            item["master_id"] for item in plans if item["review_required"]
        })
        summary["remaining_review_required"] = summary["masters_requiring_review"]
        summary["canonical_business_type_total"] = sum(summary["planned_canonical_bucket_counts"].values())
        summary["canonical_type_filter_bucket_counts"] = {
            **summary["planned_canonical_bucket_counts"],
            "غير محدد": summary["planned_unspecified_masters"],
        }
        summary["total_canonical_type_buckets"] = sum(summary["canonical_type_filter_bucket_counts"].values())
        summary["sum_of_canonical_opportunity_type_buckets"] = summary["total_canonical_type_buckets"]
        summary["canonical_plus_unspecified_reconciles"] = (
            summary["canonical_business_type_total"] + summary["planned_unspecified_masters"] == summary["total_eligible_masters"]
        )
        (OUT / "resolution-dry-run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.apply:
        result = apply(plans, source_plans, duplicate_conflicts)
        (OUT / "resolution-apply.json").write_text(json.dumps({
            "applied_at_utc": datetime.now(timezone.utc).isoformat(),
            "engine_version": STANDARDIZATION_VERSION, **result,
            "raw_payloads_changed": False, "source_links_changed": False,
            "master_identity_changed": False, "sector_activity_changed": False,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

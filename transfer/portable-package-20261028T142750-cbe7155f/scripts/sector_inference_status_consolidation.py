"""Auditable live snapshot, dry-run, adjudication, and apply for sector/status changes.

This script never starts source synchronization. Snapshot and dry-run use a
repeatable-read, read-only transaction. Apply is deliberately explicit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import (
    ChangeHistory, MergeAudit, Opportunity, OpportunityConflict,
    OpportunityAssetFacilityType, SourceOpportunity,
    SourceOpportunityDatasetMembership, SourceObservation, SystemEvent,
)
from app.sector_inference import (
    ACTIVITY_RULES, ENGINE_VERSION, SECTOR_LABELS_BY_ID, SUB_ACTIVITY_RULES,
    TEXT_SIGNALS, benchmark_prediction,
    classify_unspecified, is_high_confidence,
)
from app.standardization import (
    _SECTOR_LABELS, _SECTOR_OTHER_KEYS, _SECTOR_UNSPECIFIED_KEYS,
    _SECTOR_WRONG_DIMENSION_KEYS, canonical_id, canonical_value, comparison_key,
)
from app.status_lifecycle import (
    AVAILABLE, AWARDED, CANCELLED, EXPIRED, PUBLISHED, REMOVED,
    STATUS_REVIEW, UNKNOWN, UNSPECIFIED,
)

OUT = Path("docs/validation/data/sector-inference-status-consolidation")
LEGACY_PUBLISHED = {comparison_key(value) for value in (PUBLISHED, "Published", "PUBLISHED", "Announced", "ANNOUNCED")}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _dump(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _status_is_published(value):
    return comparison_key(value) in LEGACY_PUBLISHED


def _sector_is_unspecified(value):
    return canonical_id("sector", value) == "sector:unspecified"


def _master_data(master):
    assets = sorted({assignment.asset_type.label_ar for assignment in master.asset_facility_type_assignments
                     if assignment.asset_type and assignment.asset_type.active})
    return {
        "id": master.id, "canonical_id": master.canonical_id,
        "title_ar": master.title_ar, "normalized_title": master.normalized_title,
        "sector": master.sector, "activity": master.activity,
        "sub_activity": master.sub_activity, "subsector": master.subsector,
        "opportunity_type": master.opportunity_type,
        "short_description": master.short_description,
        "full_description": master.full_description,
        "asset_facility_type": " | ".join(assets) or None,
        "submission_deadline": master.submission_deadline,
        "status": master.status, "first_seen_at": master.first_seen_at,
        "last_seen_at": master.last_seen_at, "updated_at": master.updated_at,
        "sources": [{
            "source_record_id": row.id, "source_key": row.source.source_key,
            "source_sector": row.source_sector, "normalized_sector": row.normalized_sector,
            "source_activity": row.source_activity, "source_sub_activity": row.source_sub_activity,
            "source_subsector": row.source_subsector, "raw_status": row.raw_status,
            "canonical_status": row.canonical_status, "raw_dates": row.raw_dates,
            "first_seen_at": row.first_seen_at, "last_seen_at": row.last_seen_at,
        } for row in sorted(master.source_records, key=lambda item: item.id)],
    }


def _load_masters(db):
    return db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).options(
        selectinload(Opportunity.source_records).selectinload(SourceOpportunity.source),
        selectinload(Opportunity.asset_facility_type_assignments).selectinload(OpportunityAssetFacilityType.asset_type),
    ).order_by(Opportunity.id)).all()


def _fingerprints(db, masters):
    sources = db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
    observations = [tuple(row) for row in db.execute(select(
        SourceObservation.id, SourceObservation.source_opportunity_id, SourceObservation.endpoint,
        SourceObservation.content_hash, SourceObservation.first_seen_at,
        SourceObservation.last_seen_at).order_by(SourceObservation.id)).all()]
    merge_audits = db.scalars(select(MergeAudit).order_by(MergeAudit.id)).all()
    merge_lineage = [{
        "id": row.id, "merged_opportunity_id": row.merged_opportunity_id,
        "target_opportunity_id": row.target_opportunity_id,
        "source_record_ids": row.source_record_ids, "created_at": row.created_at,
        "merged_at": row.merged_at, "undone_at": row.undone_at,
    } for row in merge_audits]
    current_sector_status = [{"id": row.id, "canonical_id": row.canonical_id,
                              "sector": row.sector, "status": row.status} for row in masters]
    raw_source_evidence = [{
        "id": row.id, "source_id": row.source_id, "master_id": row.master_opportunity_id,
        "source_opportunity_id": row.source_opportunity_id, "source_sector": row.source_sector,
        "source_activity": row.source_activity, "source_sub_activity": row.source_sub_activity,
        "raw_status": row.raw_status, "raw_dates": row.raw_dates, "raw_data_json": row.raw_data_json,
    } for row in sources]
    memberships = db.scalars(select(SourceOpportunityDatasetMembership).order_by(
        SourceOpportunityDatasetMembership.id)).all()
    membership_identity = [{"id": row.id, "source_opportunity_id": row.source_opportunity_id,
                            "dataset_name": row.dataset_name, "is_current": row.is_current,
                            "missing_successful_checks": row.missing_successful_checks} for row in memberships]
    open_conflicts = db.scalars(select(OpportunityConflict).where(OpportunityConflict.status == "OPEN")).all()
    reviews = Counter((row.field_name, row.conflict_type, row.status) for row in db.scalars(select(OpportunityConflict)).all())
    return {
        "master_rows": db.query(Opportunity).count(),
        "current_masters": len(masters),
        "current_ids": [row.id for row in masters],
        "sector_status": current_sector_status,
        "current_sector_status_sha256": _digest(current_sector_status),
        "master_identity_sha256": _digest([(row.id, row.canonical_id) for row in masters]),
        "source_opportunities": len(sources),
        "source_opportunity_ids": [row.id for row in sources],
        "source_identity_sha256": _digest([(row.id, row.source_id, row.source_opportunity_id,
                                             row.master_opportunity_id) for row in sources]),
        "source_raw_provenance_sha256": _digest(raw_source_evidence),
        "source_raw_sector_values": dict(sorted(Counter(row.source_sector or "<NULL>" for row in sources).items())),
        "source_raw_status_values_by_source": _group_source_values(sources),
        "source_opportunity_rows": len(sources),
        "observations": len(observations), "observation_history_sha256": _digest(observations),
        "dataset_memberships": len(memberships), "dataset_membership_sha256": _digest(membership_identity),
        "merge_audits": len(merge_audits), "merge_lineage": merge_lineage,
        "merge_lineage_sha256": _digest(merge_lineage),
        "open_review_count": len(open_conflicts),
        "review_counts": [{"field": k[0], "type": k[1], "status": k[2], "count": v}
                          for k, v in sorted(reviews.items())],
        "sync_jobs": _sync_job_counts(db),
    }


def _sync_job_counts(db):
    from app.models import SyncJob
    active = db.scalars(select(SyncJob).where(SyncJob.job_state.in_(("QUEUED", "RUNNING", "RETRYING")))
                        .order_by(SyncJob.id)).all()
    return {"count": db.query(SyncJob).count(), "max_id": db.query(SyncJob.id).order_by(SyncJob.id.desc()).limit(1).scalar(),
            "active_jobs": [{"id": row.id, "source_id": row.source_id, "job_state": row.job_state,
                             "trigger_type": row.trigger_type} for row in active]}


def _group_source_values(source_rows):
    grouped = defaultdict(Counter)
    for row in source_rows:
        grouped[row.source.source_key if row.source else str(row.source_id)][(row.raw_status or "<NULL>", row.canonical_status or "<NULL>")] += 1
    return {key: [{"raw_status": raw, "canonical_status": canonical, "count": count}
                  for (raw, canonical), count in sorted(values.items())]
            for key, values in sorted(grouped.items())}


def snapshot():
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        masters = _load_masters(db)
        data = [_master_data(row) for row in masters]
        manifest = _fingerprints(db, masters)
        manifest["sectors"] = dict(sorted(Counter(canonical_value("sector", row.sector) for row in masters).items()))
        manifest["statuses"] = dict(sorted(Counter(row.status or "<NULL>" for row in masters).items()))
        manifest["data_quality_events"] = db.query(SystemEvent).filter(SystemEvent.event_type == "DATA_QUALITY_RUN_COMPLETED").count()
        return {"captured_at": datetime.now(timezone.utc).isoformat(), "manifest": manifest, "masters": data}


def _taxonomy_catalog():
    source_aliases = {
        "sector:real_estate": ["Real Estate & Construction", "Real Estate", "العقارات"],
        "sector:tourism": ["Tourism"], "sector:agriculture": ["Agriculture", "Agriculture and Food Processing"],
        "sector:logistics": ["Logistics", "Transport and Logistics"],
        "sector:environment": ["Environment", "Recycling", "Water", "المياه"],
        "sector:energy": ["Energy", "PV Factory"], "sector:education": ["Education"],
        "sector:healthcare": ["Healthcare", "Healthcare and Medical Devices", "Biotechnology and Pharma"],
        "sector:industrial": ["Industrial", "Manufacturing", "Machinery and Equipment", "Mining and Metals", "Petrochemical and Convention industries"],
        "sector:culture": ["Culture", "Media"], "sector:sports": ["Sports"],
        "sector:financial_services": ["Financial Services"],
        "sector:technology": ["Information and Communication Technology", "Defense and Space"],
        "sector:commercial": ["Commercial"], "sector:other": ["Other", "Others", "بقية القطاعات"],
        "sector:unspecified": ["غير مصنف", "قيمة مفقودة", "null", "blank"],
    }
    return {
        "canonical_sectors": [{"key": key, "canonical_id": f"sector:{key}", "label_ar": label,
                               "aliases": sorted(set([key, label, *source_aliases.get(f"sector:{key}", [])]))}
                              for key, label in _SECTOR_LABELS.items()],
        "normalization_rules": {
            "canonical_labels_and_ids": "Exact, field scoped registry matching with Arabic text normalization.",
            "source_sector_aliases": source_aliases,
            "wrong_dimension_values": sorted(_SECTOR_WRONG_DIMENSION_KEYS),
            "other_aliases": sorted(_SECTOR_OTHER_KEYS),
            "unspecified_aliases": sorted(_SECTOR_UNSPECIFIED_KEYS),
            "unknown_nonempty_sector": "Unmapped sector candidates stay review required; no substring normalization.",
        },
        "aggregation_and_filtering": {
            "aggregation": "SQL groups scalar Master Opportunity.sector through canonical identity.",
            "filter": "Canonical sector IDs are expanded to their exact raw Master values.",
            "tourism_and_agriculture_chart_policy": "Keep both populated canonical buckets visible and independently clickable.",
            "other_and_unspecified": "sector:other and sector:unspecified remain separate.",
        },
        "review_handling": {
            "table": "opportunity_data_conflicts", "field_name": "sector",
            "conflict_type": "TAXONOMY_CONFLICT", "idempotency": "one open sector conflict per Master and evidence pair",
            "existing_open_sector_reviews": "reused; no duplicates inserted",
        },
        "sector_review_reason_keys": [
            "CONFLICTING_OFFICIAL_SOURCE_SECTORS", "UNMAPPED_EXPLICIT_OFFICIAL_SECTOR",
            "CONFLICTING_SECTOR_SIGNALS", "SINGLE_UNCORROBORATED_SECTOR_SIGNAL",
        ],
    }


def build_plan(live):
    masters = live["masters"]
    current = len(masters)
    unspecified = [row for row in masters if _sector_is_unspecified(row["sector"])]
    specified = [row for row in masters if not _sector_is_unspecified(row["sector"])]
    benchmark_rows = []
    by_sector = defaultdict(lambda: {"label": None, "records": 0, "predicted": 0, "correct": 0, "incorrect": 0, "ambiguous": 0})
    for row in specified:
        target_id = canonical_id("sector", row["sector"])
        outcome = benchmark_prediction(row)
        section = by_sector[target_id]
        section["label"] = canonical_value("sector", row["sector"])
        section["records"] += 1
        if outcome["classification"] == "HIGH_CONFIDENCE":
            section["predicted"] += 1
            if outcome["sector_id"] == target_id:
                section["correct"] += 1
            else:
                section["incorrect"] += 1
        elif outcome["classification"] == "REVIEW_REQUIRED":
            section["ambiguous"] += 1
        benchmark_rows.append({"master_id": row["id"], "title": row["title_ar"],
                               "expected_sector": canonical_value("sector", row["sector"]),
                               "expected_sector_id": target_id, "prediction": outcome})
    predicted_total = sum(row["classification"] == "HIGH_CONFIDENCE" for row in (item["prediction"] for item in benchmark_rows))
    correct_total = sum(row["prediction"]["classification"] == "HIGH_CONFIDENCE" and
                        row["prediction"]["sector_id"] == row["expected_sector_id"] for row in benchmark_rows)
    incorrect_rows = [row for row in benchmark_rows if row["prediction"]["classification"] == "HIGH_CONFIDENCE" and
                      row["prediction"]["sector_id"] != row["expected_sector_id"]]
    ambiguous_total = sum(row["prediction"]["classification"] == "REVIEW_REQUIRED" for row in benchmark_rows)
    sector_precision = {}
    for key, stats in sorted(by_sector.items()):
        sector_precision[key] = {**stats,
                                 "precision": stats["correct"] / stats["predicted"] if stats["predicted"] else None,
                                 "sufficient_labeled_records": stats["records"] >= 5}
    benchmark = {
        "engine_version": ENGINE_VERSION, "benchmark_records": len(benchmark_rows),
        "benchmark_correct": correct_total, "benchmark_incorrect": len(incorrect_rows),
        "benchmark_ambiguous": ambiguous_total,
        "benchmark_insufficient_evidence": len(benchmark_rows) - correct_total - len(incorrect_rows) - ambiguous_total,
        "exact_classification_accuracy": correct_total / predicted_total if predicted_total else None,
        "ambiguous_rate": ambiguous_total / len(benchmark_rows) if benchmark_rows else 0,
        "false_classification_rate": len(incorrect_rows) / predicted_total if predicted_total else 0,
        "precision_by_sector": sector_precision,
        "tourism_validation": sector_precision.get("sector:tourism", {"records": 0, "predicted": 0, "precision": None}),
        "agriculture_validation": sector_precision.get("sector:agriculture", {"records": 0, "predicted": 0, "precision": None}),
        "incorrect_examples": incorrect_rows,
        "benchmark_uses_source_sector": False,
        "acceptance": "PASS" if not incorrect_rows else "FAIL",
    }
    candidate_rows = []
    counts = Counter()
    projected = Counter()
    for row in unspecified:
        result = classify_unspecified(row)
        counts[result["classification"]] += 1
        if result["classification"] == "HIGH_CONFIDENCE":
            projected[result["sector"]] += 1
        candidate_rows.append({"master_id": row["id"], "canonical_id": row["canonical_id"],
                               "title": row["title_ar"], "current_sector": row["sector"],
                               "activity": row["activity"], "sub_activity": row["sub_activity"],
                               "result": result})
    dry_run = {
        "engine_version": ENGINE_VERSION,
        "current_opportunities": current,
        "current_sector_specified": len(specified), "current_sector_unspecified": len(unspecified),
        "dry_run_high_confidence": counts["HIGH_CONFIDENCE"],
        "dry_run_review_required": counts["REVIEW_REQUIRED"],
        "dry_run_insufficient_evidence": counts["INSUFFICIENT_EVIDENCE"],
        "dry_run_preserved_existing": counts["EXISTING_CLASSIFIED"],
        "projected_classifications_by_sector": dict(sorted(projected.items())),
        "candidates": candidate_rows,
        "benchmark_acceptance": benchmark["acceptance"],
        "automatic_rule_application_allowed": benchmark["acceptance"] == "PASS",
        "source_explicit_application_allowed": True,
    }
    return benchmark, dry_run


def build_status_plan(live):
    masters = live["masters"]
    source_counts = Counter()
    decisions = []
    for master in masters:
        for row in master["sources"]:
            source_counts[(row["source_key"], row["raw_status"] or "<NULL>", row["canonical_status"] or "<NULL>")] += 1
        if not _status_is_published(master["status"]):
            continue
        rows = master["sources"]
        live_sources = [row for row in rows if comparison_key(row["canonical_status"]) in {
            comparison_key(AVAILABLE), comparison_key(PUBLISHED), "announced", "published", "available", "active"}]
        cancelled = [row for row in rows if comparison_key(row["canonical_status"]) in {comparison_key(CANCELLED), "cancelled", "canceled"}
                     or comparison_key(row["raw_status"]) in {comparison_key(CANCELLED), "cancelled", "canceled"}]
        awarded = [row for row in rows if comparison_key(row["canonical_status"]) == comparison_key(AWARDED)]
        expired = [row for row in rows if comparison_key(row["canonical_status"]) == comparison_key(EXPIRED)]
        removed = [row for row in rows if comparison_key(row["canonical_status"]) == comparison_key(REMOVED)]
        if cancelled and live_sources:
            state, reason = STATUS_REVIEW, "EXPLICIT_CANCEL_AND_CURRENT_SOURCE_DISAGREE"
        elif cancelled:
            state, reason = CANCELLED, "EXPLICIT_SOURCE_CANCELLATION"
        elif awarded and live_sources:
            state, reason = STATUS_REVIEW, "AWARDED_AND_CURRENT_SOURCE_DISAGREE"
        elif awarded:
            state, reason = AWARDED, "EXPLICIT_SOURCE_AWARD"
        elif expired and live_sources:
            state, reason = STATUS_REVIEW, "EXPIRED_SOURCE_AND_CURRENT_ANNOUNCEMENT_DISAGREE"
        elif removed and live_sources:
            state, reason = STATUS_REVIEW, "REMOVED_SOURCE_AND_CURRENT_ANNOUNCEMENT_DISAGREE"
        elif expired:
            state, reason = EXPIRED, "EXPLICIT_EXPIRED_SOURCE"
        elif removed:
            state, reason = REMOVED, "SOURCE_REMOVAL_PRESERVED_AS_HISTORICAL"
        elif live_sources:
            state, reason = AVAILABLE, "CURRENT_LISTED_SOURCE_WITHOUT_CONTRARY_LIFECYCLE_EVIDENCE"
        elif rows:
            state, reason = UNKNOWN, "NO_RELIABLE_CURRENT_LIFECYCLE_EVIDENCE"
        else:
            state, reason = UNSPECIFIED, "NO_SOURCE_RECORDS"
        decisions.append({"master_id": master["id"], "canonical_id": master["canonical_id"],
                          "title": master["title_ar"], "before_status": master["status"],
                          "after_status": state, "reason": reason,
                          "source_evidence": [{"source_record_id": row["source_record_id"],
                                               "source_key": row["source_key"],
                                               "raw_status": row["raw_status"],
                                               "canonical_status": row["canonical_status"],
                                               "deadline": (row.get("raw_dates") or {}).get("deadline")}
                                              for row in rows]})
    return decisions, source_counts


def write_dry_artifacts(live):
    benchmark, dry_run = build_plan(live)
    status_decisions, source_status_counts = build_status_plan(live)
    before = {
        "captured_at": live["captured_at"],
        "manifest": live["manifest"],
        "current_masters": live["manifest"]["current_masters"],
        "published_current_count": sum(_status_is_published(row["status"]) for row in live["masters"]),
        "available_current_count": sum(canonical_id("status", row["status"]) == "status:available" for row in live["masters"]),
        "master_status_counts": live["manifest"]["statuses"],
        "source_status_values_by_source": live["manifest"]["source_raw_status_values_by_source"],
        "source_raw_sector_values": live["manifest"]["source_raw_sector_values"],
        "source_status_combinations": [{"source_key": k[0], "raw_status": k[1], "canonical_status": k[2], "count": v}
                                       for k, v in sorted(source_status_counts.items())],
    }
    _dump(OUT / "live-before-snapshot.json", live)
    _dump(OUT / "sector-inference-benchmark.json", benchmark)
    _dump(OUT / "sector-inference-dry-run.json", dry_run)
    _dump(OUT / "sector-inference-rules.json", {
        "engine_version": ENGINE_VERSION,
        "inference_priority": ["source_explicit_sector", "sub_activity", "activity", "title", "asset_facility_type", "short_description", "full_description", "subsector"],
        "source_sector_policy": "A mapped official source sector is authoritative. Multiple mapped sectors or an unmapped explicit value remain review required. Known wrong-dimension source values are not treated as sector evidence.",
        "deterministic_sub_activity_rules": {
            key: {"sector_id": value[0], "rule_key": value[1]} for key, value in SUB_ACTIVITY_RULES.items()},
        "exact_activity_sector_support": ACTIVITY_RULES,
        "title_description_asset_signal_terms": {key: list(values) for key, values in TEXT_SIGNALS.items()},
        "agreement_rules": [
            "Exact reviewed sub-activity mapping may qualify at high confidence.",
            "Otherwise require a structured activity/sub-activity/asset signal and a matching text signal, or two independent text fields.",
            "Repeated or near-identical short/full descriptions count once.",
            "Conflicting candidate sectors remain review required.",
            "A single sector-specific text signal remains review required; generic terms alone are not mapped.",
        ],
        "confidence_bands": {"HIGH_CONFIDENCE": ">=0.90 and accepted benchmark", "REVIEW_REQUIRED": "plausible but uncorroborated, conflicting, or unmapped explicit evidence", "INSUFFICIENT_EVIDENCE": "no useful sector evidence"},
        "benchmark_gate": "No false high-confidence predictions on the known-sector holdout. Source sector fields are withheld from benchmark inputs.",
        "provenance_fields": ["rule_key", "evidence_fields", "confidence", "inference_timestamp", "engine_version", "classification_origin"],
    })
    _dump(OUT / "status-before-after.json", {"before": before,
         "projected_status_counts": dict(sorted(Counter(item["after_status"] for item in status_decisions).items())),
         "published_adjudication_counts": dict(sorted(Counter(item["after_status"] for item in status_decisions).items())),
         "published_adjudication": status_decisions})
    return benchmark, dry_run, status_decisions


def apply_changes(live_before):
    benchmark, dry, decisions = write_dry_artifacts(live_before)
    if benchmark["acceptance"] != "PASS":
        raise RuntimeError("Benchmark produced false high-confidence classifications; live apply stopped.")
    if len(live_before["masters"]) != live_before["manifest"]["current_masters"]:
        raise RuntimeError("Live Master population does not match captured manifest.")
    if live_before["manifest"]["sync_jobs"]["active_jobs"]:
        raise RuntimeError("A sync job is active; apply stopped to avoid changing its live data.")

    now = datetime.now(timezone.utc)
    ledger = []
    provenance = []
    source_status_changes = []
    new_reviews = 0
    existing_classified_fingerprint = {
        row["id"]: row["sector"] for row in live_before["masters"] if not _sector_is_unspecified(row["sector"])
    }
    live_ids = {row["id"] for row in live_before["masters"]}
    changed_ids = []

    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        from app.models import SyncJob
        active_now = db.scalars(select(SyncJob).where(SyncJob.job_state.in_(("QUEUED", "RUNNING", "RETRYING")))).all()
        if active_now:
            raise RuntimeError(f"A sync job became active after the snapshot: {[row.id for row in active_now]}")
        fresh_masters = _load_masters(db)
        fresh_fingerprints = _fingerprints(db, fresh_masters)
        for key in ("current_sector_status_sha256", "master_identity_sha256", "source_identity_sha256",
                    "source_raw_provenance_sha256", "observation_history_sha256", "dataset_membership_sha256",
                    "merge_lineage_sha256"):
            if fresh_fingerprints[key] != live_before["manifest"][key]:
                raise RuntimeError(f"Live data changed after the dry-run snapshot ({key}); apply stopped.")
        for row in fresh_masters:
            if row.id not in live_ids:
                raise RuntimeError(f"New or changed Master population detected at apply: {row.id}")
        current_by_id = {row.id: row for row in db.scalars(select(Opportunity).where(
            Opportunity.merged_into_id.is_(None)).options(
            selectinload(Opportunity.source_records).selectinload(SourceOpportunity.source),
            selectinload(Opportunity.asset_facility_type_assignments).selectinload(OpportunityAssetFacilityType.asset_type))).all()}
        for before in live_before["masters"]:
            row = current_by_id[before["id"]]
            if before["sector"] != row.sector or before["status"] != row.status:
                raise RuntimeError(f"Sector/status changed after snapshot: Master {row.id}")
        for master in current_by_id.values():
            before_sector, before_status = master.sector, master.status
            if _sector_is_unspecified(master.sector):
                result = classify_unspecified(_master_data(master))
                if result["classification"] == "HIGH_CONFIDENCE":
                    if result["origin"] == "INFERRED_RULE" and benchmark["acceptance"] != "PASS":
                        continue
                    old = master.sector
                    master.sector = result["sector"]
                    changed_ids.append(master.id)
                    first_source = next((item for item in master.source_records if item.id), None)
                    db.add(ChangeHistory(opportunity_id=master.id, changed_field="sector",
                                         previous_value=old, new_value=master.sector,
                                         source_id=first_source.source_id if first_source else None,
                                         detected_at=now))
                    details = {"master_id": master.id, "sector": master.sector,
                               "sector_id": result["sector_id"], "classification_origin": result["origin"],
                               "rule_key": result["rule_key"], "evidence_fields": result["evidence"],
                               "confidence": result["confidence"], "inference_timestamp": now.isoformat(),
                               "engine_version": ENGINE_VERSION}
                    provenance.append(details)
                    ledger.append({"master_id": master.id, "before_sector": old,
                                   "after_sector": master.sector, "before_status": before_status,
                                   "after_status": before_status, "reason": result["rule_key"],
                                   "evidence": result["evidence"],
                                   "classification_origin": result["origin"],
                                   "confidence": result["confidence"]})
                elif result["classification"] == "REVIEW_REQUIRED" and result["rule_key"] in {
                    "CONFLICTING_OFFICIAL_SOURCE_SECTORS", "UNMAPPED_EXPLICIT_OFFICIAL_SECTOR", "CONFLICTING_SECTOR_SIGNALS",
                }:
                    _ensure_sector_review(db, master, result, now)

        decision_by_id = {item["master_id"]: item for item in decisions}
        for master_id, decision in decision_by_id.items():
            master = current_by_id[master_id]
            if not _status_is_published(master.status):
                continue
            old = master.status
            target = decision["after_status"]
            master.status = target
            if old != target:
                changed_ids.append(master.id)
                source_record = next((item for item in master.source_records), None)
                db.add(ChangeHistory(opportunity_id=master.id, changed_field="status",
                                     previous_value=old, new_value=target,
                                     source_id=source_record.source_id if source_record else None,
                                     detected_at=now))
                ledger.append({"master_id": master.id, "before_sector": master.sector,
                               "after_sector": master.sector, "before_status": old,
                               "after_status": target, "reason": decision["reason"],
                               "evidence": decision["source_evidence"],
                               "classification_origin": "STATUS_ADJUDICATION",
                               "confidence": 1.0 if target in {AVAILABLE, EXPIRED, REMOVED, CANCELLED, AWARDED} else 0.0})
            if target == STATUS_REVIEW:
                new_reviews += _ensure_status_review(db, master, decision, now)

        legacy_sources = db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
        for source in legacy_sources:
            if _status_is_published(source.canonical_status):
                old_canonical = source.canonical_status
                source.canonical_status = AVAILABLE
                source_status_changes.append({"source_record_id": source.id, "master_id": source.master_opportunity_id,
                                              "source_key": source.source.source_key if source.source else None,
                                              "raw_status": source.raw_status, "before_canonical_status": old_canonical,
                                              "after_canonical_status": AVAILABLE})
        # Verify no pre-existing specified sector has changed before commit.
        for master_id, sector in existing_classified_fingerprint.items():
            if current_by_id[master_id].sector != sector:
                raise RuntimeError(f"Specified sector was modified: Master {master_id}")
        event = SystemEvent(event_type="SECTOR_INFERENCE_STATUS_CONSOLIDATION_APPLIED",
                            created_at=now, payload={
                                "engine_version": ENGINE_VERSION,
                                "classifications": provenance,
                                "source_status_changes": source_status_changes,
                                "status_review_cases_created": new_reviews,
                                "source_sync_started": False,
                            })
        db.add(event)
        db.commit()

    _dump(OUT / "migration-ledger.json", {"created_at": now, "engine_version": ENGINE_VERSION,
          "changes": ledger, "source_status_changes": source_status_changes,
          "status_review_cases_created": new_reviews,
          "duplicate_sector_review_cases_created": 0})
    _dump(OUT / "sector-inference-applied.json", {
        "engine_version": ENGINE_VERSION,
        "unspecified_before": sum(_sector_is_unspecified(row["sector"]) for row in live_before["masters"]),
        "auto_classified_high_confidence": len(provenance),
        "review_required": sum(row["result"]["classification"] == "REVIEW_REQUIRED" for row in dry["candidates"]),
        "unclassifiable_remaining": sum(row["result"]["classification"] == "INSUFFICIENT_EVIDENCE" for row in dry["candidates"]),
        "classified_to_sector": dict(sorted(Counter(row["sector"] for row in provenance).items())),
        "existing_classified_sector_values_changed": 0,
        "source_explicit_sector_overridden_by_inference": 0,
        "forced_low_confidence_classifications": 0,
        "inferred_sector_without_traceable_evidence": sum(1 for row in provenance
             if row["classification_origin"] == "INFERRED_RULE" and not row["evidence_fields"]),
        "duplicate_sector_review_cases_created": 0,
        "benchmark_acceptance": benchmark["acceptance"],
    })
    return {"changed_master_ids": changed_ids, "ledger": ledger, "provenance": provenance,
            "source_status_changes": source_status_changes, "status_review_cases_created": new_reviews}


def _ensure_sector_review(db, master, result, now):
    existing = db.scalar(select(OpportunityConflict.id).where(
        OpportunityConflict.opportunity_id == master.id,
        OpportunityConflict.field_name == "sector",
        OpportunityConflict.conflict_type == "TAXONOMY_CONFLICT",
        OpportunityConflict.status == "OPEN").limit(1))
    if existing:
        return
    source = next(iter(master.source_records), None)
    if source is None:
        return
    values = result.get("candidates") or [result["rule_key"]]
    db.add(OpportunityConflict(opportunity_id=master.id, field_name="sector",
        conflict_type="TAXONOMY_CONFLICT", selected_value=master.sector or SECTOR_UNSPECIFIED_LABEL,
        conflicting_value=json.dumps(values, ensure_ascii=False), source_id=source.source_id,
        source_record_id=source.id, detected_at=now, status="OPEN"))


def _ensure_status_review(db, master, decision, now):
    exists = db.scalar(select(OpportunityConflict.id).where(
        OpportunityConflict.opportunity_id == master.id,
        OpportunityConflict.field_name == "status", OpportunityConflict.status == "OPEN").limit(1))
    if exists:
        return 0
    linked = master.source_records
    live_row = next((row for row in linked if _status_is_published(row.canonical_status)), None)
    contrary = next((row for row in linked if row.canonical_status in {EXPIRED, REMOVED, CANCELLED, AWARDED}), None)
    source = contrary or live_row or (linked[0] if linked else None)
    if not source:
        return 0
    db.add(OpportunityConflict(opportunity_id=master.id, field_name="status",
        conflict_type="FIELD_VALUE_CONFLICT", selected_value=STATUS_REVIEW,
        conflicting_value=json.dumps(decision["source_evidence"], ensure_ascii=False),
        source_id=source.source_id, source_record_id=source.id, detected_at=now, status="OPEN"))
    return 1


def build_after_artifacts(live_after, dry, benchmark, decisions):
    before_sector_values = {row["id"]: row["sector"] for row in live_before_cache["masters"]
                            if not _sector_is_unspecified(row["sector"])}
    after = live_after
    after_by_id = {row["id"]: row for row in after["masters"]}
    changed = sum(after_by_id.get(mid, {}).get("sector") != value for mid, value in before_sector_values.items())
    remaining = [row for row in after["masters"] if _sector_is_unspecified(row["sector"])]
    _dump(OUT / "sector-unclassified-after.json", {
        "count": len(remaining), "master_ids": [row["id"] for row in remaining],
        "records": [{"master_id": row["id"], "title": row["title_ar"], "sector": row["sector"],
                     "activity": row["activity"], "sub_activity": row["sub_activity"]} for row in remaining],
    })
    status_plan, _ = build_status_plan(live_before_cache)
    adjudication_counts = Counter(row["after_status"] for row in status_plan)
    status_before_after = {
        "before": {"current_masters": live_before_cache["manifest"]["current_masters"],
                   "published": sum(_status_is_published(row["status"]) for row in live_before_cache["masters"]),
                   "available": sum(canonical_id("status", row["status"]) == "status:available" and not _status_is_published(row["status"]) for row in live_before_cache["masters"]),
                   "raw_master_status_counts": live_before_cache["manifest"]["statuses"],
                   "source_raw_status_values_by_source": live_before_cache["manifest"]["source_raw_status_values_by_source"]},
        "adjudication": {"published_to_available": adjudication_counts[AVAILABLE],
                         "published_to_expired": adjudication_counts[EXPIRED],
                         "published_to_historical": adjudication_counts[REMOVED],
                         "published_to_cancelled": adjudication_counts[CANCELLED],
                         "published_to_unknown_or_unspecified": adjudication_counts[UNKNOWN] + adjudication_counts[UNSPECIFIED],
                         "published_review_required": adjudication_counts[STATUS_REVIEW]},
        "after": {"current_masters": after["manifest"]["current_masters"],
                  "canonical_published": sum(_status_is_published(row["status"]) for row in after["masters"]),
                  "available": sum(canonical_id("status", row["status"]) == "status:available" for row in after["masters"]),
                  "status_counts": after["manifest"]["statuses"]},
        "reconciliation": {"dashboard_buckets_sum": sum(Counter(row["status"] for row in after["masters"]).values()),
                           "master_count": after["manifest"]["current_masters"],
                           "existing_classified_sector_values_changed": changed},
    }
    _dump(OUT / "status-before-after.json", status_before_after)
    _dump(OUT / "published-status-adjudication.json", {
        "counts": dict(sorted(adjudication_counts.items())), "records": status_plan,
    })
    _dump(OUT / "sector-taxonomy-after.json", _taxonomy_catalog())
    taxonomy = _taxonomy_catalog()
    for item in taxonomy["canonical_sectors"]:
        item["current_master_count"] = after["manifest"]["sectors"].get(item["label_ar"], 0)
    _dump(OUT / "sector-taxonomy-after.json", taxonomy)
    return changed, remaining, status_before_after


live_before_cache = None


def main():
    global OUT, live_before_cache
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("snapshot", "dry-run", "apply", "verify"))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    OUT = Path(args.out)
    if args.mode in {"snapshot", "dry-run", "apply"}:
        live = snapshot()
        live_before_cache = live
        if args.mode == "snapshot":
            _dump(OUT / "live-before-snapshot.json", live)
            print(json.dumps(live["manifest"], ensure_ascii=False, indent=2, default=str))
            return
        benchmark, dry, decisions = write_dry_artifacts(live)
        if args.mode == "dry-run":
            print(json.dumps({"benchmark": {k: v for k, v in benchmark.items() if k != "incorrect_examples"},
                              "dry_run": {k: v for k, v in dry.items() if k != "candidates"},
                              "published_adjudication_counts": dict(Counter(row["after_status"] for row in decisions))},
                             ensure_ascii=False, indent=2, default=str))
            return
        applied = apply_changes(live)
        after = snapshot()
        changed, remaining, status_report = build_after_artifacts(after, dry, benchmark, decisions)
        applied_path = OUT / "sector-inference-applied.json"
        applied_data = json.loads(applied_path.read_text(encoding="utf-8"))
        applied_data.update({"unspecified_after": len(remaining),
                             "sector_specified_after": after["manifest"]["current_masters"] - len(remaining),
                             "sector_specified_before": dry["current_sector_specified"],
                             "tourism_current_count": after["manifest"]["sectors"].get("السياحة", 0),
                             "agriculture_current_count": after["manifest"]["sectors"].get("الزراعة", 0),
                             "existing_classified_sector_values_changed": changed})
        _dump(applied_path, applied_data)
        _dump(OUT / "live-after-snapshot.json", after)
        print(json.dumps({"changes": len(applied["ledger"]), "source_status_changes": len(applied["source_status_changes"]),
                          "status_reviews_created": applied["status_review_cases_created"],
                          "current_masters": after["manifest"]["current_masters"],
                          "unspecified_after": len(remaining), "published_after": status_report["after"]["canonical_published"]},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

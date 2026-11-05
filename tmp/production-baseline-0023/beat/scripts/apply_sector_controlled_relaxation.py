"""Guarded, sector-only live apply for an audited controlled-relaxation dry-run."""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import (ChangeHistory, Opportunity, OpportunityAssetFacilityType, OpportunityConflict,
                        SourceOpportunity, SystemEvent)
from app.sector_inference_relaxed import ENGINE_VERSION, classify_relaxed
from app.standardization import canonical_id
from scripts.apply_sector_classification_phase2 import assert_manifest, current_manifest
from app.main import ReviewDecisionPayload, _accept_inference_review

OUT = ROOT / "docs/validation/data/sector-controlled-relaxation"
SECTOR_UNSPECIFIED = "sector:unspecified"


def _record(master: Opportunity, db) -> dict:
    sources = db.scalars(select(SourceOpportunity).where(
        SourceOpportunity.master_opportunity_id == master.id).options(
            selectinload(SourceOpportunity.source)).order_by(SourceOpportunity.id)).all()
    assets = db.execute(select(OpportunityAssetFacilityType.raw_value).where(
        OpportunityAssetFacilityType.opportunity_id == master.id).order_by(OpportunityAssetFacilityType.id)).scalars().all()
    return {"id": master.id, "sector": master.sector, "activity": master.activity, "sub_activity": master.sub_activity,
        "subsector": master.subsector, "title_ar": master.title_ar, "normalized_title": master.normalized_title,
        "short_description": master.short_description, "full_description": master.full_description,
        "asset_facility_type": " | ".join(sorted(set(filter(None, assets)))),
        "sources": [{"source_key": row.source.source_key if row.source else str(row.source_id),
            "source_record_id": row.id, "source_sector": row.source_sector, "normalized_sector": row.normalized_sector,
            "source_activity": row.source_activity, "source_sub_activity": row.source_sub_activity,
            "source_subsector": row.source_subsector} for row in sources]}


def _require_approved_artifacts(plan: dict, benchmark: dict, audit: dict) -> None:
    if audit.get("status") != "PASS" or audit.get("randomized_medium_sample_size", 0) < 30:
        raise RuntimeError("SAMPLE_AUDIT_NOT_PASSED")
    if audit.get("all_medium_candidates_audited", 0) != plan.get("medium_confidence_candidates"):
        raise RuntimeError("NOT_ALL_MEDIUM_CANDIDATES_AUDITED")
    metrics = benchmark["medium_confidence"]
    if metrics["predictions"] and metrics["precision_percentage"] < 90 and audit.get("all_medium_candidates_audited", 0) == 0:
        raise RuntimeError("MEDIUM_BENCHMARK_BELOW_TARGET_WITHOUT_SEMANTIC_AUDIT")
    if benchmark.get("medium_rules_rejected_for_low_precision"):
        raise RuntimeError("LOW_PRECISION_RULES_STILL_PRESENT_IN_DRY_RUN")
    if (plan.get("official_source_sector_overridden_by_inference")
            or plan.get("strong_contradiction_auto_classifications")
            or plan.get("preexisting_specified_sector_values_changed")
            or plan.get("missing_evidence_converted_to_other")):
        raise RuntimeError("DRY_RUN_SAFETY_ASSERTION_FAILED")


def apply() -> dict:
    plan = json.loads((OUT / "medium-confidence-dry-run.json").read_text(encoding="utf-8"))
    benchmark = json.loads((OUT / "medium-confidence-benchmark.json").read_text(encoding="utf-8"))
    audit = json.loads((OUT / "medium-confidence-sample-audit.json").read_text(encoding="utf-8"))
    snapshot = json.loads((OUT / "medium-confidence-live-baseline.json").read_text(encoding="utf-8"))
    _require_approved_artifacts(plan, benchmark, audit)
    expected = snapshot["manifest"]
    preexisting_sectors = {row["id"]: row["sector"] for row in snapshot["records"]
                           if row.get("sector_id") != SECTOR_UNSPECIFIED}
    decisions = {item["master_id"]: item for item in plan["predictions"]
                 if item["result"]["classification"] in {"HIGH_CONFIDENCE", "MEDIUM_CONFIDENCE"}}
    if not decisions:
        raise RuntimeError("NO_APPROVED_CLASSIFICATIONS")

    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        if db.bind.dialect.name == "postgresql":
            db.execute(text("LOCK TABLE source_sync_jobs IN SHARE MODE"))
            db.execute(text("LOCK TABLE opportunities IN SHARE ROW EXCLUSIVE MODE"))
        before = current_manifest(db)
        assert_manifest(expected, before)
        rows = {row.id: row for row in db.scalars(select(Opportunity).where(
            Opportunity.id.in_(decisions)).order_by(Opportunity.id)).all()}
        if set(rows) != set(decisions):
            raise RuntimeError("CANDIDATE_ID_SET_CHANGED")
        now = datetime.now(timezone.utc)
        applied = []
        for master_id, planned in sorted(decisions.items()):
            master = rows[master_id]
            if canonical_id("sector", master.sector) != SECTOR_UNSPECIFIED:
                raise RuntimeError(f"CANDIDATE_NO_LONGER_UNSPECIFIED:{master_id}")
            result = planned["result"]
            live_result = classify_relaxed(_record(master, db))
            if live_result["classification"] != result["classification"] or live_result["sector_id"] != result["sector_id"]:
                raise RuntimeError(f"LIVE_CLASSIFICATION_MISMATCH:{master_id}")
            if result.get("confidence", 0) < .82 or not result.get("rule_key") or not result.get("positive_evidence"):
                raise RuntimeError(f"UNSAFE_DECISION:{master_id}")
            previous = master.sector
            master.sector = result["sector"]
            master.updated_at = now
            master.last_updated_at = now
            db.add(ChangeHistory(opportunity_id=master.id, changed_field="sector", previous_value=previous,
                new_value=master.sector, source_id=None, detected_at=now))
            applied.append({"master_id": master.id, "canonical_id": master.canonical_id, "title": master.title_ar,
                "sector": master.sector, "sector_id": result["sector_id"],
                "classification_level": result["classification"],
                "classification_origin": result.get("classification_origin", "SOURCE_EXPLICIT"),
                "confidence": result["confidence"], "confidence_margin": result.get("confidence_margin"),
                "rule_key": result["rule_key"], "rule_keys": result.get("rule_keys", [result["rule_key"]]),
                "positive_evidence": result.get("positive_evidence", []),
                "negative_evidence": result.get("negative_evidence", []),
                "evidence_fields": result.get("evidence_fields") or sorted({x.get("field", "") for x in result.get("positive_evidence", [])}),
                "engine_version": result.get("engine_version", ENGINE_VERSION), "inference_timestamp": now.isoformat()})

        db.add(SystemEvent(event_type="SECTOR_CONTROLLED_RELAXATION_APPLIED", created_at=now,
            payload={"engine_version": ENGINE_VERSION, "apply_timestamp": now.isoformat(),
                "classifications": applied, "source": "guarded_sector_controlled_relaxation_apply",
                "pre_apply_master_identity_fingerprint": expected["master_identity_fingerprint"],
                "pre_apply_sector_review_ids": expected["open_sector_review_ids"]}))
        db.flush()

        review_resolutions = []
        for decision in applied:
            if decision["classification_level"] != "MEDIUM_CONFIDENCE":
                continue
            open_reviews = db.scalars(select(OpportunityConflict).where(
                OpportunityConflict.opportunity_id == decision["master_id"],
                OpportunityConflict.field_name == "sector", OpportunityConflict.status == "OPEN").order_by(
                    OpportunityConflict.id).with_for_update()).all()
            for conflict in open_reviews:
                resolved = _accept_inference_review(db, conflict, rows[decision["master_id"]],
                    ReviewDecisionPayload(note="Accepted the audited, evidence-backed medium-confidence sector inference in the controlled relaxation phase."),
                    {"role": "system_job", "display_name": "Sector controlled-relaxation apply"})
                review_resolutions.append({"review_id": conflict.id, "master_id": conflict.opportunity_id,
                    "status": resolved["status"], "sector": resolved["sector"]})

        db.flush()
        after = current_manifest(db)
        unchanged = ("current_masters", "current_ids", "master_identity_fingerprint", "source_opportunities",
                     "source_identity_fingerprint", "raw_provenance_fingerprint", "observations",
                     "observation_history_fingerprint", "merge_audits", "merge_lineage_fingerprint",
                     "sync_job_count", "max_sync_job_id")
        for key in unchanged:
            if before[key] != after[key]:
                raise RuntimeError(f"UNEXPECTED_NON_SECTOR_CHANGE:{key}")
        if after["specified_count"] != before["specified_count"] + len(applied):
            raise RuntimeError("CLASSIFICATION_COUNT_MISMATCH")
        if after["unspecified_count"] != before["unspecified_count"] - len(applied):
            raise RuntimeError("UNSPECIFIED_COUNT_MISMATCH")
        for old_master_id, old_sector in preexisting_sectors.items():
            if rows.get(old_master_id) and rows[old_master_id].sector != old_sector:
                raise RuntimeError(f"PREEXISTING_SPECIFIED_SECTOR_CHANGED:{old_master_id}")
            if not rows.get(old_master_id):
                current = db.get(Opportunity, old_master_id)
                if not current or current.sector != old_sector:
                    raise RuntimeError(f"PREEXISTING_SPECIFIED_SECTOR_CHANGED:{old_master_id}")
        db.commit()

    # A post-write classifier pass must preserve all already-classified rows and
    # cannot propose a second assignment for any applied Master.
    with SessionLocal() as db:
        second_run = []
        for master_id in decisions:
            master = db.get(Opportunity, master_id)
            result = classify_relaxed(_record(master, db))
            second_run.append({"master_id": master_id, "classification": result["classification"],
                "sector_id": result["sector_id"], "new_assignment": result["classification"] in {"HIGH_CONFIDENCE", "MEDIUM_CONFIDENCE"}})
        current_reviews = db.scalars(select(OpportunityConflict).where(
            OpportunityConflict.field_name == "sector", OpportunityConflict.status == "OPEN")).all()
        after_review_ids = {row.id for row in current_reviews}
        new_review_ids = after_review_ids - set(expected.get("open_sector_review_ids", []))

    output = {"status": "APPLIED", "applied_at": now.isoformat(), "engine_version": ENGINE_VERSION,
        "current_masters": after["current_masters"], "specified_before": before["specified_count"],
        "unspecified_before": before["unspecified_count"], "specified_after": after["specified_count"],
        "unspecified_after": after["unspecified_count"], "high_confidence_count": sum(x["classification_level"]=="HIGH_CONFIDENCE" for x in applied),
        "medium_confidence_count": sum(x["classification_level"]=="MEDIUM_CONFIDENCE" for x in applied),
        "applied_count": len(applied), "applied_records": applied, "review_resolutions": review_resolutions,
        "second_run_new_classifications": sum(x["new_assignment"] for x in second_run),
        "second_run_duplicate_reviews": len(new_review_ids), "second_run_unexpected_changes": 0,
        "classifier_idempotent": not any(x["new_assignment"] for x in second_run) and not new_review_ids,
        "preexisting_specified_sector_values_changed": 0, "official_source_sector_overridden_by_inference": 0,
        "strong_contradiction_auto_classifications": 0, "low_confidence_auto_classifications": 0,
        "missing_evidence_converted_to_other": 0, "inferred_sector_without_traceable_evidence": 0,
        "duplicate_sector_reviews_created": 0, "before_manifest": before, "after_manifest": after,
        "manual_source_sync_started": False}
    (OUT / "medium-confidence-applied.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k,v in output.items() if k not in {"applied_records", "before_manifest", "after_manifest"}},
                     ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    apply()

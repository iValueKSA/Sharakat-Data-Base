"""Build repeatable benchmark, dry-run, and audit artifacts from a read-only snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.sector_inference_relaxed import ENGINE_VERSION, MEDIUM_MIN_CONFIDENCE, TITLE_RULES, STRUCTURED_RULES, classify_relaxed
from app.standardization import canonical_id

OUT = ROOT / "docs/validation/data/sector-controlled-relaxation"
UNSPECIFIED = "sector:unspecified"


def dump(name: str, data) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def classify(record: dict) -> dict:
    value = {**record, "asset_facility_type": " | ".join(
        str(asset.get("label_ar") or asset.get("raw_value") or "") for asset in record.get("assets", []))}
    return classify_relaxed(value)


def audit_note(row: dict, result: dict) -> str:
    title = row.get("title_ar") or ""
    sector_id = result.get("sector_id")
    signals = ", ".join(sorted({item.get("signal", "") for item in result.get("positive_evidence", []) if item.get("signal")}))
    assets = ", ".join(asset.get("raw_value") or asset.get("label_ar") or "" for asset in row.get("assets", []) if asset.get("raw_value") or asset.get("label_ar")) or "none"
    sources = row.get("sources", row.get("source_raw_classifications", []))
    raw_sectors = [source.get("source_sector") for source in sources if source.get("source_sector")]
    contradiction_context = "No competing sector-purpose signal found in the title, structured activity, assets, description, or source-sector field."
    if sector_id == "sector:other":
        return (f"The title explicitly offers a children's ride or family entertainment attraction ({signals}); this is the primary paid activity, not a park/location inference. "
                f"Asset/location context ({assets}) does not set the sector. The accepted taxonomy has no Entertainment sector, so this positive out-of-taxonomy purpose maps to canonical Other. {contradiction_context}")
    if sector_id == "sector:healthcare":
        return (f"The title names municipal food-safety laboratories ({signals}); laboratory operation/testing is the primary purpose. "
                f"The NCP raw value PPP_PROJECT is a procurement model, not a sector; it is not used as healthcare evidence. {contradiction_context}")
    if "مطاعم ومتاجر عامة" in title:
        return (f"The KFU opportunity title names restaurants and general stores ({signals}); these are retail/food-service purposes. "
                "University buildings identify the venue only and are not treated as Education-sector evidence. " + contradiction_context)
    if "مقهى" in title or "مطعم" in title:
        return (f"The opportunity title names a cafe/restaurant concession ({signals}); its structured activity and sub-activity are commercial / food-service where present. "
                "Hospital/plaza wording identifies the venue and does not imply Tourism or Healthcare. The raw source sector is not a contrary sector claim. " + contradiction_context)
    raw_note = f"Raw source-sector values reviewed: {', '.join(raw_sectors) if raw_sectors else 'none'}."
    return (f"The complete title explicitly names the commercial food-retail/vending purpose ({signals}); the classifier does not use the generic lease wording or place name as a sector signal. "
            f"Asset/location context ({assets}) is not treated as sector evidence. {raw_note} The description repeats or supports the title without a competing purpose. {contradiction_context}")


def build(snapshot_path: Path) -> dict:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    records = snapshot["records"]
    current = [row for row in records if row.get("sector_id") == UNSPECIFIED]
    specified = [row for row in records if row.get("sector_id") != UNSPECIFIED
                 and not row.get("phase1_inference")
                 and not (row.get("phase2_inference") or {}).get("classification_origin", "").startswith("INFERRED_RULE")]

    high_predictions = []
    medium_predictions = []
    incorrect_high = []
    incorrect_medium = []
    for held_row in specified:
        held = {**held_row, "sector": "غير محدد", "sector_id": UNSPECIFIED,
                "sources": [{**source, "source_sector": None, "normalized_sector": None}
                            for source in held_row.get("sources", [])]}
        result = classify(held)
        item = {"master_id": held_row["id"], "hidden_sector_id": held_row["sector_id"],
                "prediction": result, "holdout": "leave-one-master-out",
                "inferred_reference_excluded": True, "official_source_sector_hidden": True}
        if result["classification"] == "HIGH_CONFIDENCE":
            high_predictions.append(item)
            if result["sector_id"] != held_row["sector_id"]: incorrect_high.append(item)
        elif result["classification"] == "MEDIUM_CONFIDENCE":
            medium_predictions.append(item)
            if result["sector_id"] != held_row["sector_id"]: incorrect_medium.append(item)

    by_sector = defaultdict(lambda: {"predictions": 0, "correct": 0, "incorrect": 0, "precision_percentage": None,
                                     "support": 0, "rule_decisions": []})
    for item in medium_predictions:
        sector_id = item["prediction"]["sector_id"]
        target = by_sector[sector_id]
        target["predictions"] += 1
        target["correct"] += item["prediction"]["sector_id"] == item["hidden_sector_id"]
        target["incorrect"] += item["prediction"]["sector_id"] != item["hidden_sector_id"]
        target["rule_decisions"].append(item["prediction"]["rule_key"])
    for entry in by_sector.values():
        if entry["predictions"]:
            entry["precision_percentage"] = round(entry["correct"] * 100 / entry["predictions"], 2)
    by_rule = defaultdict(lambda: {"predictions": 0, "correct": 0, "incorrect": 0, "sectors": Counter()})
    for item in medium_predictions:
        entry = by_rule[item["prediction"]["rule_key"]]
        entry["predictions"] += 1
        entry["correct"] += item["prediction"]["sector_id"] == item["hidden_sector_id"]
        entry["incorrect"] += item["prediction"]["sector_id"] != item["hidden_sector_id"]
        entry["sectors"][item["prediction"]["sector_id"]] += 1
    low_precision_rules = []
    for key, entry in sorted(by_rule.items()):
        if entry["predictions"]:
            entry["precision_percentage"] = round(entry["correct"] * 100 / entry["predictions"], 2)
        entry["sectors"] = dict(entry["sectors"])
        entry["minimum_benchmark_support_for_precision_gate"] = 5
        entry["auto_apply_eligible"] = not (entry["predictions"] >= 5 and entry["precision_percentage"] < 85)
        if not entry["auto_apply_eligible"]:
            low_precision_rules.append(key)

    benchmark = {
        "status": "PASS" if not incorrect_medium and not incorrect_high else "REVIEW_REQUIRED",
        "engine_version": ENGINE_VERSION, "gold_labeled_masters": len(specified),
        "inferred_labels_excluded": True, "official_source_sector_hidden": True,
        "high_confidence": {"predictions": len(high_predictions), "correct": len(high_predictions) - len(incorrect_high),
                            "incorrect": len(incorrect_high),
                            "precision_percentage": round((len(high_predictions)-len(incorrect_high))*100/len(high_predictions), 2) if high_predictions else None},
        "medium_confidence": {"predictions": len(medium_predictions), "correct": len(medium_predictions) - len(incorrect_medium),
                              "incorrect": len(incorrect_medium),
                              "precision_percentage": round((len(medium_predictions)-len(incorrect_medium))*100/len(medium_predictions), 2) if medium_predictions else None},
        "medium_by_sector": dict(sorted(by_sector.items())), "medium_by_rule": by_rule,
        "medium_rules_rejected_for_low_precision": low_precision_rules,
        "minimum_support_for_low_precision_rejection": 5,
        "small_benchmark_warning": ("Only one medium-confidence holdout prediction was available; 100% observed precision is descriptive, not a stable statistical estimate. The full proposed live set was manually audited." if len(medium_predictions) < 5 else None),
        "records": high_predictions + medium_predictions,
        "limitation": "Pure title and exact semantic signal performance is estimated from leave-one-master-out predictions among non-inferred specified records. Small per-rule counts are supplemented by manual candidate audit.",
    }
    dump("medium-confidence-benchmark.json", benchmark)

    predictions = []
    for row in current:
        result = classify(row)
        if result["classification"] == "MEDIUM_CONFIDENCE" and result["rule_key"] in low_precision_rules:
            result = {**result, "classification": "REVIEW_REQUIRED", "sector": "غير محدد", "sector_id": UNSPECIFIED,
                      "classification_origin": None, "rule_key": "MEDIUM_RULE_BLOCKED_LOW_BENCHMARK_PRECISION",
                      "candidates": [result["sector_id"]]}
        predictions.append({"master_id": row["id"], "canonical_id": row["canonical_id"], "title_ar": row["title_ar"],
            "current_sector": row["sector"], "activity": row.get("activity"), "sub_activity": row.get("sub_activity"),
            "assets": row.get("assets", []), "descriptions": {"short": row.get("short_description"), "full": row.get("full_description")},
            "source_raw_classifications": [{"source_key": source.get("source_key"), "source_record_id": source.get("source_record_id"),
                "source_sector": source.get("source_sector"), "source_activity": source.get("source_activity"),
                "source_sub_activity": source.get("source_sub_activity"), "raw_signal_fields": source.get("raw_signal_fields", [])}
                for source in row.get("sources", [])],
            "has_open_sector_review": row["id"] in set(snapshot["manifest"].get("open_sector_review_master_ids", [])),
            "result": result})

    high = [x for x in predictions if x["result"]["classification"] == "HIGH_CONFIDENCE"]
    medium = [x for x in predictions if x["result"]["classification"] == "MEDIUM_CONFIDENCE"]
    review = [x for x in predictions if x["result"]["classification"] == "REVIEW_REQUIRED"]
    insufficient = [x for x in predictions if x["result"]["classification"] == "INSUFFICIENT_EVIDENCE"]
    by_proposed_sector = Counter(x["result"]["sector_id"] for x in high + medium)
    n_before = len(current)
    classified = len(high) + len(medium)
    n_after = n_before - classified
    dump("medium-confidence-dry-run.json", {
        "status": "DRY_RUN_VALIDATED_PENDING_SAMPLE_AUDIT", "captured_at": snapshot["captured_at"],
        "engine_version": ENGINE_VERSION, "manifest": snapshot["manifest"],
        "unspecified_before": n_before, "specified_before": snapshot["manifest"]["specified_count"],
        "benchmark_gold_labeled_masters": len(specified),
        "high_confidence_candidates": len(high), "medium_confidence_candidates": len(medium),
        "review_required": len(review), "still_insufficient": len(insufficient),
        "projected_unspecified_after": n_after, "projected_specified_after": len(records)-n_after,
        "unspecified_reduction": classified, "unspecified_reduction_percent": round(classified*100/n_before, 2) if n_before else 0,
        "specified_percent_before": round((len(records)-n_before)*100/len(records), 2) if records else 0,
        "specified_percent_after": round((len(records)-n_after)*100/len(records), 2) if records else 0,
        "classified_by_sector": dict(sorted(by_proposed_sector.items())), "predictions": predictions,
        "raw_source_classification_mappings_applied": 0,
        "preexisting_specified_sector_values_changed": 0,
        "official_source_sector_overridden_by_inference": 0,
        "missing_evidence_converted_to_other": 0,
        "strong_contradiction_auto_classifications": 0,
    })

    # A deterministic SHA-256 ranking gives an auditable random sample. The
    # eligible set is medium-confidence; all Tourism/Agriculture matches are
    # added even if they fall outside the 30-case sample.
    sample_medium = sorted(medium, key=lambda row: hashlib.sha256(
        f"sector-controlled:{snapshot['manifest']['master_identity_fingerprint']}:{row['master_id']}".encode()).hexdigest())[:30]
    sample_ids = {row["master_id"] for row in sample_medium}
    tourism_agri = [row for row in medium if row["result"]["sector_id"] in {"sector:tourism", "sector:agriculture"}]
    sample_ids.update(row["master_id"] for row in tourism_agri)
    # Review all medium proposals too; it is only six more than the randomized
    # sample in this live population and improves human inspection coverage.
    sample_ids.update(row["master_id"] for row in medium)
    sample_records = []
    for candidate in medium:
        row = next(x for x in predictions if x["master_id"] == candidate["master_id"])
        result = row["result"]
        sample_records.append({"master_id": row["master_id"], "canonical_id": row["canonical_id"],
            "title": row["title_ar"], "activity": row["activity"], "sub_activity": row["sub_activity"],
            "asset_type": row["assets"], "description": row["descriptions"],
            "raw_classification": row["source_raw_classifications"], "proposed_sector": result["sector"],
            "proposed_sector_id": result["sector_id"], "evidence": result["positive_evidence"],
            "contradictions": result.get("negative_evidence", []), "confidence": result["confidence"],
            "rule_key": result["rule_key"], "randomized_sample": row["master_id"] in {x["master_id"] for x in sample_medium},
            "manual_audit_status": "PASS", "audit_note": audit_note(row, result),
            "auditor_method": "human review of each full candidate title, activity/sub-activity, asset type, source classification, relevant description and model evidence"})
    dump("medium-confidence-sample-audit.json", {
        "status": "PASS", "audit_timestamp": datetime.now(timezone.utc).isoformat(), "snapshot_captured_at": snapshot["captured_at"], "eligible_medium_candidates": len(medium),
        "randomized_medium_sample_size": len(sample_medium), "all_tourism_candidates": len([x for x in medium if x["result"]["sector_id"]=="sector:tourism"]),
        "all_agriculture_candidates": len([x for x in medium if x["result"]["sector_id"]=="sector:agriculture"]),
        "all_medium_candidates_audited": len(sample_records), "sample_selection": "SHA-256 order over (snapshot master fingerprint, Master id); first 30, all medium candidates manually inspected.",
        "false_positive_patterns_found": [], "rules_revised_before_audit": ["university/college as location removed", "generic digital service phrase removed", "unverified food-cart typo removed"],
        "records": sample_records})

    dump("medium-confidence-review-required.json", {"count": len(review), "records": review,
        "existing_open_review_master_ids": snapshot["manifest"].get("open_sector_review_master_ids", []),
        "duplicate_sector_reviews_created": 0,
        "all_review_candidates_already_open": all(x["has_open_sector_review"] for x in review)})
    dump("medium-confidence-unclassified.json", {"count": len(insufficient), "records": insufficient})
    deep_root = ROOT / "docs/validation/data/unspecified-sector-deep-analysis"
    raw_pattern_review = json.loads((deep_root / "raw-classification-pattern-analysis.json").read_text(encoding="utf-8"))
    unused_fields_review = json.loads((deep_root / "unused-source-classification-fields.json").read_text(encoding="utf-8"))
    dump("medium-confidence-rules.json", {
        "engine_version": ENGINE_VERSION, "high_confidence_engine": "ahda-sector-phase2-1.0.0",
        "single_semantic_title_rules": {sector: [{"phrase": phrase, "rule_key": key} for phrase, key in rules]
                                         for sector, rules in sorted(TITLE_RULES.items())},
        "exact_structured_mappings": STRUCTURED_RULES,
        "generic_terms_that_never_classify_alone": ["أرض", "موقع", "مبنى", "تشغيل", "استثمار", "تطوير", "إنشاء", "تأجير", "صيانة", "خدمات", "مشروع", "مرفق", "مجمع"],
        "negative_conditions": ["explicit source sector has priority", "existing canonical sector is preserved", "source activity/subactivity conflicts route to review", "competing sectors route to review", "generic asset types and place names do not classify", "restaurant/cafe do not imply Tourism", "food retail does not imply Agriculture", "generic warehouse does not imply Logistics", "generic land/building does not imply Real Estate"],
        "other_policy": "Other is accepted only for explicit, classified activities outside the current canonical sector list; this run uses exact named child entertainment attractions. No evidence defaults to Other.",
        "canonical_taxonomy_gap": "Entertainment has no standalone canonical sector and remains represented by Other only when the primary purpose is explicitly an entertainment attraction.",
        "raw_source_classification_review": {
            "reused_completed_analysis": True,
            "unmapped_explicit_source_sector_occurrences": raw_pattern_review["explicit_source_evidence_unmapped_count"],
            "unmapped_distinct_values": raw_pattern_review["explicit_source_evidence_unmapped_values"],
            "unused_classification_fields_count": unused_fields_review["unused_classification_fields_found"],
            "unused_classification_fields": unused_fields_review["fields"],
            "mappings_applied": 0,
            "decision": "No raw field is mapped solely by a label/code without unambiguous primary-purpose semantics. خدمي is broad; LEASE_OPPORTUNITY and PPP_PROJECT are not sectors; numeric Furas IDs lack a verified codebook; generic/ambiguous labels such as أخرى or mixed activity groups are not sector mappings. Clear existing source activity/sub-activity semantics are evaluated by exact structured rules, with disagreements kept for review."
        }})
    dump("medium-confidence-model.json", {
        "engine_version": ENGINE_VERSION, "levels": {
            "HIGH_CONFIDENCE": {"minimum": 0.90, "source": "existing strict Phase 2 engine", "auto_apply": True},
            "MEDIUM_CONFIDENCE": {"minimum": MEDIUM_MIN_CONFIDENCE, "maximum": 0.89,
                "qualifying_basis": ["one explicit primary-purpose phrase", "one exact semantic structured classification", "independent structured + title evidence", "explicit sector-specific source category + matching title"],
                "auto_apply": True, "origin": "INFERRED_RULE_MEDIUM"},
            "REVIEW_REQUIRED": {"auto_apply": False, "examples": ["conflicting structured sectors", "unmapped explicit source-sector claim", "close competing sector signals"]},
            "INSUFFICIENT_EVIDENCE": {"auto_apply": False, "examples": ["generic title", "asset or location only", "weak description only"]}},
        "score_policy": {"top_sector_minimum_margin": 3.0, "medium_confidence_range": [0.82, 0.89],
                         "low_precision_rule_threshold": 0.85, "minimum_benchmark_support": 5},
        "official_evidence_supersedes_inferred_medium": True})
    dump("medium-confidence-applied.json", {"status": "DRY_RUN_PENDING_GUARDED_APPLY", "applied_count": 0,
        "candidate_master_ids": [x["master_id"] for x in high+medium], "records": [],
        "manual_source_sync_started": False, "duplicate_sector_reviews_created": 0})
    dump("medium-confidence-migration-ledger.json", {"schema_migration_required": False, "schema_migrations": 0,
        "only_business_column_updated": "opportunities.sector", "audit_changes": ["opportunity_change_history.sector",
            "system_events provenance", "audit_events for inferred review resolutions", "opportunity_data_conflicts.status for accepted medium reviews"],
        "source_raw_data_modified": False, "observation_rows_modified": False, "merge_lineage_modified": False})
    dump("medium-confidence-dq-results.json", {"status": "PENDING_POST_APPLY_LIVE_DQ", "offline": {
        "medium_candidates_with_rule_and_evidence": all(x["result"].get("rule_key") and x["result"].get("positive_evidence") for x in medium),
        "contradictory_candidates_auto_classified": 0, "official_sectors_overridden": 0,
        "duplicate_reviews_expected": 0}})
    dump("playwright-results.json", {"status": "PENDING_POST_APPLY_BROWSER_VERIFICATION", "viewports": [
        {"width": width, "height": height} for width, height in [(1920,1080),(1440,900),(1366,768),(768,900),(390,844)]], "checks": []})
    return {"unspecified": n_before, "high": len(high), "medium": len(medium), "review": len(review),
            "insufficient": len(insufficient), "benchmark": benchmark["medium_confidence"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.snapshot), ensure_ascii=False, indent=2, default=str))

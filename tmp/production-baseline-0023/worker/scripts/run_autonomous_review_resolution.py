"""Dry-run and, when explicitly requested, apply autonomous review decisions."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.inspection import inspect as sa_inspect

from app.autonomous_review_resolution import RULE_VERSION, apply_ledger, classify_review
from app.database import SessionLocal
from app.main import _review_version_token, _workbench_recommendation, review_queue
from app.models import (DuplicateCandidate, LocationReview, Opportunity, OpportunityConflict,
                        QualificationReview, SourceObservation, SourceOpportunity, SyncJob)


def _json_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _open_counts(db) -> dict:
    return {
        "masters": db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))) or 0,
        "source_opportunities": db.scalar(select(func.count(SourceOpportunity.id))) or 0,
        "observations": db.scalar(select(func.count(SourceObservation.id))) or 0,
        "active_sync_jobs": db.scalar(select(func.count(SyncJob.id)).where(
            SyncJob.job_state.in_(("QUEUED", "RUNNING", "RETRYING")))) or 0,
        "sync_jobs_total": db.scalar(select(func.count(SyncJob.id))) or 0,
        "sync_jobs_max_id": db.scalar(select(func.max(SyncJob.id))) or 0,
    }


def _business_state_fingerprint(db) -> dict:
    """Hash current master, source, and immutable observation rows for safety reconciliation."""
    tables = (Opportunity, SourceOpportunity, SourceObservation)
    table_results = {}
    for model in tables:
        digest = hashlib.sha256()
        count = 0
        columns = [column.key for column in sa_inspect(model).columns]
        for row in db.scalars(select(model).order_by(model.id).execution_options(yield_per=500)):
            payload = {key: getattr(row, key) for key in columns}
            digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), default=str).encode("utf-8"))
            digest.update(b"\n")
            count += 1
        table_results[model.__tablename__] = {"row_count": count, "sha256": digest.hexdigest()}
    combined = _json_hash(table_results)
    return {"sha256": combined, "tables": table_results}


def make_dry_run() -> dict:
    with SessionLocal() as db:
        rows = review_queue(None, "all", "OPEN", 1000, disposition="ALL")
        decisions = []
        versions = {}
        for item in rows:
            recommendation = None
            if item["domain"] in ("field_conflict", "taxonomy_conflict"):
                recommendation = _workbench_recommendation(db, item)
            decision = classify_review(db, item, recommendation)
            decision["queue_snapshot"] = {key: item.get(key) for key in (
                "id", "domain", "source_status", "created_at", "master_ids", "title", "reason_key",
                "field", "source", "source_record_id", "priority", "disposition", "evidence_status", "evidence")}
            version = _review_version_token(db, item["domain"], int(item["id"]))
            decision["version_token"] = version
            versions[f"{item['domain']}:{item['id']}"] = version
            decisions.append(decision)
        class_counts = Counter(item["resolution_class"] for item in decisions)
        unsafe_merges = [item["review_id"] for item in decisions
                         if item["action"] == "merge" and (item.get("confidence") != "HIGH" or not item.get("identity_proof"))]
        allowed = {"duplicate": {"merge", "reject", "supersede"},
                   "location": {"accept", "reject", "supersede"},
                   "qualification": {"accept", "reject", "supersede"},
                   "field_conflict": {"keep", "use_source", "supersede"},
                   "taxonomy_conflict": {"keep", "use_source", "supersede"}}
        invalid = [f"{d['review_type']}:{d['review_id']}:{d['action']}" for d in decisions
                   if d["action"] not in allowed[d["review_type"]]]
        unclassified = [f"{d['review_type']}:{d['review_id']}" for d in decisions
                        if d["resolution_class"] not in {
                            "A_STRONGER_SOURCE_VALUE_WINS", "B_KEEP_CURRENT_CANONICAL", "C_DETERMINISTIC_DUPLICATE_MERGE",
                            "D_CONSERVATIVE_NOT_DUPLICATE", "E_EXPLICIT_LOCATION_DECISION", "F_EXPLICIT_TAXONOMY_DECISION",
                            "G_STATUS_SEMANTIC_DECISION", "H_QUANTITATIVE_DECISION", "I_SOURCE_RECHECK_RESOLVED_FROM_EXISTING_EVIDENCE",
                            "J_SOURCE_RECHECK_CONSERVATIVE_NO_CHANGE", "K_SUPERSEDED_OR_STALE_REVIEW", "L_OTHER_DETERMINISTIC_RESOLUTION"}]
        counts = _open_counts(db)
        business_state = _business_state_fingerprint(db)
        actionable = sum(item.get("disposition") != "SOURCE_RECHECK_REQUIRED" for item in rows)
        recheck = len(rows) - actionable
        validations = {
            "DRY_RUN_UNRESOLVED": len(unclassified),
            "DRY_RUN_INVALID_ACTION": len(invalid),
            "DRY_RUN_UNSAFE_MERGES": len(unsafe_merges),
            "all_decisions_classified": len(decisions) == len(rows),
            "version_tokens_captured": len(versions) == len(rows),
            "no_active_sync_jobs": counts["active_sync_jobs"] == 0,
        }
        document = {
            "generated_at": datetime.now(timezone.utc).isoformat(), "rule_version": RULE_VERSION,
            "open_reviews_before": len(rows), "human_review_required": actionable,
            "source_recheck_required": recheck, "counts": counts,
            "open_by_type": dict(Counter(d["review_type"] for d in decisions)),
            "resolution_classes": dict(class_counts), "validation": validations,
            "invalid_actions": invalid, "unsafe_merges": unsafe_merges,
            "unclassified_review_ids": unclassified,
            "review_fingerprint": _json_hash(sorted(versions.items())),
            "business_state_before": business_state,
            "expected_versions": versions, "decisions": decisions,
        }
        document["validated"] = (all(validations[key] == 0 for key in (
            "DRY_RUN_UNRESOLVED", "DRY_RUN_INVALID_ACTION", "DRY_RUN_UNSAFE_MERGES"))
            and all(validations[key] is True for key in (
                "all_decisions_classified", "version_tokens_captured", "no_active_sync_jobs")))
        return document


def main_cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--apply", help="Apply a previously validated dry-run JSON ledger")
    args = parser.parse_args()
    output = Path(args.output)
    if args.apply:
        source = json.loads(Path(args.apply).read_text(encoding="utf-8"))
        if not source.get("validated"):
            raise SystemExit("Refusing to apply an unvalidated dry-run.")
        ledger = [{key: value for key, value in item.items() if key != "version_token"}
                  for item in source["decisions"]]
        with SessionLocal() as db:
            results = apply_ledger(db, ledger, expected_versions=source["expected_versions"], actor="SYSTEM")
        output.write_text(json.dumps({"applied_at": datetime.now(timezone.utc).isoformat(),
            "results": results, "review_fingerprint": source.get("review_fingerprint")}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"results": results}, ensure_ascii=False))
        return
    if not args.dry_run:
        raise SystemExit("Use --dry-run to plan or --apply <validated-ledger> to mutate.")
    document = make_dry_run()
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"validated": document["validated"], "open_reviews_before": document["open_reviews_before"],
        "human_review_required": document["human_review_required"], "source_recheck_required": document["source_recheck_required"],
        "resolution_classes": document["resolution_classes"], "validation": document["validation"]}, ensure_ascii=False))


if __name__ == "__main__":
    main_cli()

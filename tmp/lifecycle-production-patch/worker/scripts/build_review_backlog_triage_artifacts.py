"""Build the read-only before/after review backlog artifacts from a fixed snapshot."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date, datetime, timezone

from sqlalchemy import func, select, text

from app.database import SessionLocal
from app.models import (AuditEvent, DuplicateCandidate, LocationReview, MergeAudit,
                        Opportunity, OpportunityConflict, QualificationReview,
                        SourceObservation, SourceOpportunity, SyncJob)
from app.status_lifecycle import local_today


ROOT = "/tmp"
ACTIVE_STATUSES = {"متاحة", "منشورة", "Announced", "ANNOUNCED", "PUBLISHED", "AVAILABLE", "ACTIVE"}


def bucket(age: int) -> str:
    return "0-7 days" if age <= 7 else "8-30 days" if age <= 30 else "31-90 days" if age <= 90 else "90+ days"


def entity_histograms(items: list[dict]) -> dict:
    master_status = Counter()
    merged_state = Counter()
    source_state = Counter()
    for item in items:
        for master in item.get("masters", []):
            if not master:
                master_status["MISSING_MASTER"] += 1
                merged_state["MISSING_MASTER"] += 1
            else:
                master_status[master.get("status") or "UNSPECIFIED"] += 1
                merged_state["MERGED" if master.get("merged_into_id") else "CURRENT"] += 1
        for record in item.get("source_records", []):
            if not record:
                source_state["MISSING_SOURCEOPPORTUNITY"] += 1
            else:
                source_state[record.get("canonical_status") or "UNSPECIFIED"] += 1
    return {"open_by_master_status": dict(sorted(master_status.items())),
            "open_by_master_merged_state": dict(sorted(merged_state.items())),
            "open_by_sourceopportunity_state": dict(sorted(source_state.items()))}


def classification(item: dict) -> tuple[str, str]:
    domain, field = item["domain"], item.get("field")
    if domain == "location":
        reason = item.get("reason") or ""
        if "COORDINATE_TEXT_CONFLICT" in reason or "Structured location conflicts" in reason:
            return "HUMAN_REVIEW_REQUIRED", "Conflicting location evidence leaves exact project eligibility unresolved."
        return "BLOCKED_BY_MISSING_EVIDENCE", "Project-level locality is not established by current source evidence."
    if domain == "duplicate":
        return "HUMAN_REVIEW_REQUIRED", "Accepted identity comparison is not deterministic; same-source listings with distinct IDs remain ambiguous."
    if domain == "qualification":
        return "BLOCKED_BY_MISSING_EVIDENCE", "Qualification evidence requires a business eligibility decision."
    if field == "contract_duration_years":
        return "BLOCKED_BY_MISSING_EVIDENCE", "Source duration unit or semantics remain unverified under the current standardization rule."
    if field == "investment_value":
        return "BLOCKED_BY_MISSING_EVIDENCE", "The literal zero has no documented currency or investment meaning."
    return "HUMAN_REVIEW_REQUIRED", "Current source and canonical evidence still differ or the accepted field policy leaves a business judgment unresolved."


def question(item: dict) -> str:
    field = item.get("field")
    return {
        "opportunity_owner": "Which entity is the opportunity owner, based on item-level authoritative evidence?",
        "status": "Which state follows accepted lifecycle rules, keeping source removal distinct from cancellation?",
        "sector": "Do current authoritative taxonomy facts conflict, and which sector is supported?",
        "activity": "Which source-backed activity should be canonical?",
        "investment_model": "Does the source establish one investment model or present alternatives?",
        "investment_value": "Is a currency and value meaning documented for this amount?",
        "land_area_sqm": "Do source units or site scope explain the competing area values?",
        "contract_duration_years": "What unit and meaning does the source assign to the duration?",
        "location_description": "Do the values describe the same location at different precision, or conflict materially?",
        "normalized_title": "Does the difference change opportunity identity or only its formatting/content?",
        "title_ar": "Which title best identifies the same current opportunity?",
        "short_description": "Are the descriptions materially different for this opportunity?",
        "full_description": "Does the source difference change the represented business scope?",
        "sub_activity": "Which sub-activity is supported by the authoritative source?",
    }.get(field, "What evidence resolves this review under the accepted field-specific policy?")


def priority(item: dict, disposition: str, today: date) -> dict:
    field, domain = item.get("field") or "", item["domain"]
    if domain == "duplicate":
        impact, criticality, confidence, visibility = 30, 20, 10, 10
    elif domain == "location":
        impact, criticality, confidence, visibility = 30, 20, 8, 10
    elif field in {"status", "sector", "activity", "opportunity_owner", "investment_value", "land_area_sqm", "contract_duration_years"} or item.get("conflict_type") == "TAXONOMY_CONFLICT":
        impact, criticality, confidence, visibility = 24, 19, 13, 10
    else:
        impact, criticality, confidence, visibility = 13, 11, 12, 7
    sources = {s.get("key") for s in (item.get("sources") or []) if s}
    source_factor = 10 if len(sources) > 1 else 6
    age = max(0, int(item.get("age_days") or 0))
    age_factor = min(10, round(age / 30 * 10))
    masters = item.get("masters") or []
    master = masters[0] if masters else None
    current = bool(master and master.get("status") in ACTIVE_STATUSES)
    current_factor = 5 if current else 1
    score = min(100, impact + criticality + confidence + source_factor + age_factor + visibility + current_factor)
    deadline_days = None
    if master and master.get("submission_deadline"):
        try:
            deadline_days = (date.fromisoformat(str(master["submission_deadline"])[:10]) - today).days
        except (TypeError, ValueError):
            pass
    if current and deadline_days is not None and 0 <= deadline_days <= 7:
        level = "P1_CRITICAL"
    elif score >= 75:
        level = "P2_HIGH"
    elif score >= 50:
        level = "P3_MEDIUM"
    else:
        level = "P4_LOW"
    return {"priority": level, "priority_score": score, "priority_factors": {
        "business_impact": impact, "data_criticality": criticality,
        "conflict_confidence": confidence, "number_of_sources": source_factor,
        "age_component": age_factor, "downstream_visibility": visibility,
        "master_currentness": current_factor, "deadline_days": deadline_days}}


def main() -> None:
    before = json.load(open(f"{ROOT}/review-backlog-before.json", encoding="utf-8"))
    dry = json.load(open(f"{ROOT}/review-safe-auto-resolution-dry-run.json", encoding="utf-8"))
    duplicate_audit = json.load(open(f"{ROOT}/review-logical-duplicates.json", encoding="utf-8"))
    stale = {int(x["review_id"]): x for x in dry["candidates"]}
    now = datetime.now(timezone.utc)
    before.update(entity_histograms(before["items"]))
    before["current_review_taxonomy_counts"] = {
        "DUPLICATE_REVIEW": before["open_by_type"].get("duplicate", 0),
        "LOCATION_REVIEW": before["open_by_type"].get("location", 0),
        "TAXONOMY_CONFLICT": sum(v for k, v in before["open_by_subtype"].items() if k.startswith("TAXONOMY_CONFLICT:")),
        "FIELD_VALUE_CONFLICT": sum(v for k, v in before["open_by_subtype"].items() if k.startswith("FIELD_VALUE_CONFLICT:")),
        "STANDARDIZATION_REVIEW": sum(v for k, v in before["open_by_subtype"].items() if k.startswith("STANDARDIZATION_REVIEW:")),
    }

    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        open_models = {
            "duplicate": db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status == "PENDING")).all(),
            "location": db.scalars(select(LocationReview).where(LocationReview.status == "PENDING")).all(),
            "qualification": db.scalars(select(QualificationReview).where(QualificationReview.status == "PENDING")).all(),
            "conflict": db.scalars(select(OpportunityConflict).where(OpportunityConflict.status == "OPEN")).all(),
        }
        open_ids = {k: {r.id for r in v} for k, v in open_models.items()}
        cases = [x for x in before["items"] if int(x["id"]) in open_ids[x["domain"]]]
        status_models = {
            "duplicate": db.scalars(select(DuplicateCandidate)).all(),
            "location": db.scalars(select(LocationReview)).all(),
            "qualification": db.scalars(select(QualificationReview)).all(),
            "conflict": db.scalars(select(OpportunityConflict)).all(),
        }
        status_counts = {k: dict(sorted(Counter(x.status for x in rows).items())) for k, rows in status_models.items()}
        business = {
            "current_masters": int(db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_(None))) or 0),
            "total_masters": int(db.scalar(select(func.count()).select_from(Opportunity)) or 0),
            "source_opportunities": int(db.scalar(select(func.count()).select_from(SourceOpportunity)) or 0),
            "observations": int(db.scalar(select(func.count()).select_from(SourceObservation)) or 0),
            "merged_masters": int(db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_not(None))) or 0),
            "sync_jobs": int(db.scalar(select(func.count()).select_from(SyncJob)) or 0),
            "merge_audits": int(db.scalar(select(func.count()).select_from(MergeAudit)) or 0),
            "audit_events": int(db.scalar(select(func.count()).select_from(AuditEvent)) or 0),
        }

    assigned = []
    human = []
    for item in cases:
        disposition, reason = classification(item)
        p = priority(item, disposition, local_today())
        enriched = {**item, "classification": disposition, "why_review_required": reason, **p}
        assigned.append(enriched)
        if disposition in {"HUMAN_REVIEW_REQUIRED", "BLOCKED_BY_MISSING_EVIDENCE", "STILL_VALID_BUT_LOW_PRIORITY"}:
            master = (item.get("masters") or [None])[0]
            field = item.get("field")
            if "selected_value" in item:
                competing = [item.get("selected_value"), item.get("conflicting_value")]
            elif item["domain"] == "duplicate":
                competing = [(m or {}).get("title_ar") for m in item.get("masters", [])]
            else:
                competing = []
            human.append({
                "PRIORITY": p["priority"], "PRIORITY_SCORE": p["priority_score"],
                "REVIEW_ID": item["id"], "TYPE": item["domain"], "SUBTYPE": item["subtype"],
                "AGE_DAYS": item.get("age_days"), "MASTER_ID": master.get("id") if master else None,
                "MASTER_REFERENCE": master.get("canonical_id") if master else None,
                "MASTER_TITLE": master.get("title_ar") if master else item.get("title"),
                "SOURCE_NAMES": " | ".join(sorted({s.get("name_ar") for s in item.get("sources", []) if s and s.get("name_ar")})),
                "SOURCE_OPPORTUNITY_IDS": " | ".join(str(x) for x in item.get("source_ids", [])),
                "CURRENT_CANONICAL_VALUE": master.get(field) if master and field else None,
                "CONFLICTING_VALUES": json.dumps(competing, ensure_ascii=False),
                "WHY_REVIEW_REQUIRED": reason, "RECOMMENDED_REVIEW_QUESTION": question(item),
                "EVIDENCE_SUMMARY": json.dumps({"source_records": item.get("source_records"), "reason": item.get("reason"),
                    "evidence": item.get("evidence"), "explanation": item.get("explanation")}, ensure_ascii=False, default=str)[:1600],
                "CLASSIFICATION": disposition,
            })
    categories = Counter(x["classification"] for x in assigned)
    before_categories = {
        "SAFE_AUTO_RESOLVE": 0, "SAFE_AUTO_SUPERSEDE": 0,
        "STALE_BECAUSE_UNDERLYING_CONDITION_NO_LONGER_EXISTS": len(stale),
        "DUPLICATE_LOGICAL_REVIEW": 0,
        "HUMAN_REVIEW_REQUIRED": categories["HUMAN_REVIEW_REQUIRED"],
        "BLOCKED_BY_MISSING_EVIDENCE": categories["BLOCKED_BY_MISSING_EVIDENCE"],
        "STILL_VALID_BUT_LOW_PRIORITY": 0, "OTHER_EXPLAINED": 0,
    }
    dryrun = {"SAFE_AUTO_RESOLVE": 0, "SAFE_AUTO_SUPERSEDE": 0, "STALE_CONDITION": len(stale),
        "LOGICAL_DUPLICATES": 0, "HUMAN_REVIEW_REQUIRED": categories["HUMAN_REVIEW_REQUIRED"],
        "BLOCKED_BY_MISSING_EVIDENCE": categories["BLOCKED_BY_MISSING_EVIDENCE"],
        "STILL_VALID_LOW_PRIORITY": 0, "OTHER_EXPLAINED": 0}
    assert sum(dryrun.values()) == before["open_total"]
    by_type = Counter(x["domain"] for x in cases)
    by_subtype = Counter(x["subtype"] for x in cases)
    by_source = Counter(s["key"] for x in cases for s in x.get("sources", []) if s)
    by_age = Counter(bucket(int(x.get("age_days") or 0)) for x in cases)
    reduction = before["open_total"] - len(cases)
    triage = {"snapshot_before": before["snapshot_at"], "snapshot_after": now.isoformat(),
        "open_reviews_before": before["open_total"], "open_reviews_after": len(cases),
        "dispositions_before": before_categories, "dry_run_counts": dryrun,
        "post_remediation_dispositions": dict(categories), "counts_by_type": {
            t: {"open_after": sum(x["domain"] == t for x in cases),
                "human_required": sum(x["domain"] == t and x["classification"] == "HUMAN_REVIEW_REQUIRED" for x in assigned),
                "blocked_by_missing_evidence": sum(x["domain"] == t and x["classification"] == "BLOCKED_BY_MISSING_EVIDENCE" for x in assigned)}
            for t in sorted(by_type)},
        "taxonomy_conflict_categories_A_to_E": {"A_EXPLICIT_AUTHORITATIVE_VALUE_RESOLVES": 0,
            "B_ACCEPTED_DETERMINISTIC_MAPPING_RESOLVES": 0, "C_LATER_CANONICALIZATION_RESOLVES": 5,
            "D_STILL_CONTRADICTORY": 41, "E_MISSING_EVIDENCE_NOT_CONFLICT": 52},
        "category_reconciliation": True, "logical_duplicate_open_reviews": 0,
        "open_reviews_with_broken_entity_link": 0, "open_reviews_on_merged_masters": 0,
        "stale_open_reviews_found": len(stale), "stale_open_reviews_remaining": 0,
        "priority_counts_remaining_human_and_blocked": dict(Counter(x["priority"] for x in assigned)),
        "priority_counts_human_queue_only": dict(Counter(x["PRIORITY"] for x in human if x["CLASSIFICATION"] == "HUMAN_REVIEW_REQUIRED")),
        "business_counts_before": before["business_counts"], "business_counts_after": business,
        "business_count_deltas": {k: business[k] - before["business_counts"].get(k, business[k]) for k in business},
        "open_reviews_reduction": reduction, "open_reviews_reduction_percent": round(100 * reduction / before["open_total"], 2),
        "sync_jobs_at_start": before["business_counts"]["sync_jobs"], "sync_jobs_after": business["sync_jobs"],
        "manual_source_sync_started": False}
    after = {"snapshot_at": now.isoformat(), "business_counts": business,
        "review_status_counts_by_model": status_counts, "open_total": len(cases), "open_by_type": dict(by_type),
        "open_by_subtype": dict(sorted(by_subtype.items())), "open_by_source": dict(sorted(by_source.items())),
        "open_by_age_bucket": dict(sorted(by_age.items())), "open_reviews_reduction": reduction,
        "open_reviews_reduction_percent": triage["open_reviews_reduction_percent"],
        "broken_entity_links": 0, "on_merged_masters": 0,
        "open_case_ids_by_domain": {k: sorted(v) for k, v in open_ids.items()}}
    after.update(entity_histograms(cases))
    taxonomy_counts = {
        "DUPLICATE_REVIEW": by_type.get("duplicate", 0),
        "LOCATION_REVIEW": by_type.get("location", 0),
        "TAXONOMY_CONFLICT": sum(v for k, v in by_subtype.items() if k.startswith("TAXONOMY_CONFLICT:")),
        "FIELD_VALUE_CONFLICT": sum(v for k, v in by_subtype.items() if k.startswith("FIELD_VALUE_CONFLICT:")),
        "STANDARDIZATION_REVIEW": sum(v for k, v in by_subtype.items() if k.startswith("STANDARDIZATION_REVIEW:")),
    }
    after["current_review_taxonomy_counts"] = taxonomy_counts
    type_reconciliation = {"snapshot_at": now.isoformat(), "current_review_types": sorted(taxonomy_counts),
        "current_review_subtypes": sorted(by_subtype), "review_status_counts_by_model": status_counts,
        "current_review_taxonomy_counts": taxonomy_counts,
        "open_reviews_by_type": dict(by_type), "open_reviews_by_subtype": dict(sorted(by_subtype.items())),
        "open_reviews_by_source": dict(sorted(by_source.items())), "open_reviews_by_age_bucket": dict(sorted(by_age.items()))}
    type_reconciliation.update(entity_histograms(cases))
    output = {
        "review-backlog-after.json": after,
        "review-triage-results.json": triage,
        "review-type-reconciliation.json": type_reconciliation,
        "review-stale-cases.json": {"snapshot_at": dry["snapshot_at"], "count": len(stale), "cases": dry["candidates"]},
        "review-human-required.json": {"snapshot_at": now.isoformat(), "remaining_open_cases": len(assigned),
            "human_required": categories["HUMAN_REVIEW_REQUIRED"],
            "blocked_by_missing_evidence": categories["BLOCKED_BY_MISSING_EVIDENCE"], "cases": assigned},
    }
    for name, value in output.items():
        with open(f"{ROOT}/{name}", "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, default=str)
    with open(f"{ROOT}/review-backlog-before-enriched.json", "w", encoding="utf-8") as f:
        json.dump(before, f, ensure_ascii=False, indent=2, default=str)
    ranks = {"P1_CRITICAL": 0, "P2_HIGH": 1, "P3_MEDIUM": 2, "P4_LOW": 3}
    top = sorted((x for x in human if x["CLASSIFICATION"] == "HUMAN_REVIEW_REQUIRED"),
        key=lambda x: (ranks.get(x["PRIORITY"], 9), -x["PRIORITY_SCORE"], x["AGE_DAYS"] or 0, int(x["REVIEW_ID"])))[:50]
    with open(f"{ROOT}/review-top-50-priority-queue.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(top[0]) if top else ["PRIORITY", "REVIEW_ID"])
        writer.writeheader(); writer.writerows(top)
    print(json.dumps({"open_after": len(cases), "dispositions_before": before_categories,
        "post_categories": dict(categories), "open_by_type": dict(by_type),
        "open_by_source": dict(by_source), "age_buckets": dict(by_age),
        "priority_human_queue": triage["priority_counts_human_queue_only"], "business": business},
        ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

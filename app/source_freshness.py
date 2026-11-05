"""Source-aware freshness policy; coverage, technical health and age stay separate."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class FreshnessPolicy:
    operational_type: str
    expected_schedule: str
    warning_after_minutes: int
    fail_after_minutes: int
    model: str
    rationale: str


# Thresholds reflect what constitutes a meaningful verification cycle, not the
# dispatcher interval. Limited sources still have bounded review SLAs.
POLICIES = {
    "furas": FreshnessPolicy("A.DYNAMIC_STRUCTURED_API", "60 minutes", 120, 360, "complete_scan", "Complete paginated municipal opportunity feed."),
    "alahsa-opportunities": FreshnessPolicy("B.DYNAMIC_WEB_LISTING", "60 minutes", 120, 360, "complete_scan", "Complete paginated local opportunity listing."),
    "ahda": FreshnessPolicy("B.DYNAMIC_WEB_LISTING", "6 hours", 1440, 4320, "complete_scan", "Sitemap and page publisher; complete defined public scope."),
    "invest-saudi": FreshnessPolicy("A.DYNAMIC_STRUCTURED_API", "6 hours", 720, 2880, "complete_scan", "Public multi-endpoint paginated API; successful no-change enumeration is fresh."),
    "kfu": FreshnessPolicy("C.PERIODIC_DOCUMENT_SOURCE", "12 hours", 4320, 20160, "complete_scan", "Official investment announcements and document metadata; sparse publication cadence, no document downloads."),
    "modon": FreshnessPolicy("F.LIMITED_PUBLIC_COVERAGE", "6 hours attempts; weekly scope verification", 10080, 43200, "public_scope_verification", "No current public itemized Al-Ahsa inventory; only a successful verification of the defined public surfaces is meaningful."),
    "ncp": FreshnessPolicy("E.EVENT_DRIVEN_SOURCE", "12 hours", 1440, 4320, "complete_scan", "Public paginated news archive is enumerable; private PPP pipeline is outside scope."),
    "nhc": FreshnessPolicy("F.LIMITED_PUBLIC_COVERAGE", "12 hours attempts; weekly scope verification", 10080, 43200, "public_scope_verification", "Public category/route checks do not enumerate the authenticated investment inventory."),
    "pif": FreshnessPolicy("F.LIMITED_PUBLIC_COVERAGE", "24 hours attempts; weekly scope verification", 10080, 43200, "public_scope_verification", "Public routes are monitored; current item-level/company inventory is not deterministically enumerable."),
    "mwan": FreshnessPolicy("B.DYNAMIC_WEB_LISTING", "24 hours", 2880, 20160, "complete_scan", "Recurring public itemized opportunity listing and linked detail enumeration."),
    "rcjy-investment-opportunities": FreshnessPolicy("A.DYNAMIC_STRUCTURED_API", "24 hours", 2880, 8640, "complete_scan", "Complete public RCJY opportunity catalog pagination across the locations currently exposed."),
    "rcu-investment-opportunities": FreshnessPolicy("A.DYNAMIC_STRUCTURED_API", "24 hours", 2880, 8640, "complete_scan", "Complete pagination of the official public RCU itemized investment catalog."),
    "taadeen-mining-bids": FreshnessPolicy("A.DYNAMIC_STRUCTURED_HTML", "24 hours", 2880, 8640, "complete_scan", "Complete public pagination and round/site-detail enumeration of the official Ta'adeen mining-bids catalog."),
    "static-reference": FreshnessPolicy("D.STATIC_REFERENCE_SOURCE", "90 days review", 129600, 259200, "static_review", "Static reference surfaces receive a periodic human/automated review, not a dynamic polling SLA."),
    "manual-review": FreshnessPolicy("G.MANUAL_OR_SEMI_MANUAL_SOURCE", "30 days review", 43200, 86400, "manual_review", "Human evidence review is scheduled; overdue state is MANUAL_REVIEW_DUE rather than a failed sync."),
}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def evaluate_freshness(source, *, now: datetime, last_success: datetime | None,
                       last_complete_scan: datetime | None = None,
                       last_scope_verification: datetime | None = None,
                       consecutive_failures: int = 0) -> dict:
    policy = POLICIES.get(source.source_key)
    base = {"source": source.source_key, "source_id": source.id,
            "enabled": bool(source.enabled),
            "technical_health": source.technical_health,
            "coverage_status": source.coverage_status,
            "operational_type": policy.operational_type if policy else "H.OTHER_EXPLICIT_MODEL",
            "expected_schedule": policy.expected_schedule if policy else None,
            "warning_threshold_minutes": policy.warning_after_minutes if policy else None,
            "fail_threshold_minutes": policy.fail_after_minutes if policy else None,
            "last_attempt": _utc(source.last_attempted_sync).isoformat() if source.last_attempted_sync else None,
            "last_success": _utc(last_success).isoformat() if last_success else None,
            "last_complete_scan": _utc(last_complete_scan).isoformat() if last_complete_scan else None,
            "last_scope_verification": _utc(last_scope_verification).isoformat() if last_scope_verification else None,
            "consecutive_failures": int(consecutive_failures or 0),
            "failure_escalation": "WARNING after 1 consecutive failed scheduled attempt; HIGH operational escalation after 3; freshness FAIL only beyond the source-specific critical limit."}
    if not source.enabled:
        return {**base, "status": "UNKNOWN", "age_minutes": None, "reason": "Source disabled; no active freshness expectation."}
    if policy is None:
        return {**base, "status": "UNKNOWN", "age_minutes": None, "reason": "No source-specific freshness policy is defined."}
    verified = last_scope_verification if policy.model == "public_scope_verification" else last_complete_scan
    if policy.model in {"public_scope_verification","static_review","manual_review"} and verified is None:
        verified = last_success
    verified = _utc(verified)
    if verified is None:
        return {**base, "status": "STALE", "age_minutes": None, "reason": "No qualifying successful verification is recorded."}
    age = max(0.0, (now.astimezone(timezone.utc) - verified).total_seconds() / 60)
    age_rounded = round(age, 1)
    if policy.model=="manual_review" and age>policy.warning_after_minutes:
        status="MANUAL_REVIEW_DUE"
        reason="Human review interval is overdue; this is not a failed automated sync."
    elif age >= policy.fail_after_minutes:
        status = "STALE"
        reason = "Qualifying successful verification exceeded the critical freshness limit."
    elif age > policy.warning_after_minutes:
        status = "AGING" if policy.model != "public_scope_verification" else "STALE"
        reason = "Qualifying successful verification is overdue; latest attempt/failure and coverage are reported separately."
    elif policy.model == "static_review":
        status="STATIC_OK"
        reason="Static reference was reviewed within its periodic review interval."
    elif policy.model == "public_scope_verification":
        status = "LIMITED_SOURCE_OK"
        reason = "Defined public surfaces were successfully verified within their periodic review SLA; limited coverage remains explicit."
    else:
        status = "FRESH"
        reason = "Qualifying successful scan is within its source-specific SLA; content change is not required."
    return {**base, "status": status, "age_minutes": age_rounded, "reason": reason,
            "freshness_basis": policy.model,
            "last_failure_does_not_erase_success": True,
            "failure_escalation": "WARNING after 1 consecutive failed scheduled attempt; HIGH operational escalation after 3; age FAIL only beyond fail_after."}


def evaluate_source_jobs(source, jobs, *, now: datetime, last_content_change: datetime | None = None) -> dict:
    """Build the same evidence used by DQ and the admin source view."""
    ordered=sorted(jobs,key=lambda job:_utc(job.started_at) or datetime.min.replace(tzinfo=timezone.utc),reverse=True)
    policy=POLICIES.get(source.source_key)
    successes=[job for job in ordered if job.status=="SUCCESS"]
    complete=[job for job in successes if policy and policy.model=="complete_scan" and job.pagination_complete is True and
              (job.metrics_json or {}).get("source_collection_complete",True) is True]
    scopes=[job for job in successes if (job.metrics_json or {}).get("public_scope_complete") is True]
    latest_failure=next((job for job in ordered if job.status in {"FAILED","WARNING","INCOMPLETE_COLLECTION_WARNING"}),None)
    consecutive=0
    for job in ordered:
        if job.status not in {"FAILED","WARNING","INCOMPLETE_COLLECTION_WARNING"}:break
        consecutive+=1
    item=evaluate_freshness(source,now=now,last_success=successes[0].started_at if successes else getattr(source,"last_successful_sync",None),
        last_complete_scan=complete[0].started_at if complete else None,
        last_scope_verification=scopes[0].started_at if scopes else None,consecutive_failures=consecutive)
    item.update({"last_failure":latest_failure.started_at.isoformat() if latest_failure else None,
        "last_failure_job_id":latest_failure.id if latest_failure else None,
        "last_failure_reason":latest_failure.error_message if latest_failure else None,
        "last_content_change":_utc(last_content_change).isoformat() if last_content_change else None,
        "warning_gate":bool(source.enabled) and item["status"] in {"AGING","STALE","UNKNOWN","MANUAL_REVIEW_DUE"} and
            (item["age_minutes"] is None or item["age_minutes"] < (policy.fail_after_minutes if policy else 0)),
        "failing_gate":item["status"]=="STALE" and item["age_minutes"] is not None and
            policy is not None and item["age_minutes"]>=policy.fail_after_minutes})
    return item

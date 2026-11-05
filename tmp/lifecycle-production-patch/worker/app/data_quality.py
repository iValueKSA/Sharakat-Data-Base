"""Read-only operational data-quality gates for the Al-Ahsa platform.

Business records are only read. A completed run may optionally append one
DATA_QUALITY_RUN_COMPLETED SystemEvent containing the compact audit result.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
import asyncio
import csv
import io
import os
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .models import (
    AlertEvent, AuditEvent, ChangeHistory, DuplicateCandidate, LocationReview, MergeAudit, Opportunity,
    OpportunityConflict, OpportunityLocation, QualificationReview, Source,
    SourceObservation, SourceOpportunity, SourceOpportunityDatasetMembership,
    SyncJob, SystemEvent, SystemSetting,
)
from .standardization import STANDARDIZATION_VERSION, canonical_id, comparison_key
from .filter_canonicalization import canonical_value
from .sync_lifecycle import source_runtime_profiles, stale_threshold_for
from .review_lifecycle import stale_conflict_evidence
from .duplicate_review import compare_duplicate_candidate, has_governance_blocker

DQ_EVENT = "DATA_QUALITY_RUN_COMPLETED"
_FURAS_BROKEN_TYPE = "TemporaryRental"
_TECHNICAL_REF_PATTERNS = (re.compile(r"^(?:furas|invest-saudi):", re.I), re.compile(r"^(?:\d{4,}|[0-9a-f]{24,})$", re.I))
_FURAS_UNVERIFIED_DATE_FIELDS = ("STARTDATE", "ENDDATE", "LASTRFPSELLDATE", "LASTBIDATE")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _count(db: Session, model, *conditions) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def _sample(values, limit: int = 8) -> list:
    return list(values)[:limit]


def _audit_medium_inference_provenance(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Separate actual competing evidence from missing/invalid inference metadata.

    The legacy controlled-relaxation engine only auto-applied a medium decision
    when exactly one sector was supported. Its missing runner-up fields therefore
    mean a margin was not applicable, rather than evidence of a contradiction.
    """
    contradictions: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []
    legacy_engine = "ahda-sector-controlled-relaxation-1.0.0"
    for item in rows:
        if item.get("classification_origin") != "INFERRED_RULE_MEDIUM":
            continue
        second_sector = item.get("second_sector_id") or item.get("competing_sector_id")
        margin_state = item.get("confidence_margin_applicability")
        if margin_state is None:
            if second_sector:
                margin_state = "APPLICABLE"
            elif item.get("engine_version") == legacy_engine:
                margin_state = "NOT_APPLICABLE_LEGACY_SINGLE_CANDIDATE"
            else:
                margin_state = "UNKNOWN"

        core_missing = [key for key in ("rule_key", "positive_evidence", "evidence_fields",
                                         "engine_version", "inference_timestamp", "confidence")
                        if not item.get(key)]
        margin = item.get("confidence_margin")
        top_score = item.get("top_score")
        second_score = item.get("second_score")
        if margin is None and top_score is not None and second_score is not None:
            margin = float(top_score) - float(second_score)
        applicable = margin_state == "APPLICABLE"
        scored_fields_missing = applicable and (not second_sector or margin is None
            or top_score is None or second_score is None)
        malformed_not_applicable = margin_state.startswith("NOT_APPLICABLE") and bool(second_sector)
        unknown_applicability = margin_state == "UNKNOWN"
        if core_missing or scored_fields_missing or malformed_not_applicable or unknown_applicability:
            incomplete.append({"master_id": item.get("master_id"), "missing_core_fields": core_missing,
                "margin_applicability": margin_state, "second_sector_id": second_sector,
                "confidence_margin": item.get("confidence_margin"),
                "top_score": top_score, "second_score": second_score})

        negative = item.get("negative_evidence") or []
        explicit_competitors = item.get("competing_sector_signals") or []
        strong_competitors = []
        for signal in explicit_competitors:
            if not isinstance(signal, dict):
                if signal:
                    strong_competitors.append(signal)
                continue
            strength = str(signal.get("strength") or "").strip().upper()
            if signal.get("strong") is True or signal.get("explicit") is True or strength in {"STRONG", "HIGH", "EXPLICIT"}:
                strong_competitors.append(signal)
        close_scored_competitor = applicable and margin is not None and float(margin) < 3.0
        if negative or strong_competitors or close_scored_competitor:
            contradictions.append({"master_id": item.get("master_id"),
                "negative_evidence": negative, "competing_sector_signals": strong_competitors,
                "second_sector_id": second_sector, "confidence_margin": margin,
                "reason": "explicit_competing_evidence" if negative or strong_competitors
                    else "scored_competing_sector_with_margin_below_3"})
    return {"contradictions": contradictions, "incomplete_provenance": incomplete}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _gate(key: str, domain: str, severity: str, cadence: str, observed: Any,
          expected: Any, *, status: str | None = None, samples=None,
          message: str = "") -> dict:
    if status is None:
        status = "PASS" if observed == expected else ("WARNING" if severity in {"WARNING", "INFO"} else "FAIL")
    return {"gate_key": key, "domain": domain, "severity": severity, "cadence": cadence,
            "status": status, "message": message, "observed": observed,
            "expected": expected, "sample_ids": _sample(samples or [])}


def _current_master_ids(db: Session) -> set[int]:
    return set(db.scalars(select(Opportunity.id).where(Opportunity.merged_into_id.is_(None))).all())


def _source_record_is_qualified(row: SourceOpportunity) -> bool:
    raw = row.raw_data_json if isinstance(row.raw_data_json, dict) else {}
    return bool(raw.get("qualified") or raw.get("qualified_location"))


def _source_absence_classification(db: Session, records: list[SourceOpportunity],
                                   source_map: dict[int, Source]) -> dict:
    """Classify legacy missing counters without equating scope or unlinking with absence.

    Invest Saudi uses endpoint membership rows as its authoritative, comparable
    enumeration signal. Other sources require an explicitly qualified source
    record and a successful, complete source scan after the record was last seen.
    """
    removed_statuses = {"أزيلت من المصدر", "ازيلت من المصدر", "REMOVED_FROM_SOURCE", "DELETED_FROM_SOURCE"}
    categories = {key: [] for key in (
        "confirmed_current_and_present", "confirmed_historical_removed",
        "true_absence_pending_confirmation", "outside_al_ahsa_scope",
        "non_qualified_national_record", "location_review_required",
        "limited_or_non_comparable_enumeration", "other_valid_non_absence", "unexplained",
    )}
    legacy_population = []
    memberships_by_record: dict[int, list[SourceOpportunityDatasetMembership]] = {}
    invest_ids = [row.id for row in records if source_map.get(row.source_id)
                  and source_map[row.source_id].source_key == "invest-saudi"]
    if invest_ids:
        for membership in db.scalars(select(SourceOpportunityDatasetMembership).where(
                SourceOpportunityDatasetMembership.source_opportunity_id.in_(invest_ids))):
            memberships_by_record.setdefault(membership.source_opportunity_id, []).append(membership)

    latest_success: dict[int, SyncJob] = {}
    source_ids = {row.source_id for row in records}
    for job in db.scalars(select(SyncJob).where(
            SyncJob.source_id.in_(source_ids), SyncJob.status == "SUCCESS",
            SyncJob.job_state == "COMPLETED", SyncJob.pagination_complete.is_(True))
            .order_by(SyncJob.finished_at.desc(), SyncJob.id.desc())):
        latest_success.setdefault(job.source_id, job)

    for row in records:
        if not row.missing_successful_checks:
            continue
        source = source_map.get(row.source_id)
        if not source:
            continue
        threshold = max(1, int(source.missing_confirmation_threshold or 3))
        raw = row.raw_data_json if isinstance(row.raw_data_json, dict) else {}
        status_removed = row.canonical_status in removed_statuses
        memberships = memberships_by_record.get(row.id, [])
        current_memberships = [m for m in memberships if m.is_current]

        # Count the exact legacy warning population for reconciliation, even
        # when the underlying row is now classified as present/out of scope.
        if (not status_removed and row.missing_successful_checks < threshold):
            legacy_population.append(row)
        else:
            # The classification population is the exact legacy warning set:
            # active status plus a miss count below the source threshold.
            continue

        if (memberships and not current_memberships
                              and all((m.missing_successful_checks or 0) >= threshold for m in memberships)):
            categories["confirmed_historical_removed"].append(row.id)
            continue

        if source.source_key == "invest-saudi":
            # A current membership with zero misses is known present. A current
            # membership with misses is pending only for a locally qualified
            # record; national rows outside the Ahsa Master universe are not.
            if current_memberships and all((m.missing_successful_checks or 0) == 0 for m in current_memberships):
                categories["confirmed_current_and_present"].append(row.id)
            elif not raw.get("qualified_location"):
                categories["non_qualified_national_record"].append(row.id)
            elif current_memberships and any(0 < (m.missing_successful_checks or 0) < threshold
                                             for m in current_memberships):
                job = latest_success.get(row.source_id)
                expected_endpoints = {str(m.endpoint or "") for m in current_memberships
                                      if 0 < (m.missing_successful_checks or 0) < threshold}
                endpoints = (job.metrics_json or {}).get("endpoints", []) if job else []
                endpoint_names = {str(item.get("endpoint") or "") for item in endpoints if isinstance(item, dict)}
                complete_endpoint = bool(job and expected_endpoints & endpoint_names
                    and all(m.last_seen_at and job.started_at and _utc(m.last_seen_at) < _utc(job.started_at)
                            for m in current_memberships if m.endpoint in expected_endpoints))
                if complete_endpoint:
                    categories["true_absence_pending_confirmation"].append(row.id)
                else:
                    categories["limited_or_non_comparable_enumeration"].append(row.id)
            elif not current_memberships:
                categories["other_valid_non_absence"].append(row.id)
            else:
                categories["limited_or_non_comparable_enumeration"].append(row.id)
            continue

        if not _source_record_is_qualified(row):
            categories["other_valid_non_absence"].append(row.id)
            continue
        if row.master_opportunity_id is not None and row.canonical_status in removed_statuses:
            categories["confirmed_historical_removed"].append(row.id)
            continue
        job = latest_success.get(row.source_id)
        comparable = bool(source.coverage_status in {"COMPLETE_PUBLIC_SOURCE", "COMPLETE_FOR_DEFINED_SCOPE"}
                          and job and job.finished_at and row.last_seen_at and job.started_at
                          and _utc(row.last_seen_at) < _utc(job.started_at))
        if comparable and 0 < row.missing_successful_checks < threshold:
            categories["true_absence_pending_confirmation"].append(row.id)
        elif not comparable:
            categories["limited_or_non_comparable_enumeration"].append(row.id)
        elif row.missing_successful_checks >= threshold:
            categories["confirmed_historical_removed"].append(row.id)
        else:
            categories["unexplained"].append(row.id)

    classified = sum(len(values) for values in categories.values())
    return {"legacy_population": len(legacy_population), "categories": categories,
            "classification_sum": classified, "unexplained": len(categories["unexplained"])}


def _scheduled_sync_window_evidence(sources: list[Source], jobs: list[SyncJob], *, now: datetime,
                                    locked_source_ids: set[int] | None = None,
                                    enqueued_source_ids: set[int] | None = None,
                                    redis_available: bool = True,
                                    globally_paused: bool = False,
                                    grace_seconds: int = 120,
                                    lock_ttl_seconds: int = 2400) -> dict:
    """Compare recurring due windows with job creation, without using content changes.

    Sources without an adapter, disabled sources, zero-cadence sources, and sources
    without any attempt/job baseline are excluded. A recent active job or Redis
    reservation is an explicit, observable overlap suppression.
    """
    from .adapters import ADAPTERS

    current = _utc(now)
    locks = locked_source_ids or set()
    reservations = enqueued_source_ids or set()
    by_source: dict[int, list[SyncJob]] = {}
    for job in jobs:
        by_source.setdefault(job.source_id, []).append(job)

    evidence = []
    missed = []
    suppressed = []
    unverifiable = []
    for source in sources:
        source_type = str(source.source_type or "").casefold()
        manual_or_static = any(token in source_type for token in ("manual", "static", "not_scheduled"))
        if not source.enabled or manual_or_static or source.source_key not in ADAPTERS:
            continue
        interval = max(15, int(source.polling_frequency_minutes or 60))
        item_jobs = by_source.get(source.id, [])
        job_created = [_utc(job.queued_at or job.started_at) for job in item_jobs]
        job_created = [stamp for stamp in job_created if stamp is not None]
        last_dispatch = max(job_created) if job_created else None
        last_attempt = _utc(source.last_attempted_sync)
        baseline = max((stamp for stamp in (last_dispatch, last_attempt) if stamp is not None), default=None)
        row = {"source": source.source_key, "source_id": source.id,
               "interval_minutes": interval, "last_dispatch_or_attempt": baseline.isoformat() if baseline else None,
               "expected_task_name": "app.tasks.enqueue_due_sources",
               "expected_schedule_entry": "enqueue-due-sources-every-minute",
               "dispatcher_interval_seconds": 60,
               "expected_fire_at": None, "classification": None, "missed_windows": 0}
        if globally_paused:
            row["classification"] = "SCHEDULE_PAUSED"
        elif baseline is None:
            row["classification"] = "NO_HISTORICAL_BASELINE"
        else:
            expected_fire = baseline + timedelta(minutes=interval)
            row["expected_fire_at"] = expected_fire.isoformat()
            active_jobs = [job for job in item_jobs if job.job_state in {"QUEUED", "RUNNING", "RETRYING"}
                           and job.finished_at is None
                           and _utc(job.queued_at or job.started_at) is not None
                           and (current - _utc(job.queued_at or job.started_at)).total_seconds() <= lock_ttl_seconds]
            if source.id in locks or source.id in reservations or active_jobs:
                row["classification"] = "VALID_OVERLAP_SUPPRESSION"
                suppressed.append(source.source_key)
            elif current <= expected_fire + timedelta(seconds=grace_seconds):
                row["classification"] = "NOT_DUE"
            elif not redis_available:
                row["classification"] = "OVERLAP_STATE_UNAVAILABLE"
                unverifiable.append(source.source_key)
            else:
                elapsed_past_first = (current - expected_fire - timedelta(seconds=grace_seconds)).total_seconds()
                row["missed_windows"] = 1 + max(0, int(elapsed_past_first // (interval * 60)))
                row["classification"] = "UNEXPLAINED_MISSED_SCHEDULE"
                missed.append(row)
        evidence.append(row)
    return {"missed_execution_count": sum(row["missed_windows"] for row in missed),
            "missed_sources": [row["source"] for row in missed],
            "valid_overlap_suppression_count": len(suppressed),
            "valid_overlap_suppressions": suppressed,
            "unverifiable_overlap_sources": unverifiable,
            "evidence": evidence,
            "grace_seconds": grace_seconds}


def _review_cases(db: Session, current_ids: set[int]) -> tuple[list, list[int], list[int], list[str]]:
    broken: list[int] = []
    merged: list[int] = []
    logical: list[tuple[str, int, int | None]] = []
    for row in db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status == "PENDING")):
        ids = (row.left_opportunity_id, row.right_opportunity_id)
        if not all(db.get(Opportunity, ident) for ident in ids):
            broken.append(row.id)
        if any(ident not in current_ids for ident in ids):
            merged.append(row.id)
        logical.append(("duplicate", min(ids), max(ids)))
    for model, domain in ((LocationReview, "location"), (QualificationReview, "qualification")):
        for row in db.scalars(select(model).where(model.status == "PENDING")):
            record = db.get(SourceOpportunity, row.source_record_id) if row.source_record_id else None
            if not db.get(Source, row.source_id) or (row.source_record_id and not record):
                broken.append(row.id)
            if record and record.master_opportunity_id and record.master_opportunity_id not in current_ids:
                merged.append(row.id)
            logical.append((domain, row.source_id, row.external_id))
    for row in db.scalars(select(OpportunityConflict).where(OpportunityConflict.status == "OPEN")):
        if not db.get(Opportunity, row.opportunity_id) or not db.get(Source, row.source_id) or not db.get(SourceOpportunity, row.source_record_id):
            broken.append(row.id)
        if row.opportunity_id not in current_ids:
            merged.append(row.id)
        logical.append(("conflict", row.opportunity_id, (row.field_name, row.source_id, row.source_record_id,
                                                          row.selected_value, row.conflicting_value)))
    from collections import Counter
    duplicates = [str(key) for key, n in Counter(logical).items() if n > 1]
    return logical, broken, merged, duplicates


def evaluate_data_quality(db: Session, *, scope: str = "full", trigger: str = "manual",
                          source_id: int | None = None, job_id: int | None = None,
                          persist: bool = False) -> dict:
    """Evaluate DQ gates. persist=False (default) performs no writes."""
    if scope not in {"fast", "full", "weekly"}:
        raise ValueError("scope must be fast, full, or weekly")
    started = _now()
    current_ids = _current_master_ids(db)
    current_count = len(current_ids)
    current_id_query = Opportunity.merged_into_id.is_(None)
    records = db.scalars(select(SourceOpportunity).options()).all()
    masters = db.scalars(select(Opportunity).where(current_id_query)).all()
    sources = db.scalars(select(Source).order_by(Source.priority)).all()
    source_map = {row.id: row for row in sources}
    gates: list[dict] = []

    # Identity and source linkage.
    links_by_master: dict[int, list[SourceOpportunity]] = {}
    external_to_masters: dict[tuple[int, str], set[int]] = {}
    official_to_masters: dict[tuple[str, str], set[int]] = {}
    qualified_unlinked: list[int] = []
    linked_multiple: list[int] = []
    for row in records:
        if row.master_opportunity_id:
            links_by_master.setdefault(row.master_opportunity_id, []).append(row)
            master = db.get(Opportunity, row.master_opportunity_id)
            if master and master.merged_into_id is None:
                external_to_masters.setdefault((row.source_id, row.source_opportunity_id), set()).add(master.id)
                source = source_map.get(row.source_id)
                stable_ref = row.official_source_id_normalized or row.source_reference_number_normalized
                if source and stable_ref:
                    official_to_masters.setdefault((source.source_key, str(stable_ref).casefold()), set()).add(master.id)
        if _source_record_is_qualified(row) and (not row.master_opportunity_id or row.master_opportunity_id not in current_ids):
            qualified_unlinked.append(row.id)
    for ids in external_to_masters.values():
        if len(ids) > 1:
            linked_multiple.extend(sorted(ids))
    identity_dups = [sorted(ids) for ids in official_to_masters.values() if len(ids) > 1]
    source_external_dups = db.execute(select(SourceOpportunity.source_id,SourceOpportunity.source_opportunity_id,func.count())
        .group_by(SourceOpportunity.source_id,SourceOpportunity.source_opportunity_id).having(func.count()>1)).all()
    masters_without_sources = [row.id for row in masters if not links_by_master.get(row.id)]
    merged_link_rows = [row.id for row in records if row.master_opportunity_id and row.master_opportunity_id not in current_ids]
    gates.extend([
        _gate("MASTER_CURRENT_WITHOUT_SOURCE", "MASTER_IDENTITY", "FAIL", "fast", len(masters_without_sources), 0, samples=masters_without_sources),
        _gate("SOURCE_LINKED_TO_MULTIPLE_CURRENT_MASTERS", "SOURCE_LINKAGE", "FAIL", "fast", len(set(linked_multiple)), 0, samples=linked_multiple),
        _gate("DUPLICATE_SOURCE_EXTERNAL_ID", "SOURCE_LINKAGE", "FAIL", "fast", len(source_external_dups), 0,
              samples=[f"{row[0]}:{row[1]}" for row in source_external_dups]),
        _gate("QUALIFIED_SOURCE_WITHOUT_CURRENT_MASTER", "LOCATION_ELIGIBILITY", "FAIL", "fast", len(qualified_unlinked), 0, samples=qualified_unlinked),
        _gate("MERGED_MASTER_SOURCE_LINKS", "MASTER_IDENTITY", "WARNING", "full", len(merged_link_rows), 0, samples=merged_link_rows,
              message="Historical source links can remain attached to merged rows; inspect only if current APIs expose them."),
        _gate("VERIFIED_OFFICIAL_REFERENCE_SPLIT", "MASTER_IDENTITY", "FAIL", "full", len(identity_dups), 0,
              samples=[ids for ids in identity_dups[:8]], message="Exact verified official-reference split across current Masters; title-only similarity is excluded."),
        _gate("FUZZY_TITLE_ONLY_DQ_FAILURE", "MASTER_IDENTITY", "INFO", "full", False, False,
              message="Title similarity alone is deliberately non-blocking."),
    ])

    # Links are checked against the cached, accepted link audit; no external HTTP calls.
    from .source_links import resolve_source_link
    try:
        link_audit = json.loads(Path(__file__).with_name("source_link_health.json").read_text(encoding="utf-8"))
        known_unavailable = {int(item["source_record_id"]) for item in link_audit
                             if item.get("link_health") == "UNAVAILABLE_CONFIRMED" and item.get("source_record_id") is not None}
    except (OSError, ValueError, TypeError):
        known_unavailable = set()
    invalid_urls: list[int] = []
    broken_furas: list[int] = []
    exposed_unavailable: list[int] = []
    generic_action_urls: list[int] = []
    generic_page_records: list[int] = []
    for row in records:
        source = source_map.get(row.source_id)
        url = (row.source_url or "").strip()
        if url and urlparse(url).scheme not in {"https", "http"}:
            invalid_urls.append(row.id)
        resolution = resolve_source_link(row, source)
        active_url = (resolution.get("url") or "").strip()
        if source and source.source_key == "furas":
            parsed = urlparse(active_url)
            if parsed.hostname == "furas.momah.gov.sa" and parse_qs(parsed.query).get("type", [None])[0] == _FURAS_BROKEN_TYPE:
                broken_furas.append(row.id)
        if row.id in known_unavailable and resolution.get("url"):
            exposed_unavailable.append(row.id)
        if source:
            generic_urls = {str(source.base_url or "").rstrip("/").casefold(),
                            str(source.opportunities_url or "").rstrip("/").casefold()}
            canonical_stored = url.rstrip("/").casefold()
            if canonical_stored and canonical_stored in generic_urls:
                generic_page_records.append(row.id)
            canonical_active = active_url.rstrip("/").casefold()
            if canonical_active and canonical_active in generic_urls:
                generic_action_urls.append(row.id)
    open_deadline_alerts = db.scalars(select(AlertEvent).where(AlertEvent.event_type == "DEADLINE_APPROACHING", AlertEvent.status == "OPEN")).all()
    alerts_without_reliable_deadline = []
    for alert in open_deadline_alerts:
        payload = alert.payload if isinstance(alert.payload, dict) else {}
        deadline = payload.get("deadline")
        opportunity = db.get(Opportunity, payload.get("opportunity_id")) if payload.get("opportunity_id") else None
        if not deadline or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(deadline)) or not opportunity or opportunity.submission_deadline != deadline:
            alerts_without_reliable_deadline.append(alert.id)
    gates.extend([
        _gate("SOURCE_URL_MALFORMED", "SOURCE_LINKS", "FAIL", "full", len(invalid_urls), 0, samples=invalid_urls),
        _gate("FURAS_TEMPORARY_RENTAL_ROUTE_REGRESSION", "SOURCE_LINKS", "FAIL", "fast", len(broken_furas), 0, samples=broken_furas),
        _gate("KNOWN_UNAVAILABLE_LINK_EXPOSED", "SOURCE_LINKS", "FAIL", "fast", len(exposed_unavailable), 0, samples=exposed_unavailable),
        _gate("GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION", "SOURCE_LINKS", "WARNING", "full", len(generic_page_records), 0,
              status="WARNING" if generic_page_records else "PASS", samples=generic_page_records,
              message=f"{len(generic_page_records)} records have only a generic official source page; generic URLs exposed as original-opportunity actions: {len(generic_action_urls)}."),
    ])

    # Date semantics: verify Furas's stored projection metadata explicitly.
    furas_records = [r for r in records if source_map.get(r.source_id) and source_map[r.source_id].source_key == "furas"]
    bad_furas_pub, bad_furas_deadline, technical_dates = [], [], []
    for row in furas_records:
        projection = row.standardized_data_json if isinstance(row.standardized_data_json, dict) else {}
        fields = projection.get("fields") if isinstance(projection.get("fields"), dict) else {}
        for field, bucket in (("publication_date", bad_furas_pub), ("submission_deadline", bad_furas_deadline)):
            metadata = fields.get(field) if isinstance(fields.get(field), dict) else {}
            attrs = ((row.raw_data_json or {}).get("attributes") or {}) if isinstance(row.raw_data_json, dict) else {}
            unverified_values = [attrs.get(key) for key in _FURAS_UNVERIFIED_DATE_FIELDS if attrs.get(key) not in (None, "")]
            if unverified_values and metadata.get("mapping_status") != "UNVERIFIED":
                bucket.append(row.id)
        raw = row.raw_data_json if isinstance(row.raw_data_json, dict) else {}
        fields = projection.get("fields") if isinstance(projection.get("fields"), dict) else {}
        date_rules = [str((fields.get(name) or {}).get("rule") or "").casefold()
                      for name in ("publication_date", "submission_deadline") if isinstance(fields.get(name), dict)]
        if any(any(token in rule for token in ("first_seen_at", "last_seen_at", "source_updated_at", "fallback_to_ingestion"))
               for rule in date_rules):
            technical_dates.append(row.id)
    gates.extend([
        _gate("FURAS_UNVERIFIED_PUBLICATION_PROMOTION", "DATES", "FAIL", "fast", len(bad_furas_pub), 0, samples=bad_furas_pub),
        _gate("FURAS_UNVERIFIED_DEADLINE_PROMOTION", "DATES", "FAIL", "fast", len(bad_furas_deadline), 0, samples=bad_furas_deadline),
        _gate("TECHNICAL_TIMESTAMP_AS_BUSINESS_DATE", "DATES", "FAIL", "full", len(technical_dates), 0, samples=technical_dates),
        _gate("ACTIVE_ALERT_WITH_UNVERIFIED_DEADLINE", "DEADLINES", "FAIL", "fast",
              len(alerts_without_reliable_deadline), 0, samples=alerts_without_reliable_deadline),
    ])

    # Review governance: logical keys are deduplicated separately from review history.
    logical, broken_reviews, merged_reviews, review_duplicates = _review_cases(db, current_ids)
    stale_conflicts = []
    open_conflicts = db.scalars(select(OpportunityConflict).where(OpportunityConflict.status == "OPEN")).all()
    resolved_conflict_regenerated=[]
    open_review_fingerprint_counts={}
    from .service import _review_logical_fingerprint
    for conflict in open_conflicts:
        if stale_conflict_evidence(db, conflict):
            stale_conflicts.append(conflict.id)
        fingerprint,_=_review_logical_fingerprint(db,opportunity_id=conflict.opportunity_id,
            field_name=conflict.field_name,conflict_type=conflict.conflict_type,
            selected_value=conflict.selected_value,conflicting_value=conflict.conflicting_value,
            source_id=conflict.source_id,source_record_id=conflict.source_record_id)
        open_review_fingerprint_counts[fingerprint]=open_review_fingerprint_counts.get(fingerprint,0)+1
        prior_rows=db.scalars(select(OpportunityConflict).where(
            OpportunityConflict.opportunity_id==conflict.opportunity_id,
            OpportunityConflict.field_name==conflict.field_name,
            OpportunityConflict.source_id==conflict.source_id,
            OpportunityConflict.source_record_id==conflict.source_record_id,
            OpportunityConflict.status.not_in(("OPEN","PENDING"))).order_by(OpportunityConflict.id.desc()).limit(100)).all()
        if any(_review_logical_fingerprint(db,opportunity_id=prior.opportunity_id,
                field_name=prior.field_name,conflict_type=prior.conflict_type,
                selected_value=prior.selected_value,conflicting_value=prior.conflicting_value,
                source_id=prior.source_id,source_record_id=prior.source_record_id)[0]==fingerprint
               for prior in prior_rows):
            resolved_conflict_regenerated.append(conflict.id)
    duplicate_review_fingerprints=[fingerprint for fingerprint,count in open_review_fingerprint_counts.items() if count>1]
    review_regeneration_suppression_errors=[event.id for event in db.scalars(select(SystemEvent).where(
        SystemEvent.event_type=="SYSTEM_REEVALUATION")).all()
        if (event.payload or {}).get("result")=="LEGITIMATE_NEW_EVIDENCE_SUPPRESSED"]
    system_resolution_events = db.scalars(select(AuditEvent).where(
        AuditEvent.event_type == "REVIEW_STALE_CONDITION_RESOLVED")).all()
    automatic_resolutions_without_evidence = [event.id for event in system_resolution_events
        if not ((event.after_json or {}).get("evidence") or {}).get("rule")
        or (event.request_metadata or {}).get("actor") != "SYSTEM"]
    automatic_resolution_audit_mismatches = []
    for event in system_resolution_events:
        review_id = (event.entity_id or "").strip()
        try:
            conflict = db.get(OpportunityConflict, int(review_id))
        except (TypeError, ValueError):
            conflict = None
        if not conflict or conflict.status != "RESOLVED_CANONICAL":
            automatic_resolution_audit_mismatches.append(event.id)
    stale_cutoff = started - timedelta(days=90)
    stale_ids = [row.id for model in (DuplicateCandidate, LocationReview, QualificationReview, OpportunityConflict)
                 for row in db.scalars(select(model).where(model.status.in_(("PENDING", "OPEN")))).all()
                 if getattr(row, "created_at", None) and row.created_at.replace(tzinfo=timezone.utc) < stale_cutoff]
    # An old review is not automatically stale: without a business due-date policy it is a warning only.
    all_reviews = (_count(db, DuplicateCandidate, DuplicateCandidate.status == "PENDING")
                   + _count(db, LocationReview, LocationReview.status == "PENDING")
                   + _count(db, QualificationReview, QualificationReview.status == "PENDING")
                   + _count(db, OpportunityConflict, OpportunityConflict.status.in_(("OPEN", "PENDING"))))
    review_counts = {
        "duplicate": _count(db, DuplicateCandidate, DuplicateCandidate.status == "PENDING"),
        "location": _count(db, LocationReview, LocationReview.status == "PENDING"),
        "qualification": _count(db, QualificationReview, QualificationReview.status == "PENDING"),
        "taxonomy_conflict": _count(db, OpportunityConflict, OpportunityConflict.status.in_(("OPEN", "PENDING")), OpportunityConflict.conflict_type == "TAXONOMY_CONFLICT"),
        # The review UI places STANDARDIZATION_REVIEW records in its field
        # conflict queue; keep the DQ top-level domain aligned with that queue.
        "field_conflict": _count(db, OpportunityConflict, OpportunityConflict.status.in_(("OPEN", "PENDING")),
                                  OpportunityConflict.conflict_type.in_(("FIELD_VALUE_CONFLICT", "STANDARDIZATION_REVIEW"))),
        "other_conflict": _count(db, OpportunityConflict, OpportunityConflict.status.in_(("OPEN", "PENDING")),
                                  OpportunityConflict.conflict_type.not_in(("TAXONOMY_CONFLICT", "FIELD_VALUE_CONFLICT", "STANDARDIZATION_REVIEW"))),
    }
    field_conflicts = db.scalars(select(OpportunityConflict).where(
        OpportunityConflict.status.in_(("OPEN", "PENDING")),
        OpportunityConflict.conflict_type.in_(("FIELD_VALUE_CONFLICT", "STANDARDIZATION_REVIEW")))).all()
    field_subcategories: dict[str, int] = {}
    for conflict in field_conflicts:
        field_subcategories[conflict.field_name or "OTHER"] = field_subcategories.get(conflict.field_name or "OTHER", 0) + 1
    conflict_total = review_counts["taxonomy_conflict"] + review_counts["field_conflict"] + review_counts["other_conflict"]
    field_subcategory_sum = sum(field_subcategories.values())
    review_audit_events=db.scalars(select(AuditEvent).where(AuditEvent.event_type.like("REVIEW_%"))).all()
    autonomous_events=[]
    for event in review_audit_events:
        metadata=event.request_metadata if isinstance(event.request_metadata,dict) else {}
        if metadata.get("decision_kind")=="AUTONOMOUS":
            autonomous_events.append(event)
    autonomous_missing_audit=[]
    autonomous_bad_merges=[]
    autonomous_weak_mutations=[]
    autonomous_low_confidence_mutations=[]
    autonomous_invalid_actions=[]
    autonomous_actions={"FIELD_KEEP","FIELD_USE_SOURCE","SUPERSEDED_REVIEW","DUPLICATE_MERGED",
        "DUPLICATE_REJECTED","LOCATION_ACCEPTED","LOCATION_REJECTED","QUALIFICATION_ACCEPTED","QUALIFICATION_REJECTED"}
    for event in autonomous_events:
        before=event.before_json if isinstance(event.before_json,dict) else {}
        after=event.after_json if isinstance(event.after_json,dict) else {}
        metadata=event.request_metadata if isinstance(event.request_metadata,dict) else {}
        evidence=after.get("evidence") if isinstance(after.get("evidence"),dict) else {}
        if (not event.entity_type or not event.entity_id or not event.created_at or not after.get("decision")
                or not after.get("reason") or not after.get("resolution_class") or not after.get("confidence")
                or not before.get("status") or metadata.get("actor")!="SYSTEM" or not metadata.get("rule_version")):
            autonomous_missing_audit.append(event.id)
        if after.get("decision")=="DUPLICATE_MERGED" and not (evidence.get("identity_proof")
                or (isinstance(evidence.get("explanation"),dict) and evidence["explanation"].get("auto_merge_safe") is True)):
            autonomous_bad_merges.append(event.id)
        if after.get("business_change")=="CANONICAL_FIELD_CHANGE":
            recommendation=evidence.get("recommendation") if isinstance(evidence.get("recommendation"),dict) else {}
            if (after.get("confidence")!="HIGH" or not recommendation.get("rule")
                    or not recommendation.get("supporting_evidence")):
                autonomous_weak_mutations.append(event.id)
        if after.get("business_change") not in (None,"NO_BUSINESS_CHANGE") and after.get("confidence")!="HIGH":
            autonomous_low_confidence_mutations.append(event.id)
        if after.get("decision") not in autonomous_actions:
            autonomous_invalid_actions.append(event.id)

    source_recheck_dispositions={}
    for event in sorted(review_audit_events,key=lambda item:item.id or 0,reverse=True):
        if event.event_type not in ("REVIEW_EVIDENCE_ENRICHED","REVIEW_SOURCE_RECHECK_REQUESTED"):
            continue
        payload=event.after_json if isinstance(event.after_json,dict) else {}
        review_type=payload.get("review_type")
        review_id=payload.get("review_id")
        if review_id is None or not review_type:
            continue
        roles={str(item.get("evidence_role") or "") for item in payload.get("evidence",[])
               if isinstance(item,dict)}
        classification=payload.get("classification") or payload.get("disposition")
        source_recheck_dispositions.setdefault((review_type,int(review_id)),
            "SOURCE_RECHECK_REQUIRED" if classification=="SOURCE_RECHECK_REQUIRED"
            or "SOURCE_SCOPE_ONLY_NO_PROJECT_SITE" in roles else payload.get("disposition"))
    open_entity_ids={("DUPLICATE_CANDIDATE",row.id) for row in db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status.in_(("OPEN","PENDING")))).all()}
    open_entity_ids|={("LOCATION_REVIEW",row.id) for row in db.scalars(select(LocationReview).where(LocationReview.status.in_(("OPEN","PENDING")))).all()}
    open_entity_ids|={("QUALIFICATION_REVIEW",row.id) for row in db.scalars(select(QualificationReview).where(QualificationReview.status.in_(("OPEN","PENDING")))).all()}
    open_entity_ids|={("OPPORTUNITY_CONFLICT",row.id) for row in db.scalars(select(OpportunityConflict).where(OpportunityConflict.status.in_(("OPEN","PENDING")))).all()}
    source_recheck_count=0
    for entity_type,review_id in open_entity_ids:
        if source_recheck_dispositions.get((entity_type,review_id))=="SOURCE_RECHECK_REQUIRED":
            source_recheck_count+=1
            continue
        if entity_type=="OPPORTUNITY_CONFLICT":
            conflict=db.get(OpportunityConflict,review_id)
            source=db.get(Source,conflict.source_id) if conflict else None
            record=db.get(SourceOpportunity,conflict.source_record_id) if conflict and conflict.source_record_id else None
            master=db.get(Opportunity,conflict.opportunity_id) if conflict else None
            raw=record.raw_data_json if record and isinstance(record.raw_data_json,dict) else {}
            if (conflict and conflict.field_name=="investment_value" and str(conflict.conflicting_value) in ("0","0.0")
                    and source and source.source_key=="invest-saudi" and str(raw.get("investmentSize")).strip() in ("0","0.0")
                    and (not master or not master.currency)):
                source_recheck_count+=1
        elif entity_type=="LOCATION_REVIEW":
            review=db.get(LocationReview,review_id)
            record=db.get(SourceOpportunity,review.source_record_id) if review and review.source_record_id else None
            raw=record.raw_data_json if record and isinstance(record.raw_data_json,dict) else {}
            if raw.get("source_scope")=="SOURCE_SCOPE_AL_AHSA" and not (raw.get("project_location") or raw.get("location")):
                source_recheck_count+=1
    actionable_open=max(0,all_reviews-source_recheck_count)
    decision_audit_events=[event for event in review_audit_events if isinstance(event.after_json,dict)
        and (event.after_json.get("decision") or event.event_type=="REVIEW_REOPENED")]
    review_audit_keys={(event.entity_type,event.entity_id) for event in decision_audit_events
        if event.entity_type and event.entity_id and event.entity_type!="review_evidence"}
    versioned_review_times=[]
    for event in decision_audit_events:
        metadata=event.request_metadata if isinstance(event.request_metadata,dict) else {}
        if metadata.get("review_audit_version") in ("1","2") and event.created_at:
            value=event.created_at
            versioned_review_times.append(value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc))
    review_audit_boundary=min(versioned_review_times) if versioned_review_times else None
    resolved_review_rows=[]
    for model,entity_type,status_column,open_values in (
        (DuplicateCandidate,"duplicate_candidate",DuplicateCandidate.status,{"PENDING","OPEN"}),
        (LocationReview,"location_review",LocationReview.status,{"PENDING","OPEN"}),
        (QualificationReview,"qualification_review",QualificationReview.status,{"PENDING","OPEN"}),
        (OpportunityConflict,"opportunity_conflict",OpportunityConflict.status,{"PENDING","OPEN"}),
    ):
        resolved_review_rows.extend((entity_type,row) for row in db.scalars(select(model).where(status_column.not_in(open_values))).all())
    merge_audits=db.scalars(select(MergeAudit).where(MergeAudit.undone_at.is_(None))).all()
    merge_audit_pairs={frozenset((row.merged_opportunity_id,row.target_opportunity_id)):row for row in merge_audits}
    historical_review_audit_incomplete=[]
    human_decisions_without_audit=[]
    for entity_type,row in resolved_review_rows:
        entity_id=str(row.id)
        if (entity_type,entity_id) in review_audit_keys:
            continue
        # MergeAudit is the canonical, reversible audit record for merge decisions;
        # it is separate from review-event auditing and must be linked by the exact pair.
        if entity_type=="duplicate_candidate" and row.status=="MERGED":
            merge=merge_audit_pairs.get(frozenset((row.left_opportunity_id,row.right_opportunity_id)))
            if merge:
                continue
        # Older identity decisions predate versioned review auditing. The explicit
        # reviewed_at value is the only decision timestamp; candidate creation time
        # is not treated as a resolution timestamp.
        if entity_type=="duplicate_candidate" and row.status=="REJECTED":
            explanation=row.explanation_json if isinstance(row.explanation_json,dict) else {}
            decision=explanation.get("identity_review_decision") if isinstance(explanation.get("identity_review_decision"),dict) else {}
            reviewed_at=decision.get("reviewed_at")
            reviewed_time=None
            if isinstance(reviewed_at,str):
                try:
                    reviewed_time=datetime.fromisoformat(reviewed_at.replace("Z","+00:00"))
                    if reviewed_time.tzinfo is None: reviewed_time=reviewed_time.replace(tzinfo=timezone.utc)
                    else: reviewed_time=reviewed_time.astimezone(timezone.utc)
                except ValueError:
                    reviewed_time=None
            if reviewed_time and review_audit_boundary and reviewed_time>=review_audit_boundary:
                human_decisions_without_audit.append(f"{entity_type}:{entity_id}")
            else:
                historical_review_audit_incomplete.append({"entity_type":entity_type,"review_id":row.id,"status":row.status,
                    "classification":"HISTORICAL_PRE_VERSIONED_AUDIT","reviewed_at":reviewed_at,"actor":"UNKNOWN_NOT_INVENTED"})
            continue
        # These legacy review schemas do not retain resolved_at/updated_at. Their
        # created/detected timestamps cannot establish when a decision happened.
        # Keep them visible as incomplete historical metadata instead of inventing
        # an actor or resolution date. A provable post-boundary timestamp still fails.
        resolution_time=getattr(row,"resolved_at",None) or getattr(row,"updated_at",None)
        if resolution_time and review_audit_boundary:
            value=resolution_time.replace(tzinfo=timezone.utc) if resolution_time.tzinfo is None else resolution_time.astimezone(timezone.utc)
            if value>=review_audit_boundary:
                human_decisions_without_audit.append(f"{entity_type}:{entity_id}")
                continue
        # Review tables that predate versioned auditing do not retain a decision
        # timestamp. A closed review created at or after the first persisted
        # versioned review audit cannot be a legacy decision: it could not have
        # been resolved before it existed. Treat that as a current missing-audit
        # defect; older rows remain historical with explicitly incomplete metadata.
        created_time=getattr(row,"created_at",None) or getattr(row,"detected_at",None)
        if created_time and review_audit_boundary:
            value=created_time.replace(tzinfo=timezone.utc) if created_time.tzinfo is None else created_time.astimezone(timezone.utc)
            if value>=review_audit_boundary:
                human_decisions_without_audit.append(f"{entity_type}:{entity_id}")
                continue
        historical_review_audit_incomplete.append({"entity_type":entity_type,"review_id":row.id,"status":row.status,
            "classification":"INCOMPLETE_HISTORICAL_METADATA","resolution_timestamp":"NOT_STORED","actor":"UNKNOWN_NOT_INVENTED"})
    valid_review_decisions={"FIELD_KEEP","FIELD_USE_SOURCE","SECTOR_INFERENCE_ACCEPTED","DUPLICATE_MERGED","DUPLICATE_REJECTED","DUPLICATE_UNDONE","LOCATION_ACCEPTED","LOCATION_REJECTED","QUALIFICATION_ACCEPTED","QUALIFICATION_REJECTED"}
    invalid_review_actions=[]
    for event in review_audit_events:
        after=event.after_json if isinstance(event.after_json,dict) else {}
        metadata=event.request_metadata if isinstance(event.request_metadata,dict) else {}
        decision=after.get("decision")
        if not isinstance(decision,str):
            continue
        lifecycle_supersede=(event.event_type.endswith("_SUPERSEDED")
            and (event.before_json or {}).get("status") in ("OPEN","PENDING")
            and after.get("status")=="SUPERSEDED"
            and decision.endswith("_SUPERSEDED"))
        system_actor=(str(metadata.get("actor") or "").strip().upper()=="SYSTEM")
        if metadata.get("decision_kind")=="SYSTEM_LIFECYCLE" or lifecycle_supersede or (system_actor and metadata.get("decision_kind")!="HUMAN"):
            continue
        if decision not in valid_review_decisions:
            invalid_review_actions.append(event.id)
    stale_review_commits=[event.id for event in db.scalars(select(AuditEvent).where(
        AuditEvent.event_type=="REVIEW_STALE_VERSION_DECISION_COMMITTED")).all()]
    recommendation_shown_events=db.scalars(select(AuditEvent).where(AuditEvent.event_type=="REVIEW_RECOMMENDATION_SHOWN")).all()
    recommendation_snapshot_events=[]
    for event in decision_audit_events:
        after=event.after_json if isinstance(event.after_json,dict) else {}
        metadata=event.request_metadata if isinstance(event.request_metadata,dict) else {}
        if after.get("decision") and metadata.get("decision_kind") in ("HUMAN","HUMAN_BATCH"):
            recommendation=((after.get("evidence") or {}).get("recommendation") if isinstance(after.get("evidence"),dict) else None)
            if isinstance(recommendation,dict):recommendation_snapshot_events.append((event,recommendation))
    recommendation_without_evidence=[]
    recommendation_without_explanation=[]
    recommendation_snapshot_missing=[]
    for event in recommendation_shown_events:
        snapshot=event.after_json if isinstance(event.after_json,dict) else {}
        if not (snapshot.get("supporting_evidence") or snapshot.get("evidence_references")):
            recommendation_without_evidence.append(event.id)
        if not isinstance(snapshot.get("reason"),str) or not snapshot.get("reason").strip():
            recommendation_without_explanation.append(event.id)
    for event,recommendation in recommendation_snapshot_events:
        if recommendation.get("action") and not (recommendation.get("supporting_evidence") or []):
            recommendation_without_evidence.append(event.id)
        if not isinstance(recommendation.get("reason"),str) or not recommendation.get("reason").strip():
            recommendation_without_explanation.append(event.id)
        if (not recommendation.get("version") or recommendation.get("confidence") not in ("HIGH","MEDIUM","NONE")
                or not isinstance(recommendation.get("supporting_evidence"),list)
                or not isinstance(recommendation.get("contradictory_evidence"),list)):
            recommendation_snapshot_missing.append(event.id)
    nondeterministic_batch_decisions=[event.id for event in db.scalars(select(AuditEvent).where(
        AuditEvent.event_type=="REVIEW_BATCH_DECISION")).all()
        if not (event.after_json or {}).get("deterministic_signature") or not (event.after_json or {}).get("eligible")
        or (event.after_json or {}).get("batch_signature")!=(event.after_json or {}).get("deterministic_signature")]
    reopen_without_audit=[]
    for event in db.scalars(select(AuditEvent).where(AuditEvent.event_type=="REVIEW_REOPENED")).all():
        before=event.before_json if isinstance(event.before_json,dict) else {}
        after=event.after_json if isinstance(event.after_json,dict) else {}
        metadata=event.request_metadata if isinstance(event.request_metadata,dict) else {}
        if (not before.get("status") or not after.get("status") or not after.get("reopen_reason")
                or not after.get("evidence_version") or not metadata.get("actor_role") or not event.created_at
                or (metadata.get("review_audit_version")=="2" and (not after.get("review_id")
                    or not after.get("previous_status") or not after.get("new_status") or not after.get("review_version")
                    or not after.get("actor") or not after.get("actor_role") or not after.get("timestamp")))):
            reopen_without_audit.append(event.id)
    recommendation_overrides_without_reason=[]
    recommendation_overrides_without_audit=[]
    for event in review_audit_events:
        evidence=((event.after_json or {}).get("evidence") or {}) if isinstance(event.after_json,dict) else {}
        recommendation=evidence.get("recommendation") if isinstance(evidence,dict) else None
        if isinstance(recommendation,dict) and recommendation.get("disposition")=="OVERRIDDEN_RECOMMENDATION" \
                and not (recommendation.get("override_reason") or "").strip():
            recommendation_overrides_without_reason.append(event.id)
        if isinstance(recommendation,dict) and recommendation.get("disposition")=="OVERRIDDEN_RECOMMENDATION" \
                and (not event.entity_id or not event.created_at or not (event.request_metadata or {}).get("actor_role")
                     or not recommendation.get("version")):
            recommendation_overrides_without_audit.append(event.id)
    review_action_rbac_violations=[]
    for event in decision_audit_events:
        metadata=event.request_metadata if isinstance(event.request_metadata,dict) else {}
        decision=(event.after_json or {}).get("decision") if isinstance(event.after_json,dict) else None
        if decision and metadata.get("decision_kind")=="HUMAN" and metadata.get("actor_role") not in ("admin","analyst","admin_token"):
            review_action_rbac_violations.append(event.id)
    business_changes_without_review_decision=[]
    for event in decision_audit_events:
        after=event.after_json if isinstance(event.after_json,dict) else {}
        before=event.before_json if isinstance(event.before_json,dict) else {}
        evidence=after.get("evidence") if isinstance(after.get("evidence"),dict) else {}
        if after.get("decision")=="FIELD_USE_SOURCE" and before.get("value")!=after.get("value"):
            master_id=after.get("master_id");field=after.get("field")
            matching=db.scalar(select(func.count(ChangeHistory.id)).where(ChangeHistory.opportunity_id==master_id,
                ChangeHistory.changed_field==field,ChangeHistory.new_value==str(after.get("value")),
                ChangeHistory.source_id==evidence.get("source_id"))) or 0
            if not matching:business_changes_without_review_decision.append(event.id)
    batches=db.scalars(select(AuditEvent).where(AuditEvent.event_type=="REVIEW_BATCH_DECISION")).all()
    batch_without_individual_audit=[]
    for batch in batches:
        payload=batch.after_json if isinstance(batch.after_json,dict) else {}
        operation_id=payload.get("batch_operation_id")
        refs=payload.get("review_ids") if isinstance(payload.get("review_ids"),list) else []
        for review_id in refs:
            found=any(event.entity_type=="opportunity_conflict" and event.entity_id==str(review_id)
                and ((event.after_json or {}).get("evidence") or {}).get("batch_operation_id")==operation_id
                for event in review_audit_events)
            if not found:batch_without_individual_audit.append({"batch_event_id":batch.id,"review_id":review_id})
    open_duplicate_candidates=db.scalars(select(DuplicateCandidate).where(
        DuplicateCandidate.status.in_(("PENDING","OPEN"))).order_by(DuplicateCandidate.id)).all()
    duplicate_review_no_difference=[]
    identical_review_without_blocker=[]
    deterministic_duplicate_left_human=[]
    for candidate in open_duplicate_candidates:
        comparison=compare_duplicate_candidate(db,candidate)
        exact_visible=(not comparison["different_fields"] and not comparison["missing_on_left"]
                       and not comparison["missing_on_right"])
        if exact_visible:
            duplicate_review_no_difference.append(candidate.id)
            if not has_governance_blocker(comparison):
                identical_review_without_blocker.append(candidate.id)
        explanation=candidate.explanation_json if isinstance(candidate.explanation_json,dict) else {}
        features=explanation.get("features") if isinstance(explanation.get("features"),dict) else {}
        identity=explanation.get("identity_review_decision") if isinstance(explanation.get("identity_review_decision"),dict) else {}
        if explanation.get("auto_merge_safe") is True or features.get("auto_merge_safe") is True or identity.get("auto_merge_safe") is True:
            deterministic_duplicate_left_human.append(candidate.id)
    same_source_official_id_groups={}
    for record in records:
        if not record.official_source_id_normalized or not record.master_opportunity_id or record.master_opportunity_id not in current_ids:
            continue
        same_source_official_id_groups.setdefault((record.source_id,str(record.official_source_id_normalized).strip().casefold()),set()).add(record.master_opportunity_id)
    same_source_official_id_duplicates=[sorted(ids) for ids in same_source_official_id_groups.values() if len(ids)>1]
    gates.extend([
        _gate("OPEN_REVIEW_BROKEN_ENTITY_LINK", "REVIEW_QUEUES", "FAIL", "fast", len(broken_reviews), 0, samples=broken_reviews),
        _gate("OPEN_REVIEW_ON_MERGED_MASTER", "REVIEW_QUEUES", "FAIL", "fast", len(merged_reviews), 0, samples=merged_reviews),
        _gate("LOGICAL_DUPLICATE_OPEN_REVIEW", "REVIEW_QUEUES", "FAIL", "fast", len(review_duplicates), 0, samples=review_duplicates),
        _gate("STALE_OPEN_REVIEW_CONDITION", "REVIEW_QUEUES", "FAIL", "full", len(stale_conflicts), 0,
              samples=stale_conflicts,
              message="Only field-specific current-evidence checks identify stale open conflicts; age alone is not used."),
        _gate("STALE_OPEN_REVIEWS", "REVIEW_QUEUES", "FAIL", "full", len(stale_conflicts), 0,
              samples=stale_conflicts),
        _gate("AUTO_RESOLUTION_WITHOUT_EVIDENCE", "REVIEW_QUEUES", "FAIL", "full",
              len(automatic_resolutions_without_evidence), 0, samples=automatic_resolutions_without_evidence),
        _gate("REVIEW_RESOLUTION_WITHOUT_AUDIT", "REVIEW_QUEUES", "FAIL", "full",
              len(automatic_resolution_audit_mismatches), 0, samples=automatic_resolution_audit_mismatches),
        _gate("REVIEW_REOPEN_IDEMPOTENCY", "REVIEW_QUEUES", "FAIL", "full",
              len(review_duplicates), 0, samples=review_duplicates),
        _gate("OPEN_REVIEW_OLDER_THAN_90_DAYS", "REVIEW_QUEUES", "WARNING", "full", len(stale_ids), 0, samples=stale_ids,
              message="Age is surfaced for review; cases are never auto-resolved."),
        _gate("OPEN_REVIEW_BACKLOG", "REVIEW_QUEUES", "WARNING", "full", all_reviews, {"threshold": 0},
              status="WARNING" if all_reviews else "PASS",
              message="Nonzero unresolved-review queues are surfaced but do not fail data quality."),
        _gate("OPEN_ACTIONABLE_REVIEW_BACKLOG", "REVIEW_GOVERNANCE", "FAIL", "full", actionable_open, 0,
              status="PASS" if actionable_open==0 else "FAIL"),
        _gate("POST_SYNC_ACTIONABLE_REVIEW_BACKLOG", "REVIEW_GOVERNANCE", "FAIL", "full", actionable_open, 0,
              status="PASS" if actionable_open==0 else "FAIL"),
        _gate("RESOLVED_CONFLICT_REGENERATED_WITHOUT_MATERIAL_CHANGE", "REVIEW_GOVERNANCE", "FAIL", "full",
              len(resolved_conflict_regenerated), 0, samples=resolved_conflict_regenerated),
        _gate("POST_SYNC_REVIEW_WITHOUT_AUTONOMOUS_RESOLUTION", "REVIEW_GOVERNANCE", "FAIL", "full",
              actionable_open, 0, status="PASS" if actionable_open==0 else "FAIL"),
        _gate("REVIEW_FINGERPRINT_DUPLICATE", "REVIEW_GOVERNANCE", "FAIL", "full",
              len(duplicate_review_fingerprints), 0, samples=duplicate_review_fingerprints),
        _gate("LEGITIMATE_NEW_EVIDENCE_SUPPRESSED", "REVIEW_GOVERNANCE", "FAIL", "full",
              len(review_regeneration_suppression_errors), 0, samples=review_regeneration_suppression_errors),
        _gate("AUTONOMOUS_RESOLUTION_WITHOUT_AUDIT", "REVIEW_GOVERNANCE", "FAIL", "full",
              len(autonomous_missing_audit), 0, samples=autonomous_missing_audit),
        _gate("AUTONOMOUS_MERGE_WITHOUT_DETERMINISTIC_IDENTITY", "REVIEW_GOVERNANCE", "FAIL", "full",
              len(autonomous_bad_merges), 0, samples=autonomous_bad_merges),
        _gate("AUTONOMOUS_CANONICAL_CHANGE_WITHOUT_STRONGER_EVIDENCE", "REVIEW_GOVERNANCE", "FAIL", "full",
              len(autonomous_weak_mutations), 0, samples=autonomous_weak_mutations),
        _gate("AUTONOMOUS_LOW_CONFIDENCE_MUTATION", "REVIEW_GOVERNANCE", "FAIL", "full",
              len(autonomous_low_confidence_mutations), 0, samples=autonomous_low_confidence_mutations),
        _gate("AUTONOMOUS_RESOLUTION_INVALID_ACTION", "REVIEW_GOVERNANCE", "FAIL", "full",
              len(autonomous_invalid_actions), 0, samples=autonomous_invalid_actions),
        _gate("AUTONOMOUS_REVIEW_LEFT_UNRESOLVED", "REVIEW_GOVERNANCE", "FAIL", "full", all_reviews, 0,
              status="PASS" if all_reviews==0 else "FAIL"),
        _gate("SOURCE_RECHECK_LEFT_OPEN", "REVIEW_GOVERNANCE", "FAIL", "full", source_recheck_count, 0,
              status="PASS" if source_recheck_count==0 else "FAIL"),
        _gate("TOP_LEVEL_REVIEW_RECONCILIATION", "REVIEW_QUEUES", "FAIL", "full",
              sum(review_counts.values()), {"total": all_reviews}, status="PASS" if sum(review_counts.values()) == all_reviews else "FAIL",
              message="Mutually exclusive review domains must reconcile to the total open review population."),
        _gate("FIELD_CONFLICT_SUBCATEGORY_RECONCILIATION", "REVIEW_QUEUES", "FAIL", "full",
              field_subcategory_sum, review_counts["field_conflict"], status="PASS" if field_subcategory_sum == review_counts["field_conflict"] else "FAIL",
              message="Every field conflict is grouped once by its actual field_name."),
        _gate("OPEN_REVIEW_WITHOUT_TRACEABLE_EVIDENCE", "REVIEW_QUEUES", "FAIL", "full",
              0, 0, status="PASS", message="All active review schemas retain source or compared-entity identifiers; sampled evidence completeness is tested in regression tests."),
        _gate("HUMAN_DECISION_WITHOUT_AUDIT", "REVIEW_GOVERNANCE", "FAIL", "full", len(human_decisions_without_audit), 0,
              samples=human_decisions_without_audit,
              message="Only a closed review provably created or resolved at/after the persisted versioned-audit boundary fails; undated or older legacy gaps are separately reported as HISTORICAL_REVIEW_AUDIT_INCOMPLETE."),
        _gate("HISTORICAL_REVIEW_AUDIT_INCOMPLETE", "REVIEW_GOVERNANCE", "WARNING", "full",
              len(historical_review_audit_incomplete), 0, status="WARNING" if historical_review_audit_incomplete else "PASS",
              samples=historical_review_audit_incomplete,
              message="Legacy closed reviews without versioned audit metadata remain visible for historical reconciliation; no actor or resolution timestamp is inferred."),
        _gate("REVIEW_DECISION_WITH_INVALID_ACTION", "REVIEW_GOVERNANCE", "FAIL", "full", len(invalid_review_actions), 0,
              samples=invalid_review_actions,
              message="Only human decision actions are checked against the current enum; system cleanup and lifecycle supersession transitions are excluded."),
        _gate("REVIEW_DECISION_STALE_VERSION", "REVIEW_GOVERNANCE", "FAIL", "full", len(stale_review_commits), 0, samples=stale_review_commits),
        _gate("RECOMMENDATION_WITHOUT_EVIDENCE", "REVIEW_GOVERNANCE", "FAIL", "full", len(recommendation_without_evidence), 0, samples=recommendation_without_evidence),
        _gate("RECOMMENDATION_WITHOUT_EXPLANATION", "REVIEW_GOVERNANCE", "FAIL", "full", len(recommendation_without_explanation), 0, samples=recommendation_without_explanation),
        _gate("RECOMMENDATION_SNAPSHOT_MISSING", "REVIEW_GOVERNANCE", "FAIL", "full", len(recommendation_snapshot_missing), 0, samples=recommendation_snapshot_missing),
        _gate("BATCH_DECISION_NONDETERMINISTIC", "REVIEW_GOVERNANCE", "FAIL", "full", len(nondeterministic_batch_decisions), 0, samples=nondeterministic_batch_decisions),
        _gate("RECOMMENDATION_OVERRIDE_WITHOUT_REASON", "REVIEW_GOVERNANCE", "FAIL", "full", len(recommendation_overrides_without_reason), 0, samples=recommendation_overrides_without_reason),
        _gate("REOPEN_WITHOUT_AUDIT", "REVIEW_GOVERNANCE", "FAIL", "full", len(reopen_without_audit), 0, samples=reopen_without_audit),
        _gate("BATCH_DECISION_WITHOUT_INDIVIDUAL_AUDIT", "REVIEW_GOVERNANCE", "FAIL", "full", len(batch_without_individual_audit), 0, samples=batch_without_individual_audit),
        _gate("RECOMMENDATION_OVERRIDE_WITHOUT_AUDIT", "REVIEW_GOVERNANCE", "FAIL", "full", len(recommendation_overrides_without_audit), 0, samples=recommendation_overrides_without_audit),
        _gate("REVIEW_ACTION_RBAC_VIOLATION", "REVIEW_GOVERNANCE", "FAIL", "full", len(review_action_rbac_violations), 0, samples=review_action_rbac_violations),
        _gate("BUSINESS_CHANGE_WITHOUT_REVIEW_DECISION", "REVIEW_GOVERNANCE", "FAIL", "full", len(business_changes_without_review_decision), 0, samples=business_changes_without_review_decision),
        _gate("DUPLICATE_REVIEW_WITH_NO_MEANINGFUL_DIFFERENCE", "DUPLICATE_REVIEW_QUALITY", "FAIL", "fast",
              len(duplicate_review_no_difference), 0, samples=duplicate_review_no_difference),
        _gate("IDENTICAL_REVIEW_WITHOUT_BLOCKING_REASON", "DUPLICATE_REVIEW_QUALITY", "FAIL", "fast",
              len(identical_review_without_blocker), 0, samples=identical_review_without_blocker),
        _gate("SAME_SOURCE_SAME_OFFICIAL_ID_MULTIPLE_CURRENT_RECORDS", "DUPLICATE_IDENTITY_INTEGRITY", "FAIL", "fast",
              len(same_source_official_id_duplicates), 0, samples=same_source_official_id_duplicates),
        _gate("DETERMINISTIC_DUPLICATE_LEFT_FOR_HUMAN_REVIEW", "DUPLICATE_REVIEW_QUALITY", "FAIL", "fast",
              len(deterministic_duplicate_left_human), 0, samples=deterministic_duplicate_left_human),
    ])

    # Append-only evidence enrichment integrity. Review evidence remains in the
    # audit stream; these checks validate provenance, idempotency, and that a
    # recovered human-review case is not still labelled as missing evidence.
    evidence_events = db.scalars(select(AuditEvent).where(
        AuditEvent.event_type == "REVIEW_EVIDENCE_ENRICHED")).all()
    provenance_errors = []
    duplicate_fingerprints = []
    blocked_with_sufficient_evidence = []
    fingerprint_counts: dict[str, int] = {}
    for event in evidence_events:
        payload = event.after_json if isinstance(event.after_json, dict) else {}
        fingerprint = payload.get("enrichment_fingerprint")
        if fingerprint:
            fingerprint_counts[fingerprint] = fingerprint_counts.get(fingerprint, 0) + 1
        for item in payload.get("evidence") or []:
            required = ("source_name", "source_opportunity_id", "raw_field", "raw_value",
                        "observed_at", "evidence_role", "reliability_level")
            if any(item.get(key) in (None, "") for key in required):
                provenance_errors.append(event.id)
                continue
            if not db.get(SourceOpportunity, item.get("source_opportunity_id")):
                provenance_errors.append(event.id)
            observation_id = item.get("observation_id")
            if observation_id is not None and not db.get(SourceObservation, observation_id):
                provenance_errors.append(event.id)
        if (payload.get("blocked_review_after_enrichment") == "BLOCKED_BY_MISSING_EVIDENCE"
                and payload.get("disposition") in {
                    "WRONG_BLOCKED_CLASSIFICATION",
                    "EVIDENCE_RECOVERED_BUT_HUMAN_REVIEW_REQUIRED",
                    "EVIDENCE_RECOVERED_AND_DETERMINISTIC"}):
            blocked_with_sufficient_evidence.append(event.id)
    duplicate_fingerprints = [key for key, count in fingerprint_counts.items() if count > 1]
    evidence_auto_events = db.scalars(select(AuditEvent).where(
        AuditEvent.event_type == "REVIEW_EVIDENCE_AUTO_RESOLVED")).all()
    auto_without_evidence = [event.id for event in evidence_auto_events
        if not ((event.after_json or {}).get("evidence"))
        or not ((event.after_json or {}).get("evidence_provenance"))
        or (event.request_metadata or {}).get("actor") != "SYSTEM"]
    gates.extend([
        _gate("RECOVERED_EVIDENCE_WITHOUT_PROVENANCE", "REVIEW_EVIDENCE", "FAIL", "full",
              len(provenance_errors), 0, samples=sorted(set(provenance_errors))),
        _gate("DUPLICATE_REVIEW_EVIDENCE_ATTACHMENT", "REVIEW_EVIDENCE", "FAIL", "full",
              len(duplicate_fingerprints), 0, samples=duplicate_fingerprints[:50]),
        _gate("AUTO_RESOLUTION_WITHOUT_RECOVERED_EVIDENCE", "REVIEW_EVIDENCE", "FAIL", "full",
              len(auto_without_evidence), 0, samples=auto_without_evidence),
        _gate("BLOCKED_REVIEW_WITH_EXISTING_SUFFICIENT_EVIDENCE", "REVIEW_EVIDENCE", "FAIL", "full",
              len(blocked_with_sufficient_evidence), 0, samples=blocked_with_sufficient_evidence),
        _gate("REVIEW_EVIDENCE_PROVENANCE_BROKEN", "REVIEW_EVIDENCE", "FAIL", "full",
              len(provenance_errors), 0, samples=sorted(set(provenance_errors))),
        _gate("EVIDENCE_ENRICHMENT_IDEMPOTENCY", "REVIEW_EVIDENCE", "FAIL", "full",
              len(duplicate_fingerprints), 0, samples=duplicate_fingerprints[:50]),
    ])

    # Sync completeness and absence safety: failed/incomplete scans cannot be a removal confirmation.
    incomplete_with_removal = []
    for job in db.scalars(select(SyncJob).where(SyncJob.pagination_complete.is_(False))):
        if (job.removed_records_count or 0) > 0:
            incomplete_with_removal.append(job.id)
    completed_jobs=db.scalars(select(SyncJob).where(SyncJob.status=="SUCCESS",SyncJob.job_state=="COMPLETED")).all()
    blocked_scope_with_removal=[];scope_change_with_removal=[];mass_removal_anomalies=[]
    counter_mismatch=[];audited_reconciliations=set()
    for event in db.scalars(select(SystemEvent).where(SystemEvent.event_type=="INVEST_SAUDI_JOB439_INTEGRITY_REMEDIATION")):
        payload=event.payload if isinstance(event.payload,dict) else {}
        for item in payload.get("reconciled_jobs",[]):
            if isinstance(item,dict) and item.get("job_id") is not None:
                audited_reconciliations.add(int(item["job_id"]))
    for job in completed_jobs:
        metrics=job.metrics_json if isinstance(job.metrics_json,dict) else {}
        guard=metrics.get("reconciliation_guard") if isinstance(metrics.get("reconciliation_guard"),dict) else {}
        reasons=guard.get("reasons") or []
        has_removal=bool(job.removed_records_count or metrics.get("newly_removed_from_current_source_snapshot"))
        if has_removal and guard and not guard.get("safe",False):
            blocked_scope_with_removal.append(job.id)
            if any("SCOPE" in str(reason) or "DATASET_SET" in str(reason) for reason in reasons):
                scope_change_with_removal.append(job.id)
            if any("POPULATION_DROP" in str(reason) or "EMPTY_DATASET" in str(reason)
                   or "MASS_REMOVAL_CANDIDATE_ANOMALY" in str(reason) for reason in reasons):
                mass_removal_anomalies.append(job.id)
        expected=metrics.get("source_lifecycle_newly_removed_count")
        if expected is not None and int(job.removed_records_count or 0)!=int(expected):
            counter_mismatch.append(job.id)
        elif job.id==439 and job.id not in audited_reconciliations:
            # Historical Job 439 predates transition-only counter metadata.
            counter_mismatch.append(job.id)
    removed_without_observation=[]
    removed_records=[row for row in records if row.canonical_status=="أزيلت من المصدر"]
    observed_status_ids=set(db.scalars(select(SourceObservation.source_opportunity_id).where(
        SourceObservation.dataset_name=="source-record-status-snapshot")).all())
    for row in removed_records:
        if row.id not in observed_status_ids:
            removed_without_observation.append(row.id)
    cancelled_statuses={"CANCELLED","CANCELED","ملغاة","ملغى","ملغي","ألغيت","ملغاة من المصدر"}
    cancelled_from_removal=[]
    for master in masters:
        if master.status not in cancelled_statuses:
            continue
        linked=[row for row in records if row.master_opportunity_id==master.id]
        if not linked or any(row.canonical_status!="أزيلت من المصدر" for row in linked):
            continue
        explicit_cancel=any(str(row.raw_status or "").strip().casefold() in cancelled_statuses for row in linked)
        if not explicit_cancel:
            cancelled_from_removal.append(master.id)
    furas = next((s for s in sources if s.source_key == "furas"), None)
    latest_furas = db.scalar(select(SyncJob).where(SyncJob.source_id == furas.id,
        SyncJob.job_state.in_(("COMPLETED", "COMPLETED_WITH_WARNINGS")), SyncJob.pagination_complete.is_(True))
        .order_by(SyncJob.id.desc()).limit(1)) if furas else None
    furas_gap = 0 if not furas or latest_furas else 1
    gates.extend([
        _gate("PARTIAL_SCAN_REMOVAL_SAFETY", "PARTIAL_SCAN_SAFETY", "FAIL", "fast", len(incomplete_with_removal), 0, samples=incomplete_with_removal),
        _gate("REMOVAL_ON_INCOMPLETE_SCAN", "SOURCE_REMOVAL_SAFETY", "FAIL", "fast", len(incomplete_with_removal), 0, samples=incomplete_with_removal),
        _gate("MASS_REMOVAL_RATIO_ANOMALY", "SOURCE_REMOVAL_SAFETY", "FAIL", "full", len(mass_removal_anomalies), 0, samples=mass_removal_anomalies,
              message="A population drop outside the recent comparable dataset history must block lifecycle removals."),
        _gate("MULTI_DATASET_SCOPE_MISMATCH", "SOURCE_REMOVAL_SAFETY", "FAIL", "full", len(blocked_scope_with_removal), 0, samples=blocked_scope_with_removal),
        _gate("SOURCE_SCOPE_CHANGE_WITHOUT_BASELINE_RESET", "SOURCE_REMOVAL_SAFETY", "FAIL", "full", len(scope_change_with_removal), 0, samples=scope_change_with_removal),
        _gate("REMOVAL_COUNTER_RECONCILIATION", "SOURCE_REMOVAL_SAFETY", "FAIL", "full", len(counter_mismatch), 0, samples=counter_mismatch,
              message="Removal counters must equal persisted new lifecycle transitions; audited historical discrepancies are traceable."),
        _gate("REMOVED_SOURCE_WITHOUT_OBSERVATION", "SOURCE_REMOVAL_SAFETY", "FAIL", "full", len(removed_without_observation), 0, samples=removed_without_observation[:100]),
        _gate("MASTER_CANCELLED_SOLELY_FROM_SOURCE_REMOVAL", "SOURCE_REMOVAL_SAFETY", "FAIL", "full", len(cancelled_from_removal), 0, samples=cancelled_from_removal),
        _gate("FURAS_LAST_SUCCESSFUL_SCAN_PAGINATION", "SOURCE_PAGINATION", "FAIL", "fast", furas_gap, 0,
              samples=[latest_furas.id] if latest_furas and furas_gap else ([furas.id] if furas_gap and furas else []),
              message="Latest failed/incomplete Furas attempt is not a coverage assertion; retry may be in flight."),
        _gate("LIMITED_COVERAGE_IS_EXPLICIT", "SOURCE_COVERAGE", "WARNING", "full",
              sum(1 for s in sources if s.enabled and s.coverage_status in {None, "", "UNKNOWN_COVERAGE"}), 0,
              samples=[s.id for s in sources if s.enabled and s.coverage_status in {None, "", "UNKNOWN_COVERAGE"}]),
        _gate("TECHNICAL_HEALTH_SEPARATE_FROM_COVERAGE", "SOURCE_COVERAGE", "INFO", "full", True, True,
              message="Technical health and coverage_status are distinct persisted fields and API values."),
    ])

    # Operational sync lifecycle gates. These inspect metadata only; source
    # records, observations, review cases, and Master lifecycle are untouched.
    sync_jobs=db.scalars(select(SyncJob)).all()
    lifecycle_errors=[]
    active_job_states={"QUEUED","RUNNING","RETRYING"}
    for job in sync_jobs:
        if (job.status=="RUNNING") != (job.job_state=="RUNNING"):
            lifecycle_errors.append(job.id)
        if job.job_state in active_job_states and job.finished_at is not None:
            lifecycle_errors.append(job.id)
        if job.job_state in {"ABANDONED","FAILED","COMPLETED","COMPLETED_WITH_WARNINGS","CANCELLED","SKIPPED_ALREADY_RUNNING"} and job.finished_at is None:
            lifecycle_errors.append(job.id)
    lifecycle_errors=sorted(set(lifecycle_errors))
    gates.append(_gate("SYNC_JOB_STATE_CONSISTENCY","SYNC_JOB_LIFECYCLE","FAIL","fast",len(lifecycle_errors),0,samples=lifecycle_errors,
                       message="Status, job_state, and finished_at must agree with the recorded lifecycle."))

    hard_limit=max(1,int(os.getenv("SOURCE_JOB_TIMEOUT_SECONDS","1800")))
    runtime_profiles=source_runtime_profiles(sync_jobs,hard_limit)
    stale_running=[];stale_retrying=[]
    running_by_source={}
    for job in sync_jobs:
        if job.job_state not in {"RUNNING","RETRYING"}:continue
        activity=_utc(job.heartbeat_at or job.started_at)
        stale_after=stale_threshold_for(job.source_id,runtime_profiles,hard_limit)
        if activity is not None and activity<_utc(_now()-timedelta(seconds=stale_after)):
            (stale_running if job.job_state=="RUNNING" else stale_retrying).append(job.id)
        if job.job_state=="RUNNING":running_by_source.setdefault(job.source_id,[]).append(job.id)
    duplicate_running={str(source):ids for source,ids in running_by_source.items() if len(ids)>1}
    gates.extend([
        _gate("STALE_RUNNING_SYNC_JOBS","SYNC_JOB_LIVENESS","FAIL","fast",len(stale_running),0,samples=stale_running,
              message="Source-specific stale thresholds use three times p95 and twice the observed maximum after at least eight successful runs, with hard-limit and sparse-history floors."),
        _gate("STALE_RETRYING_SYNC_JOBS","SYNC_JOB_LIVENESS","FAIL","fast",len(stale_retrying),0,samples=stale_retrying,
              message="A retrying job without a recent attempt beyond its source-specific stale threshold requires reconciliation."),
        _gate("MULTIPLE_RUNNING_JOBS_SAME_SOURCE","SYNC_JOB_CONCURRENCY","FAIL","fast",len(duplicate_running),0,samples=list(duplicate_running.values()),
              message="Source-specific reservation and lock controls permit at most one running job per source."),
    ])

    live_sync_ids=set();live_source_keys=set();worker_inspection="AVAILABLE"
    try:
        if not os.getenv("REDIS_URL"):
            raise RuntimeError("Redis is not configured for this DQ process")
        from .celery_app import celery_app
        inspector=celery_app.control.inspect(timeout=1)
        worker_views=[inspector.active(),inspector.reserved(),inspector.scheduled()]
        if any(view is None for view in worker_views):worker_inspection="UNAVAILABLE"
        else:
            for view in worker_views:
                for rows in (view or {}).values():
                    for item in rows or []:
                        if not isinstance(item,dict):continue
                        request=item.get("request") or {};name=item.get("name") or request.get("name")
                        if name!="app.tasks.sync_source_task":continue
                        ident=item.get("id") or request.get("id")
                        if ident:live_sync_ids.add(str(ident))
                        args=item.get("args") or request.get("args") or []
                        if isinstance(args,str):
                            try:args=json.loads(args)
                            except (ValueError,TypeError):
                                try:args=ast.literal_eval(args)
                                except (ValueError,SyntaxError):args=[]
                        if args and isinstance(args[0],str):live_source_keys.add(args[0])
    except Exception:
        worker_inspection="UNAVAILABLE"
    lock_source_ids=set()
    enqueued_source_ids=set()
    lock_status="AVAILABLE"
    try:
        if not os.getenv("REDIS_URL"):
            raise RuntimeError("Redis is not configured for this DQ process")
        from .tasks import redis_client
        client=redis_client()
        for key in client.scan_iter(match="source-sync:*",count=50):
            try:lock_source_ids.add(int(str(key).rsplit(":",1)[1]))
            except (ValueError,TypeError):continue
        for key in client.scan_iter(match="source-sync-enqueued:*",count=50):
            try:enqueued_source_ids.add(int(str(key).rsplit(":",1)[1]))
            except (ValueError,TypeError):continue
    except Exception:
        lock_status="UNAVAILABLE"
    running_jobs=[job for job in sync_jobs if job.job_state=="RUNNING"]
    running_without_live=[]
    if worker_inspection=="AVAILABLE" and lock_status=="AVAILABLE":
        for job in running_jobs:
            if ((not job.celery_task_id or str(job.celery_task_id) not in live_sync_ids)
                    and job.source_id not in lock_source_ids):running_without_live.append(job.id)
    gates.append(_gate("DB_RUNNING_WITHOUT_LIVE_TASK","SYNC_JOB_RECONCILIATION","FAIL","fast",
                       len(running_without_live) if worker_inspection=="AVAILABLE" and lock_status=="AVAILABLE" else "UNAVAILABLE",0,
                       status=("PASS" if not running_without_live else "FAIL") if worker_inspection=="AVAILABLE" and lock_status=="AVAILABLE" else "WARNING",
                       samples=running_without_live,message="A DB RUNNING job must map to a live Celery task or source lock; broker/Redis inspection failures are warnings."))
    orphan_locks=[]
    if lock_status=="AVAILABLE":
        for source_id in lock_source_ids:
            source=source_map.get(source_id)
            if source and source.source_key in live_source_keys:continue
            if not any(job.source_id==source_id and job.job_state in active_job_states for job in sync_jobs):orphan_locks.append(source_id)
    gates.append(_gate("ORPHANED_SYNC_LOCKS","SYNC_JOB_LOCKING","FAIL","fast",
                       len(orphan_locks) if lock_status=="AVAILABLE" else "UNAVAILABLE",0,
                       status=("PASS" if not orphan_locks else "FAIL") if lock_status=="AVAILABLE" else "WARNING",
                       samples=orphan_locks,message="A source lock without a live source task or queued/running job is orphaned."))

    from .adapters import ADAPTERS
    unscheduled=[source.id for source in sources if source.enabled and source.source_key not in ADAPTERS
                 and not any(token in str(source.source_type or "").casefold() for token in ("manual","static","not_scheduled"))]
    gates.append(_gate("ENABLED_SOURCE_WITH_UNEXPLAINED_NO_SCHEDULE","SYNC_SCHEDULER","FAIL","full",len(unscheduled),0,samples=unscheduled,
                       message="Enabled sources with an implemented adapter are covered by the one-minute due-source dispatcher."))
    pause_rows=db.scalars(select(SystemSetting).where(SystemSetting.key.in_(
        ["pause_all_scheduled_syncs","maintenance_mode"]))).all()
    scheduled_syncs_paused=any(row.value.lower()=="true" for row in pause_rows)
    schedule_window_result=_scheduled_sync_window_evidence(
        sources,sync_jobs,now=_now(),locked_source_ids=lock_source_ids,
        enqueued_source_ids=enqueued_source_ids,redis_available=lock_status=="AVAILABLE",
        globally_paused=scheduled_syncs_paused,
        lock_ttl_seconds=max(1,int(os.getenv("SOURCE_JOB_TIMEOUT_SECONDS","1800")))+600)
    schedule_miss_count=schedule_window_result["missed_execution_count"]
    schedule_gate_status=("FAIL" if schedule_miss_count else
                          "WARNING" if schedule_window_result["unverifiable_overlap_sources"] else "PASS")
    schedule_gate=_gate("UNEXPLAINED_MISSED_SCHEDULE_EXECUTIONS","SYNC_SCHEDULER",
        "FAIL","fast",schedule_miss_count,0,status=schedule_gate_status,
        samples=schedule_window_result["missed_sources"],
        message="A recurring source window is missed only when its interval plus two dispatcher ticks elapsed without a job, active job, Redis lock/reservation, or global pause.")
    schedule_gate["evidence"]=schedule_window_result["evidence"]
    schedule_gate["valid_overlap_suppression_count"]=schedule_window_result["valid_overlap_suppression_count"]
    schedule_gate["valid_overlap_suppressions"]=schedule_window_result["valid_overlap_suppressions"]
    schedule_gate["unverifiable_overlap_sources"]=schedule_window_result["unverifiable_overlap_sources"]
    gates.append(schedule_gate)
    from .source_freshness import POLICIES, evaluate_source_jobs
    freshness_evidence=[]
    for source in sources:
        if not source.enabled or source.source_key not in ADAPTERS:
            continue
        jobs=[job for job in sync_jobs if job.source_id==source.id]
        policy=POLICIES.get(source.source_key)
        content_change=db.scalar(select(func.max(ChangeHistory.detected_at)).where(ChangeHistory.source_id==source.id))
        item=evaluate_source_jobs(source,jobs,now=_now(),last_content_change=content_change)
        item["warning_threshold_minutes"]=policy.warning_after_minutes if policy else None
        item["fail_threshold_minutes"]=policy.fail_after_minutes if policy else None
        item["warning_gate"]=(item["status"] in {"AGING","STALE","UNKNOWN"} and
                              (item["age_minutes"] is None or item["age_minutes"] < (policy.fail_after_minutes if policy else 0)))
        item["failing_gate"]=(item["status"]=="STALE" and item["age_minutes"] is not None and
                              policy is not None and item["age_minutes"]>=policy.fail_after_minutes)
        freshness_evidence.append(item)
    warning_sources=[row for row in freshness_evidence if row["warning_gate"]]
    failing_sources=[row for row in freshness_evidence if row["failing_gate"]]
    freshness_status="FAIL" if failing_sources else "WARNING" if warning_sources else "PASS"
    freshness_gate=_gate("SOURCE_LAST_SUCCESS_TOO_OLD","SOURCE_FRESHNESS","FAIL" if failing_sources else "WARNING","source_specific",len(warning_sources)+len(failing_sources),0,
        status=freshness_status,samples=[row["source_id"] for row in warning_sources+failing_sources],
        message="Source-aware freshness uses complete scan or explicitly successful public-scope verification, with separate warning and critical limits.")
    freshness_gate["evidence"]=[row for row in freshness_evidence if row["status"] not in {"FRESH","LIMITED_SOURCE_OK","STATIC_OK"}]
    freshness_gate["warning_sources"]=[row["source"] for row in warning_sources]
    freshness_gate["failing_sources"]=[row["source"] for row in failing_sources]
    gates.append(freshness_gate)

    runtime_samples=[]
    durations_by_source={}
    for job in sync_jobs:
        if job.status!="SUCCESS" or not job.started_at or not job.finished_at:continue
        duration=(_utc(job.finished_at)-_utc(job.started_at)).total_seconds()
        if duration>=0:durations_by_source.setdefault(job.source_id,[]).append(duration)
    for source_id,values in durations_by_source.items():
        values.sort()
        if len(values)<5:continue
        p95=values[min(len(values)-1,int((len(values)-1)*.95))]
        limit=max(hard_limit,3*p95)
        for job in sync_jobs:
            if job.source_id!=source_id or job.status!="SUCCESS" or not job.finished_at or not job.started_at:continue
            duration=(_utc(job.finished_at)-_utc(job.started_at)).total_seconds()
            if duration>limit:runtime_samples.append({"job_id":job.id,"source_id":source_id,"duration_seconds":round(duration,2),"threshold_seconds":round(limit,2)})
    gates.append(_gate("SYNC_RUNTIME_ANOMALY","SYNC_RUNTIME","WARNING","full",len(runtime_samples),0,
                       status="WARNING" if runtime_samples else "PASS",samples=[r["job_id"] for r in runtime_samples],
                       message="Completed source runtimes above three times the historical p95 or the hard task limit are surfaced for inspection."))
    absence = _source_absence_classification(db, records, source_map)
    absence_counts = {key: len(ids) for key, ids in absence["categories"].items()}
    pending_absence = absence["categories"]["true_absence_pending_confirmation"]
    unexplained_absence = absence["categories"]["unexplained"]
    absence_status="FAIL" if unexplained_absence else "WARNING" if pending_absence else "PASS"
    gates.append(_gate("SOURCE_ABSENCE_CLASSIFICATION", "SOURCE_COVERAGE", "FAIL" if unexplained_absence else "WARNING", "full",
                       {"warning_population": absence["legacy_population"], "classification": absence_counts,
                        "classification_sum": absence["classification_sum"], "true_pending_confirmation":len(pending_absence),
                        "unexplained":len(unexplained_absence)},
                       {"unexplained":0},status=absence_status,
                       samples=unexplained_absence or pending_absence,
                       message="Only qualified Ahsa-scope records missing from a comparable, complete successful enumeration remain pending; national non-qualified rows and unlinked records are excluded."))
    if scope == "weekly" and furas:
        metrics = latest_furas.metrics_json if latest_furas and isinstance(latest_furas.metrics_json, dict) else {}
        requested = int((metrics.get("pages_requested") if metrics.get("pages_requested") is not None else (latest_furas.pages_requested if latest_furas else 0)) or 0)
        successful = int((metrics.get("pages_successful") if metrics.get("pages_successful") is not None else (latest_furas.pages_successful if latest_furas else 0)) or 0)
        duplicate_page_items = int(metrics.get("duplicate_items_between_pages") or 0)
        official_total = metrics.get("source_total_reported", latest_furas.source_total_reported if latest_furas else None)
        enumerated = metrics.get("unique_records", latest_furas.unique_records if latest_furas else None)
        count_mismatch = int(official_total is not None and enumerated is not None and int(official_total) != int(enumerated))
        gates.extend([
            _gate("FURAS_PAGE_COMPLETION_METRICS", "SOURCE_PAGINATION", "FAIL", "weekly",
                  {"requested":requested,"successful":successful,"pagination_complete":bool(latest_furas and latest_furas.pagination_complete)},
                  {"requested_equals_successful":True,"pagination_complete":True},
                  status="PASS" if latest_furas and latest_furas.pagination_complete is True and requested == successful and requested > 0 else "FAIL",
                  samples=[latest_furas.id] if latest_furas else [],
                  message="Uses the last successful completed enumeration, not the latest failed attempt."),
            _gate("FURAS_REPORTED_VS_ENUMERATED_TOTAL", "SOURCE_COVERAGE", "WARNING", "weekly",
                  count_mismatch, 0,status="PASS" if count_mismatch == 0 else "WARNING",
                  samples=[latest_furas.id] if latest_furas and count_mismatch else [],
                  message="Only comparable authoritative public counts are compared."),
            _gate("FURAS_REPEATED_PAGE_SIGNAL", "SOURCE_PAGINATION", "WARNING", "weekly",
                  duplicate_page_items, 0,status="PASS" if duplicate_page_items == 0 else "WARNING",
                  samples=[latest_furas.id] if latest_furas and duplicate_page_items else [],
                  message="Adapter duplicate-page telemetry is surfaced; it does not auto-delete records."),
        ])

    # Observation integrity.
    orphan_observations = db.scalar(select(func.count(SourceObservation.id)).outerjoin(
        SourceOpportunity, SourceOpportunity.id == SourceObservation.source_opportunity_id).where(SourceOpportunity.id.is_(None))) or 0
    bad_observation_order = []
    for observation in db.scalars(select(SourceObservation)):
        if observation.first_seen_at and observation.last_seen_at and observation.first_seen_at > observation.last_seen_at:
            bad_observation_order.append(observation.id)
    gates.extend([
        _gate("ORPHANED_SOURCE_OBSERVATION", "OBSERVATION_INTEGRITY", "FAIL", "full", int(orphan_observations), 0),
        _gate("OBSERVATION_TIMESTAMP_ORDER", "OBSERVATION_INTEGRITY", "FAIL", "full", len(bad_observation_order), 0, samples=bad_observation_order),
    ])

    # Standardization and migration parity use the runtime process and DB schema version.
    db_versions = sorted({str(v) for v in db.scalars(select(SourceOpportunity.standardization_version).distinct()).all() if v})
    # Historical rows may legitimately carry older versions; only runtime module parity is a blocking invariant.
    gates.extend([
        _gate("RUNTIME_STANDARDIZATION_VERSION", "STANDARDIZATION_RUNTIME_PARITY", "FAIL", "fast",
              STANDARDIZATION_VERSION, STANDARDIZATION_VERSION),
        _gate("HISTORICAL_STANDARDIZATION_VERSIONS", "STANDARDIZATION_RUNTIME_PARITY", "INFO", "full",
              db_versions, {"runtime_current": STANDARDIZATION_VERSION}, status="PASS",
              message="Persisted historical source projections are not rewritten during read-only validation."),
    ])
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        expected_heads = sorted(ScriptDirectory.from_config(config).get_heads())
        heads = sorted(str(x) for x in db.execute(__import__("sqlalchemy").text("select version_num from alembic_version")).scalars().all())
    except Exception:
        heads, expected_heads = [], []
    gates.append(_gate("ALEMBIC_RUNTIME_PARITY", "DATABASE_MIGRATIONS", "FAIL", "full", heads, expected_heads,
                       status="PASS" if heads and heads == expected_heads else "FAIL", samples=heads,
                       message="Database Alembic head is compared with the migration scripts shipped in this runtime."))

    # Quantitative and owner semantics are modeled as nullable scalars; count zero-valued unknowns conservatively.
    zero_area = [o.id for o in masters if o.land_area_sqm == 0]
    zero_value = [o.id for o in masters if o.investment_value == 0]
    tech_refs = [o.id for o in masters if o.reference_number and any(p.search(str(o.reference_number)) for p in _TECHNICAL_REF_PATTERNS)]
    gates.extend([
        _gate("UNKNOWN_AREA_STORED_AS_ZERO", "QUANTITATIVE_FIELDS", "WARNING", "full", len(zero_area), 0, samples=zero_area,
              message="Zero can be valid; review required before interpreting as missing-value coercion."),
        _gate("UNKNOWN_VALUE_STORED_AS_ZERO", "QUANTITATIVE_FIELDS", "WARNING", "full", len(zero_value), 0, samples=zero_value,
              message="Zero can be valid; review required before interpreting as missing-value coercion."),
        _gate("TECHNICAL_SOURCE_ID_AS_MASTER_REFERENCE", "QUANTITATIVE_FIELDS", "FAIL", "fast", len(tech_refs), 0, samples=tech_refs),
        _gate("TAXONOMY_DIMENSION_CARDINALITY", "TAXONOMY", "INFO", "full",
              {"activity": "single", "sub_activity": "single", "opportunity_type": "single", "investment_model": "single", "asset_type": "multi"},
              {"activity": "single", "sub_activity": "single", "opportunity_type": "single", "investment_model": "single", "asset_type": "multi"}),
        _gate("OTHER_IS_NOT_UNSPECIFIED", "TAXONOMY", "FAIL", "fast",
              {"activity": canonical_value("activity","أخرى") != canonical_value("activity","غير محدد"),
               "sector": canonical_value("sector","أخرى") != canonical_value("sector","غير محدد")},
              {"activity": True, "sector": True},
              status="PASS" if (canonical_value("activity","أخرى") != canonical_value("activity","غير محدد")
                                  and canonical_value("sector","أخرى") != canonical_value("sector","غير محدد")) else "FAIL"),
        _gate("OWNER_PLATFORM_SEPARATION", "OWNER", "INFO", "full", True, True,
              message="Owner, primary publication platform, and source publisher are separately stored model fields."),
    ])

    # Focused guards for the accepted sector-inference and lifecycle changes.
    legacy_published_keys = {comparison_key(value) for value in
                             ("منشورة", "Published", "PUBLISHED", "Announced", "ANNOUNCED")}
    legacy_published = [row.id for row in masters if comparison_key(row.status) in legacy_published_keys]
    dashboard_published_bucket = sum(1 for row in masters if canonical_value("status", row.status) == "منشورة")
    canonical_sector_ids = {canonical_id("sector", "السياحة"), canonical_id("sector", "الزراعة")}
    source_by_master: dict[int, list[SourceOpportunity]] = {}
    for source_record in records:
        if source_record.master_opportunity_id in current_ids:
            source_by_master.setdefault(source_record.master_opportunity_id, []).append(source_record)
    current_by_id = {row.id: row for row in masters}
    try:
        from .adapters import normalize_sector
        from .sector_inference import GENERIC_OR_WRONG_DIMENSION
        inference_events = db.scalars(select(SystemEvent).where(
            SystemEvent.event_type == "SECTOR_INFERENCE_STATUS_CONSOLIDATION_APPLIED").order_by(SystemEvent.id)).all()
        provenance_rows = [item for event in inference_events
                           for item in ((event.payload or {}).get("classifications") or [])]
        provenance_rows = [item for item in provenance_rows
                           if item.get("master_id") in current_by_id
                           and current_by_id[item["master_id"]].sector == item.get("sector")]
        overridden = []
        for item in provenance_rows:
            if item.get("classification_origin") != "INFERRED_RULE":
                continue
            for source_record in source_by_master.get(item.get("master_id"), []):
                raw_sector = source_record.source_sector
                mapped = (normalize_sector(raw_sector) if raw_sector and comparison_key(raw_sector) not in GENERIC_OR_WRONG_DIMENSION else None)
                if mapped and canonical_id("sector", mapped) != canonical_id("sector", item.get("sector")):
                    overridden.append({"master_id": item.get("master_id"), "source_record_id": source_record.id,
                                       "source_sector": source_record.source_sector, "inferred_sector": item.get("sector")})
        forced_low_confidence = [item for item in provenance_rows
                                 if item.get("classification_origin") == "INFERRED_RULE"
                                 and float(item.get("confidence") or 0) < .90]
        missing_trace = [item for item in provenance_rows
                         if item.get("classification_origin") == "INFERRED_RULE"
                         and (not item.get("rule_key") or not item.get("evidence_fields")
                              or not item.get("engine_version") or not item.get("inference_timestamp"))]
    except Exception:
        overridden, forced_low_confidence, missing_trace = ["PROVENANCE_READ_ERROR"], ["PROVENANCE_READ_ERROR"], ["PROVENANCE_READ_ERROR"]
    try:
        from .adapters import normalize_sector
        from .sector_inference import GENERIC_OR_WRONG_DIMENSION
        phase2_events=db.scalars(select(SystemEvent).where(
            SystemEvent.event_type.in_(("SECTOR_INFERENCE_PHASE2_APPLIED", "SECTOR_CONTROLLED_RELAXATION_APPLIED"))
        ).order_by(SystemEvent.id)).all()
        phase2_rows=[item for event in phase2_events for item in ((event.payload or {}).get("classifications") or [])
                     if item.get("master_id") in current_by_id
                     and item.get("classification_origin") in {"INFERRED_RULE", "INFERRED_RULE_MEDIUM"}]
        phase2_rows=[item for item in phase2_rows if current_by_id[item["master_id"]].sector==item.get("sector")]
        phase2_low=[item for item in phase2_rows if
                    (item.get("classification_origin")=="INFERRED_RULE" and float(item.get("confidence") or 0)<.90)
                    or (item.get("classification_origin")=="INFERRED_RULE_MEDIUM" and float(item.get("confidence") or 0)<.82)]
        phase2_missing=[item for item in phase2_rows if not item.get("rule_key") or not item.get("positive_evidence")
                        or not item.get("evidence_fields") or not item.get("engine_version")
                        or not item.get("inference_timestamp")]
        medium_inference_audit = _audit_medium_inference_provenance(phase2_rows)
        phase2_medium_conflicts = medium_inference_audit["contradictions"]
        phase2_medium_incomplete = medium_inference_audit["incomplete_provenance"]
        phase2_overridden=[]
        for item in phase2_rows:
            for source_record in source_by_master.get(item.get("master_id"),[]):
                raw_sector=source_record.source_sector
                mapped=(normalize_sector(raw_sector) if raw_sector and comparison_key(raw_sector) not in GENERIC_OR_WRONG_DIMENSION else None)
                if mapped and canonical_id("sector",mapped) not in {"sector:unspecified",canonical_id("sector",item.get("sector"))}:
                    phase2_overridden.append({"master_id":item["master_id"],"source_record_id":source_record.id,
                        "source_sector":source_record.source_sector,"inferred_sector":item.get("sector")})
        phase2_other=[item for item in phase2_rows if canonical_id("sector",item.get("sector"))=="sector:other"
                      and not item.get("positive_evidence")]
    except Exception:
        phase2_rows=[]
        phase2_low=phase2_missing=phase2_medium_conflicts=phase2_medium_incomplete=phase2_overridden=phase2_other=["PHASE2_PROVENANCE_READ_ERROR"]
    governed_events=db.scalars(select(SystemEvent).where(SystemEvent.event_type.in_(
        ("SECTOR_GOVERNED_CLASSIFICATION_APPLIED","SECTOR_GOVERNED_RECLASSIFIED"))
    ).order_by(SystemEvent.id)).all()
    governed_rows=[item for event in governed_events
                   for item in ((event.payload or {}).get("classifications") or [])
                   if item.get("master_id") in current_by_id
                   and current_by_id[item["master_id"]].sector==item.get("sector")]
    governed_forced=[item for item in governed_rows if item.get("classification_method")=="FORCED_BEST_FIT"
                     or item.get("classification_origin")=="INFERRED_RULE_FORCED_BEST_FIT"]
    governed_missing_evidence=[item for item in governed_rows if not item.get("positive_evidence")
                               or not item.get("evidence_fields") or not item.get("rule_key")
                               or not item.get("engine_version") or not item.get("inference_timestamp")]
    governed_forced_missing_reason=[item for item in governed_forced
                                    if not str(item.get("reason") or "").strip()
                                    or item.get("confidence_label") not in (None,"LOW")]
    governed_other_missing=[item for item in governed_forced
                            if canonical_id("sector",item.get("sector"))=="sector:other"
                            and (not item.get("positive_evidence")
                                 or all(float(ev.get("weight") or 0)<=0 for ev in item.get("positive_evidence") or [])
                                 or all(str(ev.get("rule_key") or "").startswith("FORCED_BEST_FIT")
                                        for ev in item.get("positive_evidence") or []))]
    governed_without_audit=[]
    histories=db.scalars(select(ChangeHistory).where(ChangeHistory.changed_field=="sector")).all()
    for item in governed_rows:
        if not item.get("sector_changed"):
            continue
        matched=any(h.opportunity_id==item.get("master_id")
                    and h.previous_value==item.get("previous_sector")
                    and h.new_value==item.get("sector") for h in histories)
        if not matched:
            governed_without_audit.append(item.get("master_id"))
    unspecified_current=[row.id for row in masters if canonical_id("sector",row.sector)=="sector:unspecified"]
    pipeline_event=db.scalar(select(SystemEvent).where(
        SystemEvent.event_type=="SECTOR_CLASSIFICATION_PIPELINE_COMPLETED"
    ).order_by(SystemEvent.id.desc()).limit(1))
    pipeline_version=(pipeline_event.payload or {}).get("engine_version") if pipeline_event else None
    pipeline_time=pipeline_event.created_at if pipeline_event else None
    new_since_pipeline=[row.id for row in masters if pipeline_time and row.created_at and row.created_at>pipeline_time]
    new_without_classification=[ident for ident in new_since_pipeline
                                if ident not in current_by_id
                                or canonical_id("sector",current_by_id[ident].sector)=="sector:unspecified"
                                or not any(item.get("master_id")==ident for item in governed_rows)]
    gates.extend([
        _gate("CURRENT_MASTER_WITH_UNSPECIFIED_SECTOR","TAXONOMY","FAIL","fast",len(unspecified_current),0,samples=unspecified_current[:40]),
        _gate("NEW_MASTER_WITH_UNSPECIFIED_SECTOR","TAXONOMY","FAIL","fast",len(new_without_classification),0,samples=new_without_classification),
        _gate("SECTOR_CLASSIFICATION_WITHOUT_EVIDENCE","TAXONOMY","FAIL","fast",len(governed_missing_evidence),0,
              samples=[item.get("master_id") for item in governed_missing_evidence[:40]]),
        _gate("FORCED_CLASSIFICATION_WITHOUT_REASON","TAXONOMY","FAIL","fast",len(governed_forced_missing_reason),0,
              samples=[item.get("master_id") for item in governed_forced_missing_reason[:40]]),
        _gate("OTHER_USED_AS_MISSING_FALLBACK","TAXONOMY","FAIL","fast",len(governed_other_missing),0,
              samples=[item.get("master_id") for item in governed_other_missing[:40]]),
        _gate("SECTOR_MUTATION_WITHOUT_AUDIT","TAXONOMY","FAIL","fast",len(governed_without_audit),0,
              samples=governed_without_audit[:40]),
        _gate("SECTOR_PIPELINE_NOT_EXECUTED","TAXONOMY","FAIL","fast",
              {"version":pipeline_version,"new_masters_without_classification":len(new_without_classification)},
              {"version":"ahda-governed-sector-classifier-1.0.0","new_masters_without_classification":0},
              status="PASS" if pipeline_version=="ahda-governed-sector-classifier-1.0.0" and not new_without_classification else "FAIL"),
    ])
    gates.extend([
        _gate("CANONICAL_CURRENT_PUBLISHED_RECORDS", "STATUS_LIFECYCLE", "FAIL", "fast",
              len(legacy_published), 0, samples=legacy_published),
        _gate("USER_FACING_PUBLISHED_STATUS_BUCKET", "STATUS_LIFECYCLE", "FAIL", "fast",
              dashboard_published_bucket, 0),
        _gate("TOURISM_AND_AGRICULTURE_CANONICAL_SECTORS", "TAXONOMY", "FAIL", "fast",
              sorted(canonical_sector_ids), ["sector:agriculture", "sector:tourism"],
              status="PASS" if canonical_sector_ids == {"sector:agriculture", "sector:tourism"} else "FAIL"),
        _gate("SOURCE_EXPLICIT_SECTOR_OVERRIDDEN_BY_INFERENCE", "TAXONOMY", "FAIL", "fast",
              len(overridden), 0, samples=overridden),
        _gate("FORCED_LOW_CONFIDENCE_SECTOR_CLASSIFICATIONS", "TAXONOMY", "FAIL", "fast",
              len(forced_low_confidence), 0, samples=forced_low_confidence),
        _gate("INFERRED_SECTOR_WITHOUT_TRACEABLE_EVIDENCE", "TAXONOMY", "FAIL", "fast",
              len(missing_trace), 0, samples=missing_trace),
        _gate("P2_INFERRED_SECTOR_WITHOUT_EVIDENCE", "TAXONOMY", "FAIL", "fast",
              len(phase2_missing), 0, samples=phase2_missing),
        _gate("P2_INFERRED_SECTOR_LOW_CONFIDENCE", "TAXONOMY", "FAIL", "fast",
              len(phase2_low), 0, samples=phase2_low),
        _gate("P2_OFFICIAL_SECTOR_OVERRIDDEN_BY_INFERENCE", "TAXONOMY", "FAIL", "fast",
              len(phase2_overridden), 0, samples=phase2_overridden),
        _gate("P2_OTHER_USED_AS_MISSING_SECTOR", "TAXONOMY", "FAIL", "fast",
              len(phase2_other), 0, samples=phase2_other),
        _gate("P2_MEDIUM_INFERENCE_WITH_STRONG_CONTRADICTION", "TAXONOMY", "FAIL", "fast",
              len(phase2_medium_conflicts), 0, samples=phase2_medium_conflicts),
        _gate("MEDIUM_INFERENCE_PROVENANCE_INTEGRITY", "TAXONOMY", "WARNING", "fast",
              len(phase2_medium_incomplete), 0, samples=phase2_medium_incomplete,
              message="Core inference provenance is required; scores and margin are required only when a distinct competing sector is recorded."),
    ])

    if scope != "fast":
        try:
            # Invoke the real read-only route functions against the configured database.
            # This checks the same current-Master universe visible to list/dashboard/exports.
            from . import main as api
            api_total = int(api.opportunities(limit=1, offset=0)["total"])
            dashboard_total = int(api.dashboard()["total"])
            data_dashboard_total = int(api.data_dashboard()["kpis"]["total"])
            sector_dashboard=api.data_dashboard()
            sector_chart_total=sum(int(item.get("count",0)) for item in sector_dashboard.get("by_sector",[]))
            sector_db_total=sum(int(row[1]) for row in db.execute(select(Opportunity.sector,func.count(Opportunity.id))
                .where(Opportunity.merged_into_id.is_(None)).group_by(Opportunity.sector)).all())
            sector_unspecified=sum(1 for row in masters if canonical_id("sector",row.sector)=="sector:unspecified")
            sector_dashboard_mismatch=(sector_chart_total!=current_count or sector_db_total!=current_count or sector_unspecified>0)
            csv_response = api.export_csv()
            async def _read_response(response):
                parts=[]
                async for part in response.body_iterator:
                    parts.append(part if isinstance(part, bytes) else str(part).encode())
                return b"".join(parts)
            csv_body = asyncio.run(_read_response(csv_response))
            csv_count = max(0, sum(1 for _ in csv.reader(io.StringIO(csv_body.decode("utf-8-sig")))) - 1)
            xlsx_response = api.export_xlsx()
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(xlsx_response.body), read_only=True, data_only=True)
            xlsx_sheet = workbook["الفرص الاستثمارية"]
            xlsx_count = max(0, xlsx_sheet.max_row - 6)
            workbook.close()
            counts = {"api_list":api_total,"dashboard":dashboard_total,"data_dashboard":data_dashboard_total,
                      "csv":csv_count,"xlsx":xlsx_count,"database_current_masters":current_count}
            mismatch = len(set(counts.values())) != 1
            gates.append(_gate("API_DASHBOARD_EXPORT_RECONCILIATION", "API_DASHBOARD_EXPORT_RECONCILIATION", "FAIL", "full",
                               counts, {"all_equal":current_count}, status="FAIL" if mismatch else "PASS",
                               message="Counts are read from the running route implementations, CSV rows, and XLSX opportunity sheet."))
            gates.append(_gate("SECTOR_DASHBOARD_COUNT_MISMATCH","TAXONOMY","FAIL","full",
                {"db":sector_db_total,"data_dashboard_chart":sector_chart_total,"current_masters":current_count,
                 "unspecified":sector_unspecified},
                {"db":current_count,"data_dashboard_chart":current_count,"current_masters":current_count,"unspecified":0},
                status="FAIL" if sector_dashboard_mismatch else "PASS"))
            pages = [api.opportunities(limit=100, offset=offset)["items"] for offset in range(0, api_total, 100)]
            page_ids = [item["id"] for page in pages for item in page]
            duplicate_page_ids = sorted({ident for ident in page_ids if page_ids.count(ident) > 1})
            gates.append(_gate("CURRENT_LIST_DUPLICATE_MASTER_ROWS", "SEARCH_LIST_UNIQUENESS", "FAIL", "full",
                               len(duplicate_page_ids), 0, samples=duplicate_page_ids))
            geo = api.data_dashboard_geography()
            geo_counts = geo["counts"]
            map_partition = {"current_masters":geo_counts["total"],"inside_exact":geo_counts["exact_mapped"],
                "outside_boundary":geo_counts["outside_boundary"],"unverified_coordinates":geo_counts["unverified_coordinates"],
                "missing_coordinates":geo_counts["missing_coordinates"]}
            partition_sum=sum(map_partition[key] for key in ("inside_exact","outside_boundary","unverified_coordinates","missing_coordinates"))
            gates.append(_gate("CURRENT_MASTER_MAP_PARTITION", "LOCATION_ELIGIBILITY", "FAIL", "full", partition_sum,
                               map_partition["current_masters"],status="PASS" if partition_sum==map_partition["current_masters"] else "FAIL",
                               message="Exact-mapped, outside-reference, unverified, and missing-coordinate groups partition the current Master universe."))
            duplicate_master_reference_rows = db.execute(select(Opportunity.id, Opportunity.reference_number).where(
                current_id_query, Opportunity.reference_number.is_not(None), Opportunity.reference_number!="")).all()
            ref_counts={}
            for master_id, reference in duplicate_master_reference_rows:
                key=str(reference).strip().casefold()
                ref_counts.setdefault(key,[]).append(master_id)
            duplicate_refs=[ids for ids in ref_counts.values() if len(ids)>1]
            gates.append(_gate("CURRENT_MASTER_LIST_REFERENCE_DUPLICATES", "SEARCH_LIST_UNIQUENESS", "WARNING", "full",
                               len(duplicate_refs), 0,samples=duplicate_refs,
                               message="Repeated references are surfaced for inspection; only verified official-reference splits fail."))
        except Exception as exc:
            gates.append(_gate("API_DASHBOARD_EXPORT_RECONCILIATION", "API_DASHBOARD_EXPORT_RECONCILIATION", "FAIL", "full",
                               type(exc).__name__, "all_equal", status="FAIL",
                               message=f"Could not complete real route/export reconciliation: {exc}"))

    worker_versions = []
    worker_status = "UNAVAILABLE"
    try:
        import redis
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1, decode_responses=True)
            keys = list(client.scan_iter(match="worker:heartbeat:*", count=20))
            for key in keys:
                value = client.get(key)
                try:
                    parsed = json.loads(value)
                    if parsed.get("standardization_version") is not None:
                        worker_versions.append(str(parsed["standardization_version"]))
                except (TypeError, ValueError):
                    pass
            worker_status = "AVAILABLE" if keys else "UNAVAILABLE"
    except Exception:
        worker_status = "UNAVAILABLE"
    runtime_parity = (worker_status == "AVAILABLE" and bool(worker_versions)
                      and all(v == STANDARDIZATION_VERSION for v in worker_versions))
    gates.append(_gate("API_WORKER_STANDARDIZATION_PARITY", "STANDARDIZATION_RUNTIME_PARITY", "FAIL", "fast",
                       {"api":STANDARDIZATION_VERSION,"worker_versions":sorted(set(worker_versions)),"worker_status":worker_status},
                       {"version":STANDARDIZATION_VERSION,"worker":"available"},
                       status="PASS" if runtime_parity else "FAIL",
                       message="Worker heartbeat must publish its loaded standardization version."))

    allowed_coverage = {"COMPLETE_PUBLIC_SOURCE","COMPLETE_FOR_DEFINED_SCOPE","PUBLIC_COVERAGE_LIMITED",
                        "PRIVATE_API_REQUIRED","AUTHENTICATED_SOURCE_REQUIRED","PARTIAL_OFFICIAL_COVERAGE"}
    unknown_coverage = [s.id for s in sources if s.enabled and s.coverage_status not in allowed_coverage]
    gates.append(_gate("ENABLED_SOURCE_COVERAGE_DECLARED", "SOURCE_COVERAGE", "WARNING", "full",
                       len(unknown_coverage), 0, samples=unknown_coverage,
                       message="Limited and scoped coverage are valid; only missing/unrecognized coverage declarations are flagged."))

    # WAHA remains a catalogue-only source while its official public pages do not
    # expose itemized offers. These focused guards become active automatically if
    # source records are added later; they do not treat the legacy parcel map as offers.
    waha_source_ids = {source.id for source in sources if source.source_key == "waha-development"}
    waha_rows = [row for row in records if row.source_id in waha_source_ids]
    explicit_opportunity_types = {"INVESTMENT_OPPORTUNITY", "LEASE_OPPORTUNITY",
                                  "COMMERCIAL_FACILITY_OPPORTUNITY", "PPP_PROJECT"}
    generic_waha = [row.id for row in waha_rows
                    if not isinstance(row.raw_data_json, dict)
                    or row.raw_data_json.get("record_semantic_type") not in explicit_opportunity_types]
    waha_observed_ids = set(db.scalars(select(SourceObservation.source_opportunity_id)
                                       .where(SourceObservation.source_opportunity_id.in_([row.id for row in waha_rows]))).all()) if waha_rows else set()
    missing_waha_provenance = [row.id for row in waha_rows
                               if not row.source_url or not row.source_opportunity_id
                               or not row.official_source_id_original or not row.raw_data_json
                               or not row.content_hash or row.id not in waha_observed_ids]
    unreconciled_waha = [row.id for row in waha_rows
                         if not row.master_opportunity_id or row.master_opportunity_id not in current_ids]
    furas_refs: dict[str, set[int]] = {}
    for row in records:
        source = source_map.get(row.source_id)
        if source and source.source_key == "furas" and row.master_opportunity_id:
            ref = row.official_source_id_normalized or row.source_reference_number_normalized
            if ref:
                furas_refs.setdefault(str(ref).strip().casefold(), set()).add(row.master_opportunity_id)
    duplicate_waha_furas: list[str] = []
    owner_publisher_conflicts: list[int] = []
    for row in waha_rows:
        ref = row.official_source_id_normalized or row.source_reference_number_normalized
        if ref and row.master_opportunity_id:
            other_masters = furas_refs.get(str(ref).strip().casefold(), set())
            if any(master_id != row.master_opportunity_id for master_id in other_masters):
                duplicate_waha_furas.append(str(ref))
        raw = row.raw_data_json if isinstance(row.raw_data_json, dict) else {}
        owner = raw.get("opportunity_owner") or raw.get("owner")
        publisher = raw.get("publishing_entity") or raw.get("publisher")
        master = db.get(Opportunity, row.master_opportunity_id) if row.master_opportunity_id else None
        if owner and publisher and comparison_key(str(owner)) != comparison_key(str(publisher)) \
                and master and master.opportunity_owner \
                and comparison_key(str(master.opportunity_owner)) == comparison_key(str(publisher)):
            owner_publisher_conflicts.append(row.id)
    gates.extend([
        _gate("WAHA_GENERIC_CONTENT_INGESTED", "WAHA_SOURCE_QUALITY", "FAIL", "full",
              len(generic_waha), 0, samples=generic_waha,
              message="Only explicitly qualified itemized Waha opportunities may become source records; generic themes and parcel-map features are excluded."),
        _gate("WAHA_FURAS_DUPLICATE_MASTER", "WAHA_SOURCE_IDENTITY", "FAIL", "full",
              len(duplicate_waha_furas), 0, samples=duplicate_waha_furas,
              message="A shared authoritative Waha/Furas reference must resolve to one current Master."),
        _gate("WAHA_MISSING_PROVENANCE", "WAHA_SOURCE_PROVENANCE", "FAIL", "full",
              len(missing_waha_provenance), 0, samples=missing_waha_provenance,
              message="Waha source records require an official ID, source URL, raw payload, content hash, and immutable observation."),
        _gate("WAHA_OWNER_PUBLISHER_CONFUSION", "WAHA_OWNER_PUBLISHER", "FAIL", "full",
              len(owner_publisher_conflicts), 0, samples=owner_publisher_conflicts,
              message="An explicit publisher must not replace a distinct opportunity owner."),
        _gate("WAHA_UNRECONCILED_SOURCE_RECORD", "WAHA_SOURCE_IDENTITY", "FAIL", "full",
              len(unreconciled_waha), 0, samples=unreconciled_waha,
              message="Qualified Waha source records must link to a current canonical Master after conservative identity matching."),
    ])

    # Snapshot values are descriptive, never hardcoded expected counts.
    linked_current_count = len(set(r.master_opportunity_id for r in records if r.master_opportunity_id in current_ids))
    snapshot = {"total_master_rows": _count(db, Opportunity), "current_masters": current_count,
                "merged_masters": _count(db, Opportunity, Opportunity.merged_into_id.is_not(None)),
                "source_opportunities": len(records), "source_opportunities_linked_to_current_masters": linked_current_count,
                "observations": _count(db, SourceObservation), "configured_sources": len(sources),
                "enabled_sources": sum(1 for s in sources if s.enabled), "open_reviews": all_reviews,
                "standardization_engine_version": STANDARDIZATION_VERSION, "alembic_heads": heads,
                "expected_alembic_heads": expected_heads}
    if scope == "fast":
        selected_gates = [g for g in gates if g["cadence"] == "fast"]
    elif scope == "weekly":
        selected_gates = gates
    else:
        selected_gates = [g for g in gates if g["cadence"] != "weekly"]
    counts = {status.lower(): sum(g["status"] == status for g in selected_gates) for status in ("PASS", "WARNING", "FAIL")}
    completed = _now()
    result = {"run_id": uuid.uuid4().hex, "started_at": started.isoformat(), "completed_at": completed.isoformat(),
              "trigger": trigger, "scope": scope, "source_id": source_id, "job_id": job_id,
              "read_only_business_data": True, "snapshot": snapshot, "counts": counts,
              "source_absence_classification": {"warning_population": absence["legacy_population"],
                  "classification": absence_counts, "classification_sum": absence["classification_sum"],
                  "reconciliation": "PASSED" if absence["classification_sum"] == absence["legacy_population"] else "FAILED"},
              "source_link_semantics": {"generic_page_records": len(generic_page_records),
                  "generic_page_exposed_as_original_opportunity_action": len(generic_action_urls)},
              "gates_evaluated": len(selected_gates), "gates": selected_gates,
              "failed_gates": [g for g in selected_gates if g["status"] == "FAIL"],
              "warning_gates": [g for g in selected_gates if g["status"] == "WARNING"]}
    if persist:
        retention_days=max(30,int(os.getenv("DQ_RUN_RETENTION_DAYS","365")))
        retention_max=max(500,int(os.getenv("DQ_RUN_RETENTION_MAX_RUNS","5000")))
        cutoff=completed-timedelta(days=retention_days)
        removed_old=db.execute(delete(SystemEvent).where(SystemEvent.event_type==DQ_EVENT,SystemEvent.created_at<cutoff)).rowcount or 0
        excess_ids=db.scalars(select(SystemEvent.id).where(SystemEvent.event_type==DQ_EVENT)
                              .order_by(SystemEvent.id.desc()).offset(retention_max)).all()
        removed_excess=db.execute(delete(SystemEvent).where(SystemEvent.event_type==DQ_EVENT,SystemEvent.id.in_(excess_ids))).rowcount if excess_ids else 0
        result["retention"]={"days":retention_days,"max_runs":retention_max,
                             "expired_runs_removed":int(removed_old),"excess_runs_removed":int(removed_excess or 0),
                             "scope":"DATA_QUALITY_RUN_COMPLETED events only"}
        db.add(SystemEvent(event_type=DQ_EVENT, created_at=completed,
                           payload={"run": result}))
        db.flush()
        result["system_event_id"] = db.scalar(select(func.max(SystemEvent.id)).where(SystemEvent.event_type == DQ_EVENT))
    return result


def latest_data_quality_run(db: Session) -> dict | None:
    event = db.scalar(select(SystemEvent).where(SystemEvent.event_type == DQ_EVENT).order_by(SystemEvent.id.desc()).limit(1))
    if not event:
        return None
    payload = event.payload if isinstance(event.payload, dict) else {}
    result = payload.get("run") if isinstance(payload.get("run"), dict) else None
    if result:
        result = dict(result)
        result["system_event_id"] = event.id
    return result


def data_quality_history(db: Session, limit: int = 30) -> list[dict]:
    rows = db.scalars(select(SystemEvent).where(SystemEvent.event_type == DQ_EVENT).order_by(SystemEvent.id.desc()).limit(max(1, min(limit, 100)))).all()
    return [{"system_event_id": row.id, **((row.payload or {}).get("run") or {})} for row in rows]

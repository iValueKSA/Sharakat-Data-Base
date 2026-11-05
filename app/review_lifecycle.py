"""Targeted, evidence-backed re-evaluation for open review conflicts.

This module deliberately recognizes a small set of stale conditions whose
current source projection proves that the original conflict no longer exists.
It never changes canonical business fields and never resolves an ambiguous
value conflict.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Opportunity, OpportunityConflict, Source, SourceOpportunity
from .security import audit
from .status_lifecycle import AVAILABLE, PUBLISHED, aggregate_master_status


_GENERIC_OPPORTUNITY_TYPES = {"investment", "استثمار", "فرصة استثمارية", "غير محدد"}


def stale_conflict_evidence(db: Session, conflict: OpportunityConflict) -> dict | None:
    """Return current, field-specific evidence only when an open issue is stale."""
    if conflict.status != "OPEN":
        return None
    record = db.get(SourceOpportunity, conflict.source_record_id)
    master = db.get(Opportunity, conflict.opportunity_id)
    source = db.get(Source, conflict.source_id)
    if not record or not master or not source or master.merged_into_id is not None:
        return None
    if record.master_opportunity_id != master.id:
        return None

    fields = (record.standardized_data_json or {}).get("fields") or {}
    projected = fields.get(conflict.field_name) or {}
    mapping_status = projected.get("mapping_status")
    current = getattr(master, conflict.field_name, None) if hasattr(master, conflict.field_name) else None
    source_evidence = {
        "source_key": source.source_key,
        "source_record_id": record.id,
        "current_source_field": projected,
        "current_raw_owner": record.source_owner,
        "current_raw_location": record.raw_location,
        "current_source_sector": record.source_sector,
        "current_canonical_value": current,
        "original_selected_value": conflict.selected_value,
        "original_conflicting_value": conflict.conflicting_value,
    }

    # Invest Saudi records can disappear from that source while a currently
    # linked Furas record still publishes the same Master opportunity.  In
    # that case the source-level removal is preserved, while the canonical
    # Master status is independently supported by the remaining live record.
    if (conflict.field_name == "status"
            and conflict.conflict_type == "FIELD_VALUE_CONFLICT"
            and source.source_key == "invest-saudi"
            and record.canonical_status == "أزيلت من المصدر"
            and record.missing_successful_checks >= max(1, source.missing_confirmation_threshold or 1)
            and str(conflict.selected_value).strip() == str(master.status).strip()
            and master.status in {AVAILABLE, PUBLISHED}):
        linked = db.scalars(select(SourceOpportunity).where(
            SourceOpportunity.master_opportunity_id == master.id).order_by(SourceOpportunity.id)).all()
        live_records = [row for row in linked if row.id != record.id
                        and row.canonical_status in {AVAILABLE, PUBLISHED}
                        and row.missing_successful_checks == 0
                        and row.last_seen_at is not None
                        and record.last_seen_at is not None
                        and row.last_seen_at > record.last_seen_at]
        projection, projection_flags = aggregate_master_status([row.canonical_status for row in linked])
        if live_records and projection == master.status:
            return {"rule": "SOURCE_SCOPED_REMOVAL_WITH_LIVE_LINKED_SUPPORT_V1",
                    **source_evidence,
                    "source_record_status": record.canonical_status,
                    "source_missing_successful_checks": record.missing_successful_checks,
                    "source_removal_confirmed_at": record.last_seen_at.isoformat() if record.last_seen_at else None,
                    "live_linked_records": [{"source_record_id": row.id,
                        "source_opportunity_id": row.source_opportunity_id,
                        "canonical_status": row.canonical_status,
                        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None}
                        for row in live_records],
                    "aggregate_master_status": projection,
                    "projection_flags": projection_flags,
                    "source_history_preserved": True}

    # A missing source sector is not a sector contradiction. Older queue
    # records sometimes stored activity/sub-activity text as a sector value.
    if (conflict.field_name == "sector"
            and conflict.conflict_type in {"TAXONOMY_CONFLICT", "FIELD_VALUE_CONFLICT"}
            and mapping_status == "MISSING" and record.source_sector in (None, "")):
        return {"rule": "CURRENT_SOURCE_SECTOR_MISSING_NOT_CONFLICT_V1", **source_evidence}

    # Generic/missing "Investment" is not an opportunity type. Other
    # taxonomy dimensions remain in their own fields and are not promoted.
    if (conflict.field_name == "opportunity_type"
            and conflict.conflict_type == "TAXONOMY_CONFLICT"
            and mapping_status == "MISSING"
            and current in (None, "", "غير محدد")
            and (projected.get("raw") in (None, "")
                 or str(projected.get("raw")).strip().casefold() in _GENERIC_OPPORTUNITY_TYPES)):
        return {"rule": "GENERIC_OR_MISSING_OPPORTUNITY_TYPE_NOT_CONFLICT_V1", **source_evidence}

    # A source with no owner whose raw location says "Municipality" cannot
    # create an owner conflict from that location string.
    if (conflict.field_name == "opportunity_owner"
            and conflict.conflict_type == "FIELD_VALUE_CONFLICT"
            and mapping_status == "MISSING" and record.source_owner in (None, "")
            and record.raw_location and str(conflict.conflicting_value).strip() == record.raw_location.strip()
            and str(record.raw_location).strip().casefold() == "municipality"):
        return {"rule": "LOCATION_VALUE_NOT_OWNER_EVIDENCE_V1", **source_evidence}

    # Exact current agreement under the accepted source projection proves that
    # these title/location field conflicts no longer reproduce.
    if (conflict.field_name in {"location_description", "normalized_title", "activity"}
            and mapping_status in {"NORMALIZED", "MAPPED"}
            and projected.get("canonical_label") not in (None, "")
            and str(projected.get("canonical_label")) == str(current)
            and str(conflict.selected_value) == str(current)):
        return {"rule": "CURRENT_CANONICAL_FIELD_AGREEMENT_V1", **source_evidence}

    # A duration case was specifically about an unverified source measure.
    # If the same linked source now has an explicit validated unit/value and
    # its raw measure changed, that old ambiguity is obsolete. Do not project
    # the value into the Master here.
    if (conflict.field_name == "contract_duration_years"
            and conflict.conflict_type == "STANDARDIZATION_REVIEW"
            and source.source_key == "furas"
            and mapping_status == "VALID"
            and projected.get("rule") == "validated_numeric_v1"
            and projected.get("canonical_label") is not None
            and str(projected.get("raw")) != str(conflict.conflicting_value)):
        return {"rule": "SOURCE_DURATION_NOW_EXPLICIT_AND_VALID_V1", **source_evidence}

    return None


def resolve_stale_conflict(db: Session, conflict: OpportunityConflict, evidence: dict,
                           *, now: datetime | None = None) -> bool:
    """Resolve one proven-stale conflict atomically with an explicit system audit."""
    if conflict.status != "OPEN" or not evidence or not evidence.get("rule"):
        return False
    now = now or datetime.now(timezone.utc)
    before = {
        "status": conflict.status,
        "master_id": conflict.opportunity_id,
        "field": conflict.field_name,
        "selected_value": conflict.selected_value,
        "conflicting_value": conflict.conflicting_value,
    }
    reason = "Underlying conflict no longer reproduces in the current linked source projection."
    conflict.status = "RESOLVED_CANONICAL"
    audit(db, "REVIEW_STALE_CONDITION_RESOLVED", user_id=None,
          entity_type="opportunity_conflict", entity_id=str(conflict.id),
          before=before,
          after={"status": conflict.status, "decision": "STALE_CONDITION_RESOLVED",
                 "reason": reason, "evidence": evidence},
          metadata={"actor": "SYSTEM", "rule": evidence["rule"],
                    "review_audit_version": "1", "resolved_at": now.isoformat()})
    return True


def reevaluate_open_conflicts(db: Session, *, source_record_id: int | None = None,
                              master_id: int | None = None,
                              field_names: set[str] | None = None,
                              now: datetime | None = None) -> list[int]:
    """Re-evaluate only open conflicts for the changed source record/Master."""
    query = select(OpportunityConflict).where(OpportunityConflict.status == "OPEN")
    if source_record_id is not None:
        query = query.where(OpportunityConflict.source_record_id == source_record_id)
    if master_id is not None:
        query = query.where(OpportunityConflict.opportunity_id == master_id)
    if source_record_id is None and master_id is None:
        raise ValueError("targeted re-evaluation requires a source_record_id or master_id")
    if field_names:
        query = query.where(OpportunityConflict.field_name.in_(field_names))
    rows = db.scalars(query.order_by(OpportunityConflict.id).with_for_update()).all()
    resolved = []
    for row in rows:
        evidence = stale_conflict_evidence(db, row)
        if evidence and resolve_stale_conflict(db, row, evidence, now=now):
            resolved.append(row.id)
    return resolved


def apply_review_triage_candidates(db: Session, conflict_ids: list[int],
                                   *, now: datetime | None = None) -> list[dict]:
    """Apply an audited dry-run list after rechecking each row under a lock."""
    if not conflict_ids:
        return []
    rows = db.scalars(select(OpportunityConflict).where(
        OpportunityConflict.id.in_(set(conflict_ids)),
        OpportunityConflict.status == "OPEN").order_by(OpportunityConflict.id).with_for_update()).all()
    applied = []
    for row in rows:
        evidence = stale_conflict_evidence(db, row)
        if evidence and resolve_stale_conflict(db, row, evidence, now=now):
            applied.append({"review_id": row.id, "previous_status": "OPEN",
                            "new_status": row.status, "rule": evidence["rule"],
                            "master_id": row.opportunity_id, "source_record_id": row.source_record_id,
                            "evidence": evidence, "actor": "SYSTEM"})
    return applied

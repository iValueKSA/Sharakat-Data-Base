"""Append-only, provenance-backed enrichment for open review records.

Evidence is attached to the audit stream so the original review payload and raw
source observations remain immutable. Re-evaluation is always scoped to one
source record or one Master; callers must not invoke this as a backlog scan.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEvent, LocationReview, OpportunityConflict, Source, SourceObservation, SourceOpportunity


EVIDENCE_EVENT = "REVIEW_EVIDENCE_ENRICHED"
EVIDENCE_VERSION = "1"
GENERIC_PUBLISHER_ROLES = {"publisher", "publication_platform", "platform", "source"}


def stable_hash(value: dict) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def value_at_path(payload: dict, path: str):
    """Read a dotted raw field path without inventing absent values."""
    value = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def owner_evidence(explicit_owner, *, source_role: str | None = None):
    """Publisher/source identity never serves as opportunity-owner evidence."""
    if source_role and source_role.casefold() in GENERIC_PUBLISHER_ROLES:
        return None
    return explicit_owner if explicit_owner not in (None, "") else None


def choose_sector(official_value, inferred_value):
    """Use explicit official taxonomy when present; otherwise preserve inference."""
    return official_value if official_value not in (None, "") else inferred_value


def compare_text(left, right) -> str:
    """Normalize only whitespace; material wording remains distinguishable."""
    normalized = lambda value: " ".join(str(value or "").split()).casefold()
    if not normalized(left) and not normalized(right):
        return "BOTH_MISSING"
    if not normalized(left) or not normalized(right):
        return "MISSING_VS_PRESENT"
    return "EQUIVALENT_TEXT" if normalized(left) == normalized(right) else "MATERIAL_TEXT_DIFFERENCE"


def numeric_evidence(field: str, value, *, unit=None, currency=None) -> dict:
    """Keep absent distinct from zero and do not fill unknown units/currency."""
    if value in (None, ""):
        return {"value": None, "unit": unit, "currency": currency, "state": "MISSING"}
    return {"value": value, "unit": unit, "currency": currency,
            "state": "UNINTERPRETED" if field == "investment_value" and not currency
            else "UNINTERPRETED" if field in {"contract_duration_years", "land_area_sqm"} and not unit
            else "EXPLICIT"}


def location_disposition(*, explicit_site: bool, confidence: float | None,
                         threshold: float, confirmed_outside: bool = False) -> str:
    if confirmed_outside:
        return "CONFIRMED_OUTSIDE_AL_AHSA"
    if not explicit_site:
        return "LOCATION_STILL_UNAVAILABLE"
    return "CONFIRMED_AL_AHSA" if (confidence or 0) >= threshold else "HUMAN_REVIEW_REQUIRED"


def duration_disposition(value, *, semantics_verified: bool) -> str:
    if value in (None, ""):
        return "TRULY_UNAVAILABLE_EVIDENCE"
    return "EVIDENCE_RECOVERED_AND_DETERMINISTIC" if semantics_verified else "EVIDENCE_RECOVERED_BUT_HUMAN_REVIEW_REQUIRED"


def merge_evidence_allowed(*, identity_proven: bool) -> bool:
    return bool(identity_proven)


def deterministic_resolution_allowed(*, explicit_or_governed: bool, provenance_complete: bool,
                                    conflicting_evidence: bool, subjective_judgment: bool,
                                    workflow_safe: bool) -> bool:
    return bool(explicit_or_governed and provenance_complete and not conflicting_evidence
                and not subjective_judgment and workflow_safe)


def lifecycle_evidence_relevant(*, historical_status: str | None, source_disappeared: bool = False) -> bool:
    """A source disappearance is historical evidence, never cancellation proof."""
    return historical_status not in (None, "") or source_disappeared


def _current_raw_field(record: SourceOpportunity, field: str):
    raw = record.raw_data_json or {}
    if field == "contract_duration_years":
        return "attributes.DURATION", value_at_path(raw, "attributes.DURATION")
    if field == "investment_value":
        return "investmentSize", raw.get("investmentSize")
    if field in {"opportunity_owner", "owner"}:
        # Do not use publisher/source/platform as a substitute for an owner.
        return "source_owner", record.source_owner
    if field in {"sector", "subsector", "activity", "sub_activity", "opportunity_type", "investment_model"}:
        attr = {"sector": "source_sector", "subsector": "source_subsector",
                "activity": "source_activity", "sub_activity": "source_sub_activity"}.get(field)
        value = getattr(record, attr, None) if attr else None
        if value in (None, ""):
            value = raw.get(field) or value_at_path(raw, f"source_taxonomy.{field}")
        return field, value
    if field in {"location_description", "city", "district", "latitude", "longitude"}:
        return field, getattr(record, "raw_location", None) or raw.get("location")
    if field in {"land_area_sqm", "land_area", "area"}:
        return "raw_area", record.raw_area
    if field == "status":
        return "raw_status", record.raw_status
    source_attr = {"title_ar": "source_title", "normalized_title": "normalized_source_title",
                   "short_description": None, "full_description": None}.get(field)
    value = getattr(record, source_attr, None) if source_attr else raw.get("description")
    return field, value


def evidence_item(*, source_type: str, source_name: str, source_opportunity_id: int,
                  raw_field: str, raw_value, normalized_value, observed_at,
                  evidence_role: str, reliability_level: str,
                  observation_id: int | None = None) -> dict:
    """Create a contract-compliant evidence item or fail closed."""
    required = (source_type, source_name, source_opportunity_id, raw_field,
                observed_at, evidence_role, reliability_level)
    if any(value in (None, "") for value in required):
        raise ValueError("evidence provenance fields are mandatory")
    if raw_value is None:
        raise ValueError("raw evidence value is mandatory")
    return {
        "source_type": source_type,
        "source_name": source_name,
        "source_opportunity_id": int(source_opportunity_id),
        "observation_id": int(observation_id) if observation_id is not None else None,
        "raw_field": raw_field,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "observed_at": observed_at.isoformat() if hasattr(observed_at, "isoformat") else str(observed_at),
        "evidence_role": evidence_role,
        "reliability_level": reliability_level,
    }


def _event_key(event: AuditEvent) -> str | None:
    return ((event.after_json or {}).get("enrichment_fingerprint")
            if isinstance(event.after_json, dict) else None)


def attach_review_evidence(db: Session, *, review_type: str, review_id: int,
                           master_id: int | None, source_ids: list[int], field: str,
                           classification: str, disposition: str,
                           evidence: list[dict], explanation: str,
                           fingerprint: str | None = None,
                           now: datetime | None = None) -> bool:
    """Append one enrichment event; return False when the same evidence exists."""
    for item in evidence:
        if not all(item.get(key) not in (None, "") for key in (
                "source_type", "source_name", "source_opportunity_id", "raw_field",
                "raw_value", "observed_at", "evidence_role", "reliability_level")):
            raise ValueError("recovered evidence without complete provenance")
    now = now or datetime.now(timezone.utc)
    payload = {
        "schema_version": EVIDENCE_VERSION,
        "review_type": review_type,
        "review_id": int(review_id),
        "master_id": master_id,
        "source_ids": sorted(set(int(item) for item in source_ids)),
        "field": field,
        "original_classification": classification,
        "disposition": disposition,
        "blocked_review_after_enrichment": (
            "HUMAN_REVIEW_REQUIRED" if disposition in {
                "WRONG_BLOCKED_CLASSIFICATION",
                "EVIDENCE_RECOVERED_BUT_HUMAN_REVIEW_REQUIRED"}
            else "BLOCKED_BY_MISSING_EVIDENCE"),
        "evidence": evidence,
        "explanation": explanation,
    }
    key = fingerprint or stable_hash(payload)
    from sqlalchemy import or_, and_
    existing = db.scalars(select(AuditEvent).where(
        AuditEvent.event_type == EVIDENCE_EVENT,
        or_(
            and_(AuditEvent.entity_type == "review_evidence",
                 AuditEvent.entity_id == f"{review_type.lower()}:{review_id}"),
            and_(AuditEvent.entity_type == review_type.lower(),
                 AuditEvent.entity_id == str(review_id)),
        ),
    )).all()
    if any(_event_key(event) == key for event in existing):
        return False
    payload["enrichment_fingerprint"] = key
    db.add(AuditEvent(
        user_id=None, event_type=EVIDENCE_EVENT,
        entity_type="review_evidence", entity_id=f"{review_type.lower()}:{review_id}",
        before_json=None, after_json=payload,
        request_metadata={"actor": "SYSTEM", "evidence_schema_version": EVIDENCE_VERSION,
                          "append_only": True}, created_at=now,
    ))
    return True


def re_evaluate_review_evidence(db: Session, *, source_record_id: int | None = None,
                                master_id: int | None = None,
                                trigger: str = "source_observation",
                                now: datetime | None = None) -> dict:
    """Re-evaluate only reviews linked to the supplied source record or Master.

    This pass records newly arrived source context. It deliberately never
    resolves reviews or writes canonical opportunity fields.
    """
    if source_record_id is None and master_id is None:
        raise ValueError("targeted review evidence evaluation requires an entity id")
    now = now or datetime.now(timezone.utc)
    query = select(OpportunityConflict).where(OpportunityConflict.status == "OPEN")
    if source_record_id is not None and master_id is not None:
        from sqlalchemy import or_
        query = query.where(or_(OpportunityConflict.source_record_id == source_record_id,
                                OpportunityConflict.opportunity_id == master_id))
    elif source_record_id is not None:
        query = query.where(OpportunityConflict.source_record_id == source_record_id)
    elif master_id is not None:
        query = query.where(OpportunityConflict.opportunity_id == master_id)
    conflicts = db.scalars(query.order_by(OpportunityConflict.id)).all()
    location_query = select(LocationReview).where(LocationReview.status == "PENDING")
    if source_record_id is not None and master_id is not None:
        from sqlalchemy import or_
        location_query = location_query.join(SourceOpportunity,
            SourceOpportunity.id == LocationReview.source_record_id).where(or_(
                LocationReview.source_record_id == source_record_id,
                SourceOpportunity.master_opportunity_id == master_id))
    elif source_record_id is not None:
        location_query = location_query.where(LocationReview.source_record_id == source_record_id)
    elif master_id is not None:
        location_query = location_query.join(SourceOpportunity,
            SourceOpportunity.id == LocationReview.source_record_id).where(
                SourceOpportunity.master_opportunity_id == master_id)
    locations = db.scalars(location_query.order_by(LocationReview.id)).all()
    attached = 0
    for conflict in conflicts:
        related = db.scalars(select(SourceOpportunity).where(
            SourceOpportunity.master_opportunity_id == conflict.opportunity_id
        ).order_by(SourceOpportunity.id)).all()
        if not any(row.id == conflict.source_record_id for row in related):
            linked_row = db.get(SourceOpportunity, conflict.source_record_id)
            if linked_row:
                related.append(linked_row)
        evidence = []
        for record in related:
            raw_field, value = _current_raw_field(record, conflict.field_name)
            if value in (None, ""):
                continue
            source = db.get(Source, record.source_id)
            if not source:
                continue
            obs = db.scalars(select(SourceObservation).where(
                SourceObservation.source_opportunity_id == record.id
            ).order_by(SourceObservation.first_seen_at.desc(), SourceObservation.id.desc()).limit(1)).first()
            observed_at = (obs.first_seen_at if obs else record.first_seen_at) or now
            evidence.append(evidence_item(
                source_type=source.source_type, source_name=source.source_key,
                source_opportunity_id=record.id, observation_id=obs.id if obs else None,
                raw_field=raw_field, raw_value=value, normalized_value=None,
                observed_at=observed_at, evidence_role="CURRENT_OR_LINKED_SOURCE_CONTEXT",
                reliability_level="RAW_SOURCE_UNINTERPRETED",
            ))
        if not evidence:
            continue
        if attach_review_evidence(db, review_type="OPPORTUNITY_CONFLICT", review_id=conflict.id,
                master_id=conflict.opportunity_id, source_ids=[item["source_opportunity_id"] for item in evidence], field=conflict.field_name,
                classification="OPEN", disposition="RETAIN_OPEN", evidence=evidence,
                explanation=f"Targeted re-evaluation triggered by {trigger}; no canonical value was changed."):
            attached += 1
    for review in locations:
        record = db.get(SourceOpportunity, review.source_record_id) if review.source_record_id else None
        if not record:
            continue
        related = db.scalars(select(SourceOpportunity).where(
            SourceOpportunity.master_opportunity_id == record.master_opportunity_id
        ).order_by(SourceOpportunity.id)).all() if record.master_opportunity_id else [record]
        evidence = []
        for linked in related:
            source = db.get(Source, linked.source_id)
            if not source:
                continue
            raw = linked.raw_data_json or {}
            raw_value = (raw.get("description") or raw.get("location_evidence")
                         or raw.get("source_scope") or raw.get("location") or linked.raw_location)
            if raw_value in (None, ""):
                continue
            obs = db.scalars(select(SourceObservation).where(
                SourceObservation.source_opportunity_id == linked.id
            ).order_by(SourceObservation.first_seen_at.desc(), SourceObservation.id.desc()).limit(1)).first()
            evidence.append(evidence_item(
                source_type=source.source_type, source_name=source.source_key,
                source_opportunity_id=linked.id, observation_id=obs.id if obs else None,
                raw_field="description/location/source_scope", raw_value=raw_value,
                normalized_value=None, observed_at=(obs.first_seen_at if obs else linked.first_seen_at) or now,
                evidence_role="LOCATION_CONTEXT", reliability_level="RAW_SOURCE_CONTEXT",
            ))
        if not evidence:
            continue
        if attach_review_evidence(db, review_type="LOCATION_REVIEW", review_id=review.id,
                master_id=record.master_opportunity_id, source_ids=[item["source_opportunity_id"] for item in evidence], field="location",
                classification="PENDING", disposition="RETAIN_OPEN", evidence=evidence,
                explanation=f"Targeted re-evaluation triggered by {trigger}; location acceptance remains governed by the review workflow."):
            attached += 1
    return {"targeted_reviews": len(conflicts) + len(locations), "evidence_items_attached": attached,
            "auto_resolutions": 0, "trigger": trigger}

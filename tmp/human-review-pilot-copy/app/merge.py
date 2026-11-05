"""Audited, reversible merge operations for confirmed cross-source duplicates."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (ChangeHistory, DuplicateCandidate, FieldProvenance, MergeAudit, Source,
                     Opportunity, OpportunityConflict, OpportunityDocument,
                     SourceOpportunity, SystemEvent)
from .normalization import normalize_reference
from .service import source_authority
from .entity_resolution import values_equivalent
from .review_lifecycle import reevaluate_open_conflicts
from .review_evidence import re_evaluate_review_evidence

NOW = lambda: datetime.now(timezone.utc)
MERGE_FIELDS = (
    "title_ar", "title_en", "normalized_title", "reference_number", "reference_number_normalized",
    "opportunity_owner", "primary_publication_platform", "sector", "subsector", "opportunity_type",
    "city", "district", "location_description", "latitude", "longitude", "land_area_sqm", "plot_number",
    "investment_value", "currency", "contract_duration_years", "publication_date", "submission_deadline",
    "status", "short_description", "full_description", "location_confidence_score",
    "location_detection_method", "location_evidence", "data_quality_score", "manual_review_required",
)


def snapshot(master: Opportunity) -> dict:
    data = {name: getattr(master, name) for name in MERGE_FIELDS}
    for name in ("last_seen_at", "last_updated_at", "updated_at"):
        value = getattr(master, name)
        data[name] = value.isoformat() if value else None
    return data


def _same(field: str, a, b) -> bool:
    return values_equivalent(field, a, b) or (a is not None and b is not None and str(a).strip() == str(b).strip())


def _field_rank(db: Session, master_id: int, field: str) -> int:
    rows = db.scalars(select(FieldProvenance).where(
        FieldProvenance.opportunity_id == master_id, FieldProvenance.field_name == field)).all()
    provenance_rank = max((source_authority(row.source.source_key) for row in rows if row.source), default=0)
    source_rows = db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id == master_id)).all()
    record_rank = max((source_authority(row.source.source_key) for row in source_rows if row.source), default=0)
    return max(provenance_rank, record_rank)


def merge_candidate(db: Session, candidate: DuplicateCandidate, *, performed_by: str = "admin") -> MergeAudit:
    if candidate.status != "PENDING":
        raise ValueError("candidate is not pending")
    target = db.get(Opportunity, candidate.left_opportunity_id)
    source = db.get(Opportunity, candidate.right_opportunity_id)
    if not target or not source or target.id == source.id:
        raise ValueError("both distinct master opportunities are required")
    if target.merged_into_id or source.merged_into_id:
        raise ValueError("candidate includes an already merged master")
    source_records = db.scalars(select(SourceOpportunity).where(
        SourceOpportunity.master_opportunity_id == source.id)).all()
    target_source_ids = {r.source_id for r in target.source_records}
    cross_source_match=bool(source_records) and any(r.source_id not in target_source_ids for r in source_records)
    # Exact same-source article aliases can create a duplicate master when a publisher
    # changes its external-ID scheme. Permit a merge only when URL and normalized title
    # match exactly; broader same-source similarity still requires normal review.
    target_articles={(r.source_id,r.source_url,r.normalized_source_title) for r in target.source_records}
    same_article_alias=any((r.source_id,r.source_url,r.normalized_source_title) in target_articles for r in source_records)
    if not source_records or not (cross_source_match or same_article_alias):
        raise ValueError("merge must connect distinct sources or exact same-source article aliases")

    before = snapshot(target)
    record_ids = [r.id for r in source_records]
    now = NOW()
    histories = db.scalars(select(ChangeHistory).where(ChangeHistory.opportunity_id == source.id)).all()
    provenance = db.scalars(select(FieldProvenance).where(FieldProvenance.opportunity_id == source.id)).all()
    conflicts = db.scalars(select(OpportunityConflict).where(OpportunityConflict.opportunity_id == source.id)).all()
    documents = db.scalars(select(OpportunityDocument).where(OpportunityDocument.opportunity_id == source.id)).all()
    audit = MergeAudit(
        merged_opportunity_id=source.id, target_opportunity_id=target.id,
        source_record_ids=record_ids, created_at=now, merged_at=now,
        merge_reason="Confirmed duplicate after official-source field review",
        merge_evidence=candidate.explanation_json or {}, performed_by=performed_by,
        target_before_json=before,
        source_history_ids=[x.id for x in histories],
        source_provenance_ids=[x.id for x in provenance],
        source_conflict_ids=[x.id for x in conflicts],
        source_document_ids=[x.id for x in documents],
        merge_history_ids=[],
    )
    db.add(audit)
    db.flush()

    # Reconcile each canonical field independently. A stronger source may replace a
    # weaker value; otherwise keep the current value and record any material conflict.
    merge_history_ids = []
    for field in MERGE_FIELDS:
        current, incoming = getattr(target, field), getattr(source, field)
        # These fields describe portal provenance or extraction confidence, not competing
        # investment facts. Both source records remain attached and preserve their values.
        if field in {"primary_publication_platform", "location_confidence_score",
                     "location_detection_method", "location_evidence"}:
            continue
        if incoming is None or incoming == "" or _same(field, current, incoming):
            continue
        current_rank = _field_rank(db, target.id, field)
        incoming_rank = _field_rank(db, source.id, field)
        selected = incoming if current in (None, "") or incoming_rank > current_rank else current
        if current not in (None, ""):
            record = next((r for r in source_records if r.source_id == max(
                (x.source_id for x in provenance if x.field_name == field),
                key=lambda sid: source_authority(next((r.source.source_key for r in source_records if r.source_id == sid), "")),
                default=source_records[0].source_id)), source_records[0])
            db.add(OpportunityConflict(opportunity_id=target.id, field_name=field,
                selected_value=str(selected), conflicting_value=str(incoming if selected != incoming else current),
                source_id=record.source_id, source_record_id=record.id, detected_at=now, status="OPEN"))
        if selected != current:
            change = ChangeHistory(opportunity_id=target.id, changed_field=field,
                previous_value=None if current is None else str(current), new_value=str(selected),
                source_id=record.source_id if current not in (None, "") else None, detected_at=now)
            db.add(change)
            db.flush()
            merge_history_ids.append(change.id)
            setattr(target, field, selected)
    if not target.reference_number_normalized and target.reference_number:
        target.reference_number_normalized = normalize_reference(target.reference_number)

    for record in source_records:
        record.master_opportunity_id = target.id
    for child in histories + provenance + conflicts + documents:
        child.opportunity_id = target.id
    source.merged_into_id = target.id
    target.last_seen_at = max(filter(None, [target.last_seen_at, source.last_seen_at]))
    target.last_updated_at = now
    target.updated_at = now
    candidate.status = "MERGED"
    audit.target_after_json = snapshot(target)
    audit.merge_history_ids = merge_history_ids
    db.add(SystemEvent(event_type="MASTER_DUPLICATE_MERGED", created_at=now, payload={
        "audit_id": audit.id, "surviving_master_id": target.id, "merged_master_id": source.id,
        "source_record_ids": record_ids, "merge_reason": audit.merge_reason,
        "merge_evidence": audit.merge_evidence, "performed_by": performed_by,
    }))
    # Moving source evidence changes the entity lineage. Re-check only conflicts
    # now attached to the surviving Master inside the merge transaction.
    reevaluate_open_conflicts(db, master_id=target.id, now=now)
    re_evaluate_review_evidence(db, master_id=target.id, trigger="master_merge", now=now)
    return audit


def undo_candidate(db: Session, candidate: DuplicateCandidate) -> MergeAudit:
    audit = db.scalar(select(MergeAudit).where(
        MergeAudit.merged_opportunity_id == candidate.right_opportunity_id,
        MergeAudit.target_opportunity_id == candidate.left_opportunity_id,
        MergeAudit.undone_at.is_(None)).order_by(MergeAudit.created_at.desc()))
    if not audit:
        raise ValueError("no reversible merge exists for this candidate")
    target = db.get(Opportunity, audit.target_opportunity_id)
    source = db.get(Opportunity, audit.merged_opportunity_id)
    if not target or not source:
        raise ValueError("merge master records are missing")
    for name, value in (audit.target_before_json or {}).items():
        if name in {"last_seen_at", "last_updated_at", "updated_at"} and value:
            value = datetime.fromisoformat(value)
        setattr(target, name, value)
    source.merged_into_id = None
    record_ids = audit.source_record_ids or []
    source_records = db.scalars(select(SourceOpportunity).where(SourceOpportunity.id.in_(record_ids))).all()
    source_ids = {record.source_id for record in source_records}
    for record in source_records:
        record.master_opportunity_id = source.id
    if audit.source_history_ids:
        db.query(ChangeHistory).filter(ChangeHistory.id.in_(audit.source_history_ids)).update(
            {ChangeHistory.opportunity_id: source.id}, synchronize_session=False)
    if source_ids:
        db.query(FieldProvenance).filter(FieldProvenance.source_record_id.in_(record_ids)).update(
            {FieldProvenance.opportunity_id: source.id}, synchronize_session=False)
        db.query(OpportunityConflict).filter(OpportunityConflict.source_record_id.in_(record_ids)).update(
            {OpportunityConflict.opportunity_id: source.id}, synchronize_session=False)
        later_history = db.scalars(select(ChangeHistory).where(
            ChangeHistory.opportunity_id == target.id, ChangeHistory.source_id.in_(source_ids),
            ChangeHistory.detected_at >= audit.merged_at,
            ChangeHistory.id.not_in(audit.merge_history_ids or []))).all()
        for history in later_history:
            history.opportunity_id = source.id
    if audit.source_provenance_ids:
        db.query(FieldProvenance).filter(FieldProvenance.id.in_(audit.source_provenance_ids)).update(
            {FieldProvenance.opportunity_id: source.id}, synchronize_session=False)
    if audit.source_conflict_ids:
        db.query(OpportunityConflict).filter(OpportunityConflict.id.in_(audit.source_conflict_ids)).update(
            {OpportunityConflict.opportunity_id: source.id}, synchronize_session=False)
    if audit.source_document_ids:
        db.query(OpportunityDocument).filter(OpportunityDocument.id.in_(audit.source_document_ids)).update(
            {OpportunityDocument.opportunity_id: source.id}, synchronize_session=False)
    if audit.merge_history_ids:
        db.query(ChangeHistory).filter(ChangeHistory.id.in_(audit.merge_history_ids)).delete(synchronize_session=False)
    now = NOW()
    audit.undone_at = now
    candidate.status = "UNDONE"
    db.add(SystemEvent(event_type="MASTER_DUPLICATE_MERGE_UNDONE", created_at=now, payload={
        "audit_id": audit.id, "surviving_master_id": target.id, "restored_master_id": source.id,
        "source_record_ids": audit.source_record_ids or [],
    }))
    re_evaluate_review_evidence(db, master_id=source.id, trigger="master_merge_undo", now=now)
    return audit

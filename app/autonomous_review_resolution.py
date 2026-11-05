"""Conservative, audited resolution of an explicitly delegated review backlog."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .models import (AuditEvent, ChangeHistory, DuplicateCandidate, FieldProvenance,
                     LocationReview, Opportunity, OpportunityConflict,
                     QualificationReview, Source, SourceObservation,
                     SourceOpportunity, SyncJob)
from .rcu_review_safety import rcu_conflict_source_value_is_promotable

RULE_VERSION = "AUTONOMOUS_REVIEW_RESOLUTION_V1"
OPEN_STATES = {"OPEN", "PENDING"}


def _current_matches_competing(field: str, current, competing) -> bool:
    if current == competing or (current is not None and competing is not None
            and str(current).strip() == str(competing).strip()):
        return True
    if field == "status":
        from .entity_resolution import lifecycle_status, values_equivalent
        left_status, right_status = lifecycle_status(str(current)), lifecycle_status(str(competing))
        return (left_status != "UNKNOWN" and right_status != "UNKNOWN"
                and values_equivalent(field, current, competing))
    if field in {"opportunity_owner", "reference_number", "land_area_sqm", "latitude", "longitude",
                 "contract_duration_years", "investment_value"}:
        from .entity_resolution import values_equivalent
        return values_equivalent(field, current, competing)
    if field in {"sector", "activity", "sub_activity", "opportunity_type", "investment_model"}:
        from .standardization import canonical_id
        left, right = canonical_id(field, current), canonical_id(field, competing)
        return left == right and not left.startswith(("unmapped:", "sector:unspecified", "activity:unspecified"))
    return False


def exact_duplicate_identity(db: Session, candidate: DuplicateCandidate) -> dict[str, Any] | None:
    """Return proof only for an exact official identity or exact same-source article."""
    left = db.get(Opportunity, candidate.left_opportunity_id)
    right = db.get(Opportunity, candidate.right_opportunity_id)
    if not left or not right or left.merged_into_id or right.merged_into_id:
        return None
    left_rows = db.scalars(select(SourceOpportunity).where(
        SourceOpportunity.master_opportunity_id == left.id)).all()
    right_rows = db.scalars(select(SourceOpportunity).where(
        SourceOpportunity.master_opportunity_id == right.id)).all()
    for a in left_rows:
        for b in right_rows:
            if (a.source_id == b.source_id and a.official_source_id_normalized
                    and a.official_source_id_normalized.casefold() == b.official_source_id_normalized.casefold()):
                source = db.get(Source, a.source_id)
                return {"kind": "SAME_SOURCE_OFFICIAL_ID", "source_key": source.source_key if source else None,
                        "source_id": a.source_id, "official_source_id_normalized": a.official_source_id_normalized,
                        "source_record_ids": [a.id, b.id]}
            if (a.source_id == b.source_id and a.source_url and b.source_url
                    and a.source_url.rstrip("/").casefold() == b.source_url.rstrip("/").casefold()
                    and a.normalized_source_title and a.normalized_source_title == b.normalized_source_title):
                source = db.get(Source, a.source_id)
                return {"kind": "EXACT_SAME_SOURCE_ARTICLE", "source_key": source.source_key if source else None,
                        "source_id": a.source_id, "url": a.source_url,
                        "normalized_title": a.normalized_source_title, "source_record_ids": [a.id, b.id]}
    return None


def classify_review(db: Session, item: dict[str, Any], recommendation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Select one deterministic class and a conservative terminal action per review."""
    domain, review_id = item["domain"], int(item["id"])
    disposition = item.get("disposition")
    evidence = dict(item.get("evidence") or {})
    if disposition == "SOURCE_RECHECK_REQUIRED":
        return {"review_id": review_id, "review_type": domain, "resolution_class": "J_SOURCE_RECHECK_CONSERVATIVE_NO_CHANGE",
                "action": "keep" if domain in {"field_conflict", "taxonomy_conflict"} else "reject",
                "confidence": "CONSERVATIVE", "business_change": "NO_BUSINESS_CHANGE",
                "reason": "INSUFFICIENT_EVIDENCE_NO_CHANGE", "evidence": evidence}
    if domain == "duplicate":
        row = db.get(DuplicateCandidate, review_id)
        proof = exact_duplicate_identity(db, row) if row else None
        masters = [db.get(Opportunity, mid) for mid in item.get("master_ids", [])]
        if not row or any(master is None or master.merged_into_id is not None for master in masters):
            return {"review_id": review_id, "review_type": domain, "resolution_class": "K_SUPERSEDED_OR_STALE_REVIEW",
                    "action": "supersede", "confidence": "HIGH", "business_change": "NO_BUSINESS_CHANGE",
                    "reason": "SUPERSEDED_REVIEW", "evidence": evidence}
        if proof:
            return {"review_id": review_id, "review_type": domain, "resolution_class": "C_DETERMINISTIC_DUPLICATE_MERGE",
                    "action": "merge", "confidence": "HIGH", "business_change": "MASTER_MERGE",
                    "reason": "IDENTITY_PROVEN", "identity_proof": proof, "evidence": evidence}
        return {"review_id": review_id, "review_type": domain, "resolution_class": "D_CONSERVATIVE_NOT_DUPLICATE",
                "action": "reject", "confidence": "CONSERVATIVE", "business_change": "NO_BUSINESS_CHANGE",
                "reason": "IDENTITY_NOT_PROVEN_KEEP_SEPARATE", "evidence": evidence}
    if domain == "location":
        row = db.get(LocationReview, review_id)
        record = db.get(SourceOpportunity, row.source_record_id) if row and row.source_record_id else None
        master = db.get(Opportunity, record.master_opportunity_id) if record and record.master_opportunity_id else None
        if not row or not record or (master and master.merged_into_id is not None):
            return {"review_id": review_id, "review_type": domain, "resolution_class": "K_SUPERSEDED_OR_STALE_REVIEW",
                    "action": "supersede", "confidence": "HIGH", "business_change": "NO_BUSINESS_CHANGE",
                    "reason": "SUPERSEDED_REVIEW", "evidence": evidence}
        # The accepted automatic rule requires explicit project-level locality and
        # confidence >= .90. Publisher scope, city lists, and indirect descriptions do not qualify.
        explicit_location = (row.source_location or record.raw_location or "").strip()
        accepted_localities = {"الأحساء", "الاحساء", "الهفوف", "المبرز", "Al-Ahsa", "Al Ahsa", "Al-Hofuf", "Al Mubarraz"}
        if row.confidence_score >= .90 and explicit_location in accepted_localities:
            return {"review_id": review_id, "review_type": domain, "resolution_class": "E_EXPLICIT_LOCATION_DECISION",
                    "action": "accept", "confidence": "HIGH", "business_change": "LOCATION_CHANGE",
                    "reason": "EXPLICIT_LOCATION_EVIDENCE", "evidence": evidence}
        return {"review_id": review_id, "review_type": domain, "resolution_class": "E_EXPLICIT_LOCATION_DECISION",
                "action": "reject", "confidence": "CONSERVATIVE", "business_change": "NO_BUSINESS_CHANGE",
                "reason": "LOCATION_EVIDENCE_INSUFFICIENT_PRESERVE_CURRENT", "evidence": evidence}
    if domain == "qualification":
        return {"review_id": review_id, "review_type": domain, "resolution_class": "L_OTHER_DETERMINISTIC_RESOLUTION",
                "action": "reject", "confidence": "CONSERVATIVE", "business_change": "NO_BUSINESS_CHANGE",
                "reason": "INSUFFICIENT_EVIDENCE_NO_CHANGE", "evidence": evidence}

    row = db.get(OpportunityConflict, review_id)
    master = db.get(Opportunity, row.opportunity_id) if row else None
    source_record = db.get(SourceOpportunity, row.source_record_id) if row and row.source_record_id else None
    if not row or not master or master.merged_into_id is not None or not source_record:
        return {"review_id": review_id, "review_type": domain, "resolution_class": "K_SUPERSEDED_OR_STALE_REVIEW",
                "action": "supersede", "confidence": "HIGH", "business_change": "NO_BUSINESS_CHANGE",
                "reason": "SUPERSEDED_REVIEW", "evidence": evidence}
    current = getattr(master, row.field_name, None) if hasattr(master, row.field_name) else None
    if current not in (None, "") and _current_matches_competing(row.field_name, current, row.conflicting_value):
        return {"review_id": review_id, "review_type": domain, "resolution_class": "K_SUPERSEDED_OR_STALE_REVIEW",
                "action": "supersede", "confidence": "HIGH", "business_change": "NO_BUSINESS_CHANGE",
                "reason": "SUPERSEDED_REVIEW", "evidence": {**evidence, "current_value": current}}
    if (recommendation and recommendation.get("action") == "use_source"
            and recommendation.get("confidence") == "HIGH"
            and not evidence.get("guarded_standardization")):
        raw = source_record.raw_data_json if isinstance(source_record.raw_data_json, dict) else {}
        if row.field_name == "opportunity_owner":
            # Require explicit opportunity-owner data; never promote publisher metadata.
            direct_owner = raw.get("owner") or raw.get("opportunityOwner") or raw.get("opportunity_owner")
            if not direct_owner or str(direct_owner).strip() != str(row.conflicting_value).strip():
                recommendation = None
        if row.field_name == "sector" and domain == "taxonomy_conflict":
            from .main import _valid_canonical_sector
            if not _valid_canonical_sector(row.conflicting_value):
                recommendation = None
    if recommendation and recommendation.get("action") == "use_source" and recommendation.get("confidence") == "HIGH" and not evidence.get("guarded_standardization"):
        return {"review_id": review_id, "review_type": domain, "resolution_class": "A_STRONGER_SOURCE_VALUE_WINS",
                "action": "use_source", "confidence": "HIGH", "business_change": "CANONICAL_FIELD_CHANGE",
                "reason": "STRONGER_AUTHORITATIVE_SOURCE", "evidence": evidence,
                "recommendation": recommendation}
    return {"review_id": review_id, "review_type": domain, "resolution_class": "B_KEEP_CURRENT_CANONICAL",
            "action": "keep", "confidence": "CONSERVATIVE", "business_change": "NO_BUSINESS_CHANGE",
            "reason": "INSUFFICIENT_EVIDENCE_NO_CHANGE",
            "evidence": {**evidence, "current_value": current, "recommendation": recommendation or {"action": None, "confidence": "NONE"}}}


def terminal_status(domain: str, action: str) -> str:
    if action == "supersede":
        return "SUPERSEDED"
    if domain == "duplicate":
        return "MERGED" if action == "merge" else "REJECTED"
    if domain in {"location", "qualification"}:
        return "ACCEPTED" if action == "accept" else "REJECTED"
    return "RESOLVED_SOURCE" if action == "use_source" else "RESOLVED_KEEP"


def _model(domain: str):
    return {"duplicate": DuplicateCandidate, "location": LocationReview, "qualification": QualificationReview,
            "field_conflict": OpportunityConflict, "taxonomy_conflict": OpportunityConflict}[domain]


def _audit_entity(domain: str) -> str:
    return {"duplicate": "duplicate_candidate", "location": "location_review", "qualification": "qualification_review",
            "field_conflict": "opportunity_conflict", "taxonomy_conflict": "opportunity_conflict"}[domain]


def apply_ledger(db: Session, ledger: list[dict[str, Any]], *, expected_versions: dict[str, str], actor: str = "SYSTEM",
                 allow_active_job_id: int | None = None, commit: bool = True,
                 mark_pilot_superseded: bool = True) -> dict[str, int]:
    """Apply the complete ledger atomically; any stale row aborts the whole transaction."""
    from .main import _review_version_token
    from .merge import merge_candidate
    from .main import _valid_canonical_sector

    results = {"resolved": 0, "no_change": 0, "canonical_changes": 0, "superseded": 0, "merges": 0}
    with db.begin_nested():
        active_query=select(func.count(SyncJob.id)).where(SyncJob.job_state.in_(["QUEUED", "RUNNING", "RETRYING"]))
        if allow_active_job_id is not None:
            active_query=active_query.where(SyncJob.id!=allow_active_job_id)
        active = db.scalar(active_query) or 0
        if active:
            raise RuntimeError("Natural source synchronization is active; retry after it terminates.")
        for decision in ledger:
            domain, review_id = decision["review_type"], int(decision["review_id"])
            row = db.scalar(select(_model(domain)).where(_model(domain).id == review_id).with_for_update())
            if not row or row.status not in OPEN_STATES:
                raise RuntimeError(f"Review {domain}:{review_id} changed after dry run.")
            version = _review_version_token(db, domain, review_id)
            if version != expected_versions.get(f"{domain}:{review_id}"):
                raise RuntimeError(f"Review {domain}:{review_id} evidence changed after dry run.")
            before = {"status": row.status, "review_type": domain, "review_id": review_id}
            evidence = dict(decision.get("evidence") or {})
            recommendation_evidence = decision.get("recommendation") or evidence.get("recommendation") or {}
            evidence.setdefault("supporting_evidence", recommendation_evidence.get("supporting_evidence") or [])
            evidence.setdefault("contradictory_evidence", recommendation_evidence.get("contradictory_evidence") or [])
            evidence.setdefault("source_references", [{"source_record_id": evidence.get("source_record_id"),
                "source_url": evidence.get("source_url"), "source": evidence.get("source")}])
            note = decision["reason"]
            action = decision["action"]
            if domain in {"field_conflict", "taxonomy_conflict"}:
                master = db.get(Opportunity, row.opportunity_id)
                source_record = db.get(SourceOpportunity, row.source_record_id)
                if not master or not source_record or master.merged_into_id is not None:
                    action, decision["resolution_class"], note = "supersede", "K_SUPERSEDED_OR_STALE_REVIEW", "SUPERSEDED_REVIEW"
                previous = getattr(master, row.field_name, None) if master and hasattr(master, row.field_name) else None
                before["canonical_value"] = previous
                if action == "use_source":
                    source = db.get(Source, source_record.source_id) if source_record else None
                    if not rcu_conflict_source_value_is_promotable(source, source_record, row.field_name, row.conflicting_value):
                        raise RuntimeError(f"RCU lifecycle review {review_id} contains unresolved evidence and cannot accept source value.")
                    if row.conflict_type == "STANDARDIZATION_REVIEW":
                        raise RuntimeError(f"Guarded standardization review {review_id} cannot accept source value.")
                    if row.field_name == "sector" and domain == "taxonomy_conflict" and not _valid_canonical_sector(row.conflicting_value):
                        raise RuntimeError(f"Noncanonical sector proposed for review {review_id}.")
                    setattr(master, row.field_name, row.conflicting_value)
                    now = datetime.now(timezone.utc)
                    db.add(ChangeHistory(opportunity_id=master.id, changed_field=row.field_name,
                        previous_value=None if previous is None else str(previous), new_value=str(row.conflicting_value),
                        source_id=row.source_id, detected_at=now))
                    db.add(FieldProvenance(opportunity_id=master.id, field_name=row.field_name,
                        selected_value=str(row.conflicting_value), source_id=row.source_id, source_record_id=source_record.id,
                        captured_at=now, confidence=1.0))
                    master.updated_at = master.last_updated_at = now
                    row.status = terminal_status(domain, action)
                    event_type, decision_name = "REVIEW_FIELD_USE_SOURCE", "FIELD_USE_SOURCE"
                    results["canonical_changes"] += 1
                elif action == "supersede":
                    row.status = "SUPERSEDED"
                    event_type, decision_name = "REVIEW_AUTONOMOUS_SUPERSEDED", "SUPERSEDED_REVIEW"
                    results["superseded"] += 1
                else:
                    row.status = "RESOLVED_KEEP"
                    event_type, decision_name = "REVIEW_FIELD_KEEP", "FIELD_KEEP"
                    results["no_change"] += 1
                after = {"status": row.status, "decision": decision_name, "reason": note,
                         "field": row.field_name, "master_id": row.opportunity_id,
                         "previous_value": previous, "value": getattr(master, row.field_name, None) if master else None,
                         "confidence": decision["confidence"], "resolution_class": decision["resolution_class"],
                         "business_change": decision["business_change"], "evidence": evidence}
            elif domain == "duplicate":
                if action == "merge":
                    proof = decision.get("identity_proof")
                    if not proof or decision["confidence"] != "HIGH":
                        raise RuntimeError(f"Duplicate {review_id} lacks deterministic identity proof.")
                    audit = merge_candidate(db, row, performed_by=actor, identity_proof=proof)
                    evidence.update({"identity_proof": proof, "merge_audit_id": audit.id})
                    row.status = "MERGED"
                    event_type, decision_name = "REVIEW_DUPLICATE_MERGED", "DUPLICATE_MERGED"
                    results["merges"] += 1
                elif action == "supersede":
                    row.status = "SUPERSEDED"
                    event_type, decision_name = "REVIEW_AUTONOMOUS_SUPERSEDED", "SUPERSEDED_REVIEW"
                    results["superseded"] += 1
                else:
                    row.status = "REJECTED"
                    event_type, decision_name = "REVIEW_DUPLICATE_REJECTED", "DUPLICATE_REJECTED"
                    results["no_change"] += 1
                after = {"status": row.status, "decision": decision_name, "reason": note,
                         "left_master_id": row.left_opportunity_id, "right_master_id": row.right_opportunity_id,
                         "confidence": decision["confidence"], "resolution_class": decision["resolution_class"],
                         "business_change": decision["business_change"], "evidence": evidence}
            else:
                if action == "supersede":
                    row.status = "SUPERSEDED"
                    event_type, decision_name = "REVIEW_AUTONOMOUS_SUPERSEDED", "SUPERSEDED_REVIEW"
                    results["superseded"] += 1
                else:
                    if domain == "location" and action == "accept":
                        from .adapters import RawOpportunity
                        from .service import _safe_record
                        source = db.get(Source, row.source_id)
                        source_record = db.get(SourceOpportunity, row.source_record_id)
                        if not source or not source_record:
                            raise RuntimeError(f"Location review {review_id} is missing its source evidence.")
                        raw_json = source_record.raw_data_json or {}
                        raw_original = dict(raw_json)
                        content_hash = source_record.content_hash
                        raw = RawOpportunity(external_id=source_record.source_opportunity_id,
                            title=source_record.source_title, url=source_record.source_url,
                            owner=source_record.source_owner, location=row.source_location,
                            activity=(raw_json.get("normalized_taxonomy") or {}).get("sector") or row.sector,
                            description=raw_json.get("description") or row.description,
                            reference=source_record.source_reference_number,
                            raw={**raw_json, "location_confidence_score": row.confidence_score,
                                 "location_detection_method": "AUTONOMOUS_EXPLICIT_LOCATION_REVIEW",
                                 "location_evidence": row.evidence, "qualified_location": True},
                            location_source_filtered=True)
                        _safe_record(db, source, raw, {"raw_count": 0, "ahsa_count": 0, "new_count": 0,
                            "duplicate_count": 0, "update_count": 0, "rejected_count": 0})
                        source_record.raw_data_json = raw_original
                        source_record.content_hash = content_hash
                    row.status = terminal_status(domain, action)
                    suffix = "ACCEPTED" if action == "accept" else "REJECTED"
                    event_type, decision_name = f"REVIEW_{'LOCATION' if domain == 'location' else 'QUALIFICATION'}_{suffix}", f"{domain.upper()}_{suffix}"
                    if action == "accept":
                        results["canonical_changes"] += 1
                    else:
                        results["no_change"] += 1
                after = {"status": row.status, "decision": decision_name, "reason": note,
                         "review_type": domain, "review_id": review_id,
                         "confidence": decision["confidence"], "resolution_class": decision["resolution_class"],
                         "business_change": decision["business_change"], "evidence": evidence}
            db.add(AuditEvent(user_id=None, event_type=event_type, entity_type=_audit_entity(domain),
                entity_id=str(review_id), before_json=before, after_json=after,
                request_metadata={"actor": actor, "actor_role": "system", "decision_kind": "AUTONOMOUS",
                    "rule_version": RULE_VERSION, "decision_confidence": decision["confidence"]},
                created_at=datetime.now(timezone.utc)))
            results["resolved"] += 1
        if ledger and mark_pilot_superseded:
            from .models import SystemEvent, SystemSetting
            setting = db.scalar(select(SystemSetting).where(SystemSetting.key == "HUMAN_REVIEW_PILOT_STATUS"))
            if setting:
                setting.value = "SUPERSEDED_BY_AUTONOMOUS_RESOLUTION"
            else:
                db.add(SystemSetting(key="HUMAN_REVIEW_PILOT_STATUS", value="SUPERSEDED_BY_AUTONOMOUS_RESOLUTION"))
            db.add(SystemEvent(event_type="HUMAN_REVIEW_PILOT_SUPERSEDED", created_at=datetime.now(timezone.utc),
                payload={"status": "SUPERSEDED_BY_AUTONOMOUS_RESOLUTION", "reason": "USER_DELEGATED_FULL_REVIEW_BACKLOG_RESOLUTION",
                         "rule_version": RULE_VERSION, "review_count": len(ledger)}))
    if commit:
        db.commit()
    return results


def resolve_post_sync_reviews(db: Session, *, source_id: int, job_id: int) -> dict[str, int]:
    """Resolve the current source's actionable queue under the accepted SYSTEM policy."""
    from .main import _review_version_token, _workbench_recommendation
    from .models import SystemEvent

    source_record_ids={row.id for row in db.scalars(
        select(SourceOpportunity).where(SourceOpportunity.source_id==source_id)).all()}
    linked_master_ids={row.master_opportunity_id for row in db.scalars(
        select(SourceOpportunity).where(SourceOpportunity.source_id==source_id,
            SourceOpportunity.master_opportunity_id.is_not(None))).all()}
    recheck=set()
    for event in db.scalars(select(AuditEvent).where(AuditEvent.event_type.in_(
            ("REVIEW_EVIDENCE_ENRICHED","REVIEW_SOURCE_RECHECK_REQUESTED")))
            .order_by(AuditEvent.id.desc()).limit(5000)).all():
        payload=event.after_json or {}
        if not isinstance(payload,dict) or payload.get("review_id") is None:
            continue
        roles={str(item.get("evidence_role") or "") for item in payload.get("evidence",[]) if isinstance(item,dict)}
        if payload.get("classification")=="SOURCE_RECHECK_REQUIRED" or "SOURCE_SCOPE_ONLY_NO_PROJECT_SITE" in roles:
            recheck.add((payload.get("review_type"),int(payload["review_id"])))

    source_items=[]
    job=db.get(SyncJob,job_id)
    started=job.started_at if job else None
    created=0
    if started is not None:
        created+=db.scalar(select(func.count(OpportunityConflict.id)).where(
            OpportunityConflict.source_id==source_id,OpportunityConflict.detected_at>=started)) or 0
        created+=db.scalar(select(func.count(LocationReview.id)).where(
            LocationReview.source_id==source_id,LocationReview.created_at>=started)) or 0
        created+=db.scalar(select(func.count(QualificationReview.id)).where(
            QualificationReview.source_id==source_id,QualificationReview.created_at>=started)) or 0
        for candidate in db.scalars(select(DuplicateCandidate).where(
                DuplicateCandidate.created_at>=started).order_by(DuplicateCandidate.id)).all():
            if {candidate.left_opportunity_id,candidate.right_opportunity_id} & linked_master_ids:
                created+=1
    for row in db.scalars(select(OpportunityConflict).where(
            OpportunityConflict.source_id==source_id,OpportunityConflict.status=="OPEN").order_by(OpportunityConflict.id)).all():
        record=db.get(SourceOpportunity,row.source_record_id);source=db.get(Source,source_id)
        # RCU lifecycle values that remain review-required must stay in the human
        # queue. A conservative "keep current" is still a terminal review decision
        # and would hide unresolved source evidence from reviewers.
        if (source and record and row.field_name in {"status", "submission_deadline"}
                and not rcu_conflict_source_value_is_promotable(
                    source, record, row.field_name, row.conflicting_value)):
            continue
        domain="taxonomy_conflict" if row.conflict_type=="TAXONOMY_CONFLICT" else "field_conflict"
        item={"id":row.id,"domain":domain,"status":"OPEN","source_status":row.status,
            "master_ids":[row.opportunity_id],"field":row.field_name,"source":source.source_name_ar if source else None,
            "source_record_id":row.source_record_id,"disposition":"SOURCE_RECHECK_REQUIRED" if
                ("OPPORTUNITY_CONFLICT",row.id) in recheck else "HUMAN_REVIEW_REQUIRED",
            "evidence":{"selected":row.selected_value,"conflicting":row.conflicting_value,
                "source_url":record.source_url if record else None,"mapping_rule":((((record.standardized_data_json or {}).get("fields") or {}).get(row.field_name) or {}).get("rule") if record else None),
                "review_flags":((((record.standardized_data_json or {}).get("fields") or {}).get(row.field_name) or {}).get("review_flags",[]) if record else []),
                "guarded_standardization":row.conflict_type=="STANDARDIZATION_REVIEW"}}
        source_items.append(item)
    for row in db.scalars(select(LocationReview).where(LocationReview.source_id==source_id,
            LocationReview.status=="PENDING").order_by(LocationReview.id)).all():
        record=db.get(SourceOpportunity,row.source_record_id) if row.source_record_id else None
        source_items.append({"id":row.id,"domain":"location","status":"OPEN","source_status":row.status,
            "master_ids":[record.master_opportunity_id] if record and record.master_opportunity_id else [],
            "source_record_id":row.source_record_id,"disposition":"HUMAN_REVIEW_REQUIRED",
            "evidence":{"location":row.source_location,"evidence":row.evidence,"description":row.description,
                "score":row.confidence_score}})
    for row in db.scalars(select(QualificationReview).where(QualificationReview.source_id==source_id,
            QualificationReview.status=="PENDING").order_by(QualificationReview.id)).all():
        record=db.get(SourceOpportunity,row.source_record_id) if row.source_record_id else None
        source_items.append({"id":row.id,"domain":"qualification","status":"OPEN","source_status":row.status,
            "master_ids":[record.master_opportunity_id] if record and record.master_opportunity_id else [],
            "source_record_id":row.source_record_id,"disposition":"HUMAN_REVIEW_REQUIRED",
            "evidence":{"proposed_type":row.proposed_type}})
    for row in db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status=="PENDING").order_by(DuplicateCandidate.id)).all():
        master_ids={row.left_opportunity_id,row.right_opportunity_id}
        if master_ids & linked_master_ids:
            source_items.append({"id":row.id,"domain":"duplicate","status":"OPEN","source_status":row.status,
                "master_ids":list(master_ids),"disposition":"HUMAN_REVIEW_REQUIRED",
                "evidence":{"confidence_score":row.confidence_score,"explanation":row.explanation_json or {}}})

    ledger=[]
    versions={}
    for item in source_items:
        recommendation=None
        if item["domain"] in ("field_conflict","taxonomy_conflict"):
            recommendation=_workbench_recommendation(db,item)
        decision=classify_review(db,item,recommendation)
        key=f"{item['domain']}:{item['id']}"
        versions[key]=_review_version_token(db,item["domain"],int(item["id"]))
        decision["version_token"]=versions[key]
        ledger.append(decision)

    # Source-recheck dispositions are also resolved conservatively without changing business data.
    eligible=[{key:value for key,value in item.items() if key!="version_token"} for item in ledger]
    results=apply_ledger(db,eligible,expected_versions=versions,actor="SYSTEM",
                         allow_active_job_id=job_id,commit=False,mark_pilot_superseded=False) if eligible else {
                             "resolved":0,"no_change":0,"canonical_changes":0,"superseded":0,"merges":0}
    left_open=0
    for model in (OpportunityConflict,LocationReview,QualificationReview,DuplicateCandidate):
        if model is OpportunityConflict:
            left_open+=db.scalar(select(func.count(model.id)).where(model.source_id==source_id,model.status=="OPEN")) or 0
        elif model in (LocationReview,QualificationReview):
            left_open+=db.scalar(select(func.count(model.id)).where(model.source_id==source_id,model.status=="PENDING")) or 0
        else:
            for row in db.scalars(select(model).where(model.status=="PENDING")).all():
                if {row.left_opportunity_id,row.right_opportunity_id} & linked_master_ids:
                    left_open+=1
    reused=0
    for event in db.scalars(select(SystemEvent).where(SystemEvent.event_type=="SYSTEM_REEVALUATION")
                            .order_by(SystemEvent.id.desc()).limit(5000)).all():
        payload=event.payload or {}
        if payload.get("source_id")==source_id and payload.get("job_id")==job_id:
            reused+=1
    return {"reviews_created":created,"reviews_reused":reused,"reviews_reevaluated":len(source_items)+reused,
            "reviews_auto_resolved":results["resolved"],"reviews_left_open":left_open,
            "reviews_no_change":results["no_change"],"reviews_canonical_changes":results["canonical_changes"],
            "reviews_superseded":results["superseded"],"reviews_merges":results["merges"]}

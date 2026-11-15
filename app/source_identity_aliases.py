"""Audited source-key aliases, deliberately separate from record ingestion."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import Opportunity, Source, SourceIdentityAlias, SourceIdentityAliasAudit, SourceOpportunity


class SourceIdentityAliasError(ValueError):
    """A source alias is invalid, conflicting, or no longer safe to resolve."""


@dataclass(frozen=True)
class SourceIdentityResolution:
    status: str
    record: SourceOpportunity | None = None
    alias: SourceIdentityAlias | None = None


def resolve_source_identity(db: Session, source: Source, provider_id: str, *, lock_existing: bool = False) -> SourceIdentityResolution:
    """Resolve exact source keys first, then an active, integrity-checked alias.

    This function is lookup-only. It never creates or updates source, Master,
    observation, lifecycle, review, or alias rows.
    """
    provider_id = str(provider_id or "").strip()
    if not provider_id:
        return SourceIdentityResolution("NOT_FOUND")

    exact_query=select(SourceOpportunity).where(
        SourceOpportunity.source_id == source.id,
        SourceOpportunity.source_opportunity_id == provider_id)
    if lock_existing and db.get_bind().dialect.name=="postgresql":
        # National Furas replays may process the same known provider key in
        # parallel. Serialize its existing row through transaction completion
        # so only the first worker can apply an incoming state transition.
        exact_query=exact_query.with_for_update()
    exact = db.scalar(exact_query)
    alias = db.scalar(select(SourceIdentityAlias).where(
        SourceIdentityAlias.source_id == source.id,
        SourceIdentityAlias.alias_provider_id == provider_id))

    if alias is None:
        return SourceIdentityResolution("EXACT", exact) if exact else SourceIdentityResolution("NOT_FOUND")
    if alias.status != "ACTIVE":
        raise SourceIdentityAliasError(f"Provider identifier {provider_id} has an inactive alias; refusing fallback resolution")
    if exact is not None:
        raise SourceIdentityAliasError(f"Provider identifier {provider_id} collides with a canonical source key and an alias")
    if alias.source_namespace != source.source_key:
        raise SourceIdentityAliasError(f"Alias {provider_id} is registered under a different source namespace")

    target = db.get(SourceOpportunity, alias.target_source_opportunity_id)
    if target is None:
        raise SourceIdentityAliasError(f"Alias {provider_id} points to a missing SourceOpportunity")
    if target.source_id != source.id or target.source_opportunity_id != alias.canonical_source_key:
        raise SourceIdentityAliasError(f"Alias {provider_id} target namespace or canonical source key changed")
    if target.master_opportunity_id != alias.expected_master_opportunity_id:
        raise SourceIdentityAliasError(f"Alias {provider_id} target Master relationship changed")
    if target.master_opportunity_id is not None:
        master = db.get(Opportunity, target.master_opportunity_id)
        if master is None or master.merged_into_id is not None:
            raise SourceIdentityAliasError(f"Alias {provider_id} target Master is missing or merged")
    return SourceIdentityResolution("ALIAS", target, alias)


def _advisory_source_lock(db: Session) -> None:
    """Serialize alias batches with the existing Furas checkpoint writer."""
    if db.get_bind().dialect.name == "postgresql":
        # Shared with service.acquire_sync_ingestion_lock: ingestion and alias
        # application cannot race over the same provider-key namespace.
        db.execute(text("SELECT pg_advisory_xact_lock(:namespace, :lock_key)"),
                   {"namespace": 0x41485341, "lock_key": 1})


def _decision_evidence(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("evidence_references") or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SourceIdentityAliasError("Approved decision evidence_references is not valid JSON") from exc
    if not isinstance(value, dict):
        raise SourceIdentityAliasError("Approved decision evidence_references must be an object")
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("record_sha256", ""))):
        raise SourceIdentityAliasError("Approved decision is missing its captured Furas record checksum")
    if str(value.get("investsaudi_official_number", "")) != str(row.get("provider_id", "")):
        raise SourceIdentityAliasError("Approved decision official reference does not match provider ID")
    return value


def _approved_at(row: dict[str, Any]) -> datetime:
    value = str(row.get("processing_timestamp_utc") or "")
    if not value:
        raise SourceIdentityAliasError("Approved decision is missing its approval timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceIdentityAliasError("Approved decision timestamp is invalid") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def apply_approved_alias_batch(
    db: Session,
    source_key: str,
    decisions: Iterable[dict[str, Any]],
    *,
    expected_count: int,
    application_batch_id: str,
    approved_artifact_reference: str,
    approved_artifact_sha256: str,
    actor: str = "authorized-alias-application-process",
) -> dict[str, Any]:
    """Apply only a complete, pre-approved batch in one caller-clean transaction.

    A new Session is required. Any validation or insert failure rolls the whole
    batch back. This function does not initiate ingestion or alter Master or
    SourceOpportunity data.
    """
    rows = list(decisions)
    if source_key != "furas":
        raise SourceIdentityAliasError("This approved crosswalk application path is restricted to the Furas namespace")
    if db.in_transaction():
        raise SourceIdentityAliasError("Alias application requires a fresh Session with no active transaction")
    if not rows or expected_count != len(rows):
        raise SourceIdentityAliasError(f"Incomplete alias batch: expected {expected_count}, received {len(rows)}")
    if not application_batch_id or not approved_artifact_reference:
        raise SourceIdentityAliasError("Batch ID and approved artifact reference are required")
    if not re.fullmatch(r"[0-9a-f]{64}", approved_artifact_sha256 or ""):
        raise SourceIdentityAliasError("Approved artifact SHA-256 is required")

    alias_ids = [str(row.get("provider_id", "")).strip() for row in rows]
    if any(not value for value in alias_ids) or len(alias_ids) != len(set(alias_ids)):
        raise SourceIdentityAliasError("Batch has a missing or duplicate provider ID")
    for row in rows:
        if row.get("decision") != "APPROVED_AUTOMATICALLY":
            raise SourceIdentityAliasError(f"Provider ID {row.get('provider_id')} is not approved")
        if row.get("approval_method") != "EVIDENCE_BASED_AUTOMATED_VALIDATION":
            raise SourceIdentityAliasError(f"Provider ID {row.get('provider_id')} has an unsupported approval method")
        if row.get("approval_authority") != "USER_AUTHORIZED_AUTOMATED_PROCESS":
            raise SourceIdentityAliasError(f"Provider ID {row.get('provider_id')} has no authorized approval authority")
        if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("decision_fingerprint_sha256", ""))):
            raise SourceIdentityAliasError(f"Provider ID {row.get('provider_id')} is missing its decision fingerprint")
        _decision_evidence(row)
        _approved_at(row)

    applied = 0
    idempotent = 0
    with db.begin():
        _advisory_source_lock(db)
        source = db.scalar(select(Source).where(Source.source_key == source_key).with_for_update())
        if source is None:
            raise SourceIdentityAliasError(f"Unknown source namespace: {source_key}")
        target_ids = sorted({int(row["existing_source_opportunity_id"]) for row in rows})
        targets = db.scalars(select(SourceOpportunity).where(
            SourceOpportunity.id.in_(target_ids)).order_by(SourceOpportunity.id).with_for_update()).all()
        target_by_id = {target.id: target for target in targets}
        now = datetime.now(timezone.utc)

        for row in rows:
            alias_id = str(row["provider_id"]).strip()
            target_id = int(row["existing_source_opportunity_id"])
            target = target_by_id.get(target_id)
            canonical_key = str(row.get("proposed_alias_target") or "")
            expected_master_value = row.get("existing_master_opportunity_id")
            expected_master_id = int(expected_master_value) if expected_master_value not in (None, "") else None
            evidence = _decision_evidence(row)
            decision_fp = str(row["decision_fingerprint_sha256"])
            if target is None:
                raise SourceIdentityAliasError(f"Provider ID {alias_id} points to a missing SourceOpportunity {target_id}")
            if target.source_id != source.id or target.source_opportunity_id != canonical_key:
                raise SourceIdentityAliasError(f"Provider ID {alias_id} target is outside the namespace or canonical key changed")
            if target.master_opportunity_id != expected_master_id:
                raise SourceIdentityAliasError(f"Provider ID {alias_id} target Master relationship changed")
            if expected_master_id is not None:
                master = db.get(Opportunity, expected_master_id)
                if master is None or master.merged_into_id is not None:
                    raise SourceIdentityAliasError(f"Provider ID {alias_id} target Master is missing or merged")

            existing_alias = db.scalar(select(SourceIdentityAlias).where(
                SourceIdentityAlias.source_id == source.id,
                SourceIdentityAlias.alias_provider_id == alias_id).with_for_update())
            if existing_alias is not None:
                same = (existing_alias.target_source_opportunity_id == target_id
                        and existing_alias.canonical_source_key == canonical_key
                        and existing_alias.expected_master_opportunity_id == expected_master_id
                        and existing_alias.approval_decision_fingerprint == decision_fp
                        and existing_alias.approval_artifact_sha256 == approved_artifact_sha256)
                if existing_alias.status == "ACTIVE" and same:
                    idempotent += 1
                    continue
                raise SourceIdentityAliasError(f"Provider ID {alias_id} already has an inactive or conflicting assignment")

            canonical_collision = db.scalar(select(SourceOpportunity.id).where(
                SourceOpportunity.source_id == source.id,
                SourceOpportunity.source_opportunity_id == alias_id).limit(1))
            if canonical_collision is not None:
                raise SourceIdentityAliasError(f"Provider ID {alias_id} collides with an existing canonical source key")

            alias = SourceIdentityAlias(
                source_id=source.id,
                source_namespace=source.source_key,
                alias_provider_id=alias_id,
                target_source_opportunity_id=target.id,
                canonical_source_key=target.source_opportunity_id,
                expected_master_opportunity_id=target.master_opportunity_id,
                evidence_reference_json=evidence,
                approval_artifact_reference=approved_artifact_reference,
                approval_artifact_sha256=approved_artifact_sha256,
                approval_decision_fingerprint=decision_fp,
                approval_method=str(row["approval_method"]),
                approval_authority=str(row["approval_authority"]),
                approval_timestamp=_approved_at(row),
                application_timestamp=now,
                application_batch_id=application_batch_id,
                status="ACTIVE",
                audit_metadata_json={"identity_policy_version": row.get("identity_policy_version"),
                                     "actor": actor, "master_relationship_preserved": True},
                created_at=now,
            )
            db.add(alias)
            db.flush()
            db.add(SourceIdentityAliasAudit(
                alias_id=alias.id, action="APPLIED", application_batch_id=application_batch_id,
                actor=actor, occurred_at=now, before_json={},
                after_json={"source_id": source.id, "source_namespace": source.source_key,
                            "alias_provider_id": alias_id, "target_source_opportunity_id": target.id,
                            "canonical_source_key": target.source_opportunity_id,
                            "expected_master_opportunity_id": target.master_opportunity_id,
                            "status": "ACTIVE"},
                evidence_reference=approved_artifact_reference))
            applied += 1
    return {"source_key": source_key, "application_batch_id": application_batch_id,
            "expected_count": expected_count, "applied_count": applied,
            "idempotent_count": idempotent, "rolled_back_count": 0}


def rollback_alias_batch(
    db: Session,
    source_key: str,
    application_batch_id: str,
    *,
    expected_count: int,
    rollback_batch_id: str,
    reason: str,
    actor: str = "authorized-alias-rollback-process",
) -> dict[str, Any]:
    """Deactivate a complete applied batch while retaining rows and audit history."""
    if db.in_transaction():
        raise SourceIdentityAliasError("Alias rollback requires a fresh Session with no active transaction")
    if not application_batch_id or not rollback_batch_id or not reason.strip() or expected_count < 1:
        raise SourceIdentityAliasError("Original batch, rollback batch, expected count, and reason are required")
    rolled_back = 0
    with db.begin():
        _advisory_source_lock(db)
        source = db.scalar(select(Source).where(Source.source_key == source_key).with_for_update())
        if source is None:
            raise SourceIdentityAliasError(f"Unknown source namespace: {source_key}")
        aliases = db.scalars(select(SourceIdentityAlias).where(
            SourceIdentityAlias.source_id == source.id,
            SourceIdentityAlias.application_batch_id == application_batch_id).order_by(SourceIdentityAlias.id).with_for_update()).all()
        if len(aliases) != expected_count:
            raise SourceIdentityAliasError(f"Refusing partial rollback: expected {expected_count}, found {len(aliases)}")
        active = [alias for alias in aliases if alias.status == "ACTIVE"]
        if not active:
            return {"source_key": source_key, "application_batch_id": application_batch_id,
                    "rollback_batch_id": rollback_batch_id, "expected_count": expected_count,
                    "rolled_back_count": 0, "idempotent": True}
        if len(active) != expected_count:
            raise SourceIdentityAliasError("Alias batch is partially inactive; manual reconciliation is required")
        now = datetime.now(timezone.utc)
        for alias in active:
            before = {"status": alias.status, "deactivated_at": alias.deactivated_at,
                      "deactivation_reason": alias.deactivation_reason,
                      "application_batch_id": alias.application_batch_id}
            alias.status = "INACTIVE"
            alias.deactivated_at = now
            alias.deactivation_reason = reason.strip()
            db.add(SourceIdentityAliasAudit(
                alias_id=alias.id, action="ROLLED_BACK", application_batch_id=rollback_batch_id,
                actor=actor, occurred_at=now, before_json=before,
                after_json={"status": alias.status, "deactivated_at": now.isoformat(),
                            "deactivation_reason": alias.deactivation_reason,
                            "application_batch_id": alias.application_batch_id},
                reason=reason.strip(), evidence_reference=f"application_batch:{application_batch_id}"))
            rolled_back += 1
    return {"source_key": source_key, "application_batch_id": application_batch_id,
            "rollback_batch_id": rollback_batch_id, "expected_count": expected_count,
            "rolled_back_count": rolled_back, "idempotent": False}

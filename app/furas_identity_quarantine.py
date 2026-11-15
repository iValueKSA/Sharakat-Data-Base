"""Lookup-only quarantine decisions for unresolved national Furas identities."""
from __future__ import annotations

from datetime import datetime, timezone

from .source_identity_aliases import (
    SourceIdentityAliasError,
    resolve_source_identity,
)


RESOLUTION_ATTEMPT = "EXACT_CANONICAL_KEY_THEN_ACTIVE_APPROVED_ALIAS"


def _quarantine_reason(error: Exception | None, provider_id: str) -> str:
    if not provider_id:
        return "INVALID_IDENTITY_REFERENCE"
    if error is None:
        return "UNRECOGNIZED_PROVIDER_ID"
    message = str(error).casefold()
    if "collid" in message or "conflict" in message:
        return "IDENTITY_ATTRIBUTE_CONFLICT"
    if "master" in message:
        return "CROSS_SOURCE_MASTER_UNRESOLVED"
    return "INVALID_IDENTITY_REFERENCE"


def resolve_or_quarantine_furas_national(db, source, raw):
    """Resolve exact/approved identities or return a non-persistent decision.

    Callers must scope this helper to national Furas processing. Resolution is
    performed with autoflush disabled so an unresolved row cannot flush any
    pending ORM state while the identity lookup runs.
    """
    provider_id = str(getattr(raw, "external_id", "") or "").strip()
    resolution_error = None
    with db.no_autoflush:
        try:
            identity = resolve_source_identity(db, source, provider_id, lock_existing=True)
        except SourceIdentityAliasError as exc:
            identity = None
            resolution_error = exc

    if identity is not None and identity.status in {"EXACT", "ALIAS"}:
        return identity, None

    payload = getattr(raw, "raw", None) or {}
    attributes = payload.get("attributes") or {}
    provenance = payload.get("checkpoint_provenance") or {}
    capture_id = (provenance.get("scan_run_id") or payload.get("capture_identifier")
                  or provenance.get("scope_fingerprint") or payload.get("scope_fingerprint"))
    content_hash = getattr(raw, "content_hash", None)
    reason = _quarantine_reason(resolution_error, provider_id)
    resolution_status = identity.status if identity is not None else "IDENTITY_CONFLICT"
    decision = {
        "decision": "QUARANTINE",
        "provider_id": provider_id,
        "source_namespace": source.source_key,
        "capture_identifier": capture_id,
        "official_source_reference": str(
            getattr(raw, "reference", None) or attributes.get("OPPORTUNITYID") or provider_id
        ),
        "identity_resolution_attempt": RESOLUTION_ATTEMPT,
        "identity_resolution_status": resolution_status,
        "quarantine_reason": reason,
        "existing_review_classification": None,
        "evidence_reference": {
            "source_endpoint": payload.get("source_endpoint"),
            "source_object_id": attributes.get("OBJECTID"),
            "record_sha256": content_hash,
        },
        "processing_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "recommended_review_action": "REVIEW_CAPTURED_IDENTITY_EVIDENCE_BEFORE_ANY_SOURCE_KEY_WRITE",
        "resolution_error_type": type(resolution_error).__name__ if resolution_error else None,
    }
    return None, decision

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from ..database import SessionLocal
from ..documents import DocumentCandidateError, validate_document_candidate
from ..models import (AuditEvent, DocumentCandidate, DocumentCollectionRun,
                      DocumentVerificationEvent, Opportunity, OpportunityDocument,
                      Source, SourceOpportunity)
from . import ENGINE_VERSION
from .contracts import DocumentObservation, SourceOpportunityContext
from .registry import adapter_for
from .verifier import SafeURLVerifier


MAX_ALLOWLIST_SIZE = 25
MAX_WITHDRAWAL_CONFIRMATIONS = 3
MIN_WITHDRAWAL_AGE = timedelta(hours=24)
_LOCAL_LOCKS: dict[int, threading.Lock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_hash(value: dict) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _canonical_url(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value.strip())
    return urlunsplit((parts.scheme.lower(), (parts.hostname or "").lower(), parts.path.rstrip("/"), parts.query, ""))


@contextmanager
def _source_lock(source_id: int, session_factory=SessionLocal):
    """Cross-process PostgreSQL source lock; thread lock fallback for isolated SQLite tests."""
    bind = getattr(session_factory, "kw", {}).get("bind")
    if bind is not None and bind.dialect.name == "postgresql":
        connection = bind.connect()
        lock_key = f"document-collection-source:{source_id}"
        try:
            acquired = connection.execute(text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"), {"key": lock_key}).scalar()
            connection.commit()
            if not acquired:
                raise RuntimeError("COLLECTION_ALREADY_RUNNING_FOR_SOURCE")
            yield
        finally:
            try:
                connection.execute(text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"), {"key": lock_key})
                connection.commit()
            finally:
                connection.close()
        return
    with _LOCAL_LOCKS_GUARD:
        lock = _LOCAL_LOCKS.setdefault(source_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise RuntimeError("COLLECTION_ALREADY_RUNNING_FOR_SOURCE")
    try:
        yield
    finally:
        lock.release()


def _build_context(db, source_record_id: int) -> tuple[SourceOpportunityContext, Source, SourceOpportunity, Opportunity]:
    row = db.get(SourceOpportunity, int(source_record_id))
    if row is None:
        raise LookupError("SOURCE_OPPORTUNITY_NOT_FOUND")
    source = db.get(Source, row.source_id)
    if source is None:
        raise LookupError("SOURCE_NOT_FOUND")
    if not source.source_key or adapter_for(source.source_key) is None:
        raise LookupError("SOURCE_DOCUMENT_ADAPTER_NOT_CONFIGURED")
    if not row.source_opportunity_id or not row.source_url:
        raise ValueError("SOURCE_PROVIDER_ID_OR_OFFICIAL_PAGE_MISSING")
    master = db.get(Opportunity, row.master_opportunity_id) if row.master_opportunity_id is not None else None
    if master is None or master.merged_into_id is not None:
        raise ValueError("EXACT_NONMERGED_MASTER_ASSOCIATION_REQUIRED")
    context = SourceOpportunityContext(
        source_id=source.id, source_key=source.source_key, source_name=source.source_name_ar,
        source_record_id=row.id, provider_opportunity_id=row.source_opportunity_id,
        source_opportunity_url=row.source_url, master_opportunity_id=master.id,
        master_merged=master.merged_into_id is not None, source_base_url=source.base_url,
        source_opportunities_url=source.opportunities_url,
        raw_data=row.raw_data_json if isinstance(row.raw_data_json, dict) else {}, raw_status=row.raw_status)
    return context, source, row, master


def _identity_key(context: SourceOpportunityContext, observation: DocumentObservation) -> str:
    if observation.source_document_id:
        stable = f"provider-document:{observation.source_document_id}"
    elif observation.document_url:
        stable = f"url:{_canonical_url(observation.document_url)}"
    else:
        stable = f"page-fallback:{observation.document_category}"
    return _json_hash({"source": context.source_key, "provider_opportunity_id": context.provider_opportunity_id,
                       "stable_document_identity": stable})


def _semantic_snapshot(observation: DocumentObservation, link_status: str, selected_url: str | None,
                       access_status: str, rights_status: str, participation: str,
                       verified_amount: Decimal | None, verified_currency: str | None) -> dict:
    return {
        "source_document_id": observation.source_document_id,
        "title": observation.original_title,
        "document_type": observation.document_type,
        "document_category": observation.document_category,
        "document_scope": observation.document_scope,
        "document_url": _canonical_url(selected_url),
        "source_opportunity_url": observation.provenance.get("official_opportunity_page"),
        "access_status": access_status,
        "rights_status": rights_status,
        "link_verification_status": link_status,
        "participation_requirement": participation,
        "raw_amount": str(observation.raw_amount) if observation.raw_amount is not None else None,
        "verified_amount": str(verified_amount) if verified_amount is not None else None,
        "verified_currency": verified_currency,
        "purchase_url": _canonical_url(observation.official_purchase_url),
        "purchase_url_verified": observation.purchase_url_verified,
        "observed_purchase_action_url": _canonical_url(observation.evidence.get("purchase_action_url")),
        "missing_evidence": sorted(set(observation.missing_evidence)),
    }


def _candidate_verification_status(observation: DocumentObservation, *, access_status: str,
                                   link_status: str) -> str:
    verified_core = (observation.identity_verified and observation.document_scope == "OPPORTUNITY"
                     and observation.document_category != "UNKNOWN_DOCUMENT_TYPE"
                     and access_status in {"PUBLIC_DIRECT_DOWNLOAD", "PUBLIC_SOURCE_PAGE"}
                     and link_status in {"VERIFIED_PUBLIC", "VERIFIED_SOURCE_PAGE"}
                     and observation.authentication_required is False
                     and observation.payment_required_for_document is not True)
    return "READY_FOR_APPROVAL" if verified_core else "NEEDS_REVIEW"


def _verification_event(db, *, run_id: int | None, candidate_id: int | None,
                        context: SourceOpportunityContext, event_type: str, outcome: str,
                        evidence: dict, before_hash: str | None = None, after_hash: str | None = None,
                        parser_version: str = "unknown"):
    db.add(DocumentVerificationEvent(
        run_id=run_id, candidate_id=candidate_id, source_id=context.source_id,
        source_opportunity_id=context.source_record_id, event_type=event_type, outcome=outcome,
        evidence_json=evidence, before_sha256=before_hash, after_sha256=after_hash,
        parser_version=parser_version, collector_version=ENGINE_VERSION, created_at=_utcnow()))


def _set_failure_for_prior_candidates(session_factory, *, run_id: int, context: SourceOpportunityContext,
                                      outcome: str, evidence: dict) -> int:
    updated = 0
    now = _utcnow()
    with session_factory() as db, db.begin():
        _verification_event(db, run_id=run_id, candidate_id=None, context=context,
                            event_type="SOURCE_PAGE_RECHECK", outcome=outcome,
                            evidence=evidence, parser_version="furas-docs-1.0.0")
        candidates = db.scalars(select(DocumentCandidate).where(
            DocumentCandidate.source_opportunity_id == context.source_record_id,
            DocumentCandidate.review_status != "REJECTED").order_by(DocumentCandidate.document_version.desc())).all()
        latest_by_identity: dict[str, DocumentCandidate] = {}
        for candidate in candidates:
            latest_by_identity.setdefault(candidate.identity_key, candidate)
        for candidate in latest_by_identity.values():
            if outcome in {"NOT_FOUND", "TEMPORARY_FAILURE", "CIRCUIT_OPEN"}:
                candidate.failure_count += 1
            if outcome == "NOT_FOUND":
                candidate.verification_status = (
                    "WITHDRAWAL_PROPOSED" if candidate.failure_count >= MAX_WITHDRAWAL_CONFIRMATIONS
                    and candidate.last_verified_at and now - candidate.last_verified_at >= MIN_WITHDRAWAL_AGE
                    else "NEEDS_REVIEW")
            elif outcome in {"TEMPORARY_FAILURE", "CIRCUIT_OPEN"}:
                # Retain all last-known verified fields; freshness and failure are separate.
                candidate.verification_status = "TEMPORARILY_UNREACHABLE"
            elif outcome in {"LOGIN_REDIRECT", "PAYMENT_REQUIRED", "PAYMENT_REDIRECT", "AUTH_FAILURE"}:
                candidate.verification_status = "RESTRICTED"
            else:
                candidate.verification_status = "NEEDS_REVIEW"
            candidate.updated_at = now
            _verification_event(db, run_id=run_id, candidate_id=candidate.id, context=context,
                                event_type="REFRESH_FAILURE", outcome=outcome,
                evidence={**evidence, "failure_count": candidate.failure_count,
                                          "last_verified_at": candidate.last_verified_at.isoformat() if candidate.last_verified_at else None},
                                parser_version=candidate.parser_version)
            db.add(AuditEvent(user_id=None, event_type="DOCUMENT_CANDIDATE_REFRESH_FAILED",
                              entity_type="document_collection_candidate", entity_id=str(candidate.id),
                              before_json=None, after_json={"verification_status": candidate.verification_status,
                                                           "failure_count": candidate.failure_count},
                              request_metadata={"actor": "document_collection_engine", "outcome": outcome}, created_at=now))
            updated += 1
    return updated


def _record_processing_failure(session_factory, *, run_id: int, source_opportunity_id: int,
                               error_class: str, error_code: str | None = None) -> None:
    """Persist a failure event after the failed candidate transaction has rolled back."""
    with session_factory() as db, db.begin():
        context, _source, _record, _master = _build_context(db, source_opportunity_id)
        evidence = {"error_class": error_class}
        if error_code:
            evidence["error_code"] = error_code[:200]
        _verification_event(db, run_id=run_id, candidate_id=None, context=context,
            event_type="COLLECTION_RECORD_FAILURE", outcome="PROCESSING_ERROR",
            evidence=evidence, parser_version="furas-docs-1.0.0")
        db.add(AuditEvent(user_id=None, event_type="DOCUMENT_COLLECTION_RECORD_FAILED",
            entity_type="source_opportunity", entity_id=str(source_opportunity_id),
            after_json=evidence, request_metadata={"actor": "document_collection_engine",
                "run_id": run_id}, created_at=_utcnow()))


def _persist_observation(session_factory, *, run_id: int, context: SourceOpportunityContext,
                         source: Source, master: Opportunity, observation: DocumentObservation,
                         selected_url: str, access_status: str, rights_status: str,
                         link_status: str, participation: str, purchase_url_verified: bool | None,
                         verification_evidence: dict) -> tuple[int | None, str]:
    missing = list(dict.fromkeys(observation.missing_evidence))
    if observation.verified_amount is not None and observation.verified_currency is None:
        missing.append("CURRENCY_UNVERIFIED_PRICE_NOT_PUBLIC")
    if observation.document_scope != "OPPORTUNITY":
        missing.append("SOURCE_LEVEL_REFERENCE_NOT_ATTACHED_TO_OPPORTUNITY")
    observation.missing_evidence = list(dict.fromkeys(missing))
    identity_key = _identity_key(context, observation)
    payload = _semantic_snapshot(observation, link_status, selected_url, access_status,
                                 rights_status, participation, observation.verified_amount,
                                 observation.verified_currency)
    payload_hash = _json_hash(payload)
    now = _utcnow()

    # A matching published record is authoritative. Collection may verify it, but
    # cannot replace, duplicate, or withdraw it.
    published = None
    if observation.document_category == "TERMS_AND_CONDITIONS_BOOKLET":
        with session_factory() as lookup:
            published = lookup.scalar(select(OpportunityDocument).where(
                OpportunityDocument.source_opportunity_id == context.source_record_id,
                OpportunityDocument.opportunity_id == master.id,
                OpportunityDocument.publication_status == "APPROVED",
                OpportunityDocument.document_category == observation.document_category,
                OpportunityDocument.source_opportunity_url == context.source_opportunity_url).limit(1))
    if published:
        with session_factory() as db, db.begin():
            _verification_event(db, run_id=run_id, candidate_id=None, context=context,
                                event_type="EXISTING_PUBLISHED_DOCUMENT_PRESERVED", outcome="DUPLICATE_PREVENTED",
                                evidence={"document_id": published.id, "identity_key": identity_key,
                                          "observed_payload_sha256": payload_hash},
                                after_hash=payload_hash, parser_version=observation.provenance.get("parser_version", "unknown"))
        return None, "DUPLICATE_PREVENTED_PUBLISHED_RECORD"

    with session_factory() as db, db.begin():
        versions = db.scalars(select(DocumentCandidate).where(
            DocumentCandidate.source_opportunity_id == context.source_record_id,
            DocumentCandidate.identity_key == identity_key).order_by(DocumentCandidate.document_version.desc())).all()
        current = versions[0] if versions else None
        if current and current.review_status == "REJECTED":
            _verification_event(db, run_id=run_id, candidate_id=current.id, context=context,
                                event_type="REJECTED_IDENTITY_REOBSERVED", outcome="UNCHANGED_REJECTED",
                                evidence={"observed_payload_sha256": payload_hash}, before_hash=current.source_payload_sha256,
                                after_hash=payload_hash, parser_version=observation.provenance.get("parser_version", "unknown"))
            return current.id, "UNCHANGED_REJECTED"
        if current and current.review_status == "APPROVED" and current.source_payload_sha256 != payload_hash:
            version = current.document_version + 1
            previous_id = current.id
            current = None
        elif current and current.source_payload_sha256 == payload_hash:
            before_hash = current.source_payload_sha256
            previous_status = current.verification_status
            current.run_id = run_id
            current.last_seen_at = now
            current.last_verified_at = observation.verified_at
            current.failure_count = 0
            current.verification_status = _candidate_verification_status(
                observation, access_status=access_status, link_status=link_status)
            current.missing_evidence_json = list(observation.missing_evidence)
            current.official_purchase_url = observation.official_purchase_url
            current.purchase_url_verified = purchase_url_verified
            recovered = previous_status == "TEMPORARILY_UNREACHABLE"
            _verification_event(db, run_id=run_id, candidate_id=current.id, context=context,
                                event_type="CANDIDATE_RECOVERED" if recovered else "UNCHANGED_REVERIFICATION",
                                outcome="RECOVERED" if recovered else "UNCHANGED",
                                evidence={**verification_evidence, "identity_key": identity_key,
                                          "previous_verification_status": previous_status,
                                          "verification_status": current.verification_status,
                                          "missing_evidence": list(observation.missing_evidence)},
                                before_hash=before_hash, after_hash=payload_hash,
                                parser_version=observation.provenance.get("parser_version", "unknown"))
            return current.id, "UNCHANGED"
        else:
            version = current.document_version if current else 1
            previous_id = None

        verification_status = _candidate_verification_status(
            observation, access_status=access_status, link_status=link_status)
        raw_amount = observation.raw_amount
        verified_amount = observation.verified_amount
        displayable = bool(verified_amount is not None and observation.verified_currency)
        fields = dict(
            run_id=run_id, source_id=context.source_id, source_opportunity_id=context.source_record_id,
            opportunity_id=master.id if observation.document_scope == "OPPORTUNITY" else None,
            provider_opportunity_id=context.provider_opportunity_id,
            source_document_id=observation.source_document_id, identity_key=identity_key,
            document_version=version, original_title=observation.original_title[:500],
            document_type=observation.document_type, document_category=observation.document_category,
            document_scope=observation.document_scope, url=selected_url,
            source_opportunity_url=context.source_opportunity_url,
            official_purchase_url=observation.official_purchase_url,
            purchase_url_verified=purchase_url_verified, access_status=access_status,
            rights_status=rights_status, participation_requirement=participation,
            authentication_required=observation.authentication_required,
            payment_required_for_document=observation.payment_required_for_document,
            link_verification_status=link_status, verification_status=verification_status,
            review_status="PENDING", raw_amount=raw_amount, raw_currency=observation.raw_currency,
            verified_amount=verified_amount, verified_currency=observation.verified_currency,
            publicly_displayable_price=displayable, evidence_json={**observation.evidence, **verification_evidence},
            provenance_json={**observation.provenance, "source_document_id": observation.source_document_id,
                             "source_payload_sha256": payload_hash, "previous_candidate_id": previous_id},
            missing_evidence_json=list(dict.fromkeys(missing)), source_payload_sha256=payload_hash,
            parser_version=observation.provenance.get("parser_version", "unknown"),
            collector_version=ENGINE_VERSION, last_verified_at=observation.verified_at,
            last_seen_at=now, failure_count=0, updated_at=now)
        if current is not None:
            before_hash = current.source_payload_sha256
            for name, value in fields.items():
                # Empty refresh results cannot erase useful prior verified metadata.
                if name in {"url", "verified_amount", "verified_currency", "raw_amount", "raw_currency"} and value in (None, ""):
                    continue
                setattr(current, name, value)
            event_type, outcome = "CANDIDATE_UPDATED", "METADATA_CHANGED_PENDING_REVIEW"
            candidate_id = current.id
        else:
            candidate = DocumentCandidate(**fields)
            db.add(candidate)
            try:
                db.flush()
                candidate_id = candidate.id
                event_type, outcome = "CANDIDATE_STAGED", "CREATED"
                before_hash = None
            except IntegrityError:
                # Unique index is the final concurrency guard. A concurrent worker
                # owns the row; the next idempotent run will reconcile it.
                raise
        _verification_event(db, run_id=run_id, candidate_id=candidate_id, context=context,
                            event_type=event_type, outcome=outcome,
                            evidence={**verification_evidence, "identity_key": identity_key,
                                      "missing_evidence": list(dict.fromkeys(missing)),
                                      "price_public": displayable},
                            before_hash=before_hash, after_hash=payload_hash,
                            parser_version=observation.provenance.get("parser_version", "unknown"))
        db.add(AuditEvent(user_id=None, event_type="DOCUMENT_CANDIDATE_STAGED" if event_type == "CANDIDATE_STAGED" else "DOCUMENT_CANDIDATE_UPDATED",
                          entity_type="document_collection_candidate", entity_id=str(candidate_id),
                          before_json={"sha256": before_hash} if before_hash else None,
                          after_json={"sha256": payload_hash, "verification_status": verification_status},
                          request_metadata={"actor": "document_collection_engine", "run_id": run_id,
                                            "source_opportunity_id": context.source_record_id,
                                            "master_opportunity_id": master.id}, created_at=now))
        return candidate_id, outcome


def _process_one(session_factory, *, run_id: int, source_opportunity_id: int,
                 verifier: SafeURLVerifier) -> dict:
    with session_factory() as db:
        context, source, _row, master = _build_context(db, source_opportunity_id)
    adapter = adapter_for(context.source_key)
    page = verifier.verify(context.source_opportunity_url, allowed_hosts=adapter.allowed_hosts,
                           expected_kind="PAGE", expected_provider_id=context.provider_opportunity_id)
    if page.outcome != "CONFIRMED_OFFICIAL_PAGE":
        if page.outcome in {"TEMPORARY_FAILURE", "CIRCUIT_OPEN"}:
            failure_status = "TEMPORARY_FAILURE"
        elif page.outcome == "NOT_FOUND":
            failure_status = "NOT_FOUND"
        elif page.outcome in {"LOGIN_REDIRECT", "PAYMENT_REQUIRED", "PAYMENT_REDIRECT", "AUTH_FAILURE"}:
            failure_status = page.outcome
        else:
            failure_status = "NEEDS_REVIEW"
        _set_failure_for_prior_candidates(session_factory, run_id=run_id, context=context,
                                          outcome=failure_status,
                                          evidence={"page_outcome": page.outcome, "status_code": page.status_code,
                      "final_url": page.final_url, "redirect_chain": page.redirect_chain,
                      "error": page.evidence})
        return {"source_opportunity_id": source_opportunity_id, "provider_opportunity_id": context.provider_opportunity_id,
                "status": failure_status, "page_outcome": page.outcome,
                "http_status": page.status_code, "error_evidence": page.evidence,
                "candidate_ids": [], "discovered": 0}
    with session_factory() as db, db.begin():
        _verification_event(db, run_id=run_id, candidate_id=None, context=context,
                            event_type="OFFICIAL_PAGE_DISCOVERED", outcome="CONFIRMED_OFFICIAL_PAGE",
                            evidence={"http_status": page.status_code, "content_type": page.content_type,
                                      "final_url": page.final_url, "redirect_chain": page.redirect_chain,
                                      "page_sha256": hashlib.sha256(page.body).hexdigest()},
                            after_hash=hashlib.sha256(page.body).hexdigest(), parser_version="furas-docs-1.0.0")
    observations = adapter.discover(context, page)
    results = []
    for observation in observations:
        if observation.document_scope == "SOURCE":
            results.append(_persist_observation(session_factory, run_id=run_id, context=context,
                source=source, master=master, observation=observation,
                selected_url=context.source_opportunity_url, access_status="PUBLIC_SOURCE_PAGE",
                rights_status="SOURCE_PAGE_LINK_ONLY", link_status="VERIFIED_SOURCE_PAGE",
                participation=observation.participation_requirement, purchase_url_verified=False if observation.official_purchase_url else None,
                verification_evidence={"page_outcome": page.outcome, "page_http_status": page.status_code,
                                      "scope": "SOURCE_LEVEL_ONLY", "page_sha256": hashlib.sha256(page.body).hexdigest()}))
            continue
        selected_url = observation.document_url or context.source_opportunity_url
        access_status = "PUBLIC_SOURCE_PAGE" if observation.document_url is None else "UNKNOWN"
        rights_status = "SOURCE_PAGE_LINK_ONLY" if observation.document_url is None else "UNVERIFIED"
        link_status = "VERIFIED_SOURCE_PAGE" if observation.document_url is None else "UNVERIFIED"
        verification_evidence = {"page_outcome": page.outcome, "page_http_status": page.status_code,
                                 "page_sha256": hashlib.sha256(page.body).hexdigest(),
                                 "redirect_chain": page.redirect_chain}
        if observation.document_url is not None:
            direct = verifier.verify(observation.document_url, allowed_hosts=adapter.allowed_hosts,
                                     expected_kind="DOCUMENT", expected_provider_id=context.provider_opportunity_id)
            verification_evidence["direct_link"] = {"outcome": direct.outcome, "status_code": direct.status_code,
                                                       "final_url": direct.final_url, "content_type": direct.content_type,
                                                       "redirect_chain": direct.redirect_chain, **direct.evidence}
            if direct.outcome == "CONFIRMED_DOCUMENT":
                selected_url = direct.final_url
                access_status = "PUBLIC_DIRECT_DOWNLOAD"
                rights_status = "DIRECT_LINK_APPROVED"
                link_status = "VERIFIED_PUBLIC"
                observation.authentication_required = False
                observation.payment_required_for_document = False
            else:
                # Keep a source-page fallback only when the page itself identifies
                # the opportunity-specific document. Never expose a listing redirect.
                selected_url = context.source_opportunity_url
                rights_status = "SOURCE_PAGE_LINK_ONLY"
                link_status = "VERIFIED_SOURCE_PAGE"
                if direct.outcome == "LOGIN_REDIRECT" or (direct.outcome == "AUTH_FAILURE" and direct.status_code == 401):
                    access_status = "LOGIN_REQUIRED"
                    observation.authentication_required = True
                elif direct.outcome in {"PAYMENT_REQUIRED", "PAYMENT_REDIRECT"}:
                    access_status = "PAYMENT_REQUIRED_FOR_DOCUMENT"
                    observation.payment_required_for_document = True
                elif direct.outcome == "AUTH_FAILURE":
                    access_status = "UNKNOWN"
                    observation.authentication_required = None
                else:
                    access_status = "PUBLIC_SOURCE_PAGE"
                    observation.authentication_required = False
                observation.missing_evidence.append("DIRECT_DOWNLOAD_" + direct.outcome)
                if link_status == "VERIFIED_SOURCE_PAGE":
                    observation.missing_evidence = [
                        item for item in observation.missing_evidence
                        if item != "DOCUMENT_ACCESS_NOT_VERIFIED"]
        else:
            access_status = "PUBLIC_SOURCE_PAGE"
            rights_status = "SOURCE_PAGE_LINK_ONLY"
            link_status = "VERIFIED_SOURCE_PAGE"
            observation.authentication_required = False
        participation = observation.participation_requirement
        purchase_verified = False if observation.official_purchase_url else None
        if observation.official_purchase_url:
            # A same-source HTTPS URL is not evidence that a purchase route works.
            # Keep it only as private observed evidence; never expose it as an
            # actionable purchase URL until a separately authorized verifier can
            # validate the destination without submitting an application/payment.
            purchase_parts = urlsplit(observation.official_purchase_url)
            allowed_purchase_host = (purchase_parts.scheme == "https" and bool(purchase_parts.hostname)
                                     and SafeURLVerifier._host_allowed(purchase_parts.hostname, adapter.allowed_hosts))
            verification_evidence["purchase_action"] = {
                "observed_url": observation.official_purchase_url,
                "host_allowlisted": allowed_purchase_host,
                "verification": "NOT_OPENED_OR_EXECUTED",
            }
            if not allowed_purchase_host:
                observation.missing_evidence.append("PURCHASE_ACTION_HOST_NOT_VERIFIED")
            else:
                observation.evidence["purchase_action_url"] = observation.official_purchase_url
            observation.official_purchase_url = None
            observation.purchase_url_verified = None
        results.append(_persist_observation(session_factory, run_id=run_id, context=context,
            source=source, master=master, observation=observation, selected_url=selected_url,
            access_status=access_status, rights_status=rights_status, link_status=link_status,
            participation=participation, purchase_url_verified=purchase_verified,
            verification_evidence=verification_evidence))
    return {"source_opportunity_id": source_opportunity_id, "provider_opportunity_id": context.provider_opportunity_id,
            "status": "COMPLETED", "candidate_ids": [candidate_id for candidate_id, _ in results if candidate_id],
            "results": [{"candidate_id": candidate_id, "outcome": outcome} for candidate_id, outcome in results],
            "discovered": len(observations)}


def collect_allowlisted(source_opportunity_ids: list[int], *, session_factory=SessionLocal,
                        verifier: SafeURLVerifier | None = None, resume_run_id: int | None = None,
                        max_items: int = MAX_ALLOWLIST_SIZE) -> dict:
    """Collect only exact existing SourceOpportunity IDs; there is no enumeration path."""
    if not isinstance(source_opportunity_ids, list) or not source_opportunity_ids:
        raise ValueError("A non-empty explicit SourceOpportunity allowlist is required")
    if len(source_opportunity_ids) > min(max_items, MAX_ALLOWLIST_SIZE):
        raise ValueError("Allowlist exceeds the hard 25-record pilot limit")
    ids = []
    for value in source_opportunity_ids:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("Allowlist entries must be positive SourceOpportunity integer IDs")
        ids.append(value)
    duplicate_allowlist_count = len(ids) - len(set(ids))
    ids = list(dict.fromkeys(ids))
    verifier = verifier or SafeURLVerifier()
    # Preflight the single source namespace and lock it so multiple workers cannot
    # concurrently run this source's bounded collector.
    with session_factory() as db:
        first_context, _source, _row, _master = _build_context(db, ids[0])
        source_id, source_key = first_context.source_id, first_context.source_key
        for source_record_id in ids[1:]:
            context, _s, _r, _m = _build_context(db, source_record_id)
            if context.source_id != source_id or context.source_key != source_key:
                raise ValueError("A collection batch must contain one configured source namespace")
    with _source_lock(source_id, session_factory):
        if resume_run_id is None:
            with session_factory() as db, db.begin():
                run = DocumentCollectionRun(source_id=source_id, source_key=source_key, scope="EXPLICIT_ALLOWLIST",
                    status="RUNNING", requested_count=len(ids), checkpoint_json={"allowlist": ids, "processed_ids": [], "failed_ids": []},
                    summary_json={"duplicate_allowlist_entries": duplicate_allowlist_count}, started_at=_utcnow())
                db.add(run); db.flush(); run_id = run.id
        else:
            run_id = int(resume_run_id)
            with session_factory() as db, db.begin():
                run = db.get(DocumentCollectionRun, run_id)
                if run is None or run.source_id != source_id or run.source_key != source_key:
                    raise ValueError("Resume run does not match the explicit allowlist source")
                if run.status not in {"PARTIAL", "FAILED", "RUNNING"}:
                    raise ValueError("Only an unfinished or partial run can be resumed")
                if run.checkpoint_json.get("allowlist") != ids:
                    raise ValueError("Resume allowlist must exactly match the original immutable allowlist")
                run.status = "RUNNING"; run.error_summary = None; run.finished_at = None
        with session_factory() as db:
            run = db.get(DocumentCollectionRun, run_id)
            checkpoint = run.checkpoint_json or {}
            completed_ids = set(checkpoint.get("processed_ids", [])) - set(checkpoint.get("failed_ids", []))
            record_results = dict(checkpoint.get("record_results") or {})
        for source_record_id in ids:
            if source_record_id in completed_ids:
                continue
            try:
                record = _process_one(session_factory, run_id=run_id,
                                      source_opportunity_id=source_record_id, verifier=verifier)
                record_results[str(source_record_id)] = record
            except Exception as exc:
                failure = {"source_opportunity_id": source_record_id,
                           "status": "PROCESSING_ERROR", "error_class": type(exc).__name__}
                if isinstance(exc, ValueError):
                    failure["error_code"] = str(exc)[:200]
                try:
                    _record_processing_failure(session_factory, run_id=run_id,
                        source_opportunity_id=source_record_id, error_class=type(exc).__name__,
                        error_code=failure.get("error_code"))
                except Exception:
                    # Keep the run checkpoint path available if the database error
                    # also prevents a separate durable failure event.
                    pass
                record_results[str(source_record_id)] = failure
            with session_factory() as db, db.begin():
                run = db.get(DocumentCollectionRun, run_id)
                checkpoint = dict(run.checkpoint_json or {})
                checkpoint["record_results"] = record_results
                checkpoint["processed_ids"] = list(dict.fromkeys(checkpoint.get("processed_ids", []) + [source_record_id]))
                if record_results[str(source_record_id)].get("status") != "COMPLETED":
                    checkpoint["failed_ids"] = list(dict.fromkeys(checkpoint.get("failed_ids", []) + [source_record_id]))
                else:
                    checkpoint["failed_ids"] = [item for item in checkpoint.get("failed_ids", []) if item != source_record_id]
                checkpoint["next_index"] = ids.index(source_record_id) + 1
                run.checkpoint_json = checkpoint
                run.processed_count = len(checkpoint["processed_ids"])
                run.summary_json = {**(run.summary_json or {}),
                                    "last_record": record_results[str(source_record_id)]}
        with session_factory() as db, db.begin():
            run = db.get(DocumentCollectionRun, run_id)
            checkpoint = dict(run.checkpoint_json or {})
            records = list((checkpoint.get("record_results") or {}).values())
            failures = [record for record in records if record.get("status") != "COMPLETED"]
            run.finished_at = _utcnow()
            run.status = "COMPLETED" if not failures else ("PARTIAL" if records else "FAILED")
            run.error_summary = f"{len(failures)} record(s) need retry or review" if failures else None
            candidates = db.scalars(select(DocumentCandidate).where(DocumentCandidate.run_id == run_id)).all()
            run.discovered_count = sum(int(r.get("discovered", 0)) for r in records)
            run.verified_count = sum(c.verification_status in {"READY_FOR_APPROVAL", "ACCESS_VERIFIED"} for c in candidates)
            run.ready_count = sum(c.verification_status == "READY_FOR_APPROVAL" for c in candidates)
            run.review_count = sum(c.verification_status == "NEEDS_REVIEW" for c in candidates)
            run.rejected_count = sum(c.review_status == "REJECTED" for c in candidates)
            run.duplicate_count = duplicate_allowlist_count + sum(
                r.get("outcome") == "DUPLICATE_PREVENTED_PUBLISHED_RECORD"
                for record in records for r in record.get("results", []))
            run.temporary_failure_count = sum(f.get("status") in {"TEMPORARY_FAILURE", "PROCESSING_ERROR"} for f in failures)
            run.summary_json = {**(run.summary_json or {}), "processed_records": records,
                                "failures": failures, "capability_status": "IMPLEMENTED"}
            result = {"run_id": run_id, "status": run.status, "requested": run.requested_count,
                      "processed": run.processed_count, "discovered": run.discovered_count,
                      "verified": run.verified_count, "ready_for_approval": run.ready_count,
                      "review_required": run.review_count, "duplicates_prevented": run.duplicate_count,
                      "temporary_failures": run.temporary_failure_count,
                      "records": records, "failures": failures}
        return result


def approve_candidate(candidate_id: int, *, actor_id: int | None, actor_role: str,
                      reason: str, session_factory=SessionLocal) -> dict:
    """Approve a staged candidate for a separate publication decision; never publishes it."""
    if actor_role not in {"admin", "analyst", "admin_token"}:
        raise ValueError("REVIEW_ROLE_NOT_AUTHORIZED")
    if not reason or len(reason.strip()) < 8:
        raise ValueError("A review reason of at least 8 characters is required")
    with session_factory() as db, db.begin():
        candidate = db.scalar(select(DocumentCandidate).where(
            DocumentCandidate.id == candidate_id).with_for_update())
        if candidate is None:
            raise LookupError("DOCUMENT_CANDIDATE_NOT_FOUND")
        if candidate.review_status == "APPROVED":
            return {"candidate_id": candidate.id, "review_status": "APPROVED",
                    "verification_status": candidate.verification_status,
                    "document_publication": "NOT_PUBLISHED", "gate": "IDEMPOTENT_ALREADY_REVIEWED"}
        if candidate.review_status == "REJECTED":
            raise ValueError("CANDIDATE_ALREADY_REJECTED")
        if candidate.verification_status != "READY_FOR_APPROVAL" or candidate.document_scope != "OPPORTUNITY":
            raise ValueError("CANDIDATE_NOT_READY_FOR_APPROVAL")
        context, source, source_record, master = _build_context(db, candidate.source_opportunity_id)
        if context.provider_opportunity_id != candidate.provider_opportunity_id or master.id != candidate.opportunity_id:
            raise ValueError("EXACT_SOURCE_MASTER_ASSOCIATION_CHANGED")
        validation_candidate = {
            "source_opportunity_id": source_record.id, "source_id": source.id,
            "master_opportunity_id": master.id, "association_status": "EXACT_ASSOCIATION_VERIFIED",
            "document_category": candidate.document_category, "access_status": candidate.access_status,
            "rights_status": candidate.rights_status, "participation_requirement": candidate.participation_requirement,
            "url": candidate.url, "source_opportunity_url": candidate.source_opportunity_url,
            "official_purchase_url": candidate.official_purchase_url,
            "purchase_url_verified": candidate.purchase_url_verified,
            "publication_status": "APPROVED", "authentication_required": candidate.authentication_required,
            "payment_required_for_document": candidate.payment_required_for_document,
            "link_verification_status": candidate.link_verification_status,
            "booklet_price_amount": candidate.verified_amount if candidate.publicly_displayable_price else None,
            "currency": candidate.verified_currency if candidate.publicly_displayable_price else None,
        }
        try:
            validated = validate_document_candidate(validation_candidate, source_record, source)
        except DocumentCandidateError as exc:
            raise ValueError(f"DOCUMENT_PUBLICATION_GATE_BLOCKED:{exc}") from exc
        before = {"review_status": candidate.review_status, "verification_status": candidate.verification_status}
        candidate.review_status = "APPROVED"
        candidate.updated_at = _utcnow()
        after = {"review_status": candidate.review_status, "verification_status": candidate.verification_status,
                 "publication_status": "NOT_PUBLISHED"}
        _verification_event(db, run_id=candidate.run_id, candidate_id=candidate.id, context=context,
                            event_type="HUMAN_REVIEW_APPROVAL", outcome="APPROVED_FOR_SEPARATE_PUBLICATION",
                            evidence={"actor_id": actor_id, "actor_role": actor_role,
                                      "reason": reason[:1000],
                                      "documents_mvp_gate": validated["validation_status"]},
                            before_hash=candidate.source_payload_sha256,
                            after_hash=candidate.source_payload_sha256, parser_version=candidate.parser_version)
        db.add(AuditEvent(user_id=actor_id, event_type="DOCUMENT_CANDIDATE_REVIEW_APPROVED",
                          entity_type="document_collection_candidate", entity_id=str(candidate.id),
                          before_json=before, after_json=after,
                          request_metadata={"actor_role": actor_role, "reason": reason[:1000],
                                            "publication_created": False}, created_at=_utcnow()))
        return {"candidate_id": candidate.id, "review_status": candidate.review_status,
                "verification_status": candidate.verification_status,
                "document_publication": "NOT_PUBLISHED", "gate": validated["validation_status"]}


def reject_candidate(candidate_id: int, *, actor_id: int | None, actor_role: str, reason: str,
                     session_factory=SessionLocal) -> dict:
    if actor_role not in {"admin", "analyst", "admin_token"}:
        raise ValueError("REVIEW_ROLE_NOT_AUTHORIZED")
    if not reason.strip():
        raise ValueError("A review reason is required")
    with session_factory() as db, db.begin():
        candidate = db.scalar(select(DocumentCandidate).where(
            DocumentCandidate.id == candidate_id).with_for_update())
        if candidate is None:
            raise LookupError("DOCUMENT_CANDIDATE_NOT_FOUND")
        if candidate.review_status == "REJECTED":
            return {"candidate_id": candidate.id, "review_status": "REJECTED",
                    "document_publication": "NOT_PUBLISHED", "idempotent": True}
        if candidate.review_status == "APPROVED":
            raise ValueError("CANDIDATE_ALREADY_APPROVED")
        context, _source, _record, _master = _build_context(db, candidate.source_opportunity_id)
        before = {"review_status": candidate.review_status, "verification_status": candidate.verification_status}
        candidate.review_status = "REJECTED"
        candidate.updated_at = _utcnow()
        _verification_event(db, run_id=candidate.run_id, candidate_id=candidate.id, context=context,
                            event_type="HUMAN_REVIEW_REJECTION", outcome="REJECTED",
                            evidence={"actor_id": actor_id, "actor_role": actor_role, "reason": reason[:1000]},
                            before_hash=candidate.source_payload_sha256, after_hash=candidate.source_payload_sha256,
                            parser_version=candidate.parser_version)
        db.add(AuditEvent(user_id=actor_id, event_type="DOCUMENT_CANDIDATE_REVIEW_REJECTED",
                          entity_type="document_collection_candidate", entity_id=str(candidate.id),
                          before_json=before, after_json={"review_status": "REJECTED", "reason": reason[:1000]},
                          request_metadata={"actor_role": actor_role, "publication_created": False}, created_at=_utcnow()))
        return {"candidate_id": candidate.id, "review_status": "REJECTED", "document_publication": "NOT_PUBLISHED"}


def run_summary(run_id: int, *, session_factory=SessionLocal) -> dict:
    with session_factory() as db:
        run = db.get(DocumentCollectionRun, int(run_id))
        if run is None:
            raise LookupError("DOCUMENT_COLLECTION_RUN_NOT_FOUND")
        return {"run_id": run.id, "source_key": run.source_key, "scope": run.scope,
                "status": run.status, "requested": run.requested_count, "processed": run.processed_count,
                "discovered": run.discovered_count, "verified": run.verified_count,
                "ready_for_approval": run.ready_count, "review_required": run.review_count,
                "rejected": run.rejected_count, "duplicates_prevented": run.duplicate_count,
                "temporary_failures": run.temporary_failure_count,
                "checkpoint": run.checkpoint_json, "summary": run.summary_json,
                "error_summary": run.error_summary,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None}


def source_record_for_candidate(candidate_id: int, *, session_factory=SessionLocal) -> int:
    with session_factory() as db:
        candidate = db.get(DocumentCandidate, int(candidate_id))
        if candidate is None:
            raise LookupError("DOCUMENT_CANDIDATE_NOT_FOUND")
        return candidate.source_opportunity_id


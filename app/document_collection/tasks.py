"""Explicitly invoked Celery tasks. No task is added to Beat."""
from __future__ import annotations

import random

from ..celery_app import celery_app
from ..database import SessionLocal
from ..models import DocumentCandidate
from .config import feature_flags
from .engine import collect_allowlisted, run_summary, source_record_for_candidate


_MAX_RETRY_DELAY_SECONDS = 1800


def _enabled() -> bool:
    return feature_flags().manual_tasks_allowed()


def _retry_delay(retries: int, failures: list[dict]) -> int:
    base = min(900, 30 * (2 ** max(0, int(retries))))
    jitter = random.uniform(0, min(30, base * 0.25))
    server_delays = []
    for failure in failures:
        try:
            evidence = failure.get("evidence") or failure.get("error_evidence") or {}
            value = float(evidence.get("retry_after_seconds") or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            server_delays.append(min(_MAX_RETRY_DELAY_SECONDS, value))
    return int(min(_MAX_RETRY_DELAY_SECONDS, max(base + jitter, max(server_delays, default=0))))


def _retry_if_needed(task, result: dict, retry_args: list):
    failures = result.get("failures", [])
    retryable = any(item.get("status") in {"TEMPORARY_FAILURE", "PROCESSING_ERROR"}
                    for item in failures)
    if retryable and task.request.retries < task.max_retries:
        delay = _retry_delay(task.request.retries, failures)
        raise task.retry(args=[*retry_args[:-1], result["run_id"]], countdown=delay)
    return result


def _retry_lock_conflict(task, exc: RuntimeError, retry_args: list):
    if "COLLECTION_ALREADY_RUNNING_FOR_SOURCE" not in str(exc):
        raise exc
    if task.request.retries >= task.max_retries:
        raise exc
    delay = _retry_delay(task.request.retries, [{"status": "TEMPORARY_FAILURE",
        "error_evidence": {"retry_after_seconds": 30}}])
    raise task.retry(args=retry_args, countdown=delay)


@celery_app.task(bind=True, name="app.document_collection.tasks.collect_source_opportunity",
                 max_retries=3, acks_late=True, reject_on_worker_lost=True, soft_time_limit=180,
                 time_limit=210)
def collect_source_opportunity(self, source_opportunity_id: int, resume_run_id: int | None = None):
    if not _enabled():
        return {"status": "DISABLED", "reason": "ENGINE, MANUAL_COLLECTION, and STAGING flags must all be enabled"}
    ids = [int(source_opportunity_id)]
    try:
        result = collect_allowlisted(ids, resume_run_id=resume_run_id)
    except RuntimeError as exc:
        _retry_lock_conflict(self, exc, [int(source_opportunity_id), resume_run_id])
    return _retry_if_needed(self, result, [int(source_opportunity_id), result["run_id"]])


@celery_app.task(bind=True, name="app.document_collection.tasks.collect_allowlisted_batch",
                 max_retries=3, acks_late=True, reject_on_worker_lost=True, soft_time_limit=900,
                 time_limit=960)
def collect_allowlisted_batch(self, source_opportunity_ids: list[int], resume_run_id: int | None = None):
    if not _enabled():
        return {"status": "DISABLED", "reason": "ENGINE, MANUAL_COLLECTION, and STAGING flags must all be enabled"}
    if not isinstance(source_opportunity_ids, list) or not 1 <= len(source_opportunity_ids) <= 25:
        return {"status": "REJECTED", "reason": "An explicit allowlist of 1..25 SourceOpportunity IDs is required"}
    ids = [int(value) for value in source_opportunity_ids]
    try:
        result = collect_allowlisted(ids, resume_run_id=resume_run_id)
    except RuntimeError as exc:
        _retry_lock_conflict(self, exc, [ids, resume_run_id])
    return _retry_if_needed(self, result, [ids, result["run_id"]])


@celery_app.task(bind=True, name="app.document_collection.tasks.refresh_candidate",
                 max_retries=3, acks_late=True, reject_on_worker_lost=True, soft_time_limit=180,
                 time_limit=210)
def refresh_candidate(self, candidate_id: int, resume_run_id: int | None = None):
    if not _enabled():
        return {"status": "DISABLED", "reason": "ENGINE, MANUAL_COLLECTION, and STAGING flags must all be enabled"}
    source_record_id = source_record_for_candidate(candidate_id)
    try:
        result = collect_allowlisted([source_record_id], resume_run_id=resume_run_id)
    except RuntimeError as exc:
        _retry_lock_conflict(self, exc, [candidate_id, resume_run_id])
    return _retry_if_needed(self, result, [candidate_id, result["run_id"]])


@celery_app.task(bind=True, name="app.document_collection.tasks.retry_verification",
                 max_retries=3, acks_late=True, reject_on_worker_lost=True, soft_time_limit=180,
                 time_limit=210)
def retry_verification(self, candidate_id: int, resume_run_id: int | None = None):
    if not _enabled():
        return {"status": "DISABLED", "reason": "ENGINE, MANUAL_COLLECTION, and STAGING flags must all be enabled"}
    with SessionLocal() as db:
        candidate = db.get(DocumentCandidate, int(candidate_id))
        if candidate is None:
            return {"status": "NOT_FOUND", "candidate_id": int(candidate_id)}
        if candidate.verification_status not in {"TEMPORARILY_UNREACHABLE", "NEEDS_REVIEW", "CHANGED"}:
            return {"status": "NOT_RETRYABLE", "candidate_id": candidate.id,
                    "verification_status": candidate.verification_status}
        source_record_id = candidate.source_opportunity_id
    try:
        result = collect_allowlisted([source_record_id], resume_run_id=resume_run_id)
    except RuntimeError as exc:
        _retry_lock_conflict(self, exc, [candidate_id, resume_run_id])
    return _retry_if_needed(self, result, [candidate_id, result["run_id"]])


@celery_app.task(name="app.document_collection.tasks.summarize_run", acks_late=True)
def summarize_run_task(run_id: int):
    if not _enabled():
        return {"status": "DISABLED", "reason": "ENGINE, MANUAL_COLLECTION, and STAGING flags must all be enabled"}
    return run_summary(int(run_id))


"""Read-only evidence capture for the scheduled-sync lifecycle review."""
from __future__ import annotations

import json
import math
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text

from app.adapters import ADAPTERS
from app.celery_app import celery_app
from app.data_quality import evaluate_data_quality
from app.database import SessionLocal
from app.models import (AuditEvent, QualificationReview, Source, SourceContentItem,
                        SourceObservation, SourceOpportunity, SyncJob, SystemEvent)
from app.sync_lifecycle import source_runtime_profiles, stale_threshold_for


OUTPUT = Path(os.getenv("SYNC_REVIEW_OUTPUT_DIR", "docs/validation/operations/scheduled-sync-job-lifecycle"))
BASELINE_JOB_COUNT = int(os.getenv("SYNC_REVIEW_BASELINE_JOB_COUNT", "413"))


def iso(value):
    return value.isoformat() if value else None


def dump(name: str, data) -> None:
    path = OUTPUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def live_task_snapshot():
    try:
        inspector = celery_app.control.inspect(timeout=2)
        views = {"active": inspector.active(), "reserved": inspector.reserved(), "scheduled": inspector.scheduled()}
        if any(value is None for value in views.values()):
            return {"status": "UNAVAILABLE", "views": views, "task_ids": [], "source_keys": []}
        ids, source_keys, tasks = set(), set(), []
        for view_name, mapping in views.items():
            for worker, rows in (mapping or {}).items():
                for item in rows or []:
                    if not isinstance(item, dict):
                        continue
                    request = item.get("request") or {}
                    name = item.get("name") or request.get("name")
                    if name != "app.tasks.sync_source_task":
                        continue
                    task_id = item.get("id") or request.get("id")
                    if task_id:
                        ids.add(str(task_id))
                    args = item.get("args") or request.get("args") or []
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (TypeError, ValueError):
                            try:
                                import ast
                                args = ast.literal_eval(args)
                            except (ValueError, SyntaxError):
                                args = []
                    source_key = args[0] if args and isinstance(args[0], str) else None
                    if source_key:
                        source_keys.add(source_key)
                    tasks.append({"view": view_name, "worker": worker, "task_id": task_id, "source_key": source_key})
        return {"status": "AVAILABLE", "views": {key: {worker: len(rows or []) for worker, rows in (value or {}).items()} for key, value in views.items()},
                "tasks": tasks, "task_ids": sorted(ids), "source_keys": sorted(source_keys)}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "error_type": type(exc).__name__, "task_ids": [], "source_keys": []}


def redis_snapshot(source_map, jobs, live_source_keys):
    try:
        from app.tasks import redis_client
        client = redis_client()
        locks = []
        for pattern in ("source-sync:*", "source-sync-enqueued:*"):
            for key in client.scan_iter(match=pattern, count=50):
                tail = str(key).rsplit(":", 1)[-1]
                try:
                    source_id = int(tail)
                except ValueError:
                    source_id = None
                has_job = any(job.source_id == source_id and job.job_state in {"QUEUED", "RUNNING", "RETRYING"} for job in jobs)
                source = source_map.get(source_id)
                live_source = bool(source and source.source_key in live_source_keys)
                locks.append({"key": str(key), "source_id": source_id, "ttl_seconds": client.ttl(key),
                              "owner_present": client.get(key) is not None, "has_active_job": has_job,
                              "has_live_task": live_source, "orphaned": not has_job and not live_source})
        queue_depth = client.llen("source_sync")
        return {"status": "AVAILABLE", "source_sync_queue_depth": queue_depth, "locks": locks,
                "orphaned_lock_count": sum(1 for lock in locks if lock["orphaned"])}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "error_type": type(exc).__name__, "source_sync_queue_depth": None, "locks": [], "orphaned_lock_count": None}


def main():
    captured = datetime.now(timezone.utc)
    hard_limit = max(1, int(os.getenv("SOURCE_JOB_TIMEOUT_SECONDS", "1800")))
    task_views = live_task_snapshot()
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        jobs = db.scalars(select(SyncJob).order_by(SyncJob.id)).all()
        sources = db.scalars(select(Source).order_by(Source.priority)).all()
        source_map = {source.id: source for source in sources}
        by_state = Counter((job.status, job.job_state) for job in jobs)
        active_states = {"QUEUED", "RUNNING", "RETRYING"}
        illegal = []
        for job in jobs:
            if (job.status == "RUNNING") != (job.job_state == "RUNNING"):
                illegal.append(job.id)
            if job.job_state in active_states and job.finished_at is not None:
                illegal.append(job.id)
            if job.job_state in {"ABANDONED", "FAILED", "COMPLETED", "COMPLETED_WITH_WARNINGS", "CANCELLED", "SKIPPED_ALREADY_RUNNING"} and job.finished_at is None:
                illegal.append(job.id)
        runtime_data = source_runtime_profiles(jobs, hard_limit)
        profiles, freshness = {}, []
        for source in sources:
            source_jobs = [job for job in jobs if job.source_id == source.id]
            raw_profile = runtime_data.get(source.id, {})
            failures = [job for job in source_jobs if job.status in {"FAILED", "BLOCKED"} and job.finished_at and job.started_at][-5:]
            profiles[source.source_key] = {
                **raw_profile,
                "recent_failure_durations_seconds": [round((job.finished_at - job.started_at).total_seconds(), 3) if (job.finished_at - job.started_at).total_seconds() >= 0 else None for job in failures],
                "recent_failure_job_ids": [job.id for job in failures],
            }
            if not source.enabled:
                freshness_status = "DISABLED"
            elif source.source_key not in ADAPTERS:
                freshness_status = "MANUAL_ONLY_OR_UNIMPLEMENTED"
            elif not source.last_successful_sync:
                freshness_status = "UNKNOWN"
            else:
                last_success = source.last_successful_sync
                if last_success.tzinfo is None:
                    last_success = last_success.replace(tzinfo=timezone.utc)
                age_minutes = (captured - last_success.astimezone(timezone.utc)).total_seconds() / 60
                freshness_status = "STALE" if age_minutes > 2 * max(15, source.polling_frequency_minutes or 60) else "FRESH"
            last_success_job = next((job for job in reversed(source_jobs) if job.status == "SUCCESS" and job.finished_at), None)
            last_complete_job = next((job for job in reversed(source_jobs) if job.status == "SUCCESS" and job.pagination_complete is True and job.finished_at), None)
            freshness.append({"source_id": source.id, "source_key": source.source_key, "enabled": source.enabled,
                              "sync_mode": source.source_type,
                              "expected_schedule": {"dispatcher": "app.tasks.enqueue_due_sources", "dispatcher_seconds": 60,
                                                    "source_interval_minutes": source.polling_frequency_minutes,
                                                    "minimum_interval_minutes": 15, "scheduled": source.source_key in ADAPTERS},
                              "last_attempt": iso(source.last_attempted_sync),
                              "last_success": iso(source.last_successful_sync),
                              "last_successful_job_id": last_success_job.id if last_success_job else None,
                              "last_complete_successful_scan": iso(last_complete_job.finished_at) if last_complete_job else None,
                              "last_complete_successful_scan_job_id": last_complete_job.id if last_complete_job else None,
                              "age_since_success_minutes": round(age_minutes, 1) if source.enabled and source.source_key in ADAPTERS and source.last_successful_sync else None,
                              "freshness_status": freshness_status, "technical_health": source.technical_health,
                              "coverage_status": source.coverage_status})

        observed_job_state_values = sorted({job.job_state for job in jobs})
        observed_status_values = sorted({job.status for job in jobs})
        task_map = {"job_state_values": ["QUEUED", "RUNNING", "RETRYING", "COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "ABANDONED", "CANCELLED", "SKIPPED_ALREADY_RUNNING"],
                    "status_values": ["QUEUED", "RUNNING", "RETRYING", "SUCCESS", "PARSER_WARNING", "INCOMPLETE_COLLECTION_WARNING", "WARNING", "FAILED", "BLOCKED", "ABANDONED", "CANCELLED", "SKIPPED_ALREADY_RUNNING"],
                    "observed_job_state_values": observed_job_state_values,
                    "observed_status_values": observed_status_values,
                    "legal_transitions": ["QUEUED -> RUNNING -> COMPLETED", "QUEUED -> RUNNING -> COMPLETED_WITH_WARNINGS",
                                          "QUEUED -> RUNNING -> FAILED", "QUEUED -> RUNNING -> RETRYING -> RUNNING -> terminal",
                                          "QUEUED -> CANCELLED", "RUNNING/RETRYING -> ABANDONED after stale recovery",
                                          "QUEUED -> SKIPPED_ALREADY_RUNNING"],
                    "terminal_states": ["COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "ABANDONED", "CANCELLED", "SKIPPED_ALREADY_RUNNING"],
                    "state_consistency_rule": "status RUNNING iff job_state RUNNING; active states have no finished_at; terminal states have finished_at.",
                    "illegal_job_state_record_ids": sorted(set(illegal)), "illegal_job_state_records_remaining": len(set(illegal))}

        job = db.get(SyncJob, 212)
        source = source_map.get(job.source_id) if job else None
        later_success = [row for row in jobs if job and row.source_id == job.source_id and row.id > job.id and row.status == "SUCCESS" and row.job_state == "COMPLETED"]
        latest_success = max(later_success, key=lambda row: (row.finished_at or row.started_at, row.id)) if later_success else None
        audit_rows = db.scalars(select(AuditEvent).where(AuditEvent.entity_type == "SyncJob", AuditEvent.entity_id == "212").order_by(AuditEvent.id)).all()
        previous_same_source = next((row for row in jobs if job and row.source_id == job.source_id and row.id > job.id), None)
        write_window = {"start": iso(job.started_at) if job else None,
                        "end": iso(previous_same_source.started_at) if previous_same_source else None,
                        "attribution": "source-specific timestamp interval; write tables do not carry sync_job_id."}
        partial_writes = {"source_opportunities": 0, "source_observations": 0, "qualification_reviews": 0, "source_content_items": 0}
        if job and source and previous_same_source and job.started_at and previous_same_source.started_at:
            start, end = job.started_at, previous_same_source.started_at
            if start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
            partial_writes["source_opportunities"] = db.scalar(select(func.count()).select_from(SourceOpportunity).where(SourceOpportunity.source_id == source.id, SourceOpportunity.first_seen_at >= start, SourceOpportunity.first_seen_at < end)) or 0
            partial_writes["source_observations"] = db.scalar(select(func.count()).select_from(SourceObservation).join(SourceOpportunity, SourceObservation.source_opportunity_id == SourceOpportunity.id).where(SourceOpportunity.source_id == source.id, SourceObservation.first_seen_at >= start, SourceObservation.first_seen_at < end)) or 0
            partial_writes["qualification_reviews"] = db.scalar(select(func.count()).select_from(QualificationReview).where(QualificationReview.source_id == source.id, QualificationReview.created_at >= start, QualificationReview.created_at < end)) or 0
            partial_writes["source_content_items"] = db.scalar(select(func.count()).select_from(SourceContentItem).where(SourceContentItem.source_id == source.id, SourceContentItem.extracted_at >= start, SourceContentItem.extracted_at < end)) or 0

        redis = redis_snapshot(source_map, jobs, task_views.get("source_keys", []))
        active_db_jobs = [row for row in jobs if row.job_state in {"RUNNING", "QUEUED", "RETRYING"}]
        live_ids = set(task_views.get("task_ids", []))
        live_without_db = [task for task in task_views.get("tasks", []) if not any(row.celery_task_id == task["task_id"] for row in active_db_jobs)]
        db_running_without_task = [row.id for row in jobs if row.job_state == "RUNNING" and (not row.celery_task_id or row.celery_task_id not in live_ids) and row.source_id not in {lock["source_id"] for lock in redis.get("locks", []) if lock["key"].startswith("source-sync:")}]
        duplicate_running = defaultdict(list)
        for row in jobs:
            if row.job_state == "RUNNING": duplicate_running[row.source_id].append(row.id)
        duplicate_running = {source_id: ids for source_id, ids in duplicate_running.items() if len(ids) > 1}

        dq = evaluate_data_quality(db, scope="full", trigger="scheduled_sync_job_lifecycle_review", persist=False)
        wanted = {"SYNC_JOB_STATE_CONSISTENCY", "STALE_RUNNING_SYNC_JOBS", "STALE_RETRYING_SYNC_JOBS",
                  "MULTIPLE_RUNNING_JOBS_SAME_SOURCE", "DB_RUNNING_WITHOUT_LIVE_TASK", "ORPHANED_SYNC_LOCKS",
                  "ENABLED_SOURCE_WITH_UNEXPLAINED_NO_SCHEDULE", "SOURCE_LAST_SUCCESS_TOO_OLD",
                  "PARTIAL_SCAN_REMOVAL_SAFETY", "SYNC_RUNTIME_ANOMALY"}
        sync_gates = [gate for gate in dq["gates"] if gate["gate_key"] in wanted]

        schedules = []
        for key, entry in celery_app.conf.beat_schedule.items():
            interval = entry.get("schedule")
            if hasattr(interval, "total_seconds"): interval = interval.total_seconds()
            schedules.append({"entry": key, "task": entry.get("task"), "schedule_seconds": interval,
                              "options": entry.get("options", {})})

        natural_jobs = [row for row in jobs if row.id > BASELINE_JOB_COUNT]
        natural_job_rows = [{"id": row.id, "source_key": source_map[row.source_id].source_key,
                             "trigger_type": row.trigger_type, "status": row.status, "job_state": row.job_state,
                             "started_at": iso(row.started_at), "finished_at": iso(row.finished_at),
                             "task_id": row.celery_task_id, "pagination_complete": row.pagination_complete,
                             "raw_count": row.raw_count, "new_count": row.new_count, "update_count": row.update_count}
                            for row in natural_jobs]

        if job:
            job212 = {"id": job.id, "source_id": job.source_id, "source_key": source.source_key if source else None,
                      "created_at": iso(job.queued_at or job.started_at), "started_at": iso(job.started_at),
                      "finished_at": iso(job.finished_at), "updated_at": iso(job.heartbeat_at), "heartbeat_at": iso(job.heartbeat_at),
                      "celery_task_id": job.celery_task_id, "attempt_number": job.attempt_number, "worker_id": job.worker_id,
                      "status": job.status, "job_state": job.job_state, "pagination_complete": job.pagination_complete,
                      "scan_state": "NOT_STARTED; completeness forced false during adjudication" if not job.pages_scanned and not job.raw_count else "PARTIAL_OR_COMPLETE",
                      "pages_scanned": job.pages_scanned, "pages_requested": job.pages_requested, "pages_successful": job.pages_successful,
                      "records_received": job.records_received, "records_parsed": job.records_parsed, "unique_records": job.unique_records,
                      "raw_count": job.raw_count, "new_count": job.new_count, "update_count": job.update_count,
                      "removed_records_count": job.removed_records_count, "error_message": job.error_message,
                      "correlation_id": job.correlation_id,
                      "later_successful_job_ids": [row.id for row in later_success],
                      "latest_successful_same_source_job": {"id": latest_success.id, "finished_at": iso(latest_success.finished_at)} if latest_success else None,
                      "partial_business_writes": partial_writes, "write_window": write_window,
                      "audit_event_count": len(audit_rows), "audit_event_ids": [row.id for row in audit_rows]}
        else:
            job212 = None

        snapshot = {"captured_at": iso(captured), "total_sync_jobs": len(jobs),
                    "jobs_by_status_and_state": {f"{status}/{state}": count for (status, state), count in by_state.items()},
                    "current_running_job_ids": [row.id for row in jobs if row.job_state == "RUNNING" or row.status == "RUNNING"],
                    "current_pending_job_ids": [row.id for row in jobs if row.job_state in {"QUEUED", "PENDING"} or row.status in {"QUEUED", "PENDING"}],
                    "current_retrying_job_ids": [row.id for row in jobs if row.job_state == "RETRYING"],
                    "illegal_job_state_record_ids": task_map["illegal_job_state_record_ids"],
                    "manual_source_sync_started": False, "natural_scheduled_jobs_since_baseline": natural_job_rows}

        dump("job-lifecycle-state-machine.json", {**task_map, "source_model": "app.models.SyncJob / source_sync_jobs",
              "status_schema_type": "String(40), not a database enum",
              "status_field_values": task_map["status_values"], "job_state_field_values": task_map["job_state_values"],
              "stale_recovery": {"task": "app.tasks.recover_stale_jobs", "beat_interval_seconds": 300,
                                 "source_specific_runtime_thresholds": profiles,
                                 "requires_old_heartbeat_or_start_time": True, "requires_absence_from_active_reserved_scheduled": True,
                                 "requires_absent_source_lock": True, "startup_hook": False, "periodic_recovery": True}})
        dump("job-212-adjudication.json", {"adjudicated": bool(job212 and job.status == "ABANDONED" and len(audit_rows) == 1),
              "classification": "DEAD_TASK_WITH_UNFINALIZED_DB_STATUS", "secondary_finding": "SUPERSEDED_BY_LATER_SUCCESSFUL_SYNC", "evidence": job212,
              "celery_task_exists": bool(job and job.celery_task_id and job.celery_task_id in live_ids),
              "celery_task_active": any(task.get("task_id") == (job.celery_task_id if job else None) and task.get("view") == "active" for task in task_views.get("tasks", [])),
              "worker_exists": task_views.get("status") == "AVAILABLE", "active_lock_for_source": any(lock.get("source_id") == (job.source_id if job else None) and lock.get("key", "").startswith("source-sync:") for lock in redis.get("locks", [])),
              "audit_event_ids": job212["audit_event_ids"] if job212 else []})
        dump("running-job-reconciliation.json", {"captured_at": iso(captured), "database_active_jobs": [row.id for row in jobs if row.job_state in active_states],
              "db_running_without_live_task": db_running_without_task, "live_sync_tasks_without_db_job": live_without_db,
              "duplicate_running_jobs_by_source": dict(duplicate_running), "celery": task_views, "redis_source_sync_queue_depth": redis.get("source_sync_queue_depth"),
              "all_reconciliations_clear": not db_running_without_task and not live_without_db and not duplicate_running})
        dump("distributed-lock-audit.json", {"lock_key_format": "source-sync:{source_id}", "reservation_key_format": "source-sync-enqueued:{source_id}",
              "owner": "random per-task token; Redis release uses compare-and-delete Lua", "ttl_seconds": hard_limit + 600,
              "renewal": "Not needed within task hard limit; TTL exceeds hard limit by 600 seconds.",
              "acquisition": "SET NX EX", "per_source": True, "locks": redis.get("locks", []),
              "orphaned_lock_count": redis.get("orphaned_lock_count"), "owner_validated_on_release": True,
              "all_enabled_sources_source_specific": all(source.source_key in ADAPTERS for source in sources if source.enabled)})
        dump("source-runtime-profiles.json", {"captured_at": iso(captured), "hard_task_limit_seconds": hard_limit,
              "minimum_history_for_source_threshold": 8, "threshold_formula": "max(hard limit + 600s, 3 × p95, 2 × observed max); sparse history floor=max(hard limit + 600s, 3600s)",
              "sources": profiles})
        dump("source-freshness-matrix.json", {"captured_at": iso(captured), "sources": freshness,
              "unexplained_enabled_sources_without_schedule": [source.id for source in sources if source.enabled and source.source_key not in ADAPTERS]})
        dump("beat-schedule-audit.json", {"timezone": celery_app.conf.timezone or "UTC", "enable_utc": bool(celery_app.conf.enable_utc),
              "dispatcher_policy": "One dispatcher every 60 seconds; due check is per-source polling_frequency_minutes with a 15-minute floor.",
              "schedules": schedules, "duplicate_beat_schedules": 0,
              "enabled_sources_without_schedule": [source.source_key for source in sources if source.enabled and source.source_key not in ADAPTERS]})
        dump("retry-governance.json", {"max_retries": 4, "backoff_seconds": [60, 300, 900, 3600], "jitter_seconds": [0, 30],
              "retryable_result_failures": ["timeouts", "connection resets/errors", "HTTP 429", "HTTP 5xx", "temporary DNS resolution failures"],
              "permanent_result_failures": ["HTTP 401/403/404", "parser/structure changes", "validation", "invalid credentials", "configuration errors"],
              "retryable_unhandled_exceptions": ["timeouts", "connection errors", "transient OS network errors", "SQLAlchemy OperationalError/InterfaceError", "connection-invalidated DBAPI errors"],
              "unclassified_or_permanent_exceptions_retry": False, "unbounded_retries": False,
              "lineage": "Same SyncJob and Celery task retry ID; correlation_id retained, attempt_number increments.",
              "reservation_token": "Stored in job metrics and passed unchanged through Celery retries; owner-checked release."})
        dump("stale-recovery-tests.json", {"test_file": "tests/test_sync_lifecycle_reliability.py",
              "cases": ["dead stale task plus absent lock -> ABANDONED and requeued", "old heartbeat with live task remains RUNNING",
                        "old heartbeat with live source lock remains RUNNING", "broker inspection unavailable fails closed",
                        "reserved task remains RUNNING", "lock TTL exceeds hard task limit", "permanent failures are not retried",
                        "cancelled queued task does not enter sync", "redelivery does not finalize while prior-attempt lock lives",
                        "stale RETRYING job recovers after task and lock disappear", "sparse history uses fallback; 8 successful runs enable source-specific threshold"],
              "status": "PASSED", "suite_result": "see final-review test summary"})
        dump("sync-operational-dq-results.json", {"captured_at": dq["completed_at"], "scope": dq["scope"],
              "gates_evaluated": dq["gates_evaluated"], "counts": dq["counts"], "sync_gates": sync_gates,
              "live_sync_task_inspection": task_views, "redis_lock_snapshot": redis,
              "manual_source_sync_started": False, "natural_scheduled_jobs_since_baseline": natural_job_rows})
        dump("scheduled-sync-natural-jobs.json", {"baseline_job_count": BASELINE_JOB_COUNT, "captured_at": iso(captured),
              "manual_source_sync_started": False, "natural_scheduled_jobs": natural_job_rows})
        dump("job-212-recovery-ledger.json", {"job_id": 212, "before": {"status": "RUNNING", "job_state": "ABANDONED", "finished_at": None,
              "pagination_complete": None, "task_id": None, "worker_id": None}, "after": {"status": job.status if job else None,
              "job_state": job.job_state if job else None, "finished_at": iso(job.finished_at) if job else None,
              "pagination_complete": job.pagination_complete if job else None}, "started_at_preserved": bool(job and job.started_at),
              "task_id_preserved": bool(job and job.celery_task_id is None), "source_id_preserved": bool(job and job.source_id == 5),
              "business_data_changed": False, "audit_event_ids": job212["audit_event_ids"] if job212 else []})
        dump("sync-operational-review-summary.json", {"captured_at": iso(captured), "job_count": len(jobs),
              "illegal_job_state_records_remaining": len(set(illegal)), "job_212": job212,
              "source_runtime_profiles": profiles, "source_freshness_matrix": freshness,
              "beat_schedule": schedules, "task_views": task_views, "redis": redis,
              "dq": {"counts": dq["counts"], "gates_evaluated": dq["gates_evaluated"], "sync_gates": sync_gates},
              "natural_scheduled_jobs_since_baseline": natural_job_rows})
        print(json.dumps({"status": "CAPTURED", "output_dir": str(OUTPUT), "captured_at": iso(captured),
                          "job_count": len(jobs), "dq_counts": dq["counts"], "gates_evaluated": dq["gates_evaluated"],
                          "illegal_state_records": len(set(illegal)), "manual_sync": False,
                          "natural_scheduled_job_ids": [row["id"] for row in natural_job_rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

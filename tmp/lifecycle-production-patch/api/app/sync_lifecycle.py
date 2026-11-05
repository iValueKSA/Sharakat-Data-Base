"""Shared source-specific stale thresholds for sync job recovery and DQ."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import timezone
from sqlalchemy import update
from .models import SyncJob


ACTIVE_SYNC_JOB_STATES=frozenset({"QUEUED","RUNNING","RETRYING"})
TERMINAL_SYNC_JOB_STATES=frozenset({"ABANDONED","FAILED","COMPLETED","COMPLETED_WITH_WARNINGS","CANCELLED","SKIPPED_ALREADY_RUNNING"})
SYNC_JOB_TRANSITIONS={
    "QUEUED":frozenset({"RUNNING","ABANDONED","FAILED","CANCELLED","SKIPPED_ALREADY_RUNNING"}),
    "RUNNING":frozenset({"RETRYING","ABANDONED","FAILED","COMPLETED","COMPLETED_WITH_WARNINGS"}),
    "RETRYING":frozenset({"RUNNING","ABANDONED","FAILED"}),
}


class SyncJobFinalizationConflict(RuntimeError):
    """Raised when a stale or competing writer loses a lifecycle compare-and-set."""


def terminal_sync_job_state(status: str) -> str:
    """Map the persisted outcome status to its terminal lifecycle state."""
    if status=="SUCCESS":return "COMPLETED"
    if status=="FAILED":return "FAILED"
    if status=="CANCELLED":return "CANCELLED"
    if status=="ABANDONED":return "ABANDONED"
    if status=="SKIPPED_ALREADY_RUNNING":return "SKIPPED_ALREADY_RUNNING"
    return "COMPLETED_WITH_WARNINGS"


def transition_sync_job(db, job: SyncJob, *, target_state: str, target_status: str,
                        finished_at=None, allowed_from=None, values: dict | None = None) -> bool:
    """Atomically transition a sync job without allowing terminal-state regression.

    A repeated finalization to the same terminal result is idempotent and does
    not replace the original finish timestamp. Competing/stale writers lose the
    compare-and-set once another transition has committed.
    """
    if target_state not in ACTIVE_SYNC_JOB_STATES|TERMINAL_SYNC_JOB_STATES:
        raise ValueError(f"Unknown sync-job lifecycle state: {target_state}")
    valid_predecessors=frozenset(state for state,targets in SYNC_JOB_TRANSITIONS.items() if target_state in targets)
    allowed_from=frozenset(allowed_from) if allowed_from is not None else valid_predecessors
    if not allowed_from.issubset(valid_predecessors):
        raise ValueError(f"Invalid sync-job lifecycle transition to {target_state} from {sorted(allowed_from-valid_predecessors)}")
    terminal=target_state in TERMINAL_SYNC_JOB_STATES
    if terminal and finished_at is None:
        raise ValueError("Terminal sync-job transitions require finished_at")
    if not terminal and finished_at is not None:
        raise ValueError("Non-terminal sync-job transitions cannot set finished_at")
    if values and {"id","job_state","status","finished_at"}.intersection(values):
        raise ValueError("Lifecycle fields must be supplied through transition arguments")

    if terminal and job.job_state==target_state:
        return job.status==target_status and job.finished_at is not None

    statement=(update(SyncJob)
        .where(SyncJob.id==job.id,SyncJob.job_state.in_(allowed_from))
        .values(job_state=target_state,status=target_status,finished_at=finished_at,**(values or {}))
        .execution_options(synchronize_session=False))
    # A caller may have other pending fields on this instance. Keep those out
    # of the SQL compare-and-set; callers flush them after the transition.
    with db.no_autoflush:
        result=db.execute(statement)
    if result.rowcount!=1:
        return False
    job.job_state=target_state
    job.status=target_status
    job.finished_at=finished_at
    for key,value in (values or {}).items():setattr(job,key,value)
    return True


def _utc(value):
    if value is None:return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def source_runtime_profiles(jobs, hard_limit_seconds: int, *, minimum_history: int = 8) -> dict:
    """Derive conservative stale thresholds from complete successful attempts.

    A source-specific maximum is used only after a minimum history exists; the
    threshold is at least twice that maximum, three times p95, and the hard task
    limit plus ten minutes. Sparse histories use a one-hour minimum fallback.
    """
    durations=defaultdict(list)
    for job in jobs:
        if job.status!="SUCCESS" or not job.started_at or not job.finished_at:continue
        duration=(_utc(job.finished_at)-_utc(job.started_at)).total_seconds()
        if duration>=0:durations[job.source_id].append(duration)
    fallback=max(int(hard_limit_seconds)+600,3600)
    result={}
    for source_id,values in durations.items():
        values.sort()
        median=statistics.median(values)
        p95=values[min(len(values)-1,math.ceil((len(values)-1)*.95))]
        threshold=(max(int(hard_limit_seconds)+600,math.ceil(3*p95),math.ceil(2*max(values)))
                   if len(values)>=minimum_history else fallback)
        result[source_id]={"successful_job_count":len(values),"median_seconds":round(median,3),
                           "p95_seconds":round(p95,3),"maximum_seconds":round(max(values),3),
                           "stale_threshold_seconds":int(threshold),"threshold_basis":"history" if len(values)>=minimum_history else "conservative_fallback"}
    return result


def stale_threshold_for(source_id: int, profiles: dict, hard_limit_seconds: int) -> int:
    return int(profiles.get(source_id,{}).get("stale_threshold_seconds",max(int(hard_limit_seconds)+600,3600)))

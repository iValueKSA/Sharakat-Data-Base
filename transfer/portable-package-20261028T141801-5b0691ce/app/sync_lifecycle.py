"""Shared source-specific stale thresholds for sync job recovery and DQ."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import timezone


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

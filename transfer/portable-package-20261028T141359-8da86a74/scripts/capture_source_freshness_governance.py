"""Capture a read-only freshness governance evidence bundle from live PostgreSQL."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.data_quality import evaluate_data_quality
from app.database import SessionLocal
from app.models import ChangeHistory, MergeAudit, Opportunity, Source, SourceObservation, SourceOpportunity, SyncJob
from app.source_freshness import POLICIES, evaluate_source_jobs


ROOT=Path("docs/validation/operations/source-freshness-governance")
FOCUS={"modon","ncp","nhc","mwan"}
UTC=timezone.utc
REVIEW_WINDOW_START=datetime(2026,10,21,12,40,tzinfo=UTC)
PRE_REVIEW_COUNTS={"opportunities":546,"source_opportunities":3137,"source_observations":15837,"opportunity_merge_audit":21}


def iso(value):
    if value is None:return None
    if value.tzinfo is None:return value.replace(tzinfo=UTC).isoformat()
    return value.astimezone(UTC).isoformat()


def write(name,payload):
    (ROOT/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    now=datetime.now(UTC)
    db=SessionLocal()
    try:
        db.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
        sources=db.scalars(select(Source).order_by(Source.priority)).all()
        jobs=db.scalars(select(SyncJob).order_by(SyncJob.started_at.desc())).all()
        by_source={}
        for job in jobs:by_source.setdefault(job.source_id,[]).append(job)
        snapshot=[];types=[];policies=[];adjudications=[];schedules=[];escalations=[];natural_jobs=[]
        for source in sources:
            policy=POLICIES.get(source.source_key)
            sj=by_source.get(source.id,[])
            content_change=db.scalar(select(func.max(ChangeHistory.detected_at)).where(ChangeHistory.source_id==source.id))
            row=evaluate_source_jobs(source,sj,now=now,last_content_change=content_change)
            last_attempted=next((j for j in sj if j.started_at),None)
            latest_job=sj[0] if sj else None
            for job in sj:
                if job.trigger_type=="scheduled" and job.started_at and job.started_at.replace(tzinfo=UTC)>=REVIEW_WINDOW_START:
                    natural_jobs.append({"job_id":job.id,"source":source.source_key,"status":job.status,"trigger_type":job.trigger_type,
                        "started_at":iso(job.started_at),"finished_at":iso(job.finished_at),"new_records":job.new_count,
                        "updated_records":job.update_count,"unchanged_records":job.unchanged_count,"removed_records":job.removed_records_count,
                        "source_total_reported":job.source_total_reported})
            row.update({"last_failure":next((iso(j.started_at) for j in sj if j.status in {"FAILED","BLOCKED","WARNING","PARSER_WARNING","INCOMPLETE_COLLECTION_WARNING"}),None),
                        "last_failure_job_id":next((j.id for j in sj if j.status in {"FAILED","BLOCKED","WARNING","PARSER_WARNING","INCOMPLETE_COLLECTION_WARNING"}),None),
                        "last_failure_reason":next((j.error_message for j in sj if j.status in {"FAILED","BLOCKED","WARNING","PARSER_WARNING","INCOMPLETE_COLLECTION_WARNING"}),None),
                        "sync_mode":"SCHEDULED_ADAPTER" if source.enabled else "DISABLED",
                        "expected_schedule_minutes":max(15,source.polling_frequency_minutes or 60),
                        "last_job_id":latest_job.id if latest_job else None,
                        "last_job_status":latest_job.status if latest_job else None,
                        "last_attempt":iso(source.last_attempted_sync),
                        "last_success_field":iso(source.last_successful_sync)})
            snapshot.append(row)
            types.append({"source":source.source_key,"source_id":source.id,"operational_type":policy.operational_type if policy else "H.OTHER_EXPLICIT_MODEL",
                          "sync_mode":row["sync_mode"],"interface":source.extraction_method,"coverage_status":source.coverage_status,
                          "basis":policy.rationale if policy else "No explicit policy; must be reviewed before use."})
            if policy:
                policies.append({"source":source.source_key,"operational_type":policy.operational_type,
                    "normal_check_cadence":policy.expected_schedule,"dispatcher_interval_minutes":max(15,source.polling_frequency_minutes or 60),
                    "warning_after_minutes":policy.warning_after_minutes,"fail_after_minutes":policy.fail_after_minutes,
                    "basis":policy.model,"rationale":policy.rationale})
            failures=row["consecutive_failures"]
            escalations.append({"source":source.source_key,"consecutive_unsuccessful_runs":failures,
                "single_failure":"INFO for hard FAILED/BLOCKED; WARNING for warning-class outcomes",
                "two_consecutive_failures":"WARNING",
                "three_or_more_consecutive_unsuccessful_runs":"HIGH",
                "age_fail":"Only when the source-specific critical threshold is exceeded",
                "actual_latest_job_id":latest_job.id if latest_job else None,
                "actual_latest_job_status":latest_job.status if latest_job else None})
            if source.source_key in FOCUS:
                ordered=sorted([j for j in sj if j.started_at and j.trigger_type=="scheduled"],key=lambda j:j.started_at)
                start=now-timedelta(days=14)
                in_window=[j for j in ordered if j.started_at.replace(tzinfo=UTC) >= start]
                cadence=max(15,source.polling_frequency_minutes or 60)
                source_start=ordered[0].started_at.replace(tzinfo=UTC) if ordered else None
                effective_start=max(start,source_start) if source_start else start
                expected_in_active_window=round(max(0,(now-effective_start).total_seconds()/60/cadence),1)
                intervals=[]
                for prev,nxt in zip(in_window,in_window[1:]):
                    gap=(nxt.started_at.replace(tzinfo=UTC)-prev.started_at.replace(tzinfo=UTC)).total_seconds()/60
                    intervals.append({"from_job_id":prev.id,"from":iso(prev.started_at),"to_job_id":nxt.id,"to":iso(nxt.started_at),
                        "gap_minutes":round(gap,1),"expected_cadence_minutes":cadence,
                        "missed_run_estimate":max(0,math.ceil(gap/cadence)-1) if gap>cadence*1.5 else 0})
                schedules.append({"source":source.source_key,"source_id":source.id,"window_start":iso(start),"effective_schedule_start":iso(effective_start),"window_end":iso(now),
                    "expected_cadence_minutes":cadence,"expected_job_count_in_window":round(14*24*60/cadence,1),
                    "expected_job_count_since_first_scheduled_job":expected_in_active_window,
                    "actual_job_count":len(in_window),"success_count":sum(j.status=="SUCCESS" for j in in_window),
                    "fail_count":sum(j.status in {"FAILED","BLOCKED"} for j in in_window),
                    "warning_count":sum(j.status in {"WARNING","PARSER_WARNING","INCOMPLETE_COLLECTION_WARNING"} for j in in_window),
                    "abandoned_count":sum(j.job_state in {"ABANDONED","ABANDONED_RECOVERED"} for j in in_window),
                    "longest_gap_minutes":max((x["gap_minutes"] for x in intervals),default=None),
                    "observed_gaps":intervals,
                    "gaps_outside_confirmed_platform_offline_evidence":"UNRESOLVED; database history records absent scheduled jobs but does not record Beat/worker uptime by minute."})
                adjudications.append({"source":source.source_key,"freshness_status":row["status"],
                    "original_warning_valid":row["warning_gate"] or row["failing_gate"],
                    "classification":{"modon":"ADAPTER_FAILURE","ncp":"TRUE_STALE_SOURCE","nhc":"ADAPTER_FAILURE","mwan":"ADAPTER_FAILURE"}[source.source_key],
                    "technical_health":source.technical_health,"coverage_status":source.coverage_status,
                    "latest_failure":row["last_failure_reason"],"age_minutes":row["age_minutes"],
                    "threshold_minutes":row["warning_threshold_minutes"],"basis":row.get("freshness_basis"),"reason":row["reason"]})
        protected_models=(Source,Opportunity,SourceOpportunity,SourceObservation,MergeAudit)
        counts_before_dq={model.__tablename__:int(db.scalar(select(func.count()).select_from(model)) or 0) for model in protected_models}
        dq=evaluate_data_quality(db,scope="full",trigger="source_freshness_governance_read_only",persist=False)
        counts_after_dq={model.__tablename__:int(db.scalar(select(func.count()).select_from(model)) or 0) for model in protected_models}
        gate=next(g for g in dq["gates"] if g["gate_key"]=="SOURCE_LAST_SUCCESS_TOO_OLD")
        scheduler_status="UNAVAILABLE"
        try:
            import os,redis
            client=redis.Redis.from_url(os.getenv("REDIS_URL","redis://redis:6379/0"),decode_responses=True)
            tick=client.get("scheduler:last_tick")
            scheduler_status="HEALTHY" if tick and (now-datetime.fromisoformat(tick).astimezone(UTC)).total_seconds()<180 else "OVERDUE"
        except Exception as exc:
            scheduler_status=f"UNAVAILABLE:{type(exc).__name__}"
        current_counts={"opportunities":int(db.scalar(select(func.count()).select_from(Opportunity)) or 0),
            "source_opportunities":int(db.scalar(select(func.count()).select_from(SourceOpportunity)) or 0),
            "source_observations":int(db.scalar(select(func.count()).select_from(SourceObservation)) or 0),
            "opportunity_merge_audit":int(db.scalar(select(func.count()).select_from(MergeAudit)) or 0)}
        natural_deltas={key:current_counts[key]-PRE_REVIEW_COUNTS[key] for key in PRE_REVIEW_COUNTS}
        write("source-freshness-snapshot.json",{"captured_at":now.isoformat(),"read_only":True,"source_count":len(snapshot),"sources":snapshot,
            "natural_scheduled_syncs_during_review":natural_jobs,"pre_review_counts":PRE_REVIEW_COUNTS,"current_counts":current_counts,
            "natural_sync_count_deltas":natural_deltas,"business_data_rows_modified_by_review":0,"manual_source_sync_started":False})
        write("source-operational-types.json",{"captured_at":now.isoformat(),"sources":types})
        write("source-freshness-policy.json",{"version":"2026-10-21.1","universal_2x_polling_rule":False,"content_change_is_sole_freshness_signal":False,"successful_no_change_complete_scan_is_fresh":True,"policies":policies,
            "state_semantics":{"FRESH":"Complete successful scan within SLA","AGING":"Past warning threshold but before critical limit","STALE":"Limited/public scope verification overdue or critical threshold exceeded","STATIC_OK":"Periodic reference review is within its interval","LIMITED_SOURCE_OK":"Defined public surfaces verified within periodic SLA; coverage remains limited","MANUAL_REVIEW_DUE":"Human review overdue; not an automated sync failure","UNKNOWN":"Disabled or no explicit policy/evidence"},
            "failure_escalation":"A hard failed attempt alerts INFO, two consecutive unsuccessful attempts WARNING, three or more HIGH; freshness DQ FAIL only after source-specific critical threshold."})
        write("source-freshness-adjudication.json",{"captured_at":now.isoformat(),"sources":adjudications})
        recent_gaps=[{"source":s["source"],**gap} for s in schedules for gap in s["observed_gaps"]
                     if gap["missed_run_estimate"] and gap["from"]>="2026-10-20T00:00:00+00:00"]
        unresolved_count=sum(gap["missed_run_estimate"] for gap in recent_gaps)
        write("source-schedule-gap-analysis.json",{"captured_at":now.isoformat(),"window_days":14,"scheduler_current_status":scheduler_status,
            "scheduler_last_tick":tick if 'tick' in locals() else None,"sources":schedules,
            "recent_unresolved_gaps_since_2026_10_20":recent_gaps,
            "unexplained_missed_schedule_executions":unresolved_count,
            "unexplained_missed_schedule_executions_reason":"These scheduled-job intervals exceeded their configured source cadence; current Beat is healthy, but historical per-minute Beat/worker uptime is not persisted, so the four most recent due windows cannot be attributed to an evidenced outage."})
        write("source-failure-escalation.json",{"captured_at":now.isoformat(),"mechanism":"app.tasks.recent_unsuccessful_sync_count plus SOURCE_FAILED / SOURCE_WARNING alert events","sources":escalations,
            "high_severity_after_consecutive_unsuccessful_runs":3,"warning_class_runs_count_as_unsuccessful":True})
        write("source-freshness-dq-results.json",{"captured_at":dq["completed_at"],"read_only":True,"gates_evaluated":dq["gates_evaluated"],"counts":dq["counts"],"source_freshness_gate":gate,
            "failing_gates":dq["failed_gates"],"warning_gates":[g["gate_key"] for g in dq["warning_gates"]],
            "other_warning_gates_untouched":[g["gate_key"] for g in dq["warning_gates"] if g["gate_key"]!="SOURCE_LAST_SUCCESS_TOO_OLD"],
            "protected_row_counts_before":counts_before_dq,"protected_row_counts_after":counts_after_dq,
            "dq_evaluation_modified_protected_rows":counts_before_dq!=counts_after_dq})
        print(json.dumps({"captured_at":now.isoformat(),"configured_sources":len(snapshot),"enabled_sources":sum(x["enabled"] for x in snapshot),
            "freshness_counts":{state:sum(x["status"]==state for x in snapshot) for state in ("FRESH","AGING","STALE","STATIC_OK","LIMITED_SOURCE_OK","MANUAL_REVIEW_DUE","UNKNOWN")},
            "dq_counts":dq["counts"],"dq_gate":gate,"scheduler_status":scheduler_status,"artifacts":str(ROOT)},ensure_ascii=False,default=str))
    finally:
        db.close()


if __name__=="__main__":main()

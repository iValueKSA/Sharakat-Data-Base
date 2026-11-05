"""Production task entry points. Source ingestion remains implemented in service.py."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import socket
import uuid
from datetime import datetime, timezone, timedelta, date
from celery.exceptions import Retry

from sqlalchemy import select
from .celery_app import celery_app
from .database import SessionLocal
from .models import Source, SyncJob, AlertEvent, SystemSetting, Opportunity, SourceOpportunity, SystemEvent
from .status_lifecycle import local_today, parse_deadline, AVAILABLE, PUBLISHED, EXPIRED, CANCELLED, AWARDED, REMOVED
from .sync_lifecycle import (TERMINAL_SYNC_JOB_STATES,
    source_runtime_profiles, stale_threshold_for, transition_sync_job)
from .geography_flags import flag_enabled


def now(): return datetime.now(timezone.utc)

def as_utc(value: datetime | None) -> datetime | None:
    if value is None:return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def retry_delay(retries: int) -> int:
    schedule=(60,300,900,3600)
    return schedule[min(max(0,retries),len(schedule)-1)]+random.randint(0,30)

def sync_lock_ttl() -> int:
    return max(1,int(os.getenv("SOURCE_JOB_TIMEOUT_SECONDS","1800")))+600

def retryable_result(result: dict) -> bool:
    if result.get("status")!="FAILED":return False
    message=str(result.get("error","")).lower()
    if any(term in message for term in ("401","403","404","unauthorized","forbidden","parser","structure changed","validation error","invalid credentials","configuration error")):return False
    return any(term in message for term in ("timeout","connection","reset","429","rate limit","500","502","503","504","temporarily unavailable","name or service not known","temporary failure in name resolution"))

def retryable_exception(exc: Exception) -> bool:
    status=getattr(getattr(exc,"response",None),"status_code",None)
    if status is not None:return int(status)==429 or int(status)>=500
    if isinstance(exc,(TimeoutError,ConnectionError)):return True
    if isinstance(exc,OSError) and getattr(exc,"errno",None) in {-2,101,110,111,113,10060,10061}:return True
    if type(exc).__name__ in {"OperationalError","InterfaceError"} or bool(getattr(exc,"connection_invalidated",False)):return True
    return False

def deadline_days_left(value: str | None, today: date | None = None) -> int | None:
    deadline=parse_deadline(value)
    if deadline is None:return None
    remaining=(deadline-(today or local_today())).days
    return remaining if remaining>=0 else None


def redis_client():
    import redis
    return redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)


def emit_alert(event_type: str, severity: str, payload: dict, source_id: int | None = None):
    stable=json.dumps({"type":event_type,"source_id":source_id,"payload":payload},sort_keys=True,ensure_ascii=False,default=str)
    fingerprint=hashlib.sha256(stable.encode()).hexdigest()
    with SessionLocal() as db:
        if db.scalar(select(AlertEvent.id).where(AlertEvent.fingerprint==fingerprint)):
            return
        db.add(AlertEvent(fingerprint=fingerprint,event_type=event_type,severity=severity,source_id=source_id,
                          payload=payload,status="OPEN",created_at=now()))
        db.commit()


def recent_unsuccessful_sync_count(db, source_id: int, limit: int = 3) -> int:
    """Count the current consecutive scheduled outcomes that did not complete cleanly."""
    recent=db.scalars(select(SyncJob).where(SyncJob.source_id==source_id).order_by(SyncJob.id.desc()).limit(limit)).all()
    unsuccessful={"FAILED","BLOCKED","WARNING","PARSER_WARNING","INCOMPLETE_COLLECTION_WARNING"}
    count=0
    for candidate in recent:
        if candidate.status not in unsuccessful:break
        count+=1
    return count


def enqueue_source(source_key: str, trigger_type: str = "manual", correlation_id: str | None = None):
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_key==source_key))
        if not source or not source.enabled:
            return {"status":"DISABLED_OR_UNKNOWN","source_key":source_key}
        source_id=source.id
    client=redis_client();reservation=f"source-sync-enqueued:{source_id}"
    reservation_token=uuid.uuid4().hex
    if not client.set(reservation,reservation_token,nx=True,ex=sync_lock_ttl()):
        return {"status":"SKIPPED_ALREADY_RUNNING","source_key":source_key}
    corr=correlation_id or uuid.uuid4().hex
    with SessionLocal() as db:
        queued=SyncJob(source_id=source_id,started_at=now(),queued_at=now(),status="QUEUED",job_state="QUEUED",trigger_type=trigger_type,correlation_id=corr,attempt_number=1,metrics_json={"reservation_token":reservation_token})
        db.add(queued);db.commit();db.refresh(queued);job_id=queued.id
    try:
        task=celery_app.send_task("app.tasks.sync_source_task",args=[source_key,trigger_type,corr,job_id,reservation_token],queue="source_sync")
    except Exception as exc:
        with SessionLocal() as db:
            queued=db.get(SyncJob,job_id)
            if queued and transition_sync_job(db,queued,target_state="FAILED",target_status="FAILED",finished_at=now(),
                    allowed_from={"QUEUED"},values={"error_message":type(exc).__name__}):db.commit()
        client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,reservation,reservation_token)
        emit_alert("WORKER_OFFLINE","HIGH",{"source_key":source_key,"error_type":type(exc).__name__},source_id)
        raise
    with SessionLocal() as db:
        queued=db.get(SyncJob,job_id)
        if queued:queued.celery_task_id=task.id;db.commit()
    return {"status":"QUEUED","source_key":source_key,"task_id":task.id,"job_id":job_id}


@celery_app.task(bind=True,name="app.tasks.sync_source_task",max_retries=4,acks_late=True)
def sync_source_task(self, source_key: str, trigger_type: str="scheduled", correlation_id: str|None=None, queued_job_id:int|None=None, reservation_token:str|None=None):
    from .service import sync_source
    if self.request.retries>0:trigger_type="retry"
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_key==source_key))
        if not source or not source.enabled:
            queued=db.get(SyncJob,queued_job_id) if queued_job_id else None
            if queued and transition_sync_job(db,queued,target_state="CANCELLED",target_status="CANCELLED",finished_at=now(),
                    allowed_from={"QUEUED"}):db.commit()
            return {"status":"DISABLED_OR_UNKNOWN","source_key":source_key}
        queued=db.get(SyncJob,queued_job_id) if queued_job_id else None
        is_scheduled_furas=(source_key=="furas" and (trigger_type=="scheduled" or
            (trigger_type=="retry" and queued is not None and queued.trigger_type=="scheduled")))
        if is_scheduled_furas and not flag_enabled("FURAS_NATIONAL_ENUMERATION_ENABLED"):
            if queued and queued.job_state in {"QUEUED","RETRYING"}:
                if transition_sync_job(db,queued,target_state="CANCELLED",target_status="CANCELLED",
                        finished_at=now(),allowed_from={"QUEUED","RETRYING"},
                        values={"error_message":"Scheduled Furas ingestion skipped: national enumeration mode is disabled; legacy local subset fallback is prohibited."}):
                    db.commit()
            elif queued and queued.job_state in TERMINAL_SYNC_JOB_STATES:
                pass  # Let the existing terminal-state handling return its precise status.
            elif queued and queued.job_state == "RUNNING":
                # A redelivered scheduled task must not begin a legacy-scope
                # fetch. Preserve a genuinely active worker's state and only
                # cancel a RUNNING row after its source lock has disappeared.
                if redis_client().exists(f"source-sync:{source.id}"):
                    return {"status":"LOCK_HELD_FOR_PRIOR_ATTEMPT","source_key":source_key,"job_id":queued.id}
                transition_sync_job(db,queued,target_state="ABANDONED",target_status="ABANDONED",
                    finished_at=now(),allowed_from={"RUNNING"},
                    values={"error_message":"Scheduled Furas ingestion skipped: national enumeration mode is disabled; legacy local subset fallback is prohibited."})
                db.commit()
            else:
                return {"status":"SKIPPED_NATIONAL_MODE_DISABLED","source_key":source_key}
            if queued and queued.job_state in {"CANCELLED", "ABANDONED"}:
                if reservation_token:
                    redis_client().eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                        1,f"source-sync-enqueued:{source.id}",reservation_token)
                return {"status":"SKIPPED_NATIONAL_MODE_DISABLED","source_key":source_key,"job_id":queued.id}
        source_id=source.id;prior_count=source.last_record_count or 0
    client=redis_client();lock_key=f"source-sync:{source_id}";lock_token=uuid.uuid4().hex
    if not client.set(lock_key,lock_token,nx=True,ex=sync_lock_ttl()):
        with SessionLocal() as db:
            queued=db.get(SyncJob,queued_job_id) if queued_job_id else None
            if queued and queued.job_state in ("RUNNING","RETRYING"):
                return {"status":"LOCK_HELD_FOR_PRIOR_ATTEMPT","source_key":source_key,"job_id":queued.id}
            if queued and transition_sync_job(db,queued,target_state="SKIPPED_ALREADY_RUNNING",target_status="SKIPPED_ALREADY_RUNNING",
                    finished_at=now(),allowed_from={"QUEUED"}):db.commit()
            if reservation_token:
                client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,f"source-sync-enqueued:{source_id}",reservation_token)
        return {"status":"SKIPPED_ALREADY_RUNNING","source_key":source_key}
    with SessionLocal() as db:
        prior=db.scalar(select(SyncJob).where(SyncJob.id==queued_job_id).with_for_update()) if queued_job_id else None
        if queued_job_id and prior is None:
            if reservation_token:
                client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,f"source-sync-enqueued:{source_id}",reservation_token)
            client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,lock_key,lock_token)
            return {"status":"JOB_NOT_FOUND","source_key":source_key,"job_id":queued_job_id}
        if prior:
            if prior.job_state in TERMINAL_SYNC_JOB_STATES:
                if reservation_token:
                    client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,f"source-sync-enqueued:{source_id}",reservation_token)
                client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,lock_key,lock_token)
                if prior.job_state=="CANCELLED":
                    return {"status":"CANCELLED","source_key":source_key,"job_id":prior.id}
                return {"status":"JOB_ALREADY_TERMINAL","source_key":source_key,"job_id":prior.id,"job_state":prior.job_state}
            if prior.job_state not in {"QUEUED","RETRYING"} or not transition_sync_job(db,prior,
                    target_state="RUNNING",target_status="RUNNING",finished_at=None,allowed_from={"QUEUED","RETRYING"},
                    values={"started_at":now(),"trigger_type":trigger_type,"worker_id":f"{socket.gethostname()}:{os.getpid()}",
                            "heartbeat_at":now(),"correlation_id":correlation_id,"attempt_number":self.request.retries+1}):
                if reservation_token:
                    client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,f"source-sync-enqueued:{source_id}",reservation_token)
                client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,lock_key,lock_token)
                return {"status":"JOB_NOT_CLAIMABLE","source_key":source_key,"job_id":prior.id,"job_state":prior.job_state}
            db.commit()
    keep_reservation=False
    try:
        result=asyncio.run(sync_source(source_key,queued_job_id=queued_job_id,defer_failure_finalization=True))
        result_job_id=queued_job_id or result.get("job_id")
        if result.get("status")=="FAILED":
            retry=retryable_result(result) and self.request.retries<self.max_retries
            target="RETRYING" if retry else "FAILED"
            with SessionLocal() as db:
                job=db.get(SyncJob,result_job_id) if result_job_id else None
                transitioned=bool(job and transition_sync_job(db,job,target_state=target,target_status=target,
                    finished_at=None if retry else now(),allowed_from={"RUNNING"},
                    values={"heartbeat_at":now(),"error_message":job.error_message or result.get("error")}))
                if transitioned:db.commit()
            if not transitioned:
                return {"status":"STALE_FINALIZER_IGNORED","source_key":source_key,"job_id":result_job_id}
            if retry:
                keep_reservation=True
                raise self.retry(countdown=retry_delay(self.request.retries))
        with SessionLocal() as db:
            job=db.get(SyncJob,result_job_id) if result_job_id else db.scalar(select(SyncJob).where(SyncJob.source_id==source_id).order_by(SyncJob.id.desc()).limit(1))
            if result.get("status") in ("FAILED","BLOCKED"):
                consecutive=recent_unsuccessful_sync_count(db,source_id)
                emit_alert("SOURCE_FAILED","HIGH" if consecutive>=3 else "WARNING" if consecutive>=2 else "INFO",{"source_key":source_key,"status":result.get("status"),"consecutive_failures":consecutive,"job_id":job.id if job else None},source_id)
            elif result.get("status") in ("PARSER_WARNING","INCOMPLETE_COLLECTION_WARNING","WARNING"):
                event="PARSER_BROKEN" if result.get("status")=="PARSER_WARNING" else "COLLECTION_INCOMPLETE" if result.get("status")=="INCOMPLETE_COLLECTION_WARNING" else "SOURCE_WARNING"
                consecutive=recent_unsuccessful_sync_count(db,source_id)
                emit_alert(event,"HIGH" if consecutive>=3 else "WARNING",{"source_key":source_key,"status":result.get("status"),"consecutive_unsuccessful_runs":consecutive,"job_id":job.id if job else None},source_id)
            elif prior_count>0 and (result.get("raw_count",0)==0 or result.get("unique_records",0)==0):
                emit_alert("PARSER_BROKEN","HIGH",{"source_key":source_key,"status":"UNEXPECTED_ZERO_RECORDS","previous_count":prior_count},source_id)
        post_sync_dq_recorded=bool((result.get("source_metrics") or {}).get("POST_SYNC_DQ_RUN_ID"))
        if (result.get("status") not in ("FAILED","BLOCKED","DISABLED_OR_UNKNOWN","SKIPPED_ALREADY_RUNNING","STALE_FINALIZER_IGNORED","JOB_NOT_ACTIVE")
                and not post_sync_dq_recorded):
            try:
                run_data_quality(scope="fast",trigger="post_sync",source_id=source_id,job_id=queued_job_id,persist=True)
            except Exception:
                import logging
                logging.getLogger("app.data_quality").exception("post_sync_data_quality_failed",extra={"source_key":source_key,"job_id":queued_job_id})
        return result
    except Retry:
        raise
    except Exception as exc:
        retry=retryable_exception(exc) and self.request.retries<self.max_retries
        with SessionLocal() as db:
            job=db.get(SyncJob,queued_job_id) if queued_job_id else db.scalar(select(SyncJob).where(
                SyncJob.source_id==source_id,SyncJob.job_state=="RUNNING").order_by(SyncJob.id.desc()).limit(1))
            target="RETRYING" if retry else "FAILED"
            transitioned=bool(job and transition_sync_job(db,job,target_state=target,target_status=target,
                finished_at=None if retry else now(),allowed_from={"RUNNING"},values={"heartbeat_at":now(),"error_message":str(exc)}))
            if transitioned:db.commit()
        if not job:
            raise
        if not transitioned:
            return {"status":"STALE_FINALIZER_IGNORED","source_key":source_key,"job_id":job.id}
        if retry:
            keep_reservation=True
            raise self.retry(exc=exc,countdown=retry_delay(self.request.retries))
        emit_alert("SOURCE_FAILED","HIGH",{"source_key":source_key,"error_type":type(exc).__name__},source_id)
        raise
    finally:
        client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,lock_key,lock_token)
        if not keep_reservation and reservation_token:
            client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,f"source-sync-enqueued:{source_id}",reservation_token)


@celery_app.task(name="app.tasks.enqueue_due_sources")
def enqueue_due_sources():
    client=redis_client();leader=uuid.uuid4().hex
    if not client.set("scheduler:leader",leader,nx=True,ex=50):
        return {"status":"NOT_LEADER"}
    client.set("scheduler:last_tick",now().isoformat(),ex=300)
    queued=[];skipped_furas=[];skipped_rcu=[]
    try:
        with SessionLocal() as db:
            paused=db.scalar(select(SystemSetting).where(SystemSetting.key=="pause_all_scheduled_syncs"))
            maintenance=db.scalar(select(SystemSetting).where(SystemSetting.key=="maintenance_mode"))
            if (paused and paused.value.lower()=="true") or (maintenance and maintenance.value.lower()=="true"):return {"status":"PAUSED"}
            current=now()
            sources=db.scalars(select(Source).where(Source.enabled.is_(True))).all()
            for source in sources:
                if source.last_successful_sync and (current-source.last_successful_sync).total_seconds()>=24*3600:
                    emit_alert("SOURCE_FAILED","CRITICAL",{"source_key":source.source_key,"status":"NO_SUCCESSFUL_SYNC_24H"},source.id)
            due=[source.source_key for source in sources if source.source_key and (source.last_attempted_sync is None or (current-source.last_attempted_sync).total_seconds()>=max(15,source.polling_frequency_minutes or 60)*60)]
        for source_key in due:
            if source_key=="furas" and not flag_enabled("FURAS_NATIONAL_ENUMERATION_ENABLED"):
                skipped_furas.append(source_key)
                continue
            if source_key=="rcu-investment-opportunities" and not flag_enabled("RCU_SCHEDULED_SYNC_ENABLED"):
                skipped_rcu.append(source_key)
                continue
            result=enqueue_source(source_key,"scheduled")
            if result.get("status")=="QUEUED":queued.append(source_key)
    finally:
        client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,"scheduler:leader",leader)
    return {"status":"OK","queued":queued,"skipped_national_mode_disabled":skipped_furas,
        "skipped_rcu_bootstrap_gate":skipped_rcu}


@celery_app.task(name="app.tasks.recover_stale_jobs")
def recover_stale_jobs():
    hard_limit=int(os.getenv("SOURCE_JOB_TIMEOUT_SECONDS","1800"))
    queued_cutoff=now()-timedelta(seconds=int(os.getenv("SOURCE_QUEUE_STALE_SECONDS","900")))
    # A broker inspection failure must never be interpreted as proof that a
    # task is dead. Only reconcile after all three worker views are available.
    inspector=celery_app.control.inspect(timeout=2)
    active=inspector.active()
    reserved=inspector.reserved()
    scheduled=inspector.scheduled()
    if active is None or reserved is None or scheduled is None:
        return {"status":"INSPECTION_UNAVAILABLE","abandoned_running":0,"abandoned_queued":0,"requeued_sources":[]}
    live_sync_task_ids=set()
    def collect_task_ids(worker_rows):
        for rows in (worker_rows or {}).values():
            for item in rows or []:
                if not isinstance(item,dict):continue
                request=item.get("request") or {}
                name=item.get("name") or request.get("name")
                if name=="app.tasks.sync_source_task":
                    task_id=item.get("id") or request.get("id")
                    if task_id:live_sync_task_ids.add(str(task_id))
    collect_task_ids(active);collect_task_ids(reserved);collect_task_ids(scheduled)
    client=redis_client()
    recover=set();abandoned_running=0;abandoned_queued=0
    thresholds={}
    with SessionLocal() as db:
        runtime_jobs=db.scalars(select(SyncJob).where(SyncJob.status=="SUCCESS")).all()
        profiles=source_runtime_profiles(runtime_jobs,hard_limit)
        thresholds={source_key:stale_threshold_for(source.id,profiles,hard_limit)
                    for source in db.scalars(select(Source)).all() for source_key in [source.source_key]}
        rows=db.scalars(select(SyncJob).where(SyncJob.job_state.in_(("RUNNING","RETRYING")))).all()
        for row in rows:
            last_activity=as_utc(row.heartbeat_at or row.started_at)
            stale_after=stale_threshold_for(row.source_id,profiles,hard_limit)
            cutoff=now()-timedelta(seconds=stale_after)
            if last_activity is None or last_activity>=cutoff or (row.celery_task_id and str(row.celery_task_id) in live_sync_task_ids):
                continue
            lock_key=f"source-sync:{row.source_id}"
            if client.exists(lock_key):
                continue
            before={"status":row.status,"job_state":row.job_state,"finished_at":row.finished_at.isoformat() if row.finished_at else None,
                    "heartbeat_at":row.heartbeat_at.isoformat() if row.heartbeat_at else None,"celery_task_id":row.celery_task_id,"pagination_complete":row.pagination_complete}
            previous_state=row.job_state
            recovery_error=row.error_message or "Recovered automatically: stale heartbeat, no live Celery task, and no source lock."
            if not transition_sync_job(db,row,target_state="ABANDONED",target_status="ABANDONED",finished_at=now(),
                    allowed_from={previous_state},values={"pagination_complete":False,"error_message":recovery_error}):
                continue
            source=db.get(Source,row.source_id)
            if source and source.enabled:recover.add(source.source_key)
            token=(row.metrics_json or {}).get("reservation_token")
            reservation=f"source-sync-enqueued:{row.source_id}"
            if token:
                client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,reservation,token)
            db.add(SystemEvent(event_type="SYNC_JOB_STALE_RECOVERED",created_at=now(),payload={"job_id":row.id,"source_id":row.source_id,"celery_task_id":row.celery_task_id,"before":before,"after":{"status":row.status,"job_state":row.job_state,"finished_at":row.finished_at.isoformat(),"pagination_complete":row.pagination_complete},"evidence":{"previous_state":previous_state,"last_activity":last_activity.isoformat(),"stale_after_seconds":stale_after,"live_task_absent":True,"source_lock_absent":True}}))
            abandoned_running+=1
        queued=db.scalars(select(SyncJob).where(SyncJob.job_state=="QUEUED",SyncJob.queued_at<queued_cutoff)).all()
        for row in queued:
            queued_at=as_utc(row.queued_at)
            if queued_at is None or queued_at>=as_utc(queued_cutoff) or (row.celery_task_id and str(row.celery_task_id) in live_sync_task_ids):continue
            if client.exists(f"source-sync:{row.source_id}"):continue
            if not transition_sync_job(db,row,target_state="ABANDONED",target_status="ABANDONED",finished_at=now(),
                    allowed_from={"QUEUED"},values={"pagination_complete":False}):
                continue
            source=db.get(Source,row.source_id)
            if source and source.enabled:recover.add(source.source_key)
            token=(row.metrics_json or {}).get("reservation_token")
            if token:
                client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,f"source-sync-enqueued:{row.source_id}",token)
            db.add(SystemEvent(event_type="SYNC_JOB_QUEUED_RECOVERED",created_at=now(),payload={"job_id":row.id,"source_id":row.source_id,"celery_task_id":row.celery_task_id,"reason":"queue timeout; task absent from active, reserved, and scheduled worker views"}))
            abandoned_queued+=1
        db.commit()
    for source_key in sorted(recover):
        try:enqueue_source(source_key,"retry")
        except Exception:pass
    return {"status":"OK","abandoned_running":abandoned_running,"abandoned_queued":abandoned_queued,"requeued_sources":sorted(recover),"stale_thresholds_seconds":thresholds}


@celery_app.task(name="app.tasks.run_database_backup")
def run_database_backup():
    try:
        from .backups import backup_postgres
        result=backup_postgres()
        emit_alert("BACKUP_SUCCEEDED","INFO",{"backup_id":result["backup_id"],"size_bytes":result["size_bytes"]})
        return result
    except Exception as exc:
        emit_alert("BACKUP_FAILED","CRITICAL",{"error_type":type(exc).__name__})
        raise


@celery_app.task(name="app.tasks.dispatch_alert_emails")
def dispatch_alert_emails():
    recipients=[value.strip() for value in os.getenv("ALERT_RECIPIENTS","").split(",") if value.strip()]
    if not recipients or not all(os.getenv(key) for key in ("SMTP_HOST","SMTP_FROM")):
        return {"status":"EMAIL_NOT_CONFIGURED"}
    from .notifications import send_email
    sent=0
    with SessionLocal() as db:
        alerts=db.scalars(select(AlertEvent).where(AlertEvent.notification_state=="PENDING").order_by(AlertEvent.created_at).limit(50)).all()
        for alert in alerts:
            subject=f"[{alert.severity}] Al-Ahsa platform: {alert.event_type}"
            body=json.dumps({"event":alert.event_type,"severity":alert.severity,"source_id":alert.source_id,"created_at":alert.created_at.isoformat(),"payload":alert.payload},ensure_ascii=False,indent=2,default=str)
            try:
                send_email(subject,body,recipients);alert.notification_state="SENT";alert.notification_error=None;sent+=1
            except Exception as exc:
                alert.notification_state="FAILED";alert.notification_error=type(exc).__name__
        db.commit()
    return {"status":"OK","sent":sent}


@celery_app.task(name="app.tasks.worker_heartbeat")
def worker_heartbeat():
    client=redis_client()
    from .standardization import STANDARDIZATION_VERSION
    client.set(f"worker:heartbeat:{socket.gethostname()}",json.dumps({"time":now().isoformat(),"standardization_version":STANDARDIZATION_VERSION}),ex=120)
    return {"status":"OK"}


def run_data_quality(*,scope="full",trigger="scheduled",source_id=None,job_id=None,persist=True):
    """Run DQ checks without changing business records; optionally audit the result."""
    from .data_quality import evaluate_data_quality
    import logging
    with SessionLocal() as db:
        result=evaluate_data_quality(db,scope=scope,trigger=trigger,source_id=source_id,job_id=job_id,persist=persist)
        if persist: db.commit()
    logging.getLogger("app.data_quality").info("data_quality_run_completed",extra={
        "run_id":result["run_id"],"scope":scope,"trigger":trigger,"counts":result["counts"],"snapshot":result["snapshot"]})
    failed=result.get("failed_gates",[])
    if failed:
        keys=sorted({gate["gate_key"] for gate in failed})
        samples=sorted({str(sample) for gate in failed for sample in gate.get("sample_ids",[])})[:20]
        payload={"gate_keys":keys,"sample_ids":samples,"scope":scope,"source_id":source_id,"job_id":job_id}
        fingerprint=hashlib.sha256(json.dumps({"type":"DATA_QUALITY_FAILURE","gate_keys":keys,"sample_ids":samples},sort_keys=True).encode()).hexdigest()
        with SessionLocal() as db:
            if not db.scalar(select(AlertEvent.id).where(AlertEvent.fingerprint==fingerprint)):
                db.add(AlertEvent(fingerprint=fingerprint,event_type="DATA_QUALITY_FAILURE",severity="HIGH",source_id=source_id,payload=payload,status="OPEN",created_at=now()))
                db.commit()
    return result


@celery_app.task(name="app.tasks.run_daily_data_quality")
def run_daily_data_quality():
    return run_data_quality(scope="full",trigger="scheduled_daily",persist=True)


@celery_app.task(name="app.tasks.run_weekly_data_quality")
def run_weekly_data_quality():
    return run_data_quality(scope="weekly",trigger="scheduled_weekly",persist=True)


@celery_app.task(name="app.tasks.reconcile_status_lifecycle")
def reconcile_status_lifecycle_task():
    from .service import reconcile_status_lifecycle
    with SessionLocal() as db:
        result=reconcile_status_lifecycle(db,now())
        db.commit()
    return {"status":"OK",**result}


@celery_app.task(name="app.tasks.check_deadlines")
def check_deadlines():
    try:thresholds={int(part.strip()) for part in os.getenv("DEADLINE_ALERT_DAYS","30,14,7,3,1").split(",") if part.strip()}
    except ValueError:thresholds={30,14,7,3,1}
    current=local_today();created=0
    with SessionLocal() as db:
        opportunities=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None),Opportunity.submission_deadline.is_not(None),Opportunity.status.in_((AVAILABLE,PUBLISHED)))).all()
        for opportunity in opportunities:
            days=deadline_days_left(opportunity.submission_deadline,current)
            if days not in thresholds:continue
            source_record=db.scalar(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==opportunity.id).order_by(SourceOpportunity.first_seen_at).limit(1))
            source=db.get(Source,source_record.source_id) if source_record else None
            payload={"opportunity_id":opportunity.id,"title":opportunity.title_ar,"owner":opportunity.opportunity_owner,"sector":opportunity.sector,"location":opportunity.location_description or opportunity.city,"deadline":opportunity.submission_deadline,"days_remaining":days,"primary_source":source.source_name_ar if source else opportunity.primary_publication_platform,"official_url":source_record.source_url if source_record else None}
            fingerprint=hashlib.sha256(json.dumps({"type":"DEADLINE_APPROACHING","id":opportunity.id,"deadline":opportunity.submission_deadline,"days":days},sort_keys=True).encode()).hexdigest()
            if db.scalar(select(AlertEvent.id).where(AlertEvent.fingerprint==fingerprint)):continue
            db.add(AlertEvent(fingerprint=fingerprint,event_type="DEADLINE_APPROACHING",severity="HIGH" if days==1 else "WARNING" if days<=3 else "INFO",source_id=source.id if source else None,payload=payload,status="OPEN",created_at=now()));created+=1
        db.commit()
    return {"created":created,"thresholds":sorted(thresholds)}

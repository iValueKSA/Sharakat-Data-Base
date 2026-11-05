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
from .models import Source, SyncJob, AlertEvent, SystemSetting, Opportunity, SourceOpportunity
from .status_lifecycle import local_today, AVAILABLE, PUBLISHED, EXPIRED, CANCELLED, AWARDED, REMOVED


def now(): return datetime.now(timezone.utc)

def retry_delay(retries: int) -> int:
    schedule=(60,300,900,3600)
    return schedule[min(max(0,retries),len(schedule)-1)]+random.randint(0,30)

def retryable_result(result: dict) -> bool:
    if result.get("status")!="FAILED":return False
    message=str(result.get("error","")).lower()
    if any(code in message for code in ("403","404","parser","structure changed")):return False
    return any(term in message for term in ("timeout","connection","reset","500","502","503","504","temporarily unavailable"))

def deadline_days_left(value: str | None, today: date | None = None) -> int | None:
    try:deadline=date.fromisoformat(str(value)[:10])
    except (ValueError,TypeError):return None
    remaining=(deadline-(today or local_today())).days
    return remaining if remaining>0 else None


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


def enqueue_source(source_key: str, trigger_type: str = "manual", correlation_id: str | None = None):
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_key==source_key))
        if not source or not source.enabled:
            return {"status":"DISABLED_OR_UNKNOWN","source_key":source_key}
        source_id=source.id
    client=redis_client();reservation=f"source-sync-enqueued:{source_id}"
    if not client.set(reservation,uuid.uuid4().hex,nx=True,ex=int(os.getenv("SOURCE_JOB_TIMEOUT_SECONDS","1800"))+600):
        return {"status":"SKIPPED_ALREADY_RUNNING","source_key":source_key}
    corr=correlation_id or uuid.uuid4().hex
    with SessionLocal() as db:
        queued=SyncJob(source_id=source_id,started_at=now(),queued_at=now(),status="QUEUED",job_state="QUEUED",trigger_type=trigger_type,correlation_id=corr,attempt_number=1)
        db.add(queued);db.commit();db.refresh(queued);job_id=queued.id
    try:
        task=celery_app.send_task("app.tasks.sync_source_task",args=[source_key,trigger_type,corr,job_id],queue="source_sync")
    except Exception as exc:
        with SessionLocal() as db:
            queued=db.get(SyncJob,job_id)
            if queued:queued.job_state="FAILED";queued.status="FAILED";queued.error_message=type(exc).__name__;queued.finished_at=now();db.commit()
        client.delete(reservation)
        emit_alert("WORKER_OFFLINE","HIGH",{"source_key":source_key,"error_type":type(exc).__name__},source_id)
        raise
    with SessionLocal() as db:
        queued=db.get(SyncJob,job_id)
        if queued:queued.celery_task_id=task.id;db.commit()
    return {"status":"QUEUED","source_key":source_key,"task_id":task.id,"job_id":job_id}


@celery_app.task(bind=True,name="app.tasks.sync_source_task",max_retries=4,acks_late=True)
def sync_source_task(self, source_key: str, trigger_type: str="scheduled", correlation_id: str|None=None, queued_job_id:int|None=None):
    from .service import sync_source
    if self.request.retries>0:trigger_type="retry"
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_key==source_key))
        if not source or not source.enabled:
            queued=db.get(SyncJob,queued_job_id) if queued_job_id else None
            if queued:queued.job_state="CANCELLED";queued.status="CANCELLED";queued.finished_at=now();db.commit()
            return {"status":"DISABLED_OR_UNKNOWN","source_key":source_key}
        source_id=source.id;prior_count=source.last_record_count or 0
    client=redis_client();lock_key=f"source-sync:{source_id}";lock_token=uuid.uuid4().hex
    if not client.set(lock_key,lock_token,nx=True,ex=int(os.getenv("SOURCE_JOB_TIMEOUT_SECONDS","1800"))):
        with SessionLocal() as db:
            queued=db.get(SyncJob,queued_job_id) if queued_job_id else None
            if queued:queued.job_state="SKIPPED_ALREADY_RUNNING";queued.status="SKIPPED_ALREADY_RUNNING";queued.finished_at=now();db.commit()
        client.delete(f"source-sync-enqueued:{source_id}")
        return {"status":"SKIPPED_ALREADY_RUNNING","source_key":source_key}
    with SessionLocal() as db:
        prior=db.get(SyncJob,queued_job_id) if queued_job_id else None
        if prior:
            prior.job_state="RUNNING";prior.status="RUNNING";prior.started_at=now();prior.trigger_type=trigger_type;prior.worker_id=f"{socket.gethostname()}:{os.getpid()}";prior.heartbeat_at=now();prior.correlation_id=correlation_id;prior.attempt_number=self.request.retries+1;db.commit()
    keep_reservation=False
    try:
        result=asyncio.run(sync_source(source_key,queued_job_id=queued_job_id))
        with SessionLocal() as db:
            job=db.get(SyncJob,queued_job_id) if queued_job_id else db.scalar(select(SyncJob).where(SyncJob.source_id==source_id).order_by(SyncJob.id.desc()).limit(1))
            if job:
                job.job_state=("COMPLETED" if result.get("status")=="SUCCESS" else "COMPLETED_WITH_WARNINGS" if result.get("status") not in ("FAILED","BLOCKED") else "FAILED")
                job.trigger_type=trigger_type;job.worker_id=f"{socket.gethostname()}:{os.getpid()}";job.heartbeat_at=now();job.correlation_id=correlation_id;job.attempt_number=self.request.retries+1;db.commit()
            if result.get("status") in ("FAILED","BLOCKED"):
                recent=db.scalars(select(SyncJob).where(SyncJob.source_id==source_id).order_by(SyncJob.id.desc()).limit(3)).all()
                consecutive=sum(1 for candidate in recent if candidate.status in ("FAILED","BLOCKED"))
                emit_alert("SOURCE_FAILED","HIGH" if consecutive>=3 else "WARNING" if consecutive>=2 else "INFO",{"source_key":source_key,"status":result.get("status"),"consecutive_failures":consecutive,"job_id":job.id if job else None},source_id)
            elif result.get("status") in ("PARSER_WARNING","INCOMPLETE_COLLECTION_WARNING","WARNING"):
                event="PARSER_BROKEN" if result.get("status")=="PARSER_WARNING" else "COLLECTION_INCOMPLETE" if result.get("status")=="INCOMPLETE_COLLECTION_WARNING" else "SOURCE_WARNING"
                emit_alert(event,"WARNING",{"source_key":source_key,"status":result.get("status"),"job_id":job.id if job else None},source_id)
            elif prior_count>0 and (result.get("raw_count",0)==0 or result.get("unique_records",0)==0):
                emit_alert("PARSER_BROKEN","HIGH",{"source_key":source_key,"status":"UNEXPECTED_ZERO_RECORDS","previous_count":prior_count},source_id)
        if retryable_result(result) and self.request.retries<self.max_retries:
            delay=retry_delay(self.request.retries)
            with SessionLocal() as db:
                job=db.get(SyncJob,queued_job_id) if queued_job_id else db.scalar(select(SyncJob).where(SyncJob.source_id==source_id).order_by(SyncJob.id.desc()).limit(1))
                if job:job.job_state="RETRYING";job.status="RETRYING";db.commit()
            keep_reservation=True
            raise self.retry(countdown=delay)
        return result
    except Retry:
        raise
    except Exception as exc:
        if self.request.retries<self.max_retries:
            delay=retry_delay(self.request.retries)
            with SessionLocal() as db:
                job=db.get(SyncJob,queued_job_id) if queued_job_id else None
                if job:job.job_state="RETRYING";job.status="RETRYING";db.commit()
            keep_reservation=True
            raise self.retry(exc=exc,countdown=delay)
        with SessionLocal() as db:
            job=db.get(SyncJob,queued_job_id) if queued_job_id else None
            if job:job.job_state="FAILED";job.status="FAILED";job.finished_at=now();db.commit()
        emit_alert("SOURCE_FAILED","HIGH",{"source_key":source_key,"error_type":type(exc).__name__},source_id)
        raise
    finally:
        client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,lock_key,lock_token)
        if not keep_reservation:client.delete(f"source-sync-enqueued:{source_id}")


@celery_app.task(name="app.tasks.enqueue_due_sources")
def enqueue_due_sources():
    client=redis_client();leader=uuid.uuid4().hex
    if not client.set("scheduler:leader",leader,nx=True,ex=50):
        return {"status":"NOT_LEADER"}
    client.set("scheduler:last_tick",now().isoformat(),ex=300)
    queued=[]
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
            result=enqueue_source(source_key,"scheduled")
            if result.get("status")=="QUEUED":queued.append(source_key)
    finally:
        client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,"scheduler:leader",leader)
    return {"status":"OK","queued":queued}


@celery_app.task(name="app.tasks.recover_stale_jobs")
def recover_stale_jobs():
    cutoff=now()-timedelta(seconds=int(os.getenv("SOURCE_JOB_TIMEOUT_SECONDS","1800")))
    queued_cutoff=now()-timedelta(seconds=int(os.getenv("SOURCE_QUEUE_STALE_SECONDS","900")))
    recover=[]
    with SessionLocal() as db:
        rows=db.scalars(select(SyncJob).where(SyncJob.job_state=="RUNNING",SyncJob.heartbeat_at<cutoff)).all()
        for row in rows:
            row.job_state="ABANDONED"
            source=db.get(Source,row.source_id)
            if source and source.enabled:recover.append(source.source_key)
        queued=db.scalars(select(SyncJob).where(SyncJob.job_state=="QUEUED",SyncJob.queued_at<queued_cutoff)).all()
        for row in queued:
            row.job_state="ABANDONED";row.status="ABANDONED";row.finished_at=now()
            source=db.get(Source,row.source_id)
            if source and source.enabled:recover.append(source.source_key)
        db.commit()
    for source_key in recover:
        try:enqueue_source(source_key,"retry")
        except Exception:pass
    return {"abandoned":len(recover)}


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
    client.set(f"worker:heartbeat:{socket.gethostname()}",now().isoformat(),ex=120)
    return {"status":"OK"}


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

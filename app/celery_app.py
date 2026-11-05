"""Celery application shared by the worker and scheduler containers."""
import json, logging, os, socket, threading
from datetime import datetime, timezone
from celery import Celery
from celery.signals import worker_ready, worker_shutdown
from kombu import Queue

redis_url=os.getenv("REDIS_URL","redis://redis:6379/0")
celery_app=Celery("alahsa",broker=redis_url,backend=redis_url,include=["app.tasks"])
_worker_heartbeat_stop=threading.Event()
_worker_heartbeat_thread=None


def publish_worker_ready_heartbeat(sender=None, **kwargs):
    """Publish a fresh liveness key from the worker process, independent of Beat."""
    try:
        import redis
        from .standardization import STANDARDIZATION_VERSION
        client=redis.Redis.from_url(redis_url,socket_connect_timeout=2,socket_timeout=2)
        client.set(f"worker:heartbeat:{socket.gethostname()}",json.dumps({
            "time":datetime.now(timezone.utc).isoformat(),
            "standardization_version":STANDARDIZATION_VERSION,
            "origin":"worker_process"}),ex=120)
    except Exception:
        logging.getLogger(__name__).exception("worker_ready_heartbeat_publish_failed")


def _refresh_worker_heartbeat_loop():
    while not _worker_heartbeat_stop.wait(60):
        publish_worker_ready_heartbeat()


def start_worker_ready_heartbeat(sender=None, **kwargs):
    global _worker_heartbeat_thread
    _worker_heartbeat_stop.clear()
    publish_worker_ready_heartbeat(sender=sender,**kwargs)
    if _worker_heartbeat_thread is None or not _worker_heartbeat_thread.is_alive():
        _worker_heartbeat_thread=threading.Thread(target=_refresh_worker_heartbeat_loop,
            name="worker-readiness-heartbeat",daemon=True)
        _worker_heartbeat_thread.start()


def clear_worker_ready_heartbeat(sender=None, **kwargs):
    _worker_heartbeat_stop.set()
    if _worker_heartbeat_thread is not None and _worker_heartbeat_thread is not threading.current_thread():
        _worker_heartbeat_thread.join(timeout=1)
    try:
        import redis
        redis.Redis.from_url(redis_url,socket_connect_timeout=2,socket_timeout=2).delete(
            f"worker:heartbeat:{socket.gethostname()}")
    except Exception:
        logging.getLogger(__name__).exception("worker_ready_heartbeat_clear_failed")


worker_ready.connect(start_worker_ready_heartbeat,weak=False)
worker_shutdown.connect(clear_worker_ready_heartbeat,weak=False)
_transfer_test_mode=os.getenv("PORTABLE_TRANSFER_TEST_MODE", "0").lower() in ("1", "true", "yes")
celery_app.conf.update(
    task_default_queue="source_sync",
    task_queues=tuple(Queue(name) for name in ("source_sync","document_processing","exports","notifications","maintenance")),
    task_routes={"app.tasks.sync_source_task":{"queue":"source_sync"},"app.tasks.recover_stale_jobs":{"queue":"maintenance"},"app.tasks.run_database_backup":{"queue":"maintenance"},"app.tasks.dispatch_alert_emails":{"queue":"notifications"},"app.tasks.worker_heartbeat":{"queue":"maintenance"},"app.tasks.check_deadlines":{"queue":"maintenance"},"app.tasks.run_daily_data_quality":{"queue":"maintenance"},"app.tasks.run_weekly_data_quality":{"queue":"maintenance"}},
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=int(os.getenv("SOURCE_JOB_TIMEOUT_SECONDS","1800")),
    task_soft_time_limit=int(os.getenv("SOURCE_JOB_SOFT_TIMEOUT_SECONDS","1740")),
    broker_connection_retry_on_startup=True,
    result_expires=86400,
    beat_schedule={} if _transfer_test_mode else {"enqueue-due-sources-every-minute":{"task":"app.tasks.enqueue_due_sources","schedule":60.0,"options":{"queue":"maintenance"}},
                   "recover-stale-jobs-every-five-minutes":{"task":"app.tasks.recover_stale_jobs","schedule":300.0,"options":{"queue":"maintenance"}},
                   "dispatch-alert-emails-every-minute":{"task":"app.tasks.dispatch_alert_emails","schedule":60.0,"options":{"queue":"notifications"}},
                   "worker-heartbeat-every-minute":{"task":"app.tasks.worker_heartbeat","schedule":60.0,"options":{"queue":"maintenance"}},
                   "daily-deadline-check":{"task":"app.tasks.check_deadlines","schedule":86400.0,"options":{"queue":"maintenance"}},
                   "daily-data-quality-gates":{"task":"app.tasks.run_daily_data_quality","schedule":86400.0,"options":{"queue":"maintenance"}},
                   "weekly-data-quality-gates":{"task":"app.tasks.run_weekly_data_quality","schedule":604800.0,"options":{"queue":"maintenance"}},
                   "hourly-status-lifecycle-reconcile":{"task":"app.tasks.reconcile_status_lifecycle","schedule":3600.0,"options":{"queue":"maintenance"}},
                   "daily-postgres-backup":{"task":"app.tasks.run_database_backup","schedule":86400.0,"options":{"queue":"maintenance"}}},
)

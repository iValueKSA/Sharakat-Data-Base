"""Celery application shared by the worker and scheduler containers."""
import os
from celery import Celery
from kombu import Queue

redis_url=os.getenv("REDIS_URL","redis://redis:6379/0")
celery_app=Celery("alahsa",broker=redis_url,backend=redis_url,include=["app.tasks"])
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
    beat_schedule={"enqueue-due-sources-every-minute":{"task":"app.tasks.enqueue_due_sources","schedule":60.0,"options":{"queue":"maintenance"}},
                   "recover-stale-jobs-every-five-minutes":{"task":"app.tasks.recover_stale_jobs","schedule":300.0,"options":{"queue":"maintenance"}},
                   "dispatch-alert-emails-every-minute":{"task":"app.tasks.dispatch_alert_emails","schedule":60.0,"options":{"queue":"notifications"}},
                   "worker-heartbeat-every-minute":{"task":"app.tasks.worker_heartbeat","schedule":60.0,"options":{"queue":"maintenance"}},
                   "daily-deadline-check":{"task":"app.tasks.check_deadlines","schedule":86400.0,"options":{"queue":"maintenance"}},
                   "daily-data-quality-gates":{"task":"app.tasks.run_daily_data_quality","schedule":86400.0,"options":{"queue":"maintenance"}},
                   "weekly-data-quality-gates":{"task":"app.tasks.run_weekly_data_quality","schedule":604800.0,"options":{"queue":"maintenance"}},
                   "hourly-status-lifecycle-reconcile":{"task":"app.tasks.reconcile_status_lifecycle","schedule":3600.0,"options":{"queue":"maintenance"}},
                   "daily-postgres-backup":{"task":"app.tasks.run_database_backup","schedule":86400.0,"options":{"queue":"maintenance"}}},
)

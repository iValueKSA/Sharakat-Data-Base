"""Command lines for the application processes (replace api/worker/scheduler/migrate)."""
from __future__ import annotations

import sys
from pathlib import Path

from .config import Settings
from .home import IS_WINDOWS, PROJECT_ROOT

PYTHON = sys.executable
CELERY_APP = "app.celery_app:celery_app"
# Exactly the queues the Compose `worker` service consumed.
WORKER_QUEUES = "source_sync,maintenance,notifications"
WORKER_NAME = "sharakat-worker@%h"
LEGACY_IMPORT_REVISION = "0016_source_type_text"


def api_command(settings: Settings) -> list[str]:
    args = [PYTHON, "-m", "uvicorn", "app.main:app", "--host", settings.bind_address,
            "--port", str(settings.int("UI_PORT")), "--timeout-graceful-shutdown", "30"]
    if settings.behind_proxy:
        # Trust X-Forwarded-* only from the configured reverse proxy address(es).
        args += ["--proxy-headers", "--forwarded-allow-ips", settings.get("FORWARDED_ALLOW_IPS")]
    else:
        # Nothing sits in front of uvicorn, so never trust X-Forwarded-*: any
        # client could otherwise spoof its address and bypass the rate limits.
        args.append("--no-proxy-headers")
    if settings.tls_enabled:
        args += ["--ssl-certfile", settings.get("TLS_CERT_FILE"), "--ssl-keyfile", settings.get("TLS_KEY_FILE")]
    return args


def worker_command(settings: Settings) -> list[str]:
    args = [PYTHON, "-m", "celery", "-A", CELERY_APP, "worker", "--loglevel=INFO",
            f"--queues={WORKER_QUEUES}", f"--concurrency={settings.int('WORKER_CONCURRENCY')}", "-n", WORKER_NAME]
    if IS_WINDOWS:
        # Celery's prefork pool isn't supported on Windows. With threads, the
        # hard task_time_limit isn't enforced; stuck jobs are reclaimed by the
        # existing recover_stale_jobs schedule instead (accepted decision).
        args.append("--pool=threads")
    return args


def beat_command(settings: Settings) -> list[str]:
    run_dir = settings.layout.run_dir
    return [PYTHON, "-m", "celery", "-A", CELERY_APP, "beat", "--loglevel=INFO",
            "--schedule", str(run_dir / "celerybeat-schedule"), "--pidfile", str(beat_pidfile(settings))]


def beat_pidfile(settings: Settings) -> Path:
    return settings.layout.run_dir / "celerybeat.pid"


def alembic_command(target: str = "head") -> list[str]:
    return [PYTHON, "-m", "alembic", "upgrade", target]


def legacy_import_command() -> list[str]:
    return [PYTHON, str(PROJECT_ROOT / "scripts" / "local_database_setup.py")]


def backup_command() -> list[str]:
    return [PYTHON, "-c", "import json; from app.backups import backup_postgres; print(json.dumps(backup_postgres()))"]

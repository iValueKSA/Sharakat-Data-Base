"""Long-running supervisor: ordered startup, restart-on-crash, graceful stop.

Replaces Compose's depends_on/healthcheck ordering and `restart: unless-stopped`:

    PostgreSQL ready -> Redis ready -> migrations -> API + worker + beat -> /health/ready

`stop` is requested by creating run/stop.request (works identically on every
OS, without signals or consoles), which the supervisor polls.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import postgres, procs, redis_server, services
from .config import Settings, app_environment, load, validate_server_settings
from .home import PROJECT_ROOT, Layout
from .net import local_open

RESTART_LIMIT = 5            # crashes within RESTART_WINDOW before giving up on a component
RESTART_WINDOW = 600
WORKER_DRAIN_SECONDS = 120   # Compose stop_grace_period: 2m


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Child:
    name: str
    args: list[str]
    env: dict
    proc: subprocess.Popen | None = None
    crashes: list[float] = field(default_factory=list)
    failed: bool = False


class Supervisor:
    def __init__(self, layout: Layout):
        self.layout = layout
        self.settings: Settings = load(layout)
        self.state = {"status": "starting", "started_at": _now(), "components": {}, "message": ""}
        self.children: dict[str, Child] = {}
        self.pg_bin = None
        self.redis_engine = None

    # ---------- state file (read by `status` / `start`) ----------
    def _set(self, status: str | None = None, message: str | None = None, **components) -> None:
        if status:
            self.state["status"] = status
        if message is not None:
            self.state["message"] = message
        self.state["components"].update(components)
        self.state["updated_at"] = _now()
        self.state["pid"] = os.getpid()
        temporary = self.layout.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.layout.state_file)

    def log(self, message: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
        with (self.layout.logs_dir / "supervisor.log").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    # ---------- startup ----------
    def run(self) -> int:
        self.layout.stop_request.unlink(missing_ok=True)
        procs.write_pid(self.layout.supervisor_pid, os.getpid())
        try:
            self._start_all()
        except Exception as exc:   # noqa: BLE001 - report any startup failure to the user
            self.log(f"startup failed: {exc!r}")
            self._set("failed", f"{type(exc).__name__}: {exc}")
            self._stop_all()
            self.layout.supervisor_pid.unlink(missing_ok=True)
            return 1
        self._set("running", "")
        self.log("platform running")
        try:
            self._watch()
        finally:
            self._set("stopping", "")
            self._stop_all()
            self._set("stopped", "")
            self.layout.supervisor_pid.unlink(missing_ok=True)
            self.layout.stop_request.unlink(missing_ok=True)
        return 0

    def _start_all(self) -> None:
        settings = self.settings
        problems = validate_server_settings(settings)
        if problems:
            raise RuntimeError("Server settings are invalid: " + "; ".join(problems))
        self.pg_bin = postgres.locate(settings)          # also provides pg_dump for backups
        if settings.manages_postgres:
            self._set(message="Starting PostgreSQL", postgres="starting")
            if not self.pg_bin:
                raise postgres.PostgresError("PostgreSQL binaries not found. Run the installer first.")
            postgres.init_cluster(settings, self.pg_bin, self.log)
            postgres.start(settings, self.pg_bin, self.log)
            postgres.ensure_database(settings)
            self._set(postgres="running")
        else:
            self._set(message="Connecting to the external PostgreSQL", postgres="external")
            postgres.wait_app_database(settings)
            self._set(postgres="external (reachable)")

        if settings.manages_redis:
            self._set(message="Starting Redis", redis="starting")
            self.redis_engine = redis_server.resolve(settings, install=False, log=self.log)
            if redis_server.port_in_use(settings.int("REDIS_PORT")) and not redis_server.ping(settings):
                raise redis_server.RedisError(f"Port {settings.int('REDIS_PORT')} is used by another program.")
            if not redis_server.ping(settings):
                child = Child("redis", self.redis_engine.command(settings), redis_server.engine_env(self.redis_engine))
                self.children["redis"] = child
                self._spawn(child)
                redis_server.wait_ready(settings, child.proc)
            self._set(redis=f"running ({self.redis_engine.kind})")
        else:
            self._set(message="Connecting to the external Redis", redis="external")
            redis_server.wait_ready(settings, None, timeout=60)
            self._set(redis="external (reachable)")

        env = app_environment(settings, extra_path=[p for p in (self.pg_bin,) if p])   # pg_dump for backups
        if settings.flag("AUTO_MIGRATE"):
            self._set(message="Applying database migrations", migrations="running")
            result = procs.run(services.alembic_command(), env=env, cwd=PROJECT_ROOT, timeout=3600,
                               log_path=self.layout.logs_dir / "migrations.log")
            if result.returncode != 0:
                raise RuntimeError("Database migrations failed; see logs/migrations.log")
            self._set(migrations="done")
        else:
            self._set(migrations="skipped (AUTO_MIGRATE=false)")

        services.beat_pidfile(settings).unlink(missing_ok=True)   # we own beat; a stale file only blocks it
        for name, args in (("api", services.api_command(settings)),
                           ("worker", services.worker_command(settings)),
                           ("scheduler", services.beat_command(settings))):
            child = Child(name, args, env)
            self.children[name] = child
            self._spawn(child)
            self._set(**{name: "starting"})

        self._set(message="Waiting for the platform to become ready")
        self._wait_http("/health/ready", timeout=180)
        for name in ("api", "worker", "scheduler"):
            self._set(**{name: "running"})

    def _spawn(self, child: Child) -> None:
        child.proc = procs.spawn(child.args, self.layout.logs_dir / f"{child.name}.log", child.env, PROJECT_ROOT)
        procs.write_pid(self.layout.run_dir / f"{child.name}.pid", child.proc.pid)
        self.log(f"started {child.name} pid={child.proc.pid}")

    def _wait_http(self, path: str, timeout: float) -> None:
        url = self.settings.local_url + path
        deadline = time.monotonic() + timeout
        last = ""
        while time.monotonic() < deadline:
            api = self.children.get("api")
            if api and api.proc and api.proc.poll() is not None:
                raise RuntimeError(f"The API exited with code {api.proc.returncode}; see logs/api.log")
            try:
                with local_open(self.settings, path, timeout=5) as response:
                    if response.status == 200:
                        return
            except Exception as exc:   # noqa: BLE001
                last = str(exc)
            time.sleep(1)
        raise RuntimeError(f"The platform did not become ready at {url}: {last}")

    # ---------- watch loop ----------
    def _watch(self) -> None:
        last_pg_check = time.monotonic()
        while not self.layout.stop_request.exists():
            time.sleep(1)
            for child in self.children.values():
                if child.failed or child.proc is None or child.proc.poll() is None:
                    continue
                code = child.proc.returncode
                now = time.monotonic()
                child.crashes = [t for t in child.crashes if now - t < RESTART_WINDOW] + [now]
                self.log(f"{child.name} exited with code {code}")
                if len(child.crashes) > RESTART_LIMIT:
                    child.failed = True
                    self._set("degraded", f"{child.name} keeps crashing; see logs/{child.name}.log",
                              **{child.name: f"failed (exit {code})"})
                    continue
                time.sleep(min(30, 2 ** len(child.crashes)))
                self._spawn(child)
                self._set(**{child.name: f"restarted (after exit {code})"})
            if self.settings.manages_postgres and time.monotonic() - last_pg_check > 15:
                last_pg_check = time.monotonic()
                if not postgres.is_running(self.settings, self.pg_bin):
                    self.log("PostgreSQL is not running; restarting it")
                    try:
                        postgres.start(self.settings, self.pg_bin, self.log)
                        self._set(postgres="restarted")
                    except Exception as exc:   # noqa: BLE001
                        self._set("degraded", f"PostgreSQL restart failed: {exc}", postgres="failed")

    # ---------- shutdown (reverse order) ----------
    def _stop_all(self) -> None:
        worker = self.children.get("worker")
        if worker and worker.proc and worker.proc.poll() is None:
            self._set(message="Letting running jobs finish", worker="stopping")
            self._celery_warm_shutdown()
            deadline = time.monotonic() + WORKER_DRAIN_SECONDS
            while worker.proc.poll() is None and time.monotonic() < deadline:
                time.sleep(1)
        for name in ("scheduler", "worker", "api"):
            child = self.children.get(name)
            if child and child.proc:
                procs.terminate(child.proc)
                self._set(**{name: "stopped"})
        redis_child = self.children.get("redis")
        if redis_child and redis_child.proc and redis_child.proc.poll() is None:
            redis_server.shutdown(self.settings)
            try:
                redis_child.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                procs.terminate(redis_child.proc)
            self._set(redis="stopped")
        if self.pg_bin and self.settings.manages_postgres:
            postgres.stop(self.settings, self.pg_bin)
            self._set(postgres="stopped")
        for name in ("api", "worker", "scheduler", "redis"):
            (self.layout.run_dir / f"{name}.pid").unlink(missing_ok=True)

    def _celery_warm_shutdown(self) -> None:
        """Ask the worker to finish its current tasks and exit (portable; no signals)."""
        env = app_environment(self.settings)
        code = ("from app.celery_app import celery_app; "
                f"celery_app.control.shutdown(destination=[{services.WORKER_NAME.replace('%h', '')!r}+__import__('socket').gethostname()])")
        try:
            procs.run([services.PYTHON, "-c", code], env=env, cwd=PROJECT_ROOT, timeout=30,
                      log_path=self.layout.logs_dir / "worker.log")
        except subprocess.TimeoutExpired:
            pass


def main(layout: Layout) -> int:
    return Supervisor(layout).run()

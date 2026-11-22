"""`python -m sharakat_runtime <command>` – install and operate the platform natively."""
from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from . import downloads, postgres, procs, redis_server, services
from .config import app_environment, load, load_or_create, validate_server_settings, write_credentials_file
from .net import local_open
from .home import IS_LINUX, IS_MACOS, IS_WINDOWS, PROJECT_ROOT, layout as resolve_layout, machine_arch, os_key


def say(message: str) -> None:
    print(message, flush=True)


# ------------------------------------------------------------------ install
def _newest_transfer_dump() -> tuple[Path, str] | None:
    """The transfer package's database dump, if any.

    When the installer runs from inside a copied transfer package (the package
    is a full project copy), its own manifest wins; otherwise the newest package
    under transfer/ is used. The caller verifies the recorded SHA-256.
    """
    own = PROJECT_ROOT / "transfer-manifest.json"
    packages = sorted((PROJECT_ROOT / "transfer").glob("portable-package-*/transfer-manifest.json"), reverse=True)
    for manifest in ([own] if own.is_file() else []) + packages:
        try:
            data = json.loads(manifest.read_text(encoding="utf-8-sig"))
            info = data["database_backup"]
            dump = (manifest.parent / info["path"]).resolve()
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if dump.is_file() and dump.is_relative_to(manifest.parent.resolve()):
            return dump, info.get("sha256", "")
    return None


def _verify_dump(dump: Path, expected_sha256: str) -> None:
    if expected_sha256:
        say(f"Verifying checksum of {dump.name}")
        actual = downloads.sha256_file(dump)
        if actual != expected_sha256.lower():
            raise SystemExit(f"Checksum mismatch for {dump}: the transfer package is damaged or incomplete.")


def cmd_install(args) -> int:
    layout = resolve_layout()
    settings, created = load_or_create(layout)
    say(f"Platform home: {layout.root}")
    if created:
        say(f"Generated private settings in {layout.env_file}")

    from .config import validate_server_settings
    problems = validate_server_settings(settings)
    if problems:
        raise SystemExit("Fix the server settings first:\n  - " + "\n  - ".join(problems))

    say("Step 1/5: PostgreSQL")
    # Installed even with an external database: pg_dump/pg_restore are needed
    # for backups, restores and transfers.
    pg_bin = postgres.install(settings, say)
    say(f"  using {pg_bin} (PostgreSQL {postgres.major_version(pg_bin)})")

    say("Step 2/5: Redis-protocol server")
    if settings.manages_redis:
        engine_kind = redis_server.resolve(settings, install=True, log=say).kind
        say(f"  using {engine_kind}")
    else:
        engine_kind = "external"
        say("  using the external Redis in EXTERNAL_REDIS_URL")

    say("Step 3/5: Database")
    if settings.manages_postgres:
        postgres.init_cluster(settings, pg_bin, say)
        postgres.start(settings, pg_bin, say)
    else:
        say("  using the external PostgreSQL in EXTERNAL_DATABASE_URL")
        postgres.wait_app_database(settings)
    try:
        if settings.manages_postgres:
            postgres.ensure_database(settings)
        source = _load_initial_data(args, settings, pg_bin)
        admin_preexisted = _account_exists(settings, settings.get("BOOTSTRAP_ADMIN_EMAIL"))
    finally:
        if settings.manages_postgres:
            postgres.stop(settings, pg_bin)

    say("Step 4/5: Local administrator")
    credentials = write_credentials_file(settings, account_preexisted=admin_preexisted)
    if admin_preexisted:
        say(f"  {settings.get('BOOTSTRAP_ADMIN_EMAIL')} came with the restored data and keeps its previous password.")
        say("  Sign in with the previous computer's password, or run: reset-admin-password")
    say(f"  sign-in details written to {credentials}")

    marker = {"installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "os": os_key(), "arch": machine_arch(), "postgres_bin": str(pg_bin),
              "postgres_major": postgres.major_version(pg_bin), "redis_engine": engine_kind,
              "server_mode": settings.server_mode or "workstation",
              "initial_data": source}
    previous = json.loads(layout.install_marker.read_text(encoding="utf-8")) if layout.install_marker.is_file() else {}
    if previous.get("initial_data") and source == "existing database (kept)":
        marker["initial_data"] = previous["initial_data"]
    layout.install_marker.write_text(json.dumps(marker, indent=2), encoding="utf-8")

    say("Step 5/5: Done")
    if args.no_start:
        say("Installation complete. Start the platform with the Start Platform launcher.")
        return 0
    return cmd_start(argparse.Namespace(no_browser=args.no_browser))


def _account_exists(settings, email: str) -> bool:
    """Whether the database already holds this account (e.g. from restored data)."""
    if postgres.database_is_empty(settings):
        return False
    code, payload, _ = _run_json_script([services.PYTHON, "-m", "sharakat_runtime.admin_tools", "has-user", email],
                                        app_environment(settings), 120)
    return bool(code == 0 and payload and payload.get("exists"))


def cmd_reset_admin_password(args) -> int:
    """Give the local admin account a new generated password (explicit user action)."""
    import secrets
    from .config import parse_env_file, write_env_file
    layout = resolve_layout()
    settings = load(layout)
    email = (args.email or settings.get("BOOTSTRAP_ADMIN_EMAIL")).strip().lower()
    password = secrets.token_urlsafe(18)
    pg_bin = postgres.locate(settings)
    owns_postgres = settings.manages_postgres and not postgres.is_running(settings, pg_bin)
    if owns_postgres:
        postgres.start(settings, pg_bin, say)
    try:
        env = {**app_environment(settings), "SHARAKAT_NEW_PASSWORD": password}
        code, payload, stderr = _run_json_script(
            [services.PYTHON, "-m", "sharakat_runtime.admin_tools", "reset-password", email], env, 300)
    finally:
        if owns_postgres:
            postgres.stop(settings, pg_bin)
    if code != 0 or not payload:
        raise SystemExit("Resetting the password failed: " + (stderr or "")[-1000:])
    values = parse_env_file(layout.env_file)
    values["BOOTSTRAP_ADMIN_EMAIL"] = email
    values["BOOTSTRAP_ADMIN_PASSWORD"] = password
    write_env_file(layout.env_file, values)
    credentials = write_credentials_file(load(layout))
    say(f"Password {payload['status']} for {email}; {payload.get('sessions_revoked', 0)} old session(s) signed out.")
    say(f"The new password is in {credentials}")
    return 0


def _load_initial_data(args, settings, pg_bin) -> str:
    """Populate an empty database once. Never touches a database that has data."""
    if not postgres.database_is_empty(settings):
        if args.restore:
            raise SystemExit("The platform database already contains data; refusing to restore over it.")
        say("  existing platform database found; keeping it unchanged")
        return "existing database (kept)"
    env = app_environment(settings, extra_path=[pg_bin])
    if args.fresh:
        say("  starting with an empty database (--fresh)")
        return "empty"
    if args.restore:
        dump = Path(args.restore).expanduser().resolve()
        postgres.restore(settings, pg_bin, dump, say)
        return f"restored backup {dump.name}"
    package = None if args.import_sqlite else _newest_transfer_dump()
    if package:
        dump, digest = package
        package_root = dump.parent.parent.parent
        say(f"  restoring the transfer package: {package_root.name}")
        _verify_dump(dump, digest)
        postgres.restore(settings, pg_bin, dump, say)
        differences = _compare_with_baseline(package_root / "expected-data-manifest.json", env)
        if differences:
            # The restore came entirely from the package, so discarding it loses nothing.
            postgres.reset_database(settings)
            raise SystemExit("The restored data does not match the transfer package's expected counts "
                             f"({', '.join(differences)}). The restore was discarded; the package may be damaged.")
        return f"transfer package {package_root.name}"
    sqlite = PROJECT_ROOT / "data" / "al-ahsa-live.db"
    if sqlite.is_file():
        # local_database_setup.py imports into a schema at exactly this revision.
        say("  importing the legacy SQLite workspace (one time)")
        for step in (services.alembic_command(services.LEGACY_IMPORT_REVISION), services.legacy_import_command()):
            result = procs.run(step, env=env, cwd=PROJECT_ROOT, timeout=7200,
                               log_path=settings.layout.logs_dir / "initial-import.log")
            if result.returncode != 0:
                raise SystemExit("Initial SQLite import failed; see logs/initial-import.log\n" + result.stderr[-2000:])
        return "legacy SQLite import"
    say("  no existing data found; starting with an empty database")
    return "empty"


# Business fields that must be identical after a transfer (same list the
# Docker-era verify-installation.ps1 compared).
STABLE_SNAPSHOT_KEYS = ("total_masters", "current_masters", "merged_masters", "source_opportunities",
                        "qualification_reviews", "location_reviews", "duplicate_reviews", "conflict_reviews",
                        "review_history_records", "open_review_records", "merge_lineage_records",
                        "configured_sources", "enabled_sources", "source_configuration_sha256", "users",
                        "active_admin_users", "rbac_fingerprint_sha256", "alembic_heads")


def _run_json_script(args: list, env: dict, timeout: float = 1800):
    """Run a read-only helper script and parse the JSON object it prints last."""
    result = procs.run(args, env=env, cwd=PROJECT_ROOT, timeout=timeout)
    text = result.stdout or ""
    start = text.find("{")
    payload = None
    if start >= 0:
        try:
            payload = json.loads(text[start:])
        except ValueError:
            lines = [line for line in text.splitlines() if line.strip().startswith("{")]
            payload = json.loads(lines[-1]) if lines else None
    return result.returncode, payload, result.stderr


def _snapshot(env: dict) -> dict:
    code, payload, stderr = _run_json_script([services.PYTHON, "scripts/portable_transfer_snapshot.py"], env, 600)
    if code != 0 or not isinstance(payload, dict):
        raise RuntimeError("Reading the database snapshot failed: " + (stderr or "")[-1000:])
    return payload


def _compare_with_baseline(baseline_path: Path, env: dict) -> list[str]:
    if not baseline_path.is_file():
        say("  no expected-data manifest in the package; skipping the count comparison")
        return []
    baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig")).get("snapshot", {})
    try:
        snapshot = _snapshot(env)
    except RuntimeError as exc:
        # Can't compare (e.g. the snapshot script expects a newer schema than the
        # dump). Keep the restore; `verify` re-checks after migrations.
        say(f"  WARNING: could not compare with the source computer's counts: {exc}")
        return []
    differences = [key for key in STABLE_SNAPSHOT_KEYS
                   if key in baseline and json.dumps(snapshot.get(key), sort_keys=True) != json.dumps(baseline.get(key), sort_keys=True)]
    if not differences:
        say(f"  verified: {snapshot.get('total_masters')} opportunities, {snapshot.get('users')} users, "
            f"{snapshot.get('observations')} observations match the source computer")
    return differences


# ------------------------------------------------------------------ start / stop / status
def _supervisor_running(layout) -> bool:
    pid = procs.read_pid(layout.supervisor_pid)
    return bool(pid and procs.pid_alive(pid))


def _read_state(layout) -> dict:
    try:
        return json.loads(layout.state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def cmd_start(args) -> int:
    layout = resolve_layout()
    if not layout.install_marker.is_file():
        say("First start on this computer: installing the platform.")
        return cmd_install(argparse.Namespace(restore=None, import_sqlite=False, fresh=False, no_start=False,
                                              no_browser=getattr(args, "no_browser", False)))
    settings = load(layout)
    if _supervisor_running(layout):
        say("The platform is already running.")
    else:
        layout.state_file.unlink(missing_ok=True)
        layout.stop_request.unlink(missing_ok=True)
        procs.spawn([services.PYTHON, "-m", "sharakat_runtime", "supervise"], layout.logs_dir / "supervisor.out.log",
                    dict(__import__("os").environ), PROJECT_ROOT, detached=True)
        say("Starting the platform (first start can take a minute)...")
        deadline = time.monotonic() + 600
        shown = ""
        while time.monotonic() < deadline:
            state = _read_state(layout)
            message = state.get("message", "")
            if message and message != shown:
                say(f"  {message}")
                shown = message
            if state.get("status") == "running":
                break
            if state.get("status") == "failed":
                say(f"STARTUP FAILED: {state.get('message')}")
                say(f"Logs: {layout.logs_dir}")
                return 1
            time.sleep(1)
        else:
            say(f"The platform did not report ready in time. Logs: {layout.logs_dir}")
            return 1
    say(f"PLATFORM READY: {settings.ui_url}")
    if not getattr(args, "no_browser", False) and not settings.server_mode:
        webbrowser.open(settings.ui_url)
    return 0


def cmd_stop(args) -> int:
    layout = resolve_layout()
    if not _supervisor_running(layout):
        say("The platform is not running.")
        _cleanup_orphans(layout)
        return 0
    layout.stop_request.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    say("Stopping the platform (running jobs are allowed to finish, up to 2 minutes)...")
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline and _supervisor_running(layout):
        time.sleep(1)
    if _supervisor_running(layout):
        say("The supervisor did not stop in time; stopping remaining processes.")
        procs.terminate(procs.read_pid(layout.supervisor_pid))
        _cleanup_orphans(layout)
    say("Platform stopped. Your data is kept.")
    return 0


def _cleanup_orphans(layout) -> None:
    """After a crash of the supervisor itself, stop children it left behind."""
    for name in ("scheduler", "worker", "api", "redis"):
        pid_file = layout.run_dir / f"{name}.pid"
        pid = procs.read_pid(pid_file)
        if pid and procs.pid_alive(pid):
            procs.terminate(pid)
        pid_file.unlink(missing_ok=True)
    try:
        settings = load(layout)
        pg_bin = postgres.locate(settings)
        if pg_bin and settings.manages_postgres:
            postgres.stop(settings, pg_bin)
    except RuntimeError:
        pass


def cmd_restart(args) -> int:
    cmd_stop(args)
    return cmd_start(args)


def cmd_status(args) -> int:
    layout = resolve_layout()
    state = _read_state(layout)
    running = _supervisor_running(layout)
    ready = None
    settings = None
    try:
        settings = load(layout)
        with local_open(settings, "/health/ready", timeout=5) as response:
            ready = json.loads(response.read().decode("utf-8"))
    except Exception:   # noqa: BLE001
        pass
    if args.json:
        print(json.dumps({"supervisor_running": running, "state": state, "ready": ready}, indent=2, ensure_ascii=False))
        return 0 if running else 3
    say(f"Platform: {'RUNNING' if running else 'STOPPED'} ({state.get('status', 'unknown')})")
    if settings is not None:
        say(f"  address: {settings.ui_url}  (mode: {settings.server_mode or 'workstation'})")
    for name, value in state.get("components", {}).items():
        say(f"  {name:<11} {value}")
    if state.get("message"):
        say(f"  note: {state['message']}")
    if ready:
        say(f"  health/ready: {ready}")
    say(f"  logs: {layout.logs_dir}")
    return 0 if running else 3


# ------------------------------------------------------------------ doctor / backup / restore / logs
def cmd_doctor(args) -> int:
    layout = resolve_layout()
    problems = 0
    def check(label, ok, detail=""):
        nonlocal problems
        problems += 0 if ok else 1
        say(f"[{'OK ' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    check("Python 3.12+", sys.version_info >= (3, 12), sys.version.split()[0])
    check("Supported OS", IS_WINDOWS or IS_MACOS or IS_LINUX, f"{os_key()} {machine_arch()}")
    import shutil
    free = shutil.disk_usage(layout.root if layout.root.exists() else Path.home()).free
    check("Free disk space >= 5 GB", free >= 5 * 1024**3, f"{free // 1024**3} GB free")
    for module in ("fastapi", "uvicorn", "celery", "redis", "psycopg", "alembic", "sqlalchemy", "openpyxl", "lxml"):
        try:
            __import__(module)
            check(f"Python package {module}", True)
        except ImportError as exc:
            check(f"Python package {module}", False, str(exc))
    if layout.env_file.is_file():
        settings = load(layout)
        pg_bin = postgres.locate(settings)
        check("PostgreSQL binaries", bool(pg_bin), str(pg_bin or "not installed"))
        if settings.manages_redis:
            try:
                engine = redis_server.resolve(settings)
                check("Redis-protocol server", engine.executable.is_file(), f"{engine.kind}: {engine.executable}")
            except redis_server.RedisError as exc:
                check("Redis-protocol server", False, str(exc))
        problems_found = validate_server_settings(settings)
        check(f"Server settings (mode: {settings.server_mode or 'workstation'})", not problems_found,
              "; ".join(problems_found))
        if not _supervisor_running(layout):
            ports = [("UI port", settings.int("UI_PORT"))]
            if settings.manages_postgres:
                ports.append(("PostgreSQL port", settings.int("POSTGRES_PORT")))
            if settings.manages_redis:
                ports.append(("Redis port", settings.int("REDIS_PORT")))
            for label, port in ports:
                check(f"{label} {port} free", not redis_server.port_in_use(port))
    else:
        say("[INFO] Not installed yet (no platform.env).")
    return 1 if problems else 0


def cmd_backup(args) -> int:
    layout = resolve_layout()
    settings = load(layout)
    if not _supervisor_running(layout):
        raise SystemExit("Start the platform before taking a backup.")
    pg_bin = postgres.locate(settings)
    result = procs.run(services.backup_command(), env=app_environment(settings, extra_path=[p for p in (pg_bin,) if p]),
                       cwd=PROJECT_ROOT,
                       timeout=7200, log_path=layout.logs_dir / "backup.log")
    if result.returncode != 0:
        say(result.stderr[-2000:])
        return 1
    say(result.stdout.strip())
    return 0


def cmd_restore(args) -> int:
    layout = resolve_layout()
    settings = load(layout)
    if _supervisor_running(layout):
        raise SystemExit("Stop the platform before restoring.")
    pg_bin = postgres.locate(settings)
    dump = Path(args.dump).expanduser().resolve()
    if settings.manages_postgres:
        postgres.start(settings, pg_bin, say)
    try:
        if settings.manages_postgres:
            postgres.ensure_database(settings)
        postgres.restore(settings, pg_bin, dump, say)
    finally:
        if settings.manages_postgres:
            postgres.stop(settings, pg_bin)
    say("Restore complete. Migrations run automatically on the next start.")
    return 0


def cmd_verify(args) -> int:
    """Read-only health verification (native counterpart of verify-installation.ps1)."""
    layout = resolve_layout()
    settings = load(layout)
    checks: list[dict] = []
    def check(key, passed, observed=None):
        checks.append({"key": key, "status": "PASS" if passed else "FAIL", "observed": observed})
        say(f"{key:<32} {'PASS' if passed else 'FAIL'}  {'' if observed is None else observed}")
    check("supervisor_running", _supervisor_running(layout))
    server_problems = validate_server_settings(settings)
    check("server_settings", not server_problems, server_problems or (settings.server_mode or "workstation"))
    for key, path in (("health_live", "/health/live"), ("frontend", "/")):
        try:
            with local_open(settings, path, timeout=10) as response:
                check(key, response.status == 200, f"HTTP {response.status}")
        except Exception as exc:   # noqa: BLE001
            check(key, False, str(exc))
    try:
        with local_open(settings, "/health/ready", timeout=10) as response:
            ready = json.loads(response.read().decode("utf-8"))
        check("health_ready", ready.get("status") == "ready", ready)
    except Exception as exc:   # noqa: BLE001
        check("health_ready", False, str(exc))
    env = app_environment(settings, extra_path=[postgres.locate(settings) or Path(".")])
    code, ping, _ = _run_json_script([services.PYTHON, "-c",
        "import json; from app.celery_app import celery_app; print(json.dumps({'replies': celery_app.control.ping(timeout=5)}))"], env, 60)
    check("celery_worker_ping", code == 0 and bool((ping or {}).get("replies")), (ping or {}).get("replies"))
    heads = procs.run([services.PYTHON, "-m", "alembic", "heads"], env=env, cwd=PROJECT_ROOT, timeout=120).stdout
    head_ids = sorted(line.split()[0] for line in heads.splitlines() if line.strip())
    try:
        snapshot = _snapshot(env)
        check("database_snapshot", True, "read-only count/fingerprint query succeeded")
        check("alembic_at_head", sorted(snapshot.get("alembic_heads", [])) == head_ids,
              {"heads": head_ids, "current": snapshot.get("alembic_heads")})
        check("active_admin_account", int(snapshot.get("active_admin_users", 0)) > 0, snapshot.get("active_admin_users"))
        check("masters_and_merge_lineage",
              snapshot["total_masters"] == snapshot["current_masters"] + snapshot["merged_masters"]
              and snapshot["merge_lineage_records"] >= snapshot["merged_masters"],
              {k: snapshot.get(k) for k in ("total_masters", "current_masters", "merged_masters", "merge_lineage_records")})
    except (RuntimeError, KeyError) as exc:
        check("database_snapshot", False, str(exc))
    if not args.skip_data_quality:
        code, dq, _ = _run_json_script([services.PYTHON, "-m", "scripts.run_data_quality", "--scope", "full"], env, 1800)
        counts = (dq or {}).get("counts", {})
        check("read_only_data_quality", dq is not None and int(counts.get("fail", 1)) == 0,
              {"exit_code": code, **{k: counts.get(k) for k in ("pass", "warning", "fail")}})
    # The managed PostgreSQL and Redis must only be reachable on loopback. So
    # must the UI on a workstation; on a server it is meant to be reachable.
    import socket
    try:
        lan_ip = next(ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127."))
    except (StopIteration, OSError):
        lan_ip = None
    probes = []
    if settings.manages_postgres:
        probes.append(("postgres", settings.int("POSTGRES_PORT"), False))
    if settings.manages_redis:
        probes.append(("redis", settings.int("REDIS_PORT"), False))
    ui_public = bool(settings.server_mode) and settings.bind_address not in ("127.0.0.1", "::1", "localhost")
    probes.append(("ui", settings.int("UI_PORT"), ui_public))
    for label, port, should_be_reachable in probes:
        if lan_ip:
            with socket.socket() as probe:
                probe.settimeout(1)
                reachable = probe.connect_ex((lan_ip, port)) == 0
            if should_be_reachable:
                check(f"{label}_reachable_on_network", reachable,
                      f"{lan_ip}:{port}" + ("" if reachable else " - check the firewall rule"))
            else:
                check(f"{label}_not_exposed_on_network", not reachable, f"{lan_ip}:{port}")
    report = layout.logs_dir / f"verification-{time.strftime('%Y%m%d-%H%M%S')}.json"
    report.write_text(json.dumps({"checks": checks}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    say(f"\nDetails: {report}")
    return 1 if any(c["status"] == "FAIL" for c in checks) else 0


EXPORT_EXCLUDE_DIRS = {".git", "transfer", "tmp", "backups", "logs", ".venv", ".local-setup", ".local", ".cache",
                       "__pycache__", ".pytest_cache", ".sharakat", "node_modules"}
EXPORT_EXCLUDE_FILES = {".env", ".env.local", ".env.staging", "Local Admin Credentials.txt", ".local-platform.pid"}


def cmd_export_transfer(args) -> int:
    """Create a transfer package: a project copy plus a verified database dump.

    Same layout as the Docker-era packages (transfer-manifest.json with a
    database_backup entry, expected-data-manifest.json), so `install` on the new
    computer restores it automatically. Secrets and the legacy SQLite files are
    not included; users sign in again on the new computer.
    """
    import shutil
    import uuid
    layout = resolve_layout()
    settings = load(layout)
    if not _supervisor_running(layout):
        raise SystemExit("Start the platform before preparing a transfer.")
    pg_bin = postgres.locate(settings)
    env = app_environment(settings, extra_path=[pg_bin])
    package_id = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    root = PROJECT_ROOT / "transfer" / f"portable-package-{package_id}"
    say(f"Preparing {root}")
    snapshot_before = _snapshot(env)
    dump_rel = f"transfer/database/al-ahsa-platform-{package_id}.dump"
    dump = root / dump_rel
    dump.parent.mkdir(parents=True)
    db = settings.database_params()
    result = procs.run([pg_bin / f"pg_dump{postgres.EXE}", "--format=custom", "--no-owner", "--no-acl",
                        "-h", db["host"], "-p", db["port"], "-U", db["user"], "-d", db["dbname"], "-f", dump],
                       env={**env, "PGPASSWORD": db["password"]}, timeout=7200,
                       log_path=layout.logs_dir / "transfer.log")
    if result.returncode != 0:
        shutil.rmtree(root, ignore_errors=True)
        raise SystemExit("pg_dump failed; see logs/transfer.log")
    if procs.run([pg_bin / f"pg_restore{postgres.EXE}", "--list", dump], timeout=600).returncode != 0:
        shutil.rmtree(root, ignore_errors=True)
        raise SystemExit("The new dump failed validation (pg_restore --list).")
    snapshot_after = _snapshot(env)
    if any(snapshot_before.get(k) != snapshot_after.get(k) for k in STABLE_SNAPSHOT_KEYS):
        shutil.rmtree(root, ignore_errors=True)
        raise SystemExit("Data changed while the backup was taken (a sync or review ran). Try again.")
    say("Copying the project files")
    for item in PROJECT_ROOT.iterdir():
        if item.name in EXPORT_EXCLUDE_DIRS or item.name in EXPORT_EXCLUDE_FILES or item.name.startswith(".env"):
            continue
        target = root / item.name
        if item.is_dir():
            ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.db", "*.db-*")
            if item.name == "docs":
                ignore = shutil.ignore_patterns("__pycache__", "validation")   # large generated evidence, not needed to run
            shutil.copytree(item, target, ignore=ignore)
        else:
            shutil.copy2(item, target)
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (root / "expected-data-manifest.json").write_text(json.dumps(
        {"schema_version": 1, "created_at_utc": created, "snapshot": snapshot_after}, indent=2, ensure_ascii=False), encoding="utf-8")
    digest = downloads.sha256_file(dump)
    (root / "transfer-manifest.json").write_text(json.dumps({
        "schema_version": "native-1", "package_id": package_id, "created_at_utc": created, "package_root": ".",
        "database_transfer_method": "LOGICAL_BACKUP_RESTORE",
        "database_backup": {"path": dump_rel, "format": "PostgreSQL custom", "sha256": digest,
                            "validated_with": "pg_restore --list", "contains_business_data_and_password_hashes": True},
        "expected_data_manifest": "expected-data-manifest.json",
        "excluded": ["platform.env and all generated secrets", "Local Admin Credentials.txt", "legacy SQLite files",
                     "logs", "backups", "docs/validation"],
    }, indent=2), encoding="utf-8")
    say(f"TRANSFER PACKAGE READY: {root}")
    say("Copy this whole folder to the new computer and run the installer there. "
        "The dump contains business data and password hashes: treat the folder as private.")
    return 0


SERVER_KEYS = ("SERVER_MODE", "PUBLIC_URL", "BIND_ADDRESS", "TLS_CERT_FILE", "TLS_KEY_FILE", "BEHIND_PROXY",
               "FORWARDED_ALLOW_IPS", "EXTERNAL_DATABASE_URL", "EXTERNAL_REDIS_URL")


def cmd_server(args) -> int:
    """Show or change how this installation serves users (workstation / server)."""
    from .config import parse_env_file, write_env_file
    layout = resolve_layout()
    settings, _ = load_or_create(layout)
    values = parse_env_file(layout.env_file)
    changes = {
        "SERVER_MODE": None if args.mode is None else ("" if args.mode == "off" else args.mode),
        "PUBLIC_URL": args.public_url,
        "BIND_ADDRESS": args.bind,
        "TLS_CERT_FILE": str(Path(args.tls_cert).resolve()) if args.tls_cert else None,
        "TLS_KEY_FILE": str(Path(args.tls_key).resolve()) if args.tls_key else None,
        "BEHIND_PROXY": None if args.behind_proxy is None else ("true" if args.behind_proxy else "false"),
        "FORWARDED_ALLOW_IPS": args.trusted_proxies,
        "EXTERNAL_DATABASE_URL": args.database_url,
        "EXTERNAL_REDIS_URL": args.redis_url,
    }
    if args.port is not None:
        changes["UI_PORT"] = str(args.port)
    if args.mode == "off":
        for key in SERVER_KEYS:
            changes[key] = ""
    changed = {key: value for key, value in changes.items() if value is not None}
    if changed:
        values.update(changed)
        candidate = type(settings)({**settings.values, **values}, layout)
        problems = validate_server_settings(candidate)
        if problems:
            say("Not saved. Fix these first:")
            for problem in problems:
                say(f"  - {problem}")
            return 1
        write_env_file(layout.env_file, values)
        settings = load(layout)
        say(f"Saved to {layout.env_file}")
    mode = settings.server_mode or "workstation"
    say(f"Mode:        {mode}")
    say(f"Address:     {settings.ui_url}")
    say(f"Listens on:  {settings.bind_address}:{settings.int('UI_PORT')}"
        f"{' (HTTPS)' if settings.tls_enabled else ''}{' behind a reverse proxy' if settings.behind_proxy else ''}")
    say(f"Database:    {'managed by the platform' if settings.manages_postgres else 'external'}")
    say(f"Redis:       {'managed by the platform' if settings.manages_redis else 'external'}")
    for problem in validate_server_settings(settings):
        say(f"  ! {problem}")
    if changed:
        if settings.server_mode and settings.bind_address not in ("127.0.0.1", "::1", "localhost"):
            port = settings.int("UI_PORT")
            say("\nOpen the port in the server firewall (once, as administrator):")
            if IS_WINDOWS:
                say(f'  netsh advfirewall firewall add rule name="Sharakat Platform" dir=in action=allow protocol=TCP localport={port}')
            elif IS_MACOS:
                say("  System Settings > Network > Firewall > allow incoming connections for Python")
            else:
                say(f"  sudo ufw allow {port}/tcp      (or: sudo firewall-cmd --permanent --add-port={port}/tcp && sudo firewall-cmd --reload)")
        if settings.server_mode:
            say("Start automatically when the server boots:  service install --at-boot")
        say("Apply the change:  restart")
    return 0


def cmd_logs(args) -> int:
    layout = resolve_layout()
    path = layout.logs_dir / f"{args.component}.log"
    if not path.is_file():
        say(f"No log yet: {path}")
        return 1
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(lines[-args.lines:]))
    return 0


def cmd_open(args) -> int:
    settings = load(resolve_layout())
    webbrowser.open(settings.ui_url)
    return 0


def cmd_supervise(args) -> int:
    from .supervisor import main
    return main(resolve_layout())


def cmd_service(args) -> int:
    from . import autostart
    if getattr(args, "at_boot", False):
        return autostart.install_at_boot() if args.action == "install" else autostart.uninstall_at_boot()
    return autostart.install() if args.action == "install" else autostart.uninstall()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sharakat", description="Install and run the Al-Ahsa platform natively.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("install", help="Provision PostgreSQL/Redis, create the database, load initial data")
    source = p.add_mutually_exclusive_group()
    source.add_argument("--restore", metavar="DUMP", help="Restore this pg_dump custom-format backup")
    source.add_argument("--import-sqlite", action="store_true", help="Import data/al-ahsa-live.db instead of a transfer package")
    source.add_argument("--fresh", action="store_true", help="Start with an empty database")
    p.add_argument("--no-start", action="store_true")
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_install)
    p = sub.add_parser("start"); p.add_argument("--no-browser", action="store_true"); p.set_defaults(func=cmd_start)
    sub.add_parser("stop").set_defaults(func=cmd_stop)
    p = sub.add_parser("restart"); p.add_argument("--no-browser", action="store_true"); p.set_defaults(func=cmd_restart)
    p = sub.add_parser("status"); p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_status)
    sub.add_parser("doctor", help="Check this computer and the installation").set_defaults(func=cmd_doctor)
    sub.add_parser("backup", help="Take a PostgreSQL backup now").set_defaults(func=cmd_backup)
    p = sub.add_parser("verify", help="Read-only health and data verification")
    p.add_argument("--skip-data-quality", action="store_true"); p.set_defaults(func=cmd_verify)
    sub.add_parser("export-transfer", help="Create a package to move the platform to another computer").set_defaults(func=cmd_export_transfer)
    p = sub.add_parser("restore", help="Restore a backup into an empty installation"); p.add_argument("dump"); p.set_defaults(func=cmd_restore)
    p = sub.add_parser("logs"); p.add_argument("component", nargs="?", default="supervisor"); p.add_argument("-n", "--lines", type=int, default=80); p.set_defaults(func=cmd_logs)
    sub.add_parser("open", help="Open the platform in the browser").set_defaults(func=cmd_open)
    p = sub.add_parser("reset-admin-password", help="Set a new generated password for the local admin account")
    p.add_argument("--email", help="Account to reset (default: BOOTSTRAP_ADMIN_EMAIL)"); p.set_defaults(func=cmd_reset_admin_password)
    p = sub.add_parser("service", help="Start automatically at login, or at boot on a server (--at-boot)")
    p.add_argument("action", choices=("install", "uninstall"))
    p.add_argument("--at-boot", action="store_true", help="Start when the machine boots, before anyone signs in (needs admin/sudo)")
    p.set_defaults(func=cmd_service)
    p = sub.add_parser("server", help="Show or configure server mode (internal LAN / staging / production)")
    p.add_argument("--mode", choices=("internal", "staging", "production", "off"))
    p.add_argument("--public-url", help="Address users open, e.g. http://srv-name:8080 or https://platform.example.org")
    p.add_argument("--port", type=int, help="Port the platform listens on (default 8080)")
    p.add_argument("--bind", help="Listen address (default: 0.0.0.0 on servers, 127.0.0.1 behind a proxy)")
    p.add_argument("--tls-cert", help="PEM certificate (chain) file for HTTPS served by the platform itself")
    p.add_argument("--tls-key", help="PEM private key file for that certificate")
    proxy = p.add_mutually_exclusive_group()
    proxy.add_argument("--behind-proxy", dest="behind_proxy", action="store_true", default=None,
                       help="An HTTPS reverse proxy (nginx, IIS, a load balancer) sits in front")
    proxy.add_argument("--no-proxy", dest="behind_proxy", action="store_false")
    p.add_argument("--trusted-proxies", help="Proxy IPs/CIDRs allowed to send X-Forwarded-* (required with --behind-proxy)")
    p.add_argument("--database-url", help="Use an existing PostgreSQL 16+ (postgresql://user:pass@host:5432/db)")
    p.add_argument("--redis-url", help="Use an existing Redis (redis://:pass@host:6379/0 or rediss://...)")
    p.set_defaults(func=cmd_server)
    sub.add_parser("supervise").set_defaults(func=cmd_supervise)   # internal: used by start and service managers
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except (postgres.PostgresError, redis_server.RedisError, downloads.DownloadError, RuntimeError) as exc:
        say(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        return 130

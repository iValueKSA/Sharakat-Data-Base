"""Native (Docker-free) runtime: configuration, commands, downloads, processes."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import pytest

from sharakat_runtime import config, downloads, home, procs, services
from sharakat_runtime.postgres import filter_restore_list

ROOT = Path(__file__).resolve().parents[1]


def _layout(tmp_path):
    return home.Layout(tmp_path / "home")


# ---------------------------------------------------------------- home / config
def test_home_override_and_per_os_default(tmp_path):
    assert home.default_home({"SHARAKAT_HOME": str(tmp_path)}) == tmp_path.resolve()
    default = home.default_home({"LOCALAPPDATA": str(tmp_path), "XDG_DATA_HOME": str(tmp_path)})
    assert default.name.lower() == "sharakat"


def test_settings_generate_secrets_once_and_keep_them(tmp_path):
    layout = _layout(tmp_path)
    first, created = config.load_or_create(layout)
    assert created
    for key in config.GENERATED_SECRETS:
        value = first.get(key)
        assert len(value) >= 40 and re.fullmatch(r"[A-Za-z0-9_-]+", value), key   # safe inside URLs
    second, created_again = config.load_or_create(layout)
    assert not created_again
    assert {k: second.get(k) for k in config.GENERATED_SECRETS} == {k: first.get(k) for k in config.GENERATED_SECRETS}
    assert len({first.get(k) for k in config.GENERATED_SECRETS}) == len(config.GENERATED_SECRETS)


def test_user_edits_to_platform_env_are_preserved(tmp_path):
    layout = _layout(tmp_path)
    config.load_or_create(layout)
    text = layout.env_file.read_text(encoding="utf-8").replace("UI_PORT=8080", "UI_PORT=9090")
    layout.env_file.write_text(text, encoding="utf-8")
    settings, _ = config.load_or_create(layout)
    assert settings.ui_url == "http://localhost:9090"


def test_app_environment_has_no_container_hosts_or_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@db:5432/z")   # must not leak through
    monkeypatch.setenv("ADMIN_TOKEN", "legacy")
    settings, _ = config.load_or_create(_layout(tmp_path))
    env = config.app_environment(settings, extra_path=[tmp_path / "pgbin"])
    assert env["ENVIRONMENT"] == "local_user"
    assert env["DATABASE_URL"].startswith("postgresql+psycopg://sharakat_local:")
    assert "@127.0.0.1:54329/sharakat_local" in env["DATABASE_URL"]
    assert env["REDIS_URL"].startswith("redis://:") and "@127.0.0.1:63790/0" in env["REDIS_URL"]
    assert env["SECRET_KEY"] == settings.get("SECRET_KEY")
    assert "ADMIN_TOKEN" not in env
    assert Path(env["BACKUP_DIR"]) == settings.layout.backups_dir
    assert env["MAX_REQUEST_BODY_BYTES"] == str(2 * 1024 * 1024)
    assert env["PATH"].split(os.pathsep)[0] == str(tmp_path / "pgbin")
    joined = json.dumps(env)
    for container_value in ("@db:", "@redis:", '"/backups"', "/source-data", "172.31.240"):
        assert container_value not in joined
    # Same feature flags the one-click Docker local stack used.
    assert env["NATIONAL_UI_ENABLED"] == env["NATIONAL_MAP_ENABLED"] == env["NATIONAL_DASHBOARD_ENABLED"] == "true"


# ---------------------------------------------------------------- service commands
def test_worker_consumes_the_same_queues_as_the_server_unit(tmp_path, monkeypatch):
    # Same queue set the former Compose worker used; server and workstation must agree.
    unit = (ROOT / "deploy" / "systemd" / "sharakat-worker.service").read_text(encoding="utf-8")
    assert re.search(r"--queues=(\S+)", unit).group(1) == services.WORKER_QUEUES == "source_sync,maintenance,notifications"
    settings, _ = config.load_or_create(_layout(tmp_path))
    monkeypatch.setattr(services, "IS_WINDOWS", True)
    assert "--pool=threads" in services.worker_command(settings)
    monkeypatch.setattr(services, "IS_WINDOWS", False)
    assert not any(arg.startswith("--pool") for arg in services.worker_command(settings))


def test_api_binds_loopback_and_ignores_forwarded_headers(tmp_path):
    settings, _ = config.load_or_create(_layout(tmp_path))
    command = services.api_command(settings)
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "8080"
    assert "--no-proxy-headers" in command


def test_beat_state_lives_in_the_runtime_home(tmp_path):
    settings, _ = config.load_or_create(_layout(tmp_path))
    command = services.beat_command(settings)
    assert Path(command[command.index("--schedule") + 1]).parent == settings.layout.run_dir


# ---------------------------------------------------------------- downloads
def _artifact_for(path: Path, **kwargs) -> downloads.Artifact:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return downloads.Artifact("demo", "1", path.resolve().as_uri(), kwargs.pop("sha256", digest), **kwargs)


def test_fetch_verifies_checksum(tmp_path):
    source = tmp_path / "bundle.zip"
    source.write_bytes(b"payload")
    good = downloads.fetch(_artifact_for(source), tmp_path / "dl")
    assert good.read_bytes() == b"payload"
    with pytest.raises(downloads.DownloadError, match="Checksum mismatch"):
        downloads.fetch(_artifact_for(source, sha256="0" * 64), tmp_path / "dl2")
    assert not list((tmp_path / "dl2").glob("*"))   # nothing unverified is left behind


def test_extract_keeps_only_listed_members_and_blocks_traversal(tmp_path):
    archive = tmp_path / "pg.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("pgsql/bin/pg_ctl.exe", "ctl")
        bundle.writestr("pgsql/share/extension/pg_trgm.control", "trgm")
        bundle.writestr("pgsql/pgAdmin 4/huge.bin", "skip")
        bundle.writestr("pgsql/bin/../../../escape.txt", "evil")
    archive.write_bytes(buffer.getvalue())
    artifact = _artifact_for(archive, keep=("pgsql/bin/", "pgsql/share/"), strip="pgsql")
    target = downloads.install_artifact(artifact, tmp_path / "dl", tmp_path / "runtime" / "postgresql")
    assert (target / "bin" / "pg_ctl.exe").read_text() == "ctl"
    assert (target / "share" / "extension" / "pg_trgm.control").is_file()
    assert not (target / "pgAdmin 4").exists()
    assert not (tmp_path / "escape.txt").exists() and not (tmp_path / "runtime" / "escape.txt").exists()
    # Second call is a no-op thanks to the marker.
    (target / "bin" / "pg_ctl.exe").write_text("kept")
    downloads.install_artifact(artifact, tmp_path / "dl", target)
    assert (target / "bin" / "pg_ctl.exe").read_text() == "kept"


def test_every_supported_platform_has_pinned_binaries():
    for os_key in ("windows", "macos"):
        assert ("postgres", os_key, "x64") in downloads.PINNED
    for os_key in ("windows", "linux", "macos"):
        for arch in ("x64", "arm64"):
            artifact = downloads.PINNED[("garnet", os_key, arch)]
            assert artifact.url.startswith("https://") and re.fullmatch(r"[0-9a-f]{64}", artifact.sha256)


# ---------------------------------------------------------------- restore list
def test_restore_list_skips_superuser_only_extension_entries():
    listing = "\n".join([
        ";",
        "; Archive created at 2026-10-28",
        "3; 3079 16385 EXTENSION - pg_trgm",
        "4521; 0 0 COMMENT - EXTENSION pg_trgm",
        "215; 1259 16400 TABLE public opportunities sharakat_local",
        "4522; 0 0 COMMENT public TABLE extension_requests sharakat_local",
        "5000; 0 16400 TABLE DATA public opportunities sharakat_local",
    ])
    kept = filter_restore_list(listing)
    assert "EXTENSION - pg_trgm" not in kept and "COMMENT - EXTENSION" not in kept
    assert "TABLE public opportunities" in kept and "TABLE DATA public opportunities" in kept
    assert "extension_requests" in kept      # a table merely named like an extension is kept


# ---------------------------------------------------------------- processes
def test_spawn_liveness_and_terminate_a_real_process(tmp_path):
    log = tmp_path / "child.log"
    child = procs.spawn([sys.executable, "-c", "import time; print('up', flush=True); time.sleep(120)"],
                        log, dict(os.environ), tmp_path)
    try:
        deadline = time.monotonic() + 20
        while "up" not in log.read_text(errors="replace") and time.monotonic() < deadline:
            time.sleep(0.1)
        assert procs.pid_alive(child.pid)
        procs.terminate(child, timeout=10)
        assert child.poll() is not None
        assert not procs.pid_alive(child.pid)
    finally:
        if child.poll() is None:
            child.kill()


def test_pid_files_round_trip(tmp_path):
    procs.write_pid(tmp_path / "x.pid", 4242)
    assert procs.read_pid(tmp_path / "x.pid") == 4242
    assert procs.read_pid(tmp_path / "missing.pid") is None


# ---------------------------------------------------------------- transfer packages
def test_install_prefers_the_package_it_runs_from(tmp_path, monkeypatch):
    from sharakat_runtime import cli
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    dump = tmp_path / "transfer" / "database" / "own.dump"
    dump.parent.mkdir(parents=True)
    dump.write_bytes(b"dump")
    (tmp_path / "transfer-manifest.json").write_text(json.dumps(
        {"database_backup": {"path": "transfer/database/own.dump", "sha256": "ab"}}), encoding="utf-8")
    assert cli._newest_transfer_dump() == (dump.resolve(), "ab")


def test_transfer_dump_outside_the_package_is_ignored(tmp_path, monkeypatch):
    from sharakat_runtime import cli
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    package = tmp_path / "transfer" / "portable-package-1"
    package.mkdir(parents=True)
    (tmp_path / "secret.dump").write_bytes(b"x")
    (package / "transfer-manifest.json").write_text(json.dumps(
        {"database_backup": {"path": "../../secret.dump", "sha256": ""}}), encoding="utf-8")
    assert cli._newest_transfer_dump() is None


# ---------------------------------------------------------------- application changes
def test_ui_is_served_regardless_of_working_directory(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.chdir(tmp_path)
    client = TestClient(main.app)
    response = client.get("/")
    assert response.status_code == 200 and "<html" in response.text.lower()
    assert client.get("/static/app.js").status_code == 200


def test_request_body_limit_matches_the_removed_nginx(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    client = TestClient(main.app)
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "1024")
    response = client.post("/api/auth/login", content=b"x" * 2048, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    monkeypatch.delenv("MAX_REQUEST_BODY_BYTES")
    assert client.post("/api/auth/login", content=b"x" * 2048,
                       headers={"Content-Type": "application/json"}).status_code != 413


def test_local_user_refuses_to_start_without_secret_key(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setenv("ENVIRONMENT", "local_user")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="local_user requires SECRET_KEY"):
        with TestClient(main.app):
            pass


def test_run_logged_writes_output_to_file_and_returns_exit_code(tmp_path):
    log = tmp_path / "ctl.log"
    code = procs.run_logged([sys.executable, "-c", "import sys; print('daemon-ready'); sys.exit(3)"], log, timeout=60)
    assert code == 3
    assert "daemon-ready" in log.read_text(encoding="utf-8")
    assert procs.tail(log, 1).strip() == "daemon-ready"


def test_garnet_installs_get_the_queue_expiry_workaround(tmp_path):
    settings, _ = config.load_or_create(_layout(tmp_path))
    settings.layout.install_marker.write_text(json.dumps({"redis_engine": "garnet"}), encoding="utf-8")
    assert config.app_environment(settings)["CELERY_DISABLE_QUEUE_EXPIRY"] == "1"
    settings.layout.install_marker.write_text(json.dumps({"redis_engine": "redis"}), encoding="utf-8")
    assert "CELERY_DISABLE_QUEUE_EXPIRY" not in config.app_environment(settings)


def test_celery_queue_expiry_is_unchanged_unless_requested():
    import subprocess
    code = ("import json; from app.celery_app import celery_app as a; "
            "print(json.dumps([a.conf.control_queue_expires, a.conf.event_queue_expires]))")
    default = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                             env={**os.environ, "CELERY_DISABLE_QUEUE_EXPIRY": ""})
    disabled = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                              env={**os.environ, "CELERY_DISABLE_QUEUE_EXPIRY": "1"})
    assert json.loads(default.stdout.strip().splitlines()[-1]) != [None, None]
    assert json.loads(disabled.stdout.strip().splitlines()[-1]) == [None, None]


def test_credentials_file_never_advertises_a_password_that_was_not_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("SHARAKAT_CREDENTIALS_FILE", str(tmp_path / "creds.txt"))
    settings, _ = config.load_or_create(_layout(tmp_path))
    fresh = config.write_credentials_file(settings).read_text(encoding="utf-8")
    assert settings.get("BOOTSTRAP_ADMIN_PASSWORD") in fresh
    restored = config.write_credentials_file(settings, account_preexisted=True).read_text(encoding="utf-8")
    assert settings.get("BOOTSTRAP_ADMIN_PASSWORD") not in restored
    assert "reset-admin-password" in restored


def test_admin_tools_reset_uses_app_hashing_revokes_sessions_and_audits(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    import app.database as database
    from app.models import AuditEvent, Base, User, UserSession
    from app.security import hash_password, utcnow, verify_password
    from sharakat_runtime import admin_tools

    engine = create_engine(f"sqlite:///{tmp_path / 'users.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    with factory.begin() as db:
        user = User(email="admin@local", display_name="Admin", role="admin", password_hash=hash_password("old-password-123"),
                    is_active=True, failed_login_count=7, created_at=utcnow())
        db.add(user)
        db.flush()
        db.add(UserSession(user_id=user.id, token_hash="x" * 64, created_at=utcnow(), expires_at=utcnow(), last_seen_at=utcnow()))
    monkeypatch.setenv("SHARAKAT_NEW_PASSWORD", "brand-new-password-456")
    assert admin_tools.main(["reset-password", "ADMIN@local"]) == 0
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "admin@local"))
        assert verify_password("brand-new-password-456", user.password_hash)
        assert not verify_password("old-password-123", user.password_hash)
        assert user.failed_login_count == 0 and user.is_active
        assert db.scalar(select(UserSession).where(UserSession.user_id == user.id)) is None
        assert db.scalar(select(AuditEvent).where(AuditEvent.event_type == "LOCAL_ADMIN_PASSWORD_RESET")) is not None
    monkeypatch.setenv("SHARAKAT_NEW_PASSWORD", "short")
    with pytest.raises(SystemExit):
        admin_tools.main(["reset-password", "admin@local"])


# ---------------------------------------------------------------- server mode
def _server(tmp_path, **values):
    settings, _ = config.load_or_create(_layout(tmp_path))
    return config.Settings({**settings.values, **values}, settings.layout)


def test_workstation_defaults_are_unchanged(tmp_path):
    settings = _server(tmp_path)
    assert settings.server_mode == "" and settings.bind_address == "127.0.0.1"
    assert settings.ui_url == "http://localhost:8080" and config.validate_server_settings(settings) == []
    env = config.app_environment(settings)
    assert env["ENVIRONMENT"] == "local_user" and env["PUBLIC_BASE_URL"] == "http://localhost:8080"


def test_internal_lan_server_listens_on_all_interfaces_without_hardening(tmp_path):
    settings = _server(tmp_path, SERVER_MODE="internal", PUBLIC_URL="http://srv-01:8080")
    assert config.validate_server_settings(settings) == []
    assert settings.bind_address == "0.0.0.0" and settings.local_url == "http://127.0.0.1:8080"
    env = config.app_environment(settings)
    assert env["ENVIRONMENT"] == "local_user"
    assert env["PUBLIC_BASE_URL"] == "http://srv-01:8080" and env["CORS_ORIGINS"] == "http://srv-01:8080"
    command = services.api_command(settings)
    assert command[command.index("--host") + 1] == "0.0.0.0" and "--no-proxy-headers" in command


def test_production_requires_https_and_switches_on_app_hardening(tmp_path):
    assert config.validate_server_settings(_server(tmp_path, SERVER_MODE="production", PUBLIC_URL="http://x:8080"))
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert.write_text("c"), key.write_text("k")
    settings = _server(tmp_path, SERVER_MODE="production", PUBLIC_URL="https://platform.example.org",
                       TLS_CERT_FILE=str(cert), TLS_KEY_FILE=str(key), UI_PORT="443")
    assert config.validate_server_settings(settings) == []
    env = config.app_environment(settings)
    assert env["ENVIRONMENT"] == "production" and env["CORS_ORIGINS"] == "https://platform.example.org"
    assert env["FORWARDED_ALLOW_IPS"] == "127.0.0.1"
    command = services.api_command(settings)
    assert command[command.index("--ssl-certfile") + 1] == str(cert)
    assert settings.local_url == "https://127.0.0.1:443"


def test_behind_proxy_trusts_only_the_named_proxy(tmp_path):
    bad = _server(tmp_path, SERVER_MODE="production", PUBLIC_URL="https://p.example.org", BEHIND_PROXY="true",
                  FORWARDED_ALLOW_IPS="*")
    assert any("FORWARDED_ALLOW_IPS" in problem for problem in config.validate_server_settings(bad))
    good = _server(tmp_path, SERVER_MODE="production", PUBLIC_URL="https://p.example.org", BEHIND_PROXY="true",
                   FORWARDED_ALLOW_IPS="10.0.0.5")
    assert config.validate_server_settings(good) == [] and good.bind_address == "127.0.0.1"
    command = services.api_command(good)
    assert command[command.index("--forwarded-allow-ips") + 1] == "10.0.0.5" and "--no-proxy-headers" not in command
    assert config.app_environment(good)["FORWARDED_ALLOW_IPS"] == "10.0.0.5"


def test_external_database_and_redis_are_used_as_given(tmp_path):
    settings = _server(tmp_path, EXTERNAL_DATABASE_URL="postgresql+psycopg://app:p%40ss@db.internal:6543/platform",
                       EXTERNAL_REDIS_URL="rediss://:secret@cache.internal:6380/2")
    assert not settings.manages_postgres and not settings.manages_redis
    assert settings.database_params() == {"host": "db.internal", "port": 6543, "user": "app",
                                          "password": "p@ss", "dbname": "platform"}
    env = config.app_environment(settings)
    assert env["DATABASE_URL"].endswith("@db.internal:6543/platform") and env["REDIS_URL"].startswith("rediss://")
    assert env["STAGING_DATABASE_NAME"] == "platform"
    assert config.validate_server_settings(_server(tmp_path, EXTERNAL_DATABASE_URL="mysql://x"))


def test_server_mode_rejects_localhost_public_urls(tmp_path):
    problems = config.validate_server_settings(_server(tmp_path, SERVER_MODE="internal", PUBLIC_URL="http://localhost:8080"))
    assert any("localhost" in problem for problem in problems)

"""PostgreSQL provider: locate/install binaries, own a private cluster, restore.

The cluster lives in <home>/pgdata, listens on 127.0.0.1 only, on a private
port, with scram-sha-256 passwords. It replaces the `db` Compose service
(postgres:16-alpine), including its UTC timezone and C-collation ordering.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import downloads, procs
from .config import DB_NAME, DB_USER, PG_SUPERUSER, Settings
from .home import IS_LINUX, IS_MACOS, IS_WINDOWS, machine_arch, os_key

MIN_MAJOR = 16
EXE = ".exe" if IS_WINDOWS else ""


class PostgresError(RuntimeError):
    pass


def _candidate_bin_dirs(settings: Settings) -> list[Path]:
    candidates: list[Path] = []
    if settings.get("PG_BIN"):
        candidates.append(Path(settings.get("PG_BIN")))
    candidates.append(settings.layout.runtime_dir / "postgresql" / "bin")
    found = shutil.which("pg_ctl")
    if found:
        candidates.append(Path(found).resolve().parent)
    if IS_WINDOWS:
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates += [program_files / "PostgreSQL" / str(v) / "bin" for v in (16, 17, 18)]
    elif IS_MACOS:
        for v in (16, 17, 18):
            candidates += [Path(f"/opt/homebrew/opt/postgresql@{v}/bin"), Path(f"/usr/local/opt/postgresql@{v}/bin"),
                           Path(f"/Applications/Postgres.app/Contents/Versions/{v}/bin")]
    else:
        for v in (16, 17, 18):
            candidates += [Path(f"/usr/lib/postgresql/{v}/bin"), Path(f"/usr/pgsql-{v}/bin")]
        candidates.append(Path("/usr/bin"))
    return candidates


def major_version(bin_dir: Path) -> int | None:
    exe = bin_dir / f"postgres{EXE}"
    if not exe.is_file():
        return None
    try:
        out = procs.run([exe, "--version"], timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+)(?:\.\d+)?", out or "")
    return int(match.group(1)) if match else None


def locate(settings: Settings) -> Path | None:
    """First bin directory with a usable server (>= 16) and client tools."""
    for candidate in _candidate_bin_dirs(settings):
        needed = [f"{name}{EXE}" for name in ("postgres", "initdb", "pg_ctl", "pg_dump", "pg_restore")]
        if all((candidate / name).is_file() for name in needed):
            version = major_version(candidate)
            if version and version >= MIN_MAJOR:
                return candidate
    return None


def install(settings: Settings, log=print) -> Path:
    found = locate(settings)
    if found:
        return found
    artifact = downloads.PINNED.get(("postgres", os_key(), machine_arch()))
    if artifact:
        destination = settings.layout.runtime_dir / "postgresql"
        downloads.install_artifact(artifact, settings.layout.downloads_dir, destination, log)
        found = locate(settings)
        if found:
            return found
        raise PostgresError(f"PostgreSQL binaries were extracted to {destination} but are not usable")
    if IS_LINUX:
        _install_linux_packages(log)
        found = locate(settings)
        if found:
            return found
    raise PostgresError(
        "PostgreSQL 16 or newer was not found and cannot be installed automatically on this system. "
        "Install the PostgreSQL 16 server and contrib packages, or set PG_BIN in "
        f"{settings.layout.env_file} to the directory containing pg_ctl.")


def _sudo() -> list[str]:
    return [] if hasattr(os, "geteuid") and os.geteuid() == 0 else ["sudo"]


def _install_linux_packages(log) -> None:
    """Install PostgreSQL 16 from the official PGDG repository (Debian/Ubuntu)
    or the distribution packages (Fedora/RHEL family). Prompts for sudo."""
    sudo = _sudo()
    if shutil.which("apt-get"):
        log("Installing PostgreSQL 16 from the official PostgreSQL (PGDG) apt repository; sudo may ask for your password.")
        # Don't let the package create and start a system-wide cluster on 5432;
        # the platform runs its own private cluster.
        subprocess.run([*sudo, "mkdir", "-p", "/etc/postgresql-common/createcluster.d"], check=True)
        subprocess.run([*sudo, "sh", "-c", "echo 'create_main_cluster = false' > /etc/postgresql-common/createcluster.d/sharakat.conf"], check=True)
        subprocess.run([*sudo, "apt-get", "install", "-y", "postgresql-common", "ca-certificates"], check=True)
        subprocess.run([*sudo, "/usr/share/postgresql-common/pgdg/apt.postgresql.org.sh", "-y"], check=True)
        subprocess.run([*sudo, "apt-get", "install", "-y", "postgresql-16"], check=True)
    elif shutil.which("dnf"):
        log("Installing PostgreSQL server packages with dnf; sudo may ask for your password.")
        subprocess.run([*sudo, "dnf", "install", "-y", "postgresql-server", "postgresql-contrib"], check=True)
    else:
        raise PostgresError("No supported package manager (apt-get or dnf) found to install PostgreSQL 16.")


def _tool(bin_dir: Path, name: str) -> Path:
    return bin_dir / f"{name}{EXE}"


def _socket_dir(settings: Settings) -> str:
    """Unix socket location (POSIX). Empty disables the socket; TCP on loopback
    is always used by the platform, so this only matters for local tooling."""
    if IS_WINDOWS:
        return ""
    run_dir = settings.layout.run_dir
    # sun_path is limited to ~104 bytes including the socket file name.
    return str(run_dir) if len(str(run_dir)) < 80 else ""


def _env(settings: Settings, password_key: str = "POSTGRES_SUPERUSER_PASSWORD") -> dict:
    env = dict(os.environ)
    env["PGPASSWORD"] = settings.get(password_key)
    env["PGHOST"] = "127.0.0.1"
    env["PGPORT"] = str(settings.int("POSTGRES_PORT"))
    env["PGCONNECT_TIMEOUT"] = "5"
    env.pop("PGDATABASE", None)
    env.pop("PGUSER", None)
    return env


def is_initialized(settings: Settings) -> bool:
    return (settings.layout.pgdata / "PG_VERSION").is_file()


def cluster_major(settings: Settings) -> int | None:
    try:
        return int((settings.layout.pgdata / "PG_VERSION").read_text().strip())
    except (OSError, ValueError):
        return None


def init_cluster(settings: Settings, bin_dir: Path, log=print) -> None:
    pgdata = settings.layout.pgdata
    if is_initialized(settings):
        major = cluster_major(settings)
        binary = major_version(bin_dir)
        if major != binary:
            raise PostgresError(f"The data directory was created by PostgreSQL {major} but the binaries in "
                                f"{bin_dir} are PostgreSQL {binary}. Point PG_BIN at PostgreSQL {major} binaries.")
        return
    if pgdata.exists() and any(pgdata.iterdir()):
        raise PostgresError(f"{pgdata} exists and is not empty but is not a PostgreSQL cluster; refusing to touch it.")
    log("Initialising the private PostgreSQL cluster")
    pgdata.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".pw") as pwfile:
        pwfile.write(settings.get("POSTGRES_SUPERUSER_PASSWORD"))
        pw_path = pwfile.name
    try:
        # C collation + UTF8: same ordering as the postgres:16-alpine image (musl
        # has no locale collation), so ORDER BY results don't change.
        result = procs.run([_tool(bin_dir, "initdb"), "-D", pgdata, "-U", PG_SUPERUSER, f"--pwfile={pw_path}",
                            "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C"],
                           timeout=600, log_path=settings.layout.logs_dir / "postgres-init.log")
    finally:
        os.unlink(pw_path)
    if result.returncode != 0:
        shutil.rmtree(pgdata, ignore_errors=True)
        raise PostgresError("initdb failed; see logs/postgres-init.log\n" + (result.stderr or result.stdout)[-2000:])
    write_server_config(settings)


def write_server_config(settings: Settings) -> None:
    pgdata = settings.layout.pgdata
    socket_dir = _socket_dir(settings).replace("\\", "/").replace("'", "''")
    (pgdata / "sharakat.conf").write_text(
        "# Managed by sharakat_runtime; regenerated on every start.\n"
        "listen_addresses = '127.0.0.1'\n"
        f"port = {settings.int('POSTGRES_PORT')}\n"
        f"unix_socket_directories = '{socket_dir}'\n"
        "timezone = 'UTC'\n"
        "log_timezone = 'UTC'\n"
        "password_encryption = 'scram-sha-256'\n"
        "max_connections = 100\n",
        encoding="utf-8")
    main_conf = pgdata / "postgresql.conf"
    text = main_conf.read_text(encoding="utf-8")
    if "include_if_exists = 'sharakat.conf'" not in text:
        main_conf.write_text(text.rstrip("\n") + "\n\ninclude_if_exists = 'sharakat.conf'\n", encoding="utf-8")


def is_running(settings: Settings, bin_dir: Path) -> bool:
    if not is_initialized(settings):
        return False
    result = procs.run([_tool(bin_dir, "pg_ctl"), "-D", settings.layout.pgdata, "status"], timeout=30)
    return result.returncode == 0


def start(settings: Settings, bin_dir: Path, log=print) -> None:
    if is_running(settings, bin_dir):
        return
    write_server_config(settings)
    _assert_port_free(settings.int("POSTGRES_PORT"), "PostgreSQL")
    server_log = settings.layout.logs_dir / "postgres.log"
    code = procs.run_logged([_tool(bin_dir, "pg_ctl"), "-D", settings.layout.pgdata, "-l", server_log,
                             "-w", "-t", "120", "start"], settings.layout.logs_dir / "postgres-ctl.log", timeout=180)
    if code != 0:
        raise PostgresError("PostgreSQL did not start; see logs/postgres.log\n" + procs.tail(server_log))
    wait_ready(settings)


def stop(settings: Settings, bin_dir: Path) -> None:
    if not is_running(settings, bin_dir):
        return
    procs.run_logged([_tool(bin_dir, "pg_ctl"), "-D", settings.layout.pgdata, "-m", "fast", "-w", "-t", "120", "stop"],
                     settings.layout.logs_dir / "postgres-ctl.log", timeout=180)


def _assert_port_free(port: int, what: str) -> None:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise PostgresError(f"Port {port} needed by {what} is already in use by another program. "
                                "Change the port in platform.env or stop that program.")


def _connect(settings: Settings, dbname: str = "postgres", superuser: bool = True):
    import psycopg
    return psycopg.connect(host="127.0.0.1", port=settings.int("POSTGRES_PORT"), dbname=dbname,
                           user=PG_SUPERUSER if superuser else DB_USER,
                           password=settings.get("POSTGRES_SUPERUSER_PASSWORD" if superuser else "POSTGRES_PASSWORD"),
                           connect_timeout=5, autocommit=True)


def wait_ready(settings: Settings, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            with _connect(settings) as conn:
                conn.execute("SELECT 1")
            return
        except Exception as exc:   # noqa: BLE001 - any connection failure means "not ready yet"
            last = exc
            time.sleep(1)
    raise PostgresError(f"PostgreSQL is not accepting connections: {last}")


def ensure_database(settings: Settings) -> None:
    """Create/refresh the application role and database (idempotent)."""
    from psycopg import sql
    with _connect(settings) as conn:
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (DB_USER,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        conn.execute(sql.SQL(verb + " ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(DB_USER), sql.Literal(settings.get("POSTGRES_PASSWORD"))))
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (DB_NAME,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(
                sql.Identifier(DB_NAME), sql.Identifier(DB_USER)))
    with _connect(settings, DB_NAME) as conn:
        # Migration 0014 creates pg_trgm; create it here as superuser so neither
        # migrations nor restores depend on the app role's extension rights.
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def reset_database(settings: Settings) -> None:
    """Drop and recreate the app database. Only used to discard a restore this
    same install run just performed (never on user-created data)."""
    from psycopg import sql
    with _connect(settings) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(DB_NAME)))
    ensure_database(settings)


def _connect_app(settings: Settings):
    """Connect as the application role to the application database (local or external)."""
    import psycopg
    params = settings.database_params()
    return psycopg.connect(host=params["host"], port=params["port"], dbname=params["dbname"],
                           user=params["user"], password=params["password"], connect_timeout=10, autocommit=True)


def wait_app_database(settings: Settings, timeout: float = 120) -> None:
    """Wait until the (external) application database accepts connections."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            with _connect_app(settings) as conn:
                conn.execute("SELECT 1")
            return
        except Exception as exc:   # noqa: BLE001
            last = exc
            time.sleep(2)
    raise PostgresError(f"The PostgreSQL database in EXTERNAL_DATABASE_URL is not reachable: {last}")


def database_is_empty(settings: Settings) -> bool:
    with _connect_app(settings) as conn:
        count = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"
        ).fetchone()[0]
    return count == 0


# `pg_restore --list` TOC lines look like "3; 3079 16385 EXTENSION - pg_trgm"
# and "4521; 0 0 COMMENT - EXTENSION pg_trgm".
_EXTENSION_ENTRY = re.compile(r"^\s*\d+;\s*\d+\s+\d+\s+(EXTENSION\s+-|COMMENT\s+-\s+EXTENSION)\s")


def filter_restore_list(listing: str) -> str:
    """Drop extension (and extension-comment) entries from a restore list.

    Only the superuser may create extensions or comment on them; the restore
    runs as the application role and ensure_database() already created pg_trgm.
    """
    kept = [line for line in listing.splitlines() if not _EXTENSION_ENTRY.match(line)]
    return "\n".join(kept) + "\n"


def restore(settings: Settings, bin_dir: Path, dump: Path, log=print) -> None:
    """Restore a pg_dump custom-format backup into the (empty) app database."""
    if not dump.is_file():
        raise PostgresError(f"Backup file not found: {dump}")
    if not database_is_empty(settings):
        raise PostgresError("The platform database already contains data; refusing to restore over it. "
                            "Restore only into a fresh installation.")
    params = settings.database_params()
    env = dict(os.environ, PGPASSWORD=params["password"], PGCONNECT_TIMEOUT="10")
    listing = procs.run([_tool(bin_dir, "pg_restore"), "--list", dump], env=env, timeout=600)
    if listing.returncode != 0:
        raise PostgresError("The backup file is not a valid PostgreSQL custom-format dump:\n" + listing.stderr[-2000:])
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".list") as handle:
        handle.write(filter_restore_list(listing.stdout))
        list_path = handle.name
    try:
        log(f"Restoring {dump.name} (this can take several minutes)")
        result = procs.run([_tool(bin_dir, "pg_restore"), "--no-owner", "--no-acl", "--exit-on-error",
                            "--single-transaction", "-L", list_path, "-h", params["host"],
                            "-p", params["port"], "-U", params["user"], "-d", params["dbname"], dump],
                           env=env, timeout=7200, log_path=settings.layout.logs_dir / "restore.log")
    finally:
        os.unlink(list_path)
    if result.returncode != 0:
        raise PostgresError("Restore failed (nothing was committed); see logs/restore.log\n" + result.stderr[-2000:])

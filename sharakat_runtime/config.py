"""Generated, private runtime configuration and the environment each process gets.

The application keeps reading exactly the environment variables it reads under
Docker Compose (same names, same meaning). Only the values change: hosts are
loopback addresses instead of Compose service names, and paths point into the
per-user runtime home instead of container mount points.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from .home import IS_WINDOWS, PROJECT_ROOT, Layout, restrict_to_owner

DB_NAME = "sharakat_local"      # local_database_setup.py refuses any other name
DB_USER = "sharakat_local"
PG_SUPERUSER = "sharakat_admin"
CREDENTIALS_FILE = PROJECT_ROOT / "Local Admin Credentials.txt"

# Defaults written into a fresh platform.env. Users may edit that file.
DEFAULTS = {
    "UI_PORT": "8080",
    "POSTGRES_PORT": "54329",     # private port: never collides with another PostgreSQL install
    "REDIS_PORT": "63790",
    # Same flag values the one-click local stack (docker-compose.local.yml) used.
    "NATIONAL_UI_ENABLED": "true",
    "NATIONAL_DASHBOARD_ENABLED": "true",
    "NATIONAL_MAP_ENABLED": "true",
    "RCU_SCHEDULED_SYNC_ENABLED": "false",
    "WORKER_CONCURRENCY": "4",
    "AUTO_MIGRATE": "true",
    "BOOTSTRAP_ADMIN_EMAIL": "admin@local",
}
GENERATED_SECRETS = ("POSTGRES_PASSWORD", "POSTGRES_SUPERUSER_PASSWORD", "REDIS_PASSWORD",
                     "SECRET_KEY", "BOOTSTRAP_ADMIN_PASSWORD")
# Optional settings passed through from platform.env to the app unchanged.
PASS_THROUGH = (
    "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TLS", "ALERT_RECIPIENTS",
    "DEADLINE_ALERT_DAYS", "SOURCE_JOB_TIMEOUT_SECONDS", "SOURCE_JOB_SOFT_TIMEOUT_SECONDS",
    "SOURCE_QUEUE_STALE_SECONDS", "BACKUP_RETAIN_DAILY", "BACKUP_RETAIN_WEEKLY", "BACKUP_RETAIN_MONTHLY",
    "DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_TIMEOUT_SECONDS", "SLOW_QUERY_SECONDS",
    "FURAS_NATIONAL_ENUMERATION_ENABLED", "FURAS_NATIONAL_REMOVAL_RECONCILIATION_ENABLED",
    "DOCUMENT_COLLECTION_ENGINE_ENABLED", "DOCUMENT_COLLECTION_MANUAL_ENABLED",
    "DOCUMENT_COLLECTION_SCHEDULED_ENABLED", "DOCUMENT_COLLECTION_STAGING_ENABLED",
    "DOCUMENT_COLLECTION_AUTO_APPROVAL_ENABLED", "DOCUMENT_COLLECTION_AUTO_PUBLICATION_ENABLED",
    "LOCATION_ACCEPTANCE_THRESHOLD", "DQ_RUN_RETENTION_DAYS", "DQ_RUN_RETENTION_MAX_RUNS",
    "PORTABLE_TRANSFER_TEST_MODE",
)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Sharakat native runtime settings. Generated once; edit with care.",
             "# Secrets below are local to this computer. Never commit or share this file."]
    lines += [f"{key}={value}" for key, value in values.items()]
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    restrict_to_owner(temporary)
    temporary.replace(path)
    restrict_to_owner(path)


def _secret() -> str:
    # URL-safe alphabet, so it can be embedded in DATABASE_URL / REDIS_URL unescaped.
    return secrets.token_urlsafe(32)


@dataclass
class Settings:
    values: dict[str, str]
    layout: Layout

    def get(self, key: str) -> str:
        return self.values.get(key, DEFAULTS.get(key, ""))

    def int(self, key: str) -> int:
        return int(self.get(key))

    def flag(self, key: str) -> bool:
        return self.get(key).strip().casefold() in ("1", "true", "yes", "on")

    # ----- server mode (see docs/runbooks/server.md) -----
    @property
    def server_mode(self) -> str:
        """'' (workstation), 'internal' (LAN, HTTP), 'staging' or 'production' (HTTPS)."""
        return self.get("SERVER_MODE").strip().lower()

    @property
    def protected(self) -> bool:
        return self.server_mode in ("staging", "production")

    @property
    def tls_enabled(self) -> bool:
        return bool(self.get("TLS_CERT_FILE") and self.get("TLS_KEY_FILE"))

    @property
    def behind_proxy(self) -> bool:
        return self.flag("BEHIND_PROXY")

    @property
    def bind_address(self) -> str:
        if self.get("BIND_ADDRESS"):
            return self.get("BIND_ADDRESS")
        # Workstation and proxied servers stay on loopback; servers that face
        # users directly listen on every interface.
        return "0.0.0.0" if self.server_mode and not self.behind_proxy else "127.0.0.1"

    @property
    def ui_url(self) -> str:
        """The address people open in their browser."""
        return (self.get("PUBLIC_URL") or f"http://localhost:{self.int('UI_PORT')}").rstrip("/")

    @property
    def local_url(self) -> str:
        """How processes on this machine reach the API (health checks, verify)."""
        host = self.bind_address
        if host in ("0.0.0.0", "::", ""):
            host = "127.0.0.1"
        return f"{'https' if self.tls_enabled else 'http'}://{host}:{self.int('UI_PORT')}"

    @property
    def manages_postgres(self) -> bool:
        return not self.get("EXTERNAL_DATABASE_URL")

    @property
    def manages_redis(self) -> bool:
        return not self.get("EXTERNAL_REDIS_URL")

    @property
    def database_url(self) -> str:
        if self.get("EXTERNAL_DATABASE_URL"):
            return self.get("EXTERNAL_DATABASE_URL")
        return (f"postgresql+psycopg://{DB_USER}:{self.get('POSTGRES_PASSWORD')}"
                f"@127.0.0.1:{self.int('POSTGRES_PORT')}/{DB_NAME}")

    @property
    def redis_url(self) -> str:
        if self.get("EXTERNAL_REDIS_URL"):
            return self.get("EXTERNAL_REDIS_URL")
        return f"redis://:{self.get('REDIS_PASSWORD')}@127.0.0.1:{self.int('REDIS_PORT')}/0"

    def database_params(self) -> dict:
        """host/port/user/password/dbname of the application database (local or external)."""
        from urllib.parse import unquote, urlsplit
        url = urlsplit(self.database_url.replace("postgresql+psycopg://", "postgresql://", 1))
        return {"host": url.hostname or "127.0.0.1", "port": url.port or 5432,
                "user": unquote(url.username or ""), "password": unquote(url.password or ""),
                "dbname": (url.path or "/").lstrip("/") or DB_NAME}


SERVER_MODES = ("", "internal", "staging", "production")


def validate_server_settings(settings: Settings) -> list[str]:
    """Problems that would stop (or silently weaken) a server deployment."""
    problems = []
    mode = settings.server_mode
    if mode not in SERVER_MODES:
        return [f"SERVER_MODE must be one of: internal, staging, production (or empty), not {mode!r}"]
    public = settings.get("PUBLIC_URL")
    if mode and not public:
        problems.append("Server mode needs PUBLIC_URL: the address users will open, e.g. http://srv-name:8080")
    if public and not public.startswith(("http://", "https://")):
        problems.append("PUBLIC_URL must start with http:// or https://")
    listens_on_network = settings.bind_address not in ("127.0.0.1", "::1", "localhost")
    if public and mode and listens_on_network and any(name in public for name in ("localhost", "127.0.0.1")):
        problems.append("PUBLIC_URL points at localhost; other computers can't open that. Use the server's name or IP.")
    if settings.protected:
        if not public.startswith("https://"):
            problems.append(f"{mode} requires an https:// PUBLIC_URL")
        if not settings.tls_enabled and not settings.behind_proxy:
            problems.append(f"{mode} needs HTTPS: set TLS_CERT_FILE and TLS_KEY_FILE, or BEHIND_PROXY=true "
                            "with an HTTPS reverse proxy in front")
    if settings.get("TLS_CERT_FILE") or settings.get("TLS_KEY_FILE"):
        for key in ("TLS_CERT_FILE", "TLS_KEY_FILE"):
            if not settings.get(key) or not Path(settings.get(key)).is_file():
                problems.append(f"{key} is missing or not a readable file")
        if public and not public.startswith("https://"):
            problems.append("TLS is configured, so PUBLIC_URL should start with https://")
    if settings.behind_proxy:
        trusted = [ip.strip() for ip in settings.get("FORWARDED_ALLOW_IPS").split(",") if ip.strip()]
        if not trusted or "*" in trusted:
            problems.append("BEHIND_PROXY needs FORWARDED_ALLOW_IPS: the exact proxy address(es), never *")
    external_db = settings.get("EXTERNAL_DATABASE_URL")
    if external_db and not external_db.startswith(("postgresql://", "postgresql+psycopg://")):
        problems.append("EXTERNAL_DATABASE_URL must be a postgresql:// URL")
    external_redis = settings.get("EXTERNAL_REDIS_URL")
    if external_redis and not external_redis.startswith(("redis://", "rediss://")):
        problems.append("EXTERNAL_REDIS_URL must be a redis:// or rediss:// URL")
    return problems


def load_or_create(layout: Layout) -> tuple[Settings, bool]:
    """Return settings, generating platform.env with fresh secrets on first use."""
    layout.ensure()
    existing = parse_env_file(layout.env_file)
    created = not existing
    values = dict(DEFAULTS)
    values.update(existing)
    for key in GENERATED_SECRETS:
        if not values.get(key):
            values[key] = _secret()
    if values != existing:
        write_env_file(layout.env_file, values)
    return Settings(values, layout), created


def load(layout: Layout) -> Settings:
    values = parse_env_file(layout.env_file)
    if not values:
        raise RuntimeError(f"Platform is not installed yet (missing {layout.env_file}). Run the installer first.")
    return Settings({**DEFAULTS, **values}, layout)


def redis_engine_kind(settings: Settings) -> str:
    """'garnet' or 'redis': as recorded at install time, else the per-OS default."""
    import json
    try:
        recorded = json.loads(settings.layout.install_marker.read_text(encoding="utf-8")).get("redis_engine")
    except (OSError, ValueError):
        recorded = None
    if recorded in ("garnet", "redis"):
        return recorded
    choice = (settings.get("REDIS_ENGINE") or "auto").lower()
    if choice in ("garnet", "redis"):
        return choice
    return "garnet" if IS_WINDOWS else "redis"


def app_environment(settings: Settings, extra_path: list[Path] | None = None) -> dict[str, str]:
    """Environment for the API, worker, beat, migrations and setup scripts.

    Mirrors the api/worker/scheduler environment of docker-compose.yml plus the
    docker-compose.local.yml overlay, with host-native values.
    """
    layout = settings.layout
    port = settings.int("UI_PORT")
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in ("DATABASE_URL", "REDIS_URL", "SECRET_KEY", "ENVIRONMENT", "ENV", "ADMIN_TOKEN")}
    if settings.server_mode:
        origins = [settings.ui_url]
    else:
        origins = [f"http://localhost:{port}", f"http://127.0.0.1:{port}"]
    env.update({
        # Workstations and internal (LAN, HTTP) servers run as local_user. Staging
        # and production switch on the app's own hardening: Secure cookies, HSTS,
        # generic error bodies and the startup guards in app/main.py.
        "ENVIRONMENT": settings.server_mode if settings.protected else "local_user",
        "DATABASE_URL": settings.database_url,
        "REDIS_URL": settings.redis_url,
        "SECRET_KEY": settings.get("SECRET_KEY"),
        "PUBLIC_BASE_URL": settings.ui_url,
        "CORS_ORIGINS": ",".join(origins),
        # Only consulted when uvicorn runs with --proxy-headers (BEHIND_PROXY).
        "FORWARDED_ALLOW_IPS": settings.get("FORWARDED_ALLOW_IPS") if settings.behind_proxy else "127.0.0.1",
        "STAGING_DATABASE_NAME": settings.database_params()["dbname"],
        "BOOTSTRAP_ADMIN_EMAIL": settings.get("BOOTSTRAP_ADMIN_EMAIL"),
        "BOOTSTRAP_ADMIN_PASSWORD": settings.get("BOOTSTRAP_ADMIN_PASSWORD"),
        "BACKUP_DIR": str(layout.backups_dir),
        "ATTACHMENT_DIR": str(layout.attachments_dir),
        "LOCAL_SETUP_MARKER": "local_setup_state",
        "LOCAL_EXPECTED_DATABASE": DB_NAME,
        "LOCAL_SQLITE_PATH": str(PROJECT_ROOT / "data" / "al-ahsa-live.db"),
        # nginx enforced client_max_body_size 2m in front of the API.
        "MAX_REQUEST_BODY_BYTES": str(2 * 1024 * 1024),
        "SYNC_ON_STARTUP": "false",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    if redis_engine_kind(settings) == "garnet":
        env["CELERY_DISABLE_QUEUE_EXPIRY"] = "1"   # see app/celery_app.py
    for key in ("NATIONAL_UI_ENABLED", "NATIONAL_DASHBOARD_ENABLED", "NATIONAL_MAP_ENABLED",
                "RCU_SCHEDULED_SYNC_ENABLED", *PASS_THROUGH):
        if settings.get(key) != "":
            env[key] = settings.get(key)
    if extra_path:
        env["PATH"] = os.pathsep.join([*(str(p) for p in extra_path), env.get("PATH", "")])
    return env


def write_credentials_file(settings: Settings, account_preexisted: bool = False) -> Path:
    """Write the local admin sign-in file.

    When restored data already contains the bootstrap e-mail, the app keeps that
    account and its existing password (it never overwrites users), so the file
    must not advertise the generated password as working.
    """
    email = settings.get("BOOTSTRAP_ADMIN_EMAIL")
    if account_preexisted:
        content = (
            "Al-Ahsa Investment Platform - Local Admin\n\n"
            f"Email: {email}\n"
            "Password: the SAME password this account had on the previous computer\n\n"
            "This account came with the restored data, so its password was kept.\n"
            "If you don't have it, set a new one (the platform keeps running):\n"
            "  Windows:      scripts\\native\\bootstrap.ps1 reset-admin-password\n"
            "  Linux/macOS:  bash sharakat.sh reset-admin-password\n"
            "The new password is then written to this file.\n"
        )
    else:
        content = (
            "Al-Ahsa Investment Platform - Local Admin\n\n"
            f"Email: {email}\n"
            f"Password: {settings.get('BOOTSTRAP_ADMIN_PASSWORD')}\n\n"
            "This password was generated for this computer. Keep this file private.\n"
        )
    # SHARAKAT_CREDENTIALS_FILE lets tests (and unusual setups) keep it elsewhere.
    target = Path(os.environ.get("SHARAKAT_CREDENTIALS_FILE") or CREDENTIALS_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\r\n" if IS_WINDOWS else "\n")
    restrict_to_owner(target)
    return target

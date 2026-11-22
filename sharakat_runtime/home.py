"""Per-OS locations for everything the runtime owns (data, logs, binaries)."""
from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "Sharakat"

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def default_home(environ=None) -> Path:
    """Where runtime state lives unless SHARAKAT_HOME overrides it.

    Windows: %LOCALAPPDATA%\\Sharakat   (per-user, not roamed, no admin rights)
    macOS:   ~/Library/Application Support/Sharakat
    Linux:   $XDG_DATA_HOME/sharakat or ~/.local/share/sharakat
    """
    env = os.environ if environ is None else environ
    if env.get("SHARAKAT_HOME"):
        return Path(env["SHARAKAT_HOME"]).expanduser().resolve()
    if IS_WINDOWS:
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    if IS_MACOS:
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = env.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME.lower()


def machine_arch() -> str:
    """Normalised CPU architecture: 'x64' or 'arm64'."""
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64", "x64"):
        return "x64"
    if machine in ("arm64", "aarch64", "armv8l"):
        return "arm64"
    return machine


def os_key() -> str:
    if IS_WINDOWS:
        return "windows"
    if IS_MACOS:
        return "macos"
    if IS_LINUX:
        return "linux"
    return sys.platform


@dataclass(frozen=True)
class Layout:
    root: Path

    @property
    def config_dir(self) -> Path: return self.root / "config"
    @property
    def env_file(self) -> Path: return self.config_dir / "platform.env"
    @property
    def runtime_dir(self) -> Path: return self.root / "runtime"      # downloaded binaries
    @property
    def downloads_dir(self) -> Path: return self.root / "downloads"
    @property
    def pgdata(self) -> Path: return self.root / "pgdata"
    @property
    def redis_dir(self) -> Path: return self.root / "redis"
    @property
    def backups_dir(self) -> Path: return self.root / "backups"
    @property
    def attachments_dir(self) -> Path: return self.root / "attachments"
    @property
    def logs_dir(self) -> Path: return self.root / "logs"
    @property
    def run_dir(self) -> Path: return self.root / "run"               # pid files, state, sockets
    @property
    def state_file(self) -> Path: return self.run_dir / "supervisor-state.json"
    @property
    def stop_request(self) -> Path: return self.run_dir / "stop.request"
    @property
    def supervisor_pid(self) -> Path: return self.run_dir / "supervisor.pid"
    @property
    def install_marker(self) -> Path: return self.config_dir / "installed.json"

    def ensure(self) -> None:
        for directory in (self.config_dir, self.runtime_dir, self.downloads_dir, self.redis_dir,
                          self.backups_dir, self.attachments_dir, self.logs_dir, self.run_dir):
            directory.mkdir(parents=True, exist_ok=True)
        restrict_to_owner(self.config_dir)


def restrict_to_owner(path: Path) -> None:
    """Best-effort owner-only permissions for directories/files holding secrets."""
    try:
        if IS_WINDOWS:
            import subprocess
            user = os.environ.get("USERNAME")
            if user:
                # Drop inherited ACEs, grant full control to the current user only.
                subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F" if path.is_dir() else f"{user}:F"],
                               check=False, capture_output=True)
        else:
            path.chmod(0o700 if path.is_dir() else 0o600)
    except OSError:
        pass


def layout(environ=None) -> Layout:
    return Layout(default_home(environ))

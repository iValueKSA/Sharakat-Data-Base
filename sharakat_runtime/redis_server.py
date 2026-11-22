"""Redis-protocol server provider (replaces the `redis` Compose service).

Engines:
  * ``redis``  – redis-server / valkey-server from the OS (Linux, macOS).
  * ``garnet`` – Microsoft Garnet (MIT), pinned + checksum-verified; used on
                 Windows, where no official Redis server exists, and as a
                 fallback elsewhere. Garnet builds need a .NET 10 runtime, which
                 is installed privately under the runtime directory.

Either way the server binds to 127.0.0.1 only, requires a generated password
and persists with an append-only file, like the Compose service did.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import downloads, procs
from .config import Settings
from .home import IS_LINUX, IS_MACOS, IS_WINDOWS, machine_arch, os_key


class RedisError(RuntimeError):
    pass


@dataclass
class Engine:
    kind: str                 # "redis" | "garnet"
    executable: Path
    env: dict

    def command(self, settings: Settings) -> list[str]:
        data_dir = settings.layout.redis_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        port = str(settings.int("REDIS_PORT"))
        password = settings.get("REDIS_PASSWORD")
        if self.kind == "redis":
            return [str(self.executable), "--bind", "127.0.0.1", "--port", port, "--protected-mode", "yes",
                    "--requirepass", password, "--appendonly", "yes", "--dir", str(data_dir), "--daemonize", "no"]
        args = [str(self.executable), "--bind", "127.0.0.1", "--port", port,
                "--auth", "Password", "--password", password,
                "--lua",                                   # the app's lock release uses EVAL
                "--aof", "--recover",
                # AOF and checkpoints live under checkpointdir. (--logdir is only
                # valid with --storage-tier, which the platform doesn't use.)
                "--checkpointdir", str(data_dir / "checkpoints")]
        extra = settings.get("GARNET_EXTRA_ARGS")
        if extra:
            args += shlex.split(extra, posix=not IS_WINDOWS)
        return args


def _native_redis() -> Path | None:
    for name in ("redis-server", "valkey-server"):
        found = shutil.which(name)
        if found:
            return Path(found)
    for candidate in ("/opt/homebrew/bin/redis-server", "/usr/local/bin/redis-server", "/usr/bin/redis-server",
                      "/usr/bin/valkey-server"):
        if Path(candidate).is_file():
            return Path(candidate)
    return None


def _garnet_exe(settings: Settings) -> Path:
    return settings.layout.runtime_dir / "garnet" / ("GarnetServer.exe" if IS_WINDOWS else "GarnetServer")


def _dotnet_root(settings: Settings) -> Path:
    return settings.layout.runtime_dir / "dotnet"


def _has_dotnet10(root: Path) -> bool:
    shared = root / "shared" / "Microsoft.NETCore.App"
    return shared.is_dir() and any(child.name.startswith(downloads.DOTNET_CHANNEL + ".") for child in shared.iterdir())


def _install_dotnet(settings: Settings, log) -> Path:
    root = _dotnet_root(settings)
    if _has_dotnet10(root):
        return root
    log("Installing a private .NET 10 runtime for Garnet (official Microsoft installer, no admin rights)")
    root.mkdir(parents=True, exist_ok=True)
    script_url = downloads.DOTNET_INSTALL_PS1 if IS_WINDOWS else downloads.DOTNET_INSTALL_SH
    script = settings.layout.downloads_dir / Path(script_url).name
    import urllib.request
    script.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(script_url, headers={"User-Agent": "sharakat-runtime"}), timeout=60) as response:
        script.write_bytes(response.read())
    if IS_WINDOWS:
        args = ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                "-Channel", downloads.DOTNET_CHANNEL, "-Runtime", "dotnet", "-InstallDir", str(root), "-NoPath"]
    else:
        args = ["bash", str(script), "--channel", downloads.DOTNET_CHANNEL, "--runtime", "dotnet",
                "--install-dir", str(root), "--no-path"]
    result = procs.run(args, timeout=1800, log_path=settings.layout.logs_dir / "dotnet-install.log")
    if result.returncode != 0 or not _has_dotnet10(root):
        raise RedisError("Installing the .NET 10 runtime failed; see logs/dotnet-install.log")
    return root


def _install_garnet(settings: Settings, log) -> Engine:
    artifact = downloads.PINNED.get(("garnet", os_key(), machine_arch()))
    if not artifact:
        raise RedisError(f"No Garnet build is pinned for {os_key()}/{machine_arch()}")
    downloads.install_artifact(artifact, settings.layout.downloads_dir, settings.layout.runtime_dir / "garnet", log)
    exe = _garnet_exe(settings)
    if not IS_WINDOWS:
        exe.chmod(0o755)
    dotnet = _install_dotnet(settings, log)
    return Engine("garnet", exe, {"DOTNET_ROOT": str(dotnet), "DOTNET_CLI_TELEMETRY_OPTOUT": "1"})


def _install_native_redis(log) -> None:
    sudo = [] if hasattr(os, "geteuid") and os.geteuid() == 0 else ["sudo"]
    if IS_MACOS and shutil.which("brew"):
        log("Installing Redis with Homebrew")
        subprocess.run(["brew", "install", "redis"], check=True)
    elif IS_LINUX and shutil.which("apt-get"):
        log("Installing redis-server with apt; sudo may ask for your password.")
        subprocess.run([*sudo, "apt-get", "install", "-y", "redis-server"], check=True)
        # The package starts a system-wide instance on 6379; the platform runs its own.
        subprocess.run([*sudo, "systemctl", "disable", "--now", "redis-server"], check=False)
    elif IS_LINUX and shutil.which("dnf"):
        log("Installing valkey with dnf; sudo may ask for your password.")
        if subprocess.run([*sudo, "dnf", "install", "-y", "valkey"]).returncode != 0:
            subprocess.run([*sudo, "dnf", "install", "-y", "redis"], check=True)


def resolve(settings: Settings, install: bool = False, log=print) -> Engine:
    """Pick the engine per REDIS_ENGINE (auto|redis|garnet), installing it if asked."""
    choice = (settings.get("REDIS_ENGINE") or "auto").lower()
    if choice not in ("auto", "redis", "garnet"):
        raise RedisError("REDIS_ENGINE must be auto, redis or garnet")
    if choice == "redis" or (choice == "auto" and not IS_WINDOWS):
        native = _native_redis()
        if not native and install:
            try:
                _install_native_redis(log)
            except (OSError, subprocess.CalledProcessError) as exc:
                if choice == "redis":
                    raise RedisError(f"Could not install Redis: {exc}") from exc
                log(f"Native Redis could not be installed ({exc}); using Garnet instead.")
            native = _native_redis()
        if native:
            return Engine("redis", native, {})
        if choice == "redis":
            raise RedisError("redis-server/valkey-server not found. Install Redis 7 or set REDIS_ENGINE=garnet.")
    if install:
        return _install_garnet(settings, log)
    exe = _garnet_exe(settings)
    if not exe.is_file():
        raise RedisError("Garnet is not installed yet. Run the installer first.")
    dotnet = _dotnet_root(settings)
    return Engine("garnet", exe, {"DOTNET_ROOT": str(dotnet), "DOTNET_CLI_TELEMETRY_OPTOUT": "1"})


def client(settings: Settings):
    import redis
    return redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)


def ping(settings: Settings) -> bool:
    try:
        return bool(client(settings).ping())
    except Exception:   # noqa: BLE001
        return False


def wait_ready(settings: Settings, proc: subprocess.Popen | None = None, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ping(settings):
            return
        if proc is not None and proc.poll() is not None:
            raise RedisError(f"The Redis-protocol server exited with code {proc.returncode}; see logs/redis.log")
        time.sleep(0.5)
    raise RedisError("The Redis-protocol server did not answer PING in time; see logs/redis.log")


def shutdown(settings: Settings) -> None:
    """Graceful stop through the protocol (flushes the AOF)."""
    try:
        client(settings).shutdown()
    except Exception:   # noqa: BLE001 - the connection drops when the server exits
        pass


def port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def engine_env(engine: Engine) -> dict:
    env = dict(os.environ)
    env.update(engine.env)
    return env

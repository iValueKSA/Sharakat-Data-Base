"""Cross-platform process primitives: spawn with log files, liveness, stop.

All OS-specific process handling lives here so the supervisor stays portable.
Graceful shutdown is done through each service's own protocol where possible
(pg_ctl stop, Redis SHUTDOWN, Celery remote shutdown); this module provides the
fallback terminate/kill path.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from .home import IS_WINDOWS

if IS_WINDOWS:
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def popen_kwargs(detached: bool = False) -> dict:
    """Keep children out of the launcher's console/terminal session so closing
    the window that started the platform doesn't kill it."""
    if IS_WINDOWS:
        flags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        if detached:
            flags |= CREATE_BREAKAWAY_FROM_JOB
        return {"creationflags": flags}
    return {"start_new_session": True}


def spawn(args: list[str], log_path: Path, env: dict, cwd: Path, detached: bool = False) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab", buffering=0)
    log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} starting: {' '.join(map(str, args))}\n".encode())
    kwargs = popen_kwargs(detached)
    try:
        return subprocess.Popen([str(a) for a in args], stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env=env, cwd=str(cwd), **kwargs)
    except OSError:
        if IS_WINDOWS and detached:
            # Breakaway is refused inside some job objects; fall back without it.
            kwargs["creationflags"] &= ~CREATE_BREAKAWAY_FROM_JOB
            return subprocess.Popen([str(a) for a in args], stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=env, cwd=str(cwd), **kwargs)
        raise
    finally:
        log.close()   # the child holds its own handle


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259                          # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate(proc_or_pid, timeout: float = 20.0) -> None:
    """Stop a process (and, on POSIX, its process group); escalate to kill."""
    pid = proc_or_pid.pid if isinstance(proc_or_pid, subprocess.Popen) else int(proc_or_pid)
    if not pid_alive(pid):
        return
    if IS_WINDOWS:
        # No portable graceful signal for windowless processes on Windows;
        # services that need a graceful stop get it through their own protocol
        # before this fallback runs. /T includes child processes.
        subprocess.run(["taskkill", "/PID", str(pid), "/T"], capture_output=True, check=False)
        if _wait_gone(pid, min(timeout, 5)):
            return
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
        _wait_gone(pid, 5)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    if _wait_gone(pid, timeout, proc_or_pid):
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    _wait_gone(pid, 5, proc_or_pid)


def _wait_gone(pid: int, timeout: float, proc=None) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if isinstance(proc, subprocess.Popen):
            if proc.poll() is not None:
                return True
        elif not pid_alive(pid):
            return True
        time.sleep(0.25)
    return isinstance(proc, subprocess.Popen) and proc.poll() is not None or not pid_alive(pid)


def write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid), encoding="ascii")


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def run_logged(args: list, log_path: Path, env: dict | None = None, timeout: float | None = None) -> int:
    """Run a command whose children outlive it (e.g. `pg_ctl start`).

    Output goes straight to a file. Using pipes here would hang: the daemon
    inherits the pipe handles (notably on Windows), so EOF never arrives while
    it runs.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(map(str, args))}\n".encode())
        log.flush()
        return subprocess.run([str(a) for a in args], env=env, stdout=log, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, timeout=timeout,
                              **({"creationflags": CREATE_NO_WINDOW} if IS_WINDOWS else {})).returncode


def tail(path: Path, lines: int = 30) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def run(args: list, env: dict | None = None, cwd: Path | None = None, timeout: float | None = None,
        log_path: Path | None = None) -> subprocess.CompletedProcess:
    """Run a one-shot command to completion, capturing output (and appending it to a log)."""
    result = subprocess.run([str(a) for a in args], env=env, cwd=str(cwd) if cwd else None, timeout=timeout,
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            **({"creationflags": CREATE_NO_WINDOW} if IS_WINDOWS else {}))
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(map(str, args))} -> {result.returncode}\n")
            log.write(result.stdout or "")
            log.write(result.stderr or "")
    return result

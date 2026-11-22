"""Private, size-limited temporary storage for generated XLSX exports."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import threading
import time
from pathlib import Path

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask


EXPORT_TEMP_ROOT = Path(tempfile.gettempdir()) / "alahsa-xlsx-exports"
EXPORT_DIRECTORY_PREFIX = "request-"
EXPORT_STALE_SECONDS = 24 * 60 * 60
MAX_XLSX_EXPORT_BYTES = 128 * 1024 * 1024
MIN_FREE_DISK_BYTES = 16 * 1024 * 1024
MAX_CONCURRENT_XLSX_EXPORTS = 1

_export_slots = threading.BoundedSemaphore(MAX_CONCURRENT_XLSX_EXPORTS)


class ExportCapacityBusy(Exception):
    pass


class ExportStorageUnavailable(Exception):
    pass


class ExportFileTooLarge(Exception):
    pass


def acquire_export_slot() -> None:
    if not _export_slots.acquire(blocking=False):
        raise ExportCapacityBusy


def release_export_slot() -> None:
    _export_slots.release()


def _ensure_private_root() -> Path:
    try:
        EXPORT_TEMP_ROOT.mkdir(mode=0o700, parents=False, exist_ok=True)
        info = EXPORT_TEMP_ROOT.lstat()
    except OSError as exc:
        raise ExportStorageUnavailable from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ExportStorageUnavailable
    if os.name == "nt":
        return _windows_private_root(info)
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise ExportStorageUnavailable
    try:
        os.chmod(EXPORT_TEMP_ROOT, 0o700)
    except OSError as exc:
        raise ExportStorageUnavailable from exc
    info = EXPORT_TEMP_ROOT.stat()
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise ExportStorageUnavailable
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ExportStorageUnavailable
    return EXPORT_TEMP_ROOT


def _windows_private_root(info: os.stat_result) -> Path:
    """Windows has no POSIX mode bits: chmod only toggles read-only and every
    directory reports 0o777. Privacy comes from the per-user temp directory's
    ACL, so require the root to be a real directory (not a junction or other
    reparse point) inside that per-user temp directory."""
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if getattr(info, "st_file_attributes", 0) & reparse:
        raise ExportStorageUnavailable
    try:
        if not EXPORT_TEMP_ROOT.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise ExportStorageUnavailable
    except OSError as exc:
        raise ExportStorageUnavailable from exc
    return EXPORT_TEMP_ROOT


def cleanup_stale_export_directories(now: float | None = None) -> int:
    """Remove only old, app-owned request directories from the private root."""
    if not EXPORT_TEMP_ROOT.exists():
        return 0
    root = _ensure_private_root()
    cutoff = (time.time() if now is None else now) - EXPORT_STALE_SECONDS
    removed = 0
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        raise ExportStorageUnavailable from exc
    for entry in entries:
        if not entry.name.startswith(EXPORT_DIRECTORY_PREFIX) or entry.is_symlink():
            continue
        try:
            info = entry.stat(follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or info.st_mtime >= cutoff:
                continue
            shutil.rmtree(entry)
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            # A cleanup failure should not turn into a deletion outside the
            # controlled directory or expose a filesystem path to a caller.
            continue
    return removed


def create_export_directory(estimated_bytes: int) -> Path:
    root = _ensure_private_root()
    cleanup_stale_export_directories()
    required_free = min(MAX_XLSX_EXPORT_BYTES, max(MIN_FREE_DISK_BYTES, int(estimated_bytes)))
    try:
        if shutil.disk_usage(root).free < required_free:
            raise ExportStorageUnavailable
        directory = Path(tempfile.mkdtemp(prefix=EXPORT_DIRECTORY_PREFIX, dir=root))
        os.chmod(directory, 0o700)
        return directory
    except OSError as exc:
        raise ExportStorageUnavailable from exc


def remove_export_directory(directory: Path) -> None:
    try:
        path = Path(directory)
        if path.parent == EXPORT_TEMP_ROOT and path.name.startswith(EXPORT_DIRECTORY_PREFIX):
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        return


class LimitedFileWriter:
    """File proxy that refuses writes which would exceed the per-export cap."""

    def __init__(self, file_obj, max_bytes: int = MAX_XLSX_EXPORT_BYTES):
        self._file = file_obj
        self._max_bytes = max_bytes

    def write(self, data):
        position = self._file.tell()
        size = os.fstat(self._file.fileno()).st_size
        if max(size, position + len(data)) > self._max_bytes:
            raise ExportFileTooLarge
        return self._file.write(data)

    def __getattr__(self, name):
        return getattr(self._file, name)


class TemporaryExportFileResponse(FileResponse):
    """FileResponse which cleans its private directory even on send failure."""

    def __init__(self, path, directory: Path, **kwargs):
        self._export_directory = Path(directory)
        self._cleanup_lock = threading.Lock()
        self._cleaned = False
        kwargs["background"] = BackgroundTask(self.cleanup_export_file)
        super().__init__(path, **kwargs)

    def cleanup_export_file(self):
        with self._cleanup_lock:
            if self._cleaned:
                return
            self._cleaned = True
        remove_export_directory(self._export_directory)
        release_export_slot()

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.cleanup_export_file()

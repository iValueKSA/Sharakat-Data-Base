from pathlib import Path
import asyncio

import pytest

from app import export_storage


def test_private_export_directory_permissions_limits_and_stale_cleanup(tmp_path, monkeypatch):
    root = tmp_path / "xlsx-private"
    monkeypatch.setattr(export_storage, "EXPORT_TEMP_ROOT", root)
    monkeypatch.setattr(export_storage, "EXPORT_STALE_SECONDS", 60)
    directory = export_storage.create_export_directory(10)
    second_directory = export_storage.create_export_directory(10)
    assert directory.parent == root
    assert second_directory != directory
    import os
    if os.name != "nt":  # Windows has no POSIX mode bits; privacy comes from the per-user temp ACL
        assert directory.stat().st_mode & 0o777 == 0o700

    stale = root / "request-stale"
    stale.mkdir(mode=0o700)
    old = stale / "partial.xlsx"
    old.write_bytes(b"partial")
    import os
    os.utime(stale, (1, 1))
    assert export_storage.cleanup_stale_export_directories(now=1000) == 1
    assert not stale.exists()
    export_storage.remove_export_directory(directory)
    export_storage.remove_export_directory(second_directory)
    assert not directory.exists()


def test_limited_writer_rejects_over_cap_without_writing(tmp_path):
    output = (tmp_path / "limited.xlsx").open("w+b")
    try:
        limited = export_storage.LimitedFileWriter(output, max_bytes=4)
        assert limited.write(b"1234") == 4
        with pytest.raises(export_storage.ExportFileTooLarge):
            limited.write(b"5")
        output.seek(0)
        assert output.read() == b"1234"
    finally:
        output.close()


def test_file_response_cleanup_is_idempotent_and_releases_export_slot(tmp_path, monkeypatch):
    root = tmp_path / "xlsx-private"
    monkeypatch.setattr(export_storage, "EXPORT_TEMP_ROOT", root)
    directory = export_storage.create_export_directory(0)
    path = directory / "export.xlsx"
    path.write_bytes(b"workbook")
    export_storage.acquire_export_slot()
    response = export_storage.TemporaryExportFileResponse(path, directory)

    response.cleanup_export_file()
    response.cleanup_export_file()
    assert not directory.exists()
    # A second acquisition proves cleanup released the single process-local slot.
    export_storage.acquire_export_slot()
    export_storage.release_export_slot()


@pytest.mark.parametrize("fail_send", [False, True])
def test_file_response_stream_and_send_failure_always_clean_private_directory(tmp_path, monkeypatch, fail_send):
    root = tmp_path / "xlsx-private"
    monkeypatch.setattr(export_storage, "EXPORT_TEMP_ROOT", root)
    directory = export_storage.create_export_directory(0)
    path = directory / "export.xlsx"
    path.write_bytes(b"bounded response body")
    export_storage.acquire_export_slot()
    response = export_storage.TemporaryExportFileResponse(path, directory)
    sent = bytearray()

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        if fail_send and message["type"] == "http.response.body" and message.get("body"):
            raise RuntimeError("simulated client disconnect")
        if message["type"] == "http.response.body":
            sent.extend(message.get("body", b""))

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "method": "GET", "path": "/export.xlsx", "raw_path": b"/export.xlsx",
             "query_string": b"", "headers": []}
    if fail_send:
        with pytest.raises(RuntimeError, match="simulated client disconnect"):
            asyncio.run(response(scope, receive, send))
    else:
        asyncio.run(response(scope, receive, send))
        assert bytes(sent) == b"bounded response body"
    assert not directory.exists()
    export_storage.acquire_export_slot()
    export_storage.release_export_slot()


def test_disk_and_concurrency_limits_fail_closed(tmp_path, monkeypatch):
    root = tmp_path / "xlsx-private"
    monkeypatch.setattr(export_storage, "EXPORT_TEMP_ROOT", root)
    monkeypatch.setattr(export_storage.shutil, "disk_usage",
                        lambda _path: type("Usage", (), {"free": 1})())
    with pytest.raises(export_storage.ExportStorageUnavailable):
        export_storage.create_export_directory(0)

    export_storage.acquire_export_slot()
    with pytest.raises(export_storage.ExportCapacityBusy):
        export_storage.acquire_export_slot()
    export_storage.release_export_slot()


def test_xlsx_endpoint_returns_429_when_the_single_export_slot_is_busy():
    from fastapi import HTTPException
    from app import main

    export_storage.acquire_export_slot()
    try:
        with pytest.raises(HTTPException) as raised:
            main.export_xlsx()
        assert raised.value.status_code == 429
        assert raised.value.headers["Retry-After"] == "30"
    finally:
        export_storage.release_export_slot()

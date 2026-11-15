"""Reproducible isolated XLSX export benchmark; requires a fresh SQLite URL."""

from __future__ import annotations

import asyncio
import cProfile
import gc
import json
import os
from pathlib import Path
import pstats
import threading
import time
import tracemalloc
from datetime import datetime, timezone

from openpyxl import load_workbook
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import main
from app.excel_export import HEADERS
from app.models import (
    Base, GeographicReferenceDataset, GeographicReferenceUnit, Opportunity,
    OpportunityLocation, Source, SourceOpportunity,
)


SIZES = tuple(int(value) for value in os.environ.get("XLSX_BENCHMARK_SIZES", "1,100,1000,3000,6000").split(","))
DATABASE_PATH = Path("/tmp/low-memory-xlsx-benchmark.db")
EXPORT_ROOT = Path("/tmp/alahsa-xlsx-exports")


def _rss_bytes() -> int:
    with open("/proc/self/statm", encoding="ascii") as handle:
        resident_pages = int(handle.read().split()[1])
    return resident_pages * os.sysconf("SC_PAGE_SIZE")


def _container_memory_bytes() -> int:
    for filename in ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory/memory.usage_in_bytes"):
        try:
            return int(Path(filename).read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            continue
    return 0


def _tree_bytes(root: Path) -> int:
    total = 0
    if root.exists():
        for path in root.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except FileNotFoundError:
                    pass
    return total


def _seed(factory, max_rows: int) -> list[int]:
    now = datetime.now(timezone.utc)
    with factory() as db:
        dataset = GeographicReferenceDataset(
            dataset_key="benchmark", version="1", operator="synthetic benchmark",
            source_url="https://fixture.invalid/geography", coverage_json={}, provenance_json={},
            content_sha256="b" * 64, import_status="IMPORTED", is_current=False, created_at=now,
        )
        source = Source(
            source_key="benchmark", source_name_ar="مصدر اختباري", organization_name="جهة اختبارية",
            base_url="https://fixture.invalid", opportunities_url="https://fixture.invalid/list",
            technical_health="HEALTHY", coverage_status="COMPLETE_PUBLIC_SOURCE", enabled=True, priority=1,
        )
        db.add_all([dataset, source])
        db.flush()
        region = GeographicReferenceUnit(dataset_id=dataset.id, level="region", external_id="R-01", name_ar="المنطقة الشرقية")
        db.add(region)
        db.flush()
        governorate = GeographicReferenceUnit(
            dataset_id=dataset.id, parent_id=region.id, level="governorate", external_id="G-01",
            name_ar="محافظة الأحساء")
        db.add(governorate)
        db.commit()
        source_id, unit_id = source.id, governorate.id

    ids: list[int] = []
    for offset in range(0, max_rows, 250):
        count = min(250, max_rows - offset)
        with factory() as db:
            masters = [Opportunity(
                canonical_id=f"BENCH-{index + 1:06d}", title_ar=f"فرصة اختبار وطنية رقم {index + 1:06d}",
                normalized_title=f"فرصة اختبار وطنية رقم {index + 1:06d}", sector="صناعي", status="متاحة",
                primary_publication_platform="بوابة فرص", city="الأحساء", location_description="موقع اختباري",
                geography_reference_unit_id=unit_id, location_confidence_score=.95,
                location_detection_method="benchmark", location_evidence="synthetic only",
                data_quality_score=.9, manual_review_required=False, first_seen_at=now, last_seen_at=now,
                last_updated_at=now, created_at=now, updated_at=now,
            ) for index in range(offset, offset + count)]
            db.add_all(masters)
            db.flush()
            ids.extend(master.id for master in masters)
            source_rows = [SourceOpportunity(
                source_id=source_id, master_opportunity_id=master.id,
                source_opportunity_id=f"benchmark:{offset + index + 1:06d}", source_title=master.title_ar,
                normalized_source_title=master.normalized_title, source_url="https://fixture.invalid/item",
                raw_dates={}, raw_status="متاحة", raw_data_json={"synthetic": True}, standardized_data_json={},
                standardization_version="benchmark-1", first_seen_at=now, last_seen_at=now,
                content_hash=f"{offset + index + 1:064d}", parser_version="benchmark-1",
            ) for index, master in enumerate(masters)]
            db.add_all(source_rows)
            db.flush()
            db.add_all([OpportunityLocation(source_opportunity_id=row.id, location_name="الأحساء")
                        for row in source_rows])
            db.commit()
        gc.collect()
    return ids


async def _send_to_discard(response) -> int:
    total = 0

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal total
        if message["type"] == "http.response.body":
            total += len(message.get("body", b""))

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "method": "GET", "path": "/api/export.xlsx",
             "raw_path": b"/api/export.xlsx", "query_string": b"", "headers": []}
    await response(scope, receive, send)
    return total


def main_benchmark() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("sqlite:////tmp/"):
        raise SystemExit("Refusing to run: DATABASE_URL must point to a disposable /tmp SQLite database")
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    EXPORT_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{DATABASE_PATH}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    main.SessionLocal = factory
    ids = _seed(factory, max(SIZES))

    results = []
    for size in SIZES:
        query_count = 0
        sql_seconds = 0.0

        def before_cursor_execute(*_args):
            nonlocal query_count
            query_count += 1
            _args[0].info.setdefault("xlsx_benchmark_started", []).append(time.perf_counter())

        def after_cursor_execute(connection, *_args):
            nonlocal sql_seconds
            started = connection.info.get("xlsx_benchmark_started", [])
            if started:
                sql_seconds += time.perf_counter() - started.pop()

        event.listen(engine, "before_cursor_execute", before_cursor_execute)
        event.listen(engine, "after_cursor_execute", after_cursor_execute)
        chosen_ids = ",".join(str(value) for value in ids[:size])
        baseline_rss = _rss_bytes()
        def start_monitor():
            rss_peak = [_rss_bytes()]
            container_peak = [_container_memory_bytes()]
            disk_peak = [_tree_bytes(EXPORT_ROOT)]
            stop = threading.Event()

            def sample():
                next_disk_scan = 0.0
                while not stop.is_set():
                    rss_peak[0] = max(rss_peak[0], _rss_bytes())
                    container_peak[0] = max(container_peak[0], _container_memory_bytes())
                    now = time.monotonic()
                    if now >= next_disk_scan:
                        disk_peak[0] = max(disk_peak[0], _tree_bytes(EXPORT_ROOT))
                        next_disk_scan = now + .1
                    stop.wait(.05)

            monitor = threading.Thread(target=sample, daemon=True)
            monitor.start()
            return stop, monitor, rss_peak, container_peak, disk_peak

        def stop_monitor(monitor_state):
            stop_event, monitor_thread, *_ = monitor_state
            stop_event.set()
            monitor_thread.join(timeout=2)

        generation_monitor = start_monitor()
        trace_memory = os.environ.get("XLSX_TRACE_MEMORY") == "1"
        if trace_memory:
            tracemalloc.start()
        started = time.perf_counter()
        profiler = cProfile.Profile() if int(os.environ.get("XLSX_PROFILE_SIZE", "0")) == size else None
        if profiler:
            profiler.enable()
        response = main.export_xlsx(map_ids=chosen_ids)
        if profiler:
            profiler.disable()
            pstats.Stats(profiler).strip_dirs().sort_stats("cumulative").print_stats(25)
        generation_seconds = time.perf_counter() - started
        stop_monitor(generation_monitor)
        _, _, generation_rss, generation_container, generation_disk = generation_monitor
        allocation_peak = 0
        if trace_memory:
            _, allocation_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        output_path = Path(response.path)
        output_bytes = output_path.stat().st_size
        integrity_started = time.perf_counter()
        book = load_workbook(output_path, read_only=True, data_only=False)
        sheet = book["الفرص الاستثمارية"]
        identities = [row[0] for row in sheet.iter_rows(min_row=7, values_only=True)]
        assert book.sheetnames == ["الفرص الاستثمارية", "معلومات التقرير"]
        assert sheet.max_row == size + 6 and sheet.max_column == len(HEADERS) == 32
        assert [sheet.cell(6, col).value for col in range(1, 33)] == HEADERS
        assert len(identities) == size and len(set(identities)) == size
        assert identities == [f"فرصة اختبار وطنية رقم {index + 1:06d}" for index in range(size)]
        assert book["معلومات التقرير"]["B8"].value == size
        assert identities[0].startswith("فرصة اختبار وطنية")
        book.close()
        integrity_seconds = time.perf_counter() - integrity_started
        stream_monitor = start_monitor()
        stream_started = time.perf_counter()
        streamed_bytes = asyncio.run(_send_to_discard(response))
        stream_seconds = time.perf_counter() - stream_started
        stop_monitor(stream_monitor)
        _, _, stream_rss, stream_container, stream_disk = stream_monitor
        end_to_end_seconds = generation_seconds + stream_seconds
        query_total = query_count
        rss_sample_peak = max(generation_rss[0], stream_rss[0])
        container_sample_peak = max(generation_container[0], stream_container[0])
        temporary_disk_peak = max(generation_disk[0], stream_disk[0])
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
        event.remove(engine, "after_cursor_execute", after_cursor_execute)
        assert not output_path.parent.exists(), "private export directory was not cleaned"
        result = {
            "opportunities": size, "used_rows": size + 6, "columns": 32,
            "sql_queries": query_total, "database_seconds": round(sql_seconds, 4),
            "workbook_generation_seconds": round(generation_seconds, 4),
            "file_response_stream_seconds": round(stream_seconds, 4),
            "integrity_check_seconds": round(integrity_seconds, 4),
            "end_to_end_seconds": round(end_to_end_seconds, 4),
            "process_rss_baseline_mib": round(baseline_rss / 1024**2, 2),
            "process_rss_peak_mib": round(rss_sample_peak / 1024**2, 2),
            "process_rss_peak_delta_mib": round((rss_sample_peak - baseline_rss) / 1024**2, 2),
            "container_sampled_memory_current_max_mib": round(container_sample_peak / 1024**2, 2),
            "python_tracemalloc_peak_mib": round(allocation_peak / 1024**2, 2) if trace_memory else None,
            "temporary_disk_peak_bytes": temporary_disk_peak, "xlsx_bytes": output_bytes,
            "streamed_response_bytes": streamed_bytes, "cleanup": "PASS", "integrity": "PASS",
        }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    engine.dispose()
    print(json.dumps({"benchmark": "low-memory XLSX", "memory_limit": "512 MiB", "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main_benchmark()

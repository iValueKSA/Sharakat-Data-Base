"""Same-fixture in-memory XLSX baseline for low_memory_xlsx benchmark."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import datetime, timezone
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import selectinload, sessionmaker

from app import main
from app.excel_export import HEADERS, build_opportunities_workbook
from app.models import Base, Opportunity, OpportunityAssetFacilityType, SourceOpportunity
from scripts.benchmark_low_memory_xlsx import (
    DATABASE_PATH, SIZES, _container_memory_bytes, _rss_bytes, _seed,
)


async def _send_to_discard(response) -> int:
    total = 0

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal total
        if message["type"] == "http.response.body":
            total += len(message.get("body", b""))

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "method": "GET", "path": "/api/export.xlsx", "raw_path": b"/api/export.xlsx",
             "query_string": b"", "headers": []}
    await response(scope, receive, send)
    return total


def run() -> None:
    if not os.environ.get("DATABASE_URL", "").startswith("sqlite:////tmp/"):
        raise SystemExit("Refusing to run: DATABASE_URL must use a disposable /tmp SQLite database")
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    engine = create_engine(f"sqlite:///{DATABASE_PATH}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    main.SessionLocal = factory
    ids = _seed(factory, max(SIZES))

    results = []
    for size in SIZES:
        selected = ids[:size]
        query_count = [0]
        query_seconds = [0.0]
        starts = []

        def before(connection, *_args):
            query_count[0] += 1
            starts.append(time.perf_counter())

        def after(*_args):
            if starts:
                query_seconds[0] += time.perf_counter() - starts.pop()

        event.listen(engine, "before_cursor_execute", before)
        event.listen(engine, "after_cursor_execute", after)
        started_rss = _rss_bytes()
        peaks = [started_rss, _container_memory_bytes()]
        stop = threading.Event()

        def sample():
            while not stop.is_set():
                peaks[0] = max(peaks[0], _rss_bytes())
                peaks[1] = max(peaks[1], _container_memory_bytes())
                stop.wait(.05)

        monitor = threading.Thread(target=sample, daemon=True)
        monitor.start()
        overall_started = time.perf_counter()
        with factory() as db:
            query = select(Opportunity).where(Opportunity.id.in_(selected)).options(
                selectinload(Opportunity.source_records).selectinload(SourceOpportunity.source),
                selectinload(Opportunity.source_records).selectinload(SourceOpportunity.opportunity_locations),
                selectinload(Opportunity.asset_facility_type_assignments).selectinload(OpportunityAssetFacilityType.asset_type),
            ).order_by(Opportunity.id)
            records = list(db.scalars(query))
            export_ids = [record.id for record in records]
            pending = main._pending_location_reviews_by_master(db, export_ids)
            source_locations = main._source_location_values_by_master(db, export_ids)
            reference_units, reference_datasets = main._export_geographic_reference_cache(
                db, [record.geography_reference_unit_id for record in records])
            geographies = {
                record.id: main._opportunity_geography(
                    db, record, pending, source_locations, reference_units, reference_datasets)
                for record in records
            }
            workbook = build_opportunities_workbook(
                records, main.source_fact_summary, main.spreadsheet_safe,
                datetime.now(timezone.utc), canonicalize=main.canonical_value,
                geography_for=lambda row: geographies.get(row.id, {}))
        generated_seconds = time.perf_counter() - overall_started
        output = BytesIO()
        serialization_started = time.perf_counter()
        workbook.save(output)
        payload = output.getvalue()
        serialization_seconds = time.perf_counter() - serialization_started
        from starlette.responses import Response
        response = Response(payload, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        stream_started = time.perf_counter()
        streamed_bytes = asyncio.run(_send_to_discard(response))
        total_seconds = time.perf_counter() - overall_started
        stop.set()
        monitor.join(timeout=2)
        event.remove(engine, "before_cursor_execute", before)
        event.remove(engine, "after_cursor_execute", after)

        inspection = load_workbook(BytesIO(payload), read_only=True, data_only=False)
        sheet = inspection["الفرص الاستثمارية"]
        titles = [row[0] for row in sheet.iter_rows(min_row=7, values_only=True)]
        assert inspection.sheetnames == ["الفرص الاستثمارية", "معلومات التقرير"]
        assert sheet.max_row == size + 6 and sheet.max_column == 32
        assert [sheet.cell(6, column).value for column in range(1, 33)] == HEADERS
        assert len(titles) == size and len(set(titles)) == size
        inspection.close()
        result = {
            "opportunities": size, "used_rows": size + 6, "columns": 32,
            "sql_queries": query_count[0], "database_seconds": round(query_seconds[0], 4),
            "workbook_build_seconds_including_retrieval": round(generated_seconds, 4),
            "serialization_and_getvalue_seconds": round(serialization_seconds, 4),
            "file_response_stream_seconds": round(time.perf_counter() - stream_started, 4),
            "end_to_end_seconds": round(total_seconds, 4), "process_rss_baseline_mib": round(started_rss / 1024**2, 2),
            "process_rss_peak_mib": round(peaks[0] / 1024**2, 2),
            "process_rss_peak_delta_mib": round((peaks[0] - started_rss) / 1024**2, 2),
            "container_sampled_memory_current_max_mib": round(peaks[1] / 1024**2, 2),
            "xlsx_bytes": len(payload), "streamed_response_bytes": streamed_bytes,
            "integrity": "PASS",
        }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        del payload, output, workbook, records
    engine.dispose()
    print(json.dumps({"benchmark": "normal in-memory XLSX baseline", "memory_limit": "512 MiB",
                      "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    run()

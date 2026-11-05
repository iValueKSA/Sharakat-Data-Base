"""Read-only live API and export reconciliation for the sector relaxation apply."""
from __future__ import annotations

import csv
import io
import json
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook


BASE = "http://127.0.0.1:8000"
OUT = Path("docs/validation/data/sector-controlled-relaxation")


def get(path: str) -> bytes:
    with urllib.request.urlopen(BASE + path, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP_{response.status}:{path}")
        return response.read()


def main() -> dict:
    dashboard = json.loads(get("/api/data-dashboard"))
    buckets = {row["canonical_id"]: row for row in dashboard["by_sector"]}
    total = int(dashboard["kpis"]["total"])
    if sum(int(row["count"]) for row in buckets.values()) != total:
        raise RuntimeError("SECTOR_DASHBOARD_TOTAL_MISMATCH")

    details = {}
    failures = []
    for sector_id, bucket in sorted(buckets.items()):
        label = bucket["name"]
        expected = int(bucket["count"])
        query = urllib.parse.urlencode({"sector": sector_id, "limit": 500})
        listing = json.loads(get("/api/opportunities?" + query))
        items = listing.get("items", [])
        ids = [row["canonical_id"] for row in items]
        api_ok = int(listing.get("total", -1)) == expected and len(items) == expected
        labels_ok = all(row.get("sector") == label for row in items)
        if not api_ok or not labels_ok or len(ids) != len(set(ids)):
            failures.append({"sector_id": sector_id, "check": "api_filter"})

        csv_data = get("/api/export.csv?" + query).decode("utf-8-sig")
        csv_rows = list(csv.DictReader(io.StringIO(csv_data)))
        csv_sectors = Counter(row.get("القطاع", "") for row in csv_rows)
        csv_ok = len(csv_rows) == expected and csv_sectors == Counter({label: expected})
        if not csv_ok:
            failures.append({"sector_id": sector_id, "check": "csv"})

        workbook_data = get("/api/export.xlsx?" + query)
        workbook = load_workbook(io.BytesIO(workbook_data), read_only=True, data_only=True)
        sheet = workbook["الفرص الاستثمارية"] if "الفرص الاستثمارية" in workbook.sheetnames else workbook.active
        rows = sheet.iter_rows(values_only=True)
        headers = None
        for row in rows:
            if "القطاع" in row:
                headers = row
                break
        if headers is None:
            raise RuntimeError(f"XLSX_SECTOR_COLUMN_MISSING:{sector_id}")
        sector_column = headers.index("القطاع")
        xlsx_sectors = Counter(
            str(row[sector_column] or "")
            for row in rows
            if sector_column < len(row) and row[sector_column] is not None
        )
        xlsx_count = sum(xlsx_sectors.values())
        workbook.close()
        xlsx_ok = xlsx_count == expected and xlsx_sectors == Counter({label: expected})
        if not xlsx_ok:
            failures.append({"sector_id": sector_id, "check": "xlsx"})

        details[sector_id] = {
            "label": label,
            "dashboard_count": expected,
            "api_filter_count": len(items),
            "api_filter_total": int(listing.get("total", -1)),
            "csv_rows": len(csv_rows),
            "xlsx_rows": xlsx_count,
            "api_filter_pass": api_ok and labels_ok and len(ids) == len(set(ids)),
            "csv_pass": csv_ok,
            "xlsx_pass": xlsx_ok,
        }

    result = {
        "status": "PASS" if not failures else "FAIL",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "current_opportunities": total,
        "sector_bucket_sum": sum(int(row["count"]) for row in buckets.values()),
        "sector_dashboard_reconciliation": "PASSED" if not failures else "FAILED",
        "sector_filter_reconciliation": "PASSED" if not failures else "FAILED",
        "csv_sector_reconciliation": "PASSED" if not failures else "FAILED",
        "xlsx_sector_reconciliation": "PASSED" if not failures else "FAILED",
        "buckets": details,
        "failures": failures,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "live-sector-api-export-reconciliation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

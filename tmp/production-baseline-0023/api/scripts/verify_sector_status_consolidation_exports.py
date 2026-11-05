"""Read-only live CSV/XLSX/API reconciliation for consolidated statuses and sectors."""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from openpyxl import load_workbook

BASE_URL = os.getenv("VALIDATION_BASE_URL", "http://localhost:8080").rstrip("/")
OUTPUT = Path("docs/validation/data/sector-inference-status-consolidation/export-reconciliation.json")


def workbook_rows(data: bytes, column_name: str) -> tuple[list[tuple], list[str]]:
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sheet = workbook["الفرص الاستثمارية"]
        headers = [cell.value for cell in next(sheet.iter_rows(min_row=6, max_row=6))]
        column = headers.index(column_name)
        rows = [row for row in sheet.iter_rows(min_row=7, values_only=True) if row and any(value is not None for value in row)]
        return rows, [str(row[column] or "") for row in rows]
    finally:
        workbook.close()


def get(path: str, params: dict[str, str] | None = None) -> bytes:
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    with urlopen(url, timeout=60) as response:
        return response.read()


def get_json(path: str, params: dict[str, str] | None = None) -> dict:
    return json.loads(get(path, params))


def main() -> None:
    result: dict = {"validated_at_utc": datetime.now(timezone.utc).isoformat(), "base_url": BASE_URL, "statuses": {}, "sectors": {}}
    filters = get_json("/api/filters")
    dashboard = get_json("/api/data-dashboard")
    dashboard_status = {row["canonical_id"]: int(row["count"]) for row in dashboard["by_status"]}
    assert "متاحة" in filters["statuses"] and "منشورة" not in filters["statuses"]

    for label in filters["statuses"]:
        canonical_id = filters["option_ids"]["statuses"][label]
        listing = get_json("/api/opportunities", {"status": canonical_id, "limit": "500"})
        csv_data = get("/api/export.csv", {"status": canonical_id})
        csv_rows = list(csv.DictReader(io.StringIO(csv_data.decode("utf-8-sig"))))
        xlsx_data = get("/api/export.xlsx", {"status": canonical_id})
        _, xlsx_statuses = workbook_rows(xlsx_data, "الحالة")
        expected = int(listing["total"])
        dashboard_count = dashboard_status[canonical_id]
        assert expected == dashboard_count == len(csv_rows) == len(xlsx_statuses), f"Status row count mismatch for {label}"
        assert all(row.get("الحالة") == label for row in csv_rows), f"CSV status label mismatch for {label}"
        assert all(status == label for status in xlsx_statuses), f"XLSX status label mismatch for {label}"
        result["statuses"][label] = {"canonical_id": canonical_id, "api": expected, "dashboard": dashboard_count,
            "csv": len(csv_rows), "xlsx": len(xlsx_statuses), "csv_label_match": True, "xlsx_label_match": True}

    available_id = filters["option_ids"]["statuses"]["متاحة"]
    legacy = get_json("/api/opportunities", {"status": "PUBLISHED", "limit": "500"})
    result["legacy_published_filter"] = {"total": int(legacy["total"]), "available_total": result["statuses"]["متاحة"]["api"],
        "same_results": int(legacy["total"]) == result["statuses"]["متاحة"]["api"], "canonical_id": available_id}
    assert result["legacy_published_filter"]["same_results"]

    for canonical_id, label in (("sector:tourism", "السياحة"), ("sector:agriculture", "الزراعة")):
        listing = get_json("/api/opportunities", {"sector": canonical_id, "limit": "500"})
        dashboard_row = next(row for row in dashboard["by_sector"] if row["canonical_id"] == canonical_id)
        csv_data = get("/api/export.csv", {"sector": canonical_id})
        csv_rows = list(csv.DictReader(io.StringIO(csv_data.decode("utf-8-sig"))))
        xlsx_data = get("/api/export.xlsx", {"sector": canonical_id})
        _, xlsx_sectors = workbook_rows(xlsx_data, "القطاع")
        expected = int(listing["total"])
        assert expected == int(dashboard_row["count"]) == len(csv_rows) == len(xlsx_sectors), f"Sector row count mismatch for {label}"
        assert all(row.get("القطاع") == label for row in csv_rows), f"CSV sector label mismatch for {label}"
        assert all(sector == label for sector in xlsx_sectors), f"XLSX sector label mismatch for {label}"
        result["sectors"][canonical_id] = {"label": label, "api": expected, "dashboard": int(dashboard_row["count"]),
            "csv": len(csv_rows), "xlsx": len(xlsx_sectors), "labels_match": True}

    result["status_bucket_sum"] = sum(item["api"] for item in result["statuses"].values())
    result["dashboard_total"] = int(dashboard["global_total"])
    result["status_dashboard_reconciliation"] = result["status_bucket_sum"] == result["dashboard_total"]
    assert result["status_dashboard_reconciliation"]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

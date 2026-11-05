"""Read-only live reconciliation of every canonical Master status through list/CSV/XLSX."""
from __future__ import annotations

import csv
import io
import json
import os
import time
from datetime import datetime, timezone

import httpx
from openpyxl import load_workbook

BASE_URL = os.getenv("VALIDATION_BASE_URL", "http://frontend:8080").rstrip("/")


def main() -> None:
    results = {"validated_at_utc": datetime.now(timezone.utc).isoformat(), "base_url": BASE_URL, "statuses": {}}
    with httpx.Client(base_url=BASE_URL, timeout=45) as client:
        filters = client.get("/api/filters"); filters.raise_for_status(); filters = filters.json()
        dashboard_response = client.get("/api/data-dashboard"); dashboard_response.raise_for_status()
        dashboard = dashboard_response.json()
        dashboard_counts = {row["canonical_id"]: int(row["count"]) for row in dashboard["by_status"]}
        for label in filters["statuses"]:
            canonical_id = filters["option_ids"]["statuses"][label]
            query = {"status": canonical_id, "limit": "500"}
            time.sleep(0.3)
            listing_response = client.get("/api/opportunities", params=query); listing_response.raise_for_status()
            listing = listing_response.json(); expected = int(listing["total"])
            if any(row.get("status") != label for row in listing["items"]):
                raise AssertionError(f"List status label mismatch for {label}")
            time.sleep(0.3)
            csv_response = client.get("/api/export.csv", params={"status": canonical_id}); csv_response.raise_for_status()
            csv_rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
            time.sleep(0.3)
            xlsx_response = client.get("/api/export.xlsx", params={"status": canonical_id}); xlsx_response.raise_for_status()
            workbook = load_workbook(io.BytesIO(xlsx_response.content), read_only=True, data_only=True)
            sheet = workbook["الفرص الاستثمارية"]
            headers = [cell.value for cell in next(sheet.iter_rows(min_row=6, max_row=6))]
            status_column = headers.index("الحالة")
            xlsx_rows = list(sheet.iter_rows(min_row=7, values_only=True))
            workbook.close()
            xlsx_rows = [row for row in xlsx_rows if row and any(value is not None for value in row)]
            if not (expected == len(csv_rows) == len(xlsx_rows) == dashboard_counts.get(canonical_id)):
                raise AssertionError(f"Count mismatch for {label}: API={expected}, CSV={len(csv_rows)}, XLSX={len(xlsx_rows)}, dashboard={dashboard_counts.get(canonical_id)}")
            if any(row.get("الحالة") != label for row in csv_rows):
                raise AssertionError(f"CSV status column mismatch for {label}")
            if any(row[status_column] != label for row in xlsx_rows):
                raise AssertionError(f"XLSX status column mismatch for {label}")
            results["statuses"][label] = {"canonical_id": canonical_id, "list": expected,
                "dashboard": dashboard_counts[canonical_id], "csv": len(csv_rows), "xlsx": len(xlsx_rows),
                "status_labels_match": True}
    results["total"] = sum(row["list"] for row in results["statuses"].values())
    results["all_status_buckets_reconcile"] = results["total"] == dashboard["global_total"]
    if not results["all_status_buckets_reconcile"]:
        raise AssertionError("Status buckets do not sum to global Master total")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

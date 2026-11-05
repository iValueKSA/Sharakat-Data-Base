"""Check live canonical Opportunity Type CSV/XLSX exports for both buckets."""
from __future__ import annotations

import csv
import io
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from openpyxl import load_workbook

BASE = os.getenv("VALIDATION_BASE_URL", "http://frontend:8080").rstrip("/")
CASES = {
    "opportunity_type:temporary_rental": (129, "تأجير مؤقت"),
    "opportunity_type:missing": (162, "غير محدد"),
}


def fetch(path: str) -> bytes:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected {response.status} for {path}")
        return response.read()


def main() -> None:
    results = {}
    for identity, (expected_count, label) in CASES.items():
        encoded = urllib.parse.quote(identity, safe="")
        csv_data = fetch(f"/api/export.csv?opportunity_type={encoded}").decode("utf-8-sig")
        csv_rows = list(csv.reader(io.StringIO(csv_data)))
        csv_type_column = csv_rows[0].index("نوع الفرصة")
        if len(csv_rows) - 1 != expected_count:
            raise AssertionError(f"CSV count mismatch for {identity}: {len(csv_rows) - 1}")
        if any(row[csv_type_column] != label for row in csv_rows[1:]):
            raise AssertionError(f"CSV label mismatch for {identity}")

        xlsx_data = fetch(f"/api/export.xlsx?opportunity_type={encoded}")
        workbook = load_workbook(io.BytesIO(xlsx_data), read_only=True, data_only=True)
        sheet = workbook["الفرص الاستثمارية"]
        headers = [cell.value for cell in next(sheet.iter_rows(min_row=6, max_row=6))]
        type_column = headers.index("نوع الفرصة") + 1
        xlsx_count = max(sheet.max_row - 6, 0)
        values = [sheet.cell(row, type_column).value for row in range(7, sheet.max_row + 1)]
        workbook.close()
        if xlsx_count != expected_count:
            raise AssertionError(f"XLSX count mismatch for {identity}: {xlsx_count}")
        if any(value != label for value in values):
            raise AssertionError(f"XLSX label mismatch for {identity}")
        results[identity] = {
            "label": label, "expected_count": expected_count,
            "csv_rows": len(csv_rows) - 1, "xlsx_rows": xlsx_count,
            "csv_labels_match": True, "xlsx_labels_match": True,
        }
    serialized = json.dumps(results, ensure_ascii=False, indent=2)
    report = Path(os.getenv("VALIDATION_OUTPUT", str(Path(__file__).resolve().parents[1] / "docs/validation/data/opportunity-type-taxonomy/live-export-verification.json")))
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()

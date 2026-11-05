import csv
import json
from pathlib import Path

from openpyxl import load_workbook

root = Path("docs/validation/deployment/nationwide-geographic-expansion/live-13-region-filter-evidence")
counts = {}
for label in ("all", "eastern", "riyadh", "makkah"):
    with (root / f"{label}.csv").open(encoding="utf-8-sig", newline="") as stream:
        csv_rows = sum(1 for _ in csv.DictReader(stream))
    workbook = load_workbook(root / f"{label}.xlsx", read_only=True, data_only=True)
    sheet = workbook["الفرص الاستثمارية"]
    # The workbook's six-row title/metadata block precedes its column header.
    xlsx_rows = sum(1 for _ in sheet.iter_rows(min_row=7, values_only=True))
    workbook.close()
    counts[label] = {"csv_rows": csv_rows, "xlsx_rows": xlsx_rows}
print(json.dumps(counts, ensure_ascii=False))

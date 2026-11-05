import csv
import glob
import json
import os
from openpyxl import load_workbook

root = os.environ["EXPORT_EVIDENCE_DIR"]
results = json.load(open(os.path.join(root, "browser-results.json"), encoding="utf-8"))
basename = lambda value: os.path.basename(value.replace("\\", "/"))
expected = {(basename(item["csvPath"]), basename(item["xlsxPath"])): item
            for item in results.get("exports", [])}
result = []
for csv_path in sorted(glob.glob(os.path.join(root, "*-export-*.csv"))):
    xlsx_path = csv_path[:-4] + ".xlsx"
    with open(csv_path, encoding="utf-8-sig", newline="") as handle:
        csv_count = sum(1 for _ in csv.DictReader(handle))
    workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
    sheet = workbook["الفرص الاستثمارية"]
    xlsx_count = sum(1 for index, row in enumerate(sheet.iter_rows(values_only=True), 1)
                     if index > 6 and row and row[0] is not None)
    workbook.close()
    xlsx_name = os.path.basename(xlsx_path)
    row = expected.get((basename(csv_path), xlsx_name), {})
    parity = csv_count == xlsx_count == row.get("uiTotal") == row.get("apiTotal")
    result.append({"filter": os.path.basename(csv_path), "ui_count": row.get("uiTotal"),
                   "api_count": row.get("apiTotal"), "csv_count": csv_count,
                   "xlsx_count": xlsx_count, "parity": parity})
final = {"all_parity": bool(result) and all(row["parity"] for row in result), "cases": result}
with open(os.path.join(root, "export-count-parity.json"), "w", encoding="utf-8") as handle:
    json.dump(final, handle, ensure_ascii=False, indent=2)
print(json.dumps(final, ensure_ascii=False))

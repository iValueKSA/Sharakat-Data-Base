import csv
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

root = Path(__file__).resolve().parent
evidence = root / "evidence"
api = json.loads((evidence / "live-api-opportunities.json").read_text(encoding="utf-8"))
snapshot = json.loads((evidence / "pre-correction-snapshot.json").read_text(encoding="utf-8"))
furas_ref_by_master = {row["master_id"]: row["ref"] for row in snapshot["all_furas_rows"]}
deadline_refs = {furas_ref_by_master[mid] for mid in snapshot["furas_deadline_correction_ids"]}
publication_refs = {furas_ref_by_master[mid] for mid in snapshot["furas_publication_correction_ids"]}
expected = Counter((x.get("title") or "", x.get("reference") or "", x.get("deadline") or "") for x in api["items"])

with (evidence / "live-export.csv").open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
csv_actual = Counter((r.get("اسم الفرصة", ""), r.get("الرقم المرجعي", "") or "", r.get("آخر موعد للتقديم", "") or "") for r in rows)
csv_by_ref = {r.get("الرقم المرجعي", ""): r for r in rows}

wb = load_workbook(evidence / "live-export.xlsx", data_only=True, read_only=True)
ws = wb["الفرص الاستثمارية"] if "الفرص الاستثمارية" in wb.sheetnames else wb.active
headers = [cell.value for cell in ws[6]]
title_col = headers.index("اسم الفرصة") + 1
ref_col = headers.index("الرقم المرجعي") + 1
deadline_col = headers.index("آخر موعد للتقديم") + 1
publication_col = headers.index("تاريخ النشر") + 1
xlsx_actual = Counter()
xlsx_by_ref = {}
for row in ws.iter_rows(min_row=7, values_only=True):
    title, reference, deadline = row[title_col - 1], row[ref_col - 1], row[deadline_col - 1]
    if not title:
        continue
    xlsx_by_ref[str(reference or "")] = {
        "deadline": deadline.isoformat()[:10] if isinstance(deadline, (date, datetime)) else ("" if deadline is None else str(deadline)),
        "publication": row[publication_col - 1].isoformat()[:10] if isinstance(row[publication_col - 1], (date, datetime)) else ("" if row[publication_col - 1] is None else str(row[publication_col - 1])),
    }
    if isinstance(deadline, (date, datetime)):
        deadline = deadline.isoformat()[:10]
    elif deadline is None:
        deadline = ""
    else:
        deadline = str(deadline)
    xlsx_actual[(str(title), str(reference or ""), deadline)] += 1

result = {
    "api_rows": sum(expected.values()),
    "csv_rows": sum(csv_actual.values()),
    "xlsx_rows": sum(xlsx_actual.values()),
    "csv_headers": list(rows[0]) if rows else [],
    "xlsx_headers": headers,
    "csv_matches_api_dates_and_ids": csv_actual == expected,
    "xlsx_matches_api_dates_and_ids": xlsx_actual == expected,
    "csv_deadline_present": sum(1 for row in rows if row.get("آخر موعد للتقديم")),
    "xlsx_deadline_present": sum(1 for key, count in xlsx_actual.items() if key[2] for _ in range(count)),
    "furas_corrected_deadline_refs": len(deadline_refs),
    "csv_corrected_furas_deadlines_blank": all(not csv_by_ref.get(ref, {}).get("آخر موعد للتقديم") for ref in deadline_refs),
    "xlsx_corrected_furas_deadlines_blank": all(not xlsx_by_ref.get(ref, {}).get("deadline") for ref in deadline_refs),
    "furas_unverified_publication_refs": len(publication_refs),
    "csv_unverified_furas_publications_blank": all(not csv_by_ref.get(ref, {}).get("تاريخ النشر") for ref in publication_refs),
    "xlsx_unverified_furas_publications_blank": all(not xlsx_by_ref.get(ref, {}).get("publication") for ref in publication_refs),
}
(evidence / "export-date-reconciliation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))

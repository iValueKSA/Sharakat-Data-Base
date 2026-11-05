"""Read-only API/export reconciliation for the Asset/Facility/Site Type dimension."""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys

import httpx
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.standardization import STANDARDIZATION_VERSION

BASE_URL = os.getenv("VALIDATION_BASE_URL", "http://frontend:8080").rstrip("/")
OUT = Path("docs/validation/data/asset-facility-type-taxonomy/live-api-reconciliation.json")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    result = {"validated_at_utc": datetime.now(timezone.utc).isoformat(),
              "standardization_engine_version": STANDARDIZATION_VERSION,
              "base_url": BASE_URL, "options": {}, "xls_structure": {}}
    with httpx.Client(base_url=BASE_URL, timeout=45) as client:
        filters_response = client.get("/api/filters")
        filters_response.raise_for_status()
        filters = filters_response.json()
        dashboard = client.get("/api/data-dashboard")
        dashboard.raise_for_status()
        dashboard = dashboard.json()
        check(dashboard["global_total"] == 291, "Unexpected eligible Master total")
        labels = filters["asset_facility_types"]
        ids = filters["option_ids"]["asset_facility_types"]
        counts = filters["option_counts"]["asset_facility_types"]
        expected = {
            "العربات المتنقلة": ("asset_facility_type:mobile_vending_site", 69),
            "الحدائق": ("asset_facility_type:public_park", 23),
            "الشواطئ والواجهات": ("asset_facility_type:waterfront", 11),
            "أخرى": ("asset_facility_type:other", 10),
            "الاراضي": ("asset_facility_type:land", 8),
            "الساحات الميادين": ("asset_facility_type:public_square", 5),
            "الطرق والارصفة": ("asset_facility_type:road_sidewalk", 4),
            "المباني": ("asset_facility_type:building", 1),
            "غير محدد": ("asset_facility_type:missing", 162),
        }
        check(set(labels) == set(expected), "Unexpected asset/site-type filter options")
        for label, (canonical_id, expected_count) in expected.items():
            check(ids.get(label) == canonical_id, f"Noncanonical filter ID for {label}")
            check(counts.get(label) == expected_count, f"Filter option count mismatch for {label}")
            params = {"asset_facility_type": canonical_id, "limit": 500}
            response = client.get("/api/opportunities", params=params)
            response.raise_for_status()
            listing = response.json()
            check(listing["total"] == expected_count and len(listing["items"]) == expected_count,
                  f"List/query count mismatch for {label}")
            check(all(label in {item["label"] for item in row["asset_facility_types"]}
                      for row in listing["items"] if label != "غير محدد"),
                  f"Canonical labels missing from list JSON for {label}")
            if label == "غير محدد":
                check(all(not row["asset_facility_types"] and row["asset_facility_type"] == label
                          for row in listing["items"]), "Missing type is not presented as غير محدد")
            csv_response = client.get("/api/export.csv", params=params)
            csv_response.raise_for_status()
            csv_rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
            check(len(csv_rows) == expected_count, f"CSV count mismatch for {label}")
            check(all(label in row["نوع الأصل أو الموقع"].split(" | ") for row in csv_rows),
                  f"CSV label mismatch for {label}")
            xlsx_response = client.get("/api/export.xlsx", params=params)
            xlsx_response.raise_for_status()
            workbook = load_workbook(io.BytesIO(xlsx_response.content), data_only=True)
            sheet = workbook["الفرص الاستثمارية"]
            headers = [cell.value for cell in next(sheet.iter_rows(min_row=6, max_row=6))]
            rows = list(sheet.iter_rows(min_row=7, values_only=True))
            asset_col = headers.index("نوع الأصل أو الموقع")
            check(len(rows) == expected_count, f"XLSX count mismatch for {label}")
            check(all(label in row[asset_col].split(" | ") for row in rows), f"XLSX label mismatch for {label}")
            if label == "المباني":
                result["xls_structure"] = {
                    "column_count": len(headers),
                    "right_to_left": bool(sheet.sheet_view.rightToLeft),
                    "freeze_panes": sheet.freeze_panes,
                    "auto_filter": sheet.auto_filter.ref,
                    "asset_column": asset_col + 1,
                    "asset_column_width": sheet.column_dimensions["X"].width,
                    "print_area": str(sheet.print_area),
                }
                check(result["xls_structure"]["right_to_left"], "XLSX sheet is not right-to-left")
                check(sheet.freeze_panes == "A7", "Unexpected XLSX freeze pane")
                last_column = get_column_letter(len(headers))
                check(sheet.auto_filter.ref == f"A6:{last_column}{expected_count + 6}", "Unexpected XLSX auto-filter range")
            workbook.close()
            result["options"][label] = {
                "canonical_id": canonical_id, "filter_count": counts[label],
                "api_query_count": listing["total"], "csv_count": len(csv_rows),
                "xlsx_count": len(rows), "consistent": True,
            }
        id_for_building = ids["المباني"]
        building_items = client.get("/api/opportunities", params={"asset_facility_type": id_for_building, "limit": 50}).json()["items"]
        detail = client.get(f"/api/opportunities/{building_items[0]['id']}")
        detail.raise_for_status()
        detail = detail.json()
        check(detail["asset_facility_type"] == "المباني", "Details API omits the canonical asset type")
        dashboard_filter = client.get("/api/data-dashboard", params={"asset_facility_type": id_for_building})
        dashboard_filter.raise_for_status()
        check(dashboard_filter.json()["kpis"]["total"] == 1, "Dashboard filter does not reconcile")
        result["details"] = {"asset_facility_type": detail["asset_facility_type"], "canonical_types": detail["asset_facility_types"]}
        result["dashboard_filtered_total"] = 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

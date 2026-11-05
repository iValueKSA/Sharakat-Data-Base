"""Read-only live API, filter and export reconciliation for Investment Model."""
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.standardization import STANDARDIZATION_VERSION


BASE_URL = os.getenv("VALIDATION_BASE_URL", "http://frontend:8080").rstrip("/")
OUT = Path("docs/validation/data/investment-model-taxonomy/live-api-reconciliation.json")
MODELS = {
    "investment_model:lease": ("التأجير", 4),
    "investment_model:eomt": ("التجهيز والتشغيل والصيانة والنقل", 1),
    "investment_model:missing": ("غير محدد", 286),
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def csv_export(client: httpx.Client, params: dict[str, str]) -> list[dict[str, str]]:
    response = client.get("/api/export.csv", params=params)
    response.raise_for_status()
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))


def xlsx_export(client: httpx.Client, params: dict[str, str]) -> tuple[list[str], list[tuple]]:
    response = client.get("/api/export.xlsx", params=params)
    response.raise_for_status()
    workbook = load_workbook(io.BytesIO(response.content), read_only=True, data_only=True)
    sheet = workbook["الفرص الاستثمارية"]
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=6, max_row=6))]
    rows = list(sheet.iter_rows(min_row=7, values_only=True))
    workbook.close()
    return headers, rows


def main() -> None:
    result = {"validated_at_utc": datetime.now(timezone.utc).isoformat(),
              "standardization_engine_version": STANDARDIZATION_VERSION,
              "base_url": BASE_URL, "models": {}, "sub_activity_general_trade": {}}
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        filters = client.get("/api/filters"); filters.raise_for_status(); filters = filters.json()
        dashboard = client.get("/api/data-dashboard"); dashboard.raise_for_status(); dashboard = dashboard.json()
        check(dashboard["global_total"] == 291, "Unexpected eligible Master total")
        option_ids = filters["option_ids"]["investment_models"]
        option_counts = filters["option_counts"]["investment_models"]
        dashboard_counts = {row["canonical_id"]: row["count"] for row in dashboard["by_investment_model"]}
        check(dashboard["investment_model_coverage"] == {
            "total": 291, "canonical": 5, "unspecified": 286, "review": 2, "canonical_percent": 1.7,
        }, "Dashboard model coverage is inconsistent")
        for identity, (label, expected_count) in MODELS.items():
            check(option_ids.get(label) == identity, f"Missing or incorrect filter option ID: {label}")
            check(option_counts.get(label) == expected_count, f"Filter option count mismatch: {label}")
            check(dashboard_counts.get(identity) == expected_count, f"Dashboard bucket mismatch: {label}")
            query = {"investment_model": identity}
            listing_response = client.get("/api/opportunities", params={**query, "limit": 500}); listing_response.raise_for_status()
            listing = listing_response.json()
            check(listing["total"] == expected_count, f"Opportunity list count mismatch: {label}")
            check(len(listing["items"]) == expected_count, f"Opportunity list page is incomplete: {label}")
            check(all(row["investment_model"] == label
                      for row in listing["items"]), f"List model labels are inconsistent: {label}")
            filtered_dashboard = client.get("/api/data-dashboard", params=query); filtered_dashboard.raise_for_status()
            check(filtered_dashboard.json()["kpis"]["total"] == expected_count, f"Filtered dashboard mismatch: {label}")
            csv_rows = csv_export(client, query)
            check(len(csv_rows) == expected_count, f"CSV count mismatch: {label}")
            check(all(row["نموذج الاستثمار"] == label for row in csv_rows),
                  f"CSV model values are inconsistent: {label}")
            headers, xlsx_rows = xlsx_export(client, query)
            model_col = headers.index("نموذج الاستثمار")
            check(len(xlsx_rows) == expected_count, f"XLSX count mismatch: {label}")
            check(all(row[model_col] == label for row in xlsx_rows),
                  f"XLSX model values are inconsistent: {label}")
            result["models"][identity] = {"label": label, "count": expected_count,
                "list": len(listing["items"]), "list_total": listing["total"], "dashboard": dashboard_counts[identity],
                "csv": len(csv_rows), "xlsx": len(xlsx_rows), "consistent": True}
            if listing["items"]:
                detail = client.get(f"/api/opportunities/{listing['items'][0]['id']}")
                detail.raise_for_status()
                check(detail.json()["investment_model"] == label, f"Detail mismatch: {label}")
        result["combined_filters"] = {}
        for option_group, parameter in (
            ("sectors", "sector"), ("activities", "activity"),
            ("sub_activities", "sub_activity"), ("types", "opportunity_type"),
            ("statuses", "status"), ("owners", "owner"),
            ("sources", "source"), ("locations", "location"),
        ):
            found = None
            for label, option_id in filters["option_ids"].get(option_group, {}).items():
                query = {"investment_model": "investment_model:lease", parameter: option_id, "limit": 500}
                response = client.get("/api/opportunities", params=query); response.raise_for_status()
                listing = response.json()
                if listing["total"]:
                    check(len(listing["items"]) == listing["total"], f"Combined list page is incomplete: {parameter}")
                    csv_rows = csv_export(client, query)
                    headers, xlsx_rows = xlsx_export(client, query)
                    check(len(csv_rows) == listing["total"], f"Combined CSV count mismatch: {parameter}")
                    check(len(xlsx_rows) == listing["total"], f"Combined XLSX count mismatch: {parameter}")
                    found = {"option": label, "count": listing["total"], "list": len(listing["items"]),
                             "csv": len(csv_rows), "xlsx": len(xlsx_rows), "consistent": True}
                    break
            check(found is not None, f"No non-empty lease combination available for {parameter}")
            result["combined_filters"][parameter] = found
        subactivity_id = filters["option_ids"]["sub_activities"]["أنشطة التجارة العامة"]
        query = {"sub_activity": subactivity_id}
        listing_response = client.get("/api/opportunities", params=query); listing_response.raise_for_status()
        listing = listing_response.json()
        csv_rows = csv_export(client, query)
        headers, xlsx_rows = xlsx_export(client, query)
        subactivity_col = headers.index("النشاط الفرعي")
        check(listing["total"] == 8 and len(csv_rows) == 8 and len(xlsx_rows) == 8,
              "أنشطة التجارة العامة does not reconcile to 8 across list and exports")
        check(all(row["النشاط الفرعي"] == "أنشطة التجارة العامة" for row in csv_rows), "CSV sub-activity label mismatch")
        check(all(row[subactivity_col] == "أنشطة التجارة العامة" for row in xlsx_rows), "XLSX sub-activity label mismatch")
        result["sub_activity_general_trade"] = {"canonical_id": subactivity_id, "list": 8, "csv": 8, "xlsx": 8, "consistent": True}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

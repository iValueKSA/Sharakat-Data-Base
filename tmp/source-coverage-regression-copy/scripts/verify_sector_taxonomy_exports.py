"""Read-only API/export checks against the local database."""
from __future__ import annotations

import csv
import io
import json

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app


def main() -> None:
    with TestClient(app) as client:
        filters = client.get("/api/filters")
        dashboard = client.get("/api/data-dashboard")
        opportunities = client.get("/api/opportunities", params={"sector": "sector:other", "limit": 50})
        csv_response = client.get("/api/export.csv", params={"sector": "sector:other"})
        xlsx_response = client.get("/api/export.xlsx", params={"sector": "sector:other"})
        for response in (filters, dashboard, opportunities, csv_response, xlsx_response):
            response.raise_for_status()

        filter_options = filters.json()["sectors"]
        assert "أخرى" in filter_options and "غير محدد" in filter_options
        assert not {"قيمة مفقودة", "بقية القطاعات", "فرصة استثمارية"}.intersection(filter_options)
        sectors = dashboard.json()["by_sector"]
        assert sum(item["count"] for item in sectors) == dashboard.json()["kpis"]["total"] == 291
        assert not {"قيمة مفقودة", "بقية القطاعات", "فرصة استثمارية"}.intersection(item["name"] for item in sectors)
        assert opportunities.json()["total"] == 17
        assert all(item["sector"] == "أخرى" for item in opportunities.json()["items"])

        csv_rows = list(csv.reader(io.StringIO(csv_response.text.lstrip("\ufeff"))))
        assert len(csv_rows) == 18
        expected_dimension_headers = ["القطاع", "النشاط", "النشاط الفرعي", "القطاع الفرعي", "نوع الفرصة"]
        assert csv_rows[0][2:7] == expected_dimension_headers
        assert all(row[2] == "أخرى" for row in csv_rows[1:])

        workbook = load_workbook(io.BytesIO(xlsx_response.content), read_only=True, data_only=True)
        sheet = workbook["الفرص الاستثمارية"]
        headers = [sheet.cell(6, column).value for column in range(1, sheet.max_column + 1)]
        assert headers[2:7] == expected_dimension_headers
        xlsx_rows = list(sheet.iter_rows(min_row=7, max_col=7, values_only=True))
        assert len(xlsx_rows) == 17 and all(row[2] == "أخرى" for row in xlsx_rows)
        workbook.close()

        opportunity_id = opportunities.json()["items"][0]["id"]
        detail = client.get(f"/api/opportunities/{opportunity_id}")
        detail.raise_for_status()
        assert detail.json()["sector"] == "أخرى"
        assert "activity" in detail.json()

    print(json.dumps({
        "sector_filter_options": filter_options,
        "dashboard_total_and_sector_sum": 291,
        "other_filter_rows": 17,
        "csv_rows_and_dimensions": [len(csv_rows) - 1, csv_rows[0][2:7]],
        "xlsx_rows_and_dimensions": [len(xlsx_rows), headers[2:7]],
        "detail_sector": "أخرى",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

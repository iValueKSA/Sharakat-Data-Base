from datetime import datetime, timezone
import io
import csv

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.models import Base, Opportunity


def test_opportunity_search_count_uses_filters_and_page_limit(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    now = datetime.now(timezone.utc)
    common = dict(
        primary_publication_platform="fixture",
        location_confidence_score=0.9,
        location_detection_method="fixture",
        location_evidence="fixture",
        data_quality_score=0.8,
        manual_review_required=False,
        first_seen_at=now,
        last_seen_at=now,
        last_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    with factory() as db:
        db.add_all([
            Opportunity(canonical_id="A-1", title_ar="مستودع صناعي أول", normalized_title="مستودع صناعي اول", sector="صناعي", status="متاحة", **common),
            Opportunity(canonical_id="A-2", title_ar="مستودع صناعي ثان", normalized_title="مستودع صناعي ثان", sector="صناعي", status="منشورة", **common),
            Opportunity(canonical_id="A-3", title_ar="حديقة عامة", normalized_title="حديقة عامة", sector="تجاري", status="متاحة", **common),
        ])
        db.commit()

    client = TestClient(main.app)
    try:
        response = client.get("/api/opportunities", params={"q": "مستودع", "limit": 1, "offset": 0})
        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert len(response.json()["items"]) == 1

        filtered = client.get("/api/opportunities", params={"q": "مستودع", "sector": "صناعي", "status": "متاحة"})
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["canonical_id"] == "A-1"

        export = client.get("/api/export.xlsx")
        assert export.status_code == 200
        workbook = load_workbook(io.BytesIO(export.content), read_only=False)
        sheet = workbook["الفرص الاستثمارية"]
        assert workbook.sheetnames == ["الفرص الاستثمارية", "معلومات التقرير"]
        assert sheet.max_row == 9
        assert sheet.sheet_view.rightToLeft is True
        assert sheet.freeze_panes == "A7"
        assert sheet.auto_filter.ref == "A6:AD9"
        csv_response = client.get("/api/export.csv")
        assert csv_response.status_code == 200
        csv_rows = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
        assert len(csv_rows) == 4
        assert len(csv_rows[0]) == 30
    finally:
        client.close()
        engine.dispose()

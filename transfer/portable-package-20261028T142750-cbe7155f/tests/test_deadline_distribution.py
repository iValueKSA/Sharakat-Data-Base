from datetime import date, datetime, timedelta, timezone
import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.deadline_distribution import DEADLINE_BUCKETS, classify_deadline_population
from app.models import Base, Opportunity


def test_deadline_bucket_boundaries_are_exhaustive_and_publication_dates_do_not_count():
    today = date(2026, 10, 28)
    offsets = [0, 7, 8, 14, 15, 30, 31]
    rows = [(index + 1, (today + timedelta(days=days)).isoformat()) for index, days in enumerate(offsets)]
    rows.extend([(20, None), (21, "2026-99-99")])
    buckets = classify_deadline_population(rows, today)
    assert [key for key, *_ in DEADLINE_BUCKETS] == ["7d", "8_14d", "15_30d", "over_30d", "no_deadline"]
    assert [len(buckets[key]) for key, *_ in DEADLINE_BUCKETS] == [2, 2, 2, 1, 2]
    flattened = [master_id for ids in buckets.values() for master_id in ids]
    assert len(flattened) == len(rows) == len(set(flattened))
    # Publication/start dates are not inputs to this classifier; an absent
    # canonical submission deadline therefore remains in the neutral bucket.
    assert buckets["no_deadline"] == [20, 21]


def test_no_reliable_deadline_drilldown_and_exports_match_dashboard_bucket(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", test_engine)
    today = main.local_today()
    now = datetime.now(timezone.utc)
    common = dict(
        primary_publication_platform="fixture", city="الأحساء", location_confidence_score=.9,
        location_detection_method="fixture", location_evidence="fixture", data_quality_score=.8,
        manual_review_required=False, first_seen_at=now, last_seen_at=now, last_updated_at=now,
        created_at=now, updated_at=now,
    )
    with factory() as db:
        rows = []
        for index, offset in enumerate([0, 7, 8, 14, 15, 30, 31, None, "2026-99-99"], start=1):
            deadline = (today + timedelta(days=offset)).isoformat() if isinstance(offset, int) else offset
            rows.append(Opportunity(
                canonical_id=f"DL-{index}", title_ar=f"فرصة {index}", normalized_title=f"فرصة {index}",
                status="متاحة", submission_deadline=deadline,
                publication_date="2026-10-01" if offset is None else None, **common,
            ))
        db.add_all(rows)
        db.commit()

    client = TestClient(main.app)
    try:
        dashboard_response = client.get("/api/data-dashboard")
        assert dashboard_response.status_code == 200
        dashboard = dashboard_response.json()
        assert dashboard["kpis"]["active"] == 9
        buckets = dashboard["deadline_buckets"]
        assert [row["count"] for row in buckets] == [2, 2, 2, 1, 2]
        assert sum(row["count"] for row in buckets) == dashboard["kpis"]["active"]
        assert [row["color"] for row in buckets] == ["#378AA4", "#006E61", "#C39853", "#7953A9", "#989899"]

        params = {"lifecycle": "active", "deadline_status": "without_reliable_deadline"}
        listing = client.get("/api/opportunities", params={**params, "limit": 500})
        assert listing.status_code == 200 and listing.json()["total"] == 2
        csv_response = client.get("/api/export.csv", params=params)
        assert csv_response.status_code == 200
        csv_rows = csv_response.content.decode("utf-8-sig").splitlines()
        assert len(csv_rows) == 3
        xlsx_response = client.get("/api/export.xlsx", params=params)
        assert xlsx_response.status_code == 200
        workbook = load_workbook(io.BytesIO(xlsx_response.content), read_only=True)
        sheet = workbook["الفرص الاستثمارية"]
        exported_titles = {row[0] for row in sheet.iter_rows(values_only=True) if row and row[0] in {"فرصة 8", "فرصة 9"}}
        assert exported_titles == {"فرصة 8", "فرصة 9"}
        workbook.close()
        assert client.get("/api/opportunities", params={"deadline_status": "unknown"}).status_code == 422
    finally:
        client.close()
        test_engine.dispose()

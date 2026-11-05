from datetime import date, datetime, timezone

from app.status_lifecycle import (
    AVAILABLE, PUBLISHED, EXPIRED, CANCELLED, AWARDED, REMOVED, UNKNOWN,
    UNSPECIFIED, STATUS_REVIEW, aggregate_master_status, canonical_source_status,
    local_today, parse_deadline,
)
from scripts.sector_inference_status_consolidation import build_status_plan
from app.standardization import canonical_id as canonical_status_id, canonical_value as canonical_status_value
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.models import Base, Opportunity, Source, SourceOpportunity
from app import main


def test_source_status_aliases_and_unknown_are_distinct_from_missing():
    assert canonical_source_status("furas", "Announced")[0] == AVAILABLE
    assert canonical_source_status("furas", "Published")[0] == AVAILABLE
    assert canonical_status_id("status", "PUBLISHED") == "status:available"
    assert canonical_status_value("status", "منشورة") == AVAILABLE
    assert canonical_source_status("alahsa-opportunities", "متاحة")[0] == AVAILABLE
    assert canonical_source_status("ncp", "EXPIRED")[0] == EXPIRED
    assert canonical_source_status("ncp", "AWARDED")[0] == AWARDED
    assert canonical_source_status("furas", "Deleted")[0] == REMOVED
    assert canonical_source_status("ncp", "UNKNOWN")[0] == UNKNOWN
    assert canonical_source_status("ncp", None)[0] == UNSPECIFIED
    assert canonical_source_status("ncp", "mystery-status")[0] == UNKNOWN
    state,flags=canonical_source_status("ncp","IDENTITY_ALIAS","2026-04-15",
        now=datetime(2026,10,19,12,tzinfo=timezone.utc))
    assert state==EXPIRED and flags==["IDENTITY_ALIAS_NOT_A_STATUS","EXPIRED_BY_PASSED_DATE_ONLY_DEADLINE"]


def test_deletion_and_deadline_never_become_cancellation():
    assert canonical_source_status("furas", "Deleted")[0] == REMOVED
    assert canonical_source_status("furas", "EXPIRED")[0] == EXPIRED
    assert canonical_source_status("furas", "ملغاة")[0] == CANCELLED
    assert canonical_source_status("ncp", None, "2020-01-01", now=datetime(2026, 10, 19, tzinfo=timezone.utc))[0] == EXPIRED


def test_date_only_deadline_is_valid_through_local_deadline_day():
    deadline = date(2026, 10, 21)
    assert parse_deadline("2026-10-21") == deadline
    assert parse_deadline("٢٠٢٦-١٠-٢١") == deadline
    assert canonical_source_status("ncp", None, "2026-10-21", now=datetime(2026, 10, 21, 20, tzinfo=timezone.utc))[0] == UNSPECIFIED
    assert canonical_source_status("ncp", None, "2026-10-21", now=datetime(2026, 10, 21, 21, tzinfo=timezone.utc))[0] == EXPIRED


def test_local_today_uses_saudi_timezone_and_date_parsing_handles_bad_values():
    assert local_today(datetime(2026, 10, 21, 21, 30, tzinfo=timezone.utc)) == date(2026, 10, 22)
    assert parse_deadline(None) is None
    assert parse_deadline("") is None
    assert parse_deadline("not-a-date") is None


def test_offset_deadline_uses_saudi_calendar_day_and_naive_datetime_is_reviewed():
    assert parse_deadline("2026-10-20T22:30:00Z") == date(2026, 10, 21)
    assert parse_deadline("2026-10-21T00:30:00+03:00") == date(2026, 10, 21)
    assert parse_deadline("2026-10-21T00:30:00") is None
    assert canonical_source_status("ncp", None, "2026-10-20T22:30:00Z",
        now=datetime(2026, 10, 21, 20, tzinfo=timezone.utc))[0] == UNSPECIFIED
    assert canonical_source_status("ncp", None, "2026-10-20T22:30:00Z",
        now=datetime(2026, 10, 21, 21, tzinfo=timezone.utc))[0] == EXPIRED


def test_explicit_active_source_state_and_passed_deadline_is_a_conflict_not_silent_override():
    state, flags = canonical_source_status("alahsa-opportunities", "متاحة", "2020-01-01",
        now=datetime(2026, 10, 19, tzinfo=timezone.utc))
    assert state == AVAILABLE
    assert "STATUS_DEADLINE_CONFLICT" in flags


def test_master_aggregation_decision_table():
    cases = [
        ([AVAILABLE, REMOVED], AVAILABLE),
        ([AVAILABLE, EXPIRED], AVAILABLE),
        ([EXPIRED, REMOVED], EXPIRED),
        ([CANCELLED, REMOVED], CANCELLED),
        ([UNKNOWN, AVAILABLE], AVAILABLE),
        ([UNSPECIFIED, AVAILABLE], AVAILABLE),
        ([CANCELLED, PUBLISHED], STATUS_REVIEW),
        ([EXPIRED], EXPIRED),
        ([REMOVED], REMOVED),
        ([UNKNOWN], UNKNOWN),
        ([UNSPECIFIED], UNSPECIFIED),
        ([], UNSPECIFIED),
    ]
    for evidence, expected in cases:
        actual, _ = aggregate_master_status(evidence)
        assert actual == expected, evidence


def test_master_aggregation_keeps_nonterminal_conflict_flags_for_review():
    _, flags = aggregate_master_status([AVAILABLE, EXPIRED])
    assert flags == ["MULTI_SOURCE_STATUS_CONFLICT"]
    _, flags = aggregate_master_status([CANCELLED, AVAILABLE])
    assert flags == ["SOURCE_STATUS_CONFLICT_CANCELLED_AND_LIVE"]


def test_published_status_adjudication_preserves_expiry_removal_cancellation_and_raw_values():
    cases = [
        ("CURRENT", [{"source_record_id":1,"source_key":"furas","raw_status":"Announced","canonical_status":"منشورة"}], AVAILABLE),
        ("EXPIRED", [{"source_record_id":2,"source_key":"source","raw_status":"منتهية","canonical_status":"منتهية"}], EXPIRED),
        ("REMOVED", [{"source_record_id":3,"source_key":"source","raw_status":"Deleted","canonical_status":"أزيلت من المصدر"}], REMOVED),
        ("CANCELLED", [{"source_record_id":4,"source_key":"source","raw_status":"Cancelled","canonical_status":"ملغاة"}], CANCELLED),
        ("CONFLICT", [
            {"source_record_id":5,"source_key":"furas","raw_status":"Announced","canonical_status":"منشورة"},
            {"source_record_id":6,"source_key":"source","raw_status":"منتهية","canonical_status":"منتهية"},
        ], STATUS_REVIEW),
    ]
    for canonical, evidence, expected in cases:
        decisions, _ = build_status_plan({"masters":[{"id":1,"canonical_id":canonical,
            "title_ar":"فرصة اختبار","status":PUBLISHED,"sources":evidence}]})
        assert decisions[0]["after_status"] == expected
        assert decisions[0]["source_evidence"] == [{
            "source_record_id":row["source_record_id"], "source_key":row["source_key"],
            "raw_status":row["raw_status"], "canonical_status":row["canonical_status"], "deadline":None,
        } for row in evidence]


def test_status_api_dashboard_filters_search_pagination_details_and_exports_agree(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"engine",engine)
    now=datetime.now(timezone.utc)
    with factory() as db:
        source=Source(source_key="fixture-status",source_name_ar="مصدر الحالة",organization_name="جهة",
            base_url="https://status.test",opportunities_url="https://status.test/list",technical_health="HEALTHY",
            coverage_status="COMPLETE_PUBLIC_SOURCE",enabled=True,priority=1)
        db.add(source);db.flush()
        rows=[]
        for index,status in enumerate((AVAILABLE,AVAILABLE,PUBLISHED,EXPIRED,AWARDED),1):
            master=Opportunity(canonical_id=f"STATUS-{index}",title_ar=f"فرصة حالة {index}",normalized_title=f"فرصة حالة {index}",
                opportunity_owner="جهة",primary_publication_platform="مصدر الحالة",city="الأحساء",status=status,
                first_seen_at=now,last_seen_at=now,last_updated_at=now,created_at=now,updated_at=now)
            db.add(master);db.flush();rows.append(master)
            db.add(SourceOpportunity(source_id=source.id,master_opportunity_id=master.id,source_opportunity_id=str(index),
                source_title=master.title_ar,normalized_source_title=master.normalized_title,source_url=f"https://status.test/{index}",
                raw_status=status,canonical_status=status,raw_dates={},raw_data_json={"status":status},standardized_data_json={},
                first_seen_at=now,last_seen_at=now,content_hash=f"hash-{index}",parser_version="fixture"))
        db.commit();ids=[row.id for row in rows]
    client=TestClient(main.app)
    try:
        status_value=AVAILABLE
        listing=client.get("/api/opportunities",params={"status":status_value,"limit":1,"offset":1}).json()
        assert listing["total"]==3 and len(listing["items"])==1
        assert listing["items"][0]["status"]==AVAILABLE
        legacy_listing=client.get("/api/opportunities",params={"status":"PUBLISHED","limit":500}).json()
        assert legacy_listing["total"]==3 and all(item["status"]==AVAILABLE for item in legacy_listing["items"])
        searched=client.get("/api/opportunities",params={"status":status_value,"q":"فرصة حالة 2"}).json()
        assert searched["total"]==1
        dashboard=client.get("/api/data-dashboard").json()
        status_counts={entry["name"]:entry["count"] for entry in dashboard["by_status"]}
        assert status_counts[AVAILABLE]==3 and PUBLISHED not in status_counts and status_counts[EXPIRED]==1 and status_counts[AWARDED]==1
        historical=client.get("/api/opportunities",params={"lifecycle":"historical","limit":500}).json()
        assert historical["total"]==2 and {row["status"] for row in historical["items"]}=={EXPIRED,AWARDED}
        historical_dashboard=client.get("/api/data-dashboard",params={"lifecycle":"historical"}).json()
        assert historical_dashboard["kpis"]["total"]==2 and historical_dashboard["kpis"]["historical"]==2
        drilldown=client.get("/api/data-dashboard",params={"status":status_value}).json()
        assert drilldown["kpis"]["total"]==3
        detail=client.get(f"/api/opportunities/{ids[0]}").json()
        assert detail["status"]==AVAILABLE and detail["sources"][0]["canonical_status"]==AVAILABLE
        assert detail["sources"][0]["raw_status"]==AVAILABLE
        csv_result=client.get("/api/export.csv",params={"status":status_value})
        assert csv_result.status_code==200 and len(csv_result.content.decode("utf-8-sig").splitlines())==4
        xlsx_result=client.get("/api/export.xlsx",params={"status":status_value})
        assert xlsx_result.status_code==200
        from openpyxl import load_workbook
        from io import BytesIO
        book=load_workbook(BytesIO(xlsx_result.content),read_only=True,data_only=True)
        sheet=book.active;header=next(sheet.iter_rows(min_row=6,max_row=6,values_only=True))
        status_column=header.index("الحالة")
        rows=list(sheet.iter_rows(min_row=7,values_only=True))
        assert len(rows)==3 and all(row[status_column]==AVAILABLE for row in rows)
    finally:
        client.close();engine.dispose()

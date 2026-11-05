from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.models import (
    Base,
    LocationReview,
    Opportunity,
    QualificationReview,
    Source,
    SourceOpportunity,
    SourceOpportunityDatasetMembership,
    SyncJob,
)


def test_source_coverage_api_separates_lifecycle_from_latest_failed_job(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", engine)
    now = datetime.now(timezone.utc)

    with factory() as db:
        invest = Source(
            source_key="invest-saudi", source_name_ar="استثمر في السعودية", organization_name="وزارة الاستثمار",
            base_url="https://investsaudi.sa", opportunities_url="https://investsaudi.sa/investment-opportunities",
            technical_health="WARNING", coverage_status="COMPLETE_PUBLIC_SOURCE", enabled=True, priority=1,
            missing_confirmation_threshold=3,
        )
        furas = Source(
            source_key="furas", source_name_ar="فرص", organization_name="وزارة البلديات والإسكان",
            base_url="https://furas.momah.gov.sa", opportunities_url="https://furas.momah.gov.sa/ar/list-opportunities",
            technical_health="HEALTHY", coverage_status="COMPLETE_PUBLIC_SOURCE", enabled=True, priority=2,
            missing_confirmation_threshold=3,
        )
        modon = Source(
            source_key="modon", source_name_ar="مدن", organization_name="الهيئة السعودية للمدن الصناعية ومناطق التقنية",
            base_url="https://modon.gov.sa", opportunities_url="https://modon.gov.sa/en/InvestmentOpportunities",
            technical_health="WARNING", coverage_status="PUBLIC_COVERAGE_LIMITED", enabled=True, priority=3,
            missing_confirmation_threshold=3,
        )
        db.add_all([invest, furas, modon])
        db.flush()
        master = Opportunity(
            canonical_id="COVERAGE-1", title_ar="فرصة اختبار", normalized_title="فرصة اختبار",
            primary_publication_platform="فرص", city="الأحساء", status="متاحة", location_confidence_score=1,
            location_detection_method="fixture", location_evidence="fixture", data_quality_score=1,
            manual_review_required=False, first_seen_at=now, last_seen_at=now, last_updated_at=now,
            created_at=now, updated_at=now,
        )
        db.add(master)
        db.flush()

        def source_record(source, external_id, status="متاحة", master_id=None):
            return SourceOpportunity(
                source_id=source.id,
                master_opportunity_id=master_id,
                source_opportunity_id=external_id,
                source_title=external_id,
                normalized_source_title=external_id,
                source_url=f"{source.base_url}/{external_id}",
                canonical_status=status,
                raw_dates={},
                raw_data_json={},
                first_seen_at=now,
                last_seen_at=now,
                content_hash=external_id,
                parser_version="test",
            )

        invest_current_linked = source_record(invest, "invest-1", master_id=master.id)
        invest_current_unlinked = source_record(invest, "invest-2")
        # Invest Saudi absences are per current dataset membership, not the stale
        # SourceOpportunity-level counter. Two pending datasets for one identity
        # must count once; a record counter alone must not count as a pending case.
        invest_current_unlinked.missing_successful_checks = 2
        invest_historical = source_record(invest, "invest-old", status="أزيلت من المصدر")
        furas_current = source_record(furas, "furas-1", master_id=master.id)
        furas_historical = source_record(furas, "furas-old", status="أزيلت من المصدر", master_id=master.id)
        db.add_all([invest_current_linked, invest_current_unlinked, invest_historical, furas_current, furas_historical])
        db.flush()

        for row, dataset, is_current in (
            (invest_current_linked, "Investment projects", True),
            (invest_current_unlinked, "Investment projects", True),
            (invest_historical, "Investment projects", False),
        ):
            db.add(SourceOpportunityDatasetMembership(
                source_opportunity_id=row.id, dataset_name=dataset, endpoint="https://official.test/api",
                first_seen_at=now, last_seen_at=now, is_current=is_current,
                missing_successful_checks=0 if is_current else 3,
            ))
        db.add(SourceOpportunityDatasetMembership(
            source_opportunity_id=invest_current_unlinked.id, dataset_name="Opportunities",
            endpoint="https://official.test/opportunities", first_seen_at=now, last_seen_at=now,
            is_current=True, missing_successful_checks=1,
        ))

        db.add(LocationReview(
            source_id=invest.id, external_id="location-review", title="قيد مراجعة الموقع",
            confidence_score=0.5, created_at=now,
        ))
        db.add(QualificationReview(
            source_id=furas.id, external_id="qualification-review", title="قيد مراجعة التأهيل",
            source_url="https://furas.momah.gov.sa/review", reason="fixture", status="PENDING", created_at=now,
        ))
        db.add_all([
            SyncJob(source_id=invest.id, started_at=now, finished_at=now, status="SUCCESS", job_state="COMPLETED",
                    trigger_type="scheduled", unique_records=2, pages_requested=1, pages_successful=1),
            SyncJob(source_id=invest.id, started_at=now, finished_at=now, status="FAILED", job_state="FAILED",
                    trigger_type="scheduled", unique_records=0, pages_requested=0, pages_successful=0),
        ])
        db.commit()

    client = TestClient(main.app)
    try:
        response = client.get("/api/source-coverage")
        assert response.status_code == 200, response.text
        data = {row["source_key"]: row for row in response.json()["sources"]}

        assert data["invest-saudi"]["technical_health"] == "WARNING"
        assert data["invest-saudi"]["coverage_status"] == "COMPLETE_PUBLIC_SOURCE"
        assert data["invest-saudi"]["source_record_total"] == 3
        assert data["invest-saudi"]["current_source_record_count"] == 2
        assert data["invest-saudi"]["historical_source_record_count"] == 1
        assert data["invest-saudi"]["qualified_current_source_record_count"] == 1
        assert data["invest-saudi"]["pending_location_review_count"] == 1
        assert data["invest-saudi"]["pending_absence_confirmation_count"] == 1
        assert data["invest-saudi"]["last_successful_scan"]["enumerated_count"] == 2
        assert data["invest-saudi"]["last_successful_scan"]["accepted_al_ahsa_count"] == 0
        assert "active_count" in data["invest-saudi"]["last_successful_scan"]
        assert data["invest-saudi"]["last_successful_scan"]["job_id"] < 3

        assert data["furas"]["current_source_record_count"] == 1
        assert data["furas"]["historical_source_record_count"] == 1
        assert data["furas"]["qualified_current_source_record_count"] == 1
        assert data["furas"]["pending_qualification_review_count"] == 1
        assert data["modon"]["coverage_status"] == "PUBLIC_COVERAGE_LIMITED"
        assert data["modon"]["coverage_status"] not in {"COMPLETE_PUBLIC_SOURCE", "COMPLETE_FOR_DEFINED_SCOPE"}
    finally:
        client.close()
        engine.dispose()

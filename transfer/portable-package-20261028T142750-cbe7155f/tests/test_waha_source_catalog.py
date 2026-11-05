from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main, service
from app.adapters import ADAPTERS
from app.data_quality import evaluate_data_quality
from app.models import Base, Source


def _database(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", engine)
    return engine, factory


def test_waha_is_seeded_as_limited_catalog_entry_without_sync_adapter(monkeypatch):
    engine, factory = _database(monkeypatch)
    try:
        with factory() as db:
            service.seed_sources(db)
            waha = db.scalar(select(Source).where(Source.source_key == "waha-development"))
            alahsa = db.scalars(select(Source).where(Source.source_key == "alahsa-opportunities")).all()

            assert waha is not None
            assert waha.source_name_ar == "شركة واحة للتنمية والتطوير"
            assert waha.base_url == "https://waha.sa/"
            assert waha.opportunities_url == "https://waha.sa/opportunities.html"
            assert waha.coverage_status == "PUBLIC_COVERAGE_LIMITED"
            assert waha.enabled is False
            assert waha.source_key not in ADAPTERS
            assert "84" in waha.coverage_notes
            assert "لا تُدرج كفرص" in waha.coverage_notes
            assert len(alahsa) == 1
            assert alahsa[0].base_url == "https://alahsa-opportunities.com/"
    finally:
        engine.dispose()


def test_waha_appears_in_source_coverage_and_filter_without_opportunity_records(monkeypatch):
    engine, factory = _database(monkeypatch)
    try:
        with factory() as db:
            service.seed_sources(db)
        client = TestClient(main.app)
        try:
            coverage_response = client.get("/api/source-coverage")
            assert coverage_response.status_code == 200
            coverage = {row["source_key"]: row for row in coverage_response.json()["sources"]}
            assert coverage["waha-development"]["enabled"] is False
            assert coverage["waha-development"]["coverage_status"] == "PUBLIC_COVERAGE_LIMITED"
            assert coverage["waha-development"]["source_record_total"] == 0
            assert coverage["waha-development"]["last_successful_scan"] is None

            filters_response = client.get("/api/filters")
            assert filters_response.status_code == 200
            filters = filters_response.json()
            assert any(row["key"] == "waha-development" for row in filters["sources"])
            assert filters["option_counts"]["sources"]["waha-development"] == 0
        finally:
            client.close()
    finally:
        engine.dispose()


def test_waha_quality_gates_are_zero_without_importing_map_features(monkeypatch):
    engine, factory = _database(monkeypatch)
    try:
        with factory() as db:
            service.seed_sources(db)
            before = db.query(Source).count()
            result = evaluate_data_quality(db, scope="full", persist=False)
            after = db.query(Source).count()
            assert before == after
            gates = {gate["gate_key"]: gate for gate in result["gates"]}
            expected = {
                "WAHA_GENERIC_CONTENT_INGESTED",
                "WAHA_FURAS_DUPLICATE_MASTER",
                "WAHA_MISSING_PROVENANCE",
                "WAHA_OWNER_PUBLISHER_CONFUSION",
                "WAHA_UNRECONCILED_SOURCE_RECORD",
            }
            assert expected <= gates.keys()
            assert all(gates[key]["observed"] == 0 for key in expected)
    finally:
        engine.dispose()

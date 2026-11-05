import hashlib
import json

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.adapters import RawOpportunity
from app.furas_capture_manifest import record_payload_sha256, validate_capture_manifest
from app.models import Base, Opportunity, Source, SourceObservation, SourceOpportunity
from app.service import _safe_record


def _fixture_manifest(*, complete=True):
    attrs = {
        "OBJECTID": 7,
        "OPPORTUNITYID": "001-26-0007",
        "ENDDATE": None,
        "STARTDATE": 1792540800000,
        "CITY_ID": "005011001",
    }
    geometry = {"x": None, "y": 25.0}
    record_hash = record_payload_sha256(attrs, geometry)
    record = {
        "provider_id_raw": attrs["OPPORTUNITYID"],
        "provider_id_adapter_key": attrs["OPPORTUNITYID"],
        "objectid_raw": attrs["OBJECTID"],
        "raw_payload": {"attributes": attrs, "geometry": geometry},
        "raw_record_sha256": record_hash,
    }
    from app.furas_capture_manifest import sha256_json
    index = [{"provider_id_raw": attrs["OPPORTUNITYID"], "objectid_raw": 7,
              "raw_record_sha256": record_hash}]
    return {
        "schema": "furas-national-durable-capture-v1",
        "capture": {
            "production_writes": False,
            "read_only_official_public_source": True,
            "pagination_complete": complete,
            "source_total_reported": 1,
            "records_received": 1,
            "unique_records": 1,
            "duplicate_source_ids": 0,
            "missing_object_ids": 0,
            "page_count": 1,
            "request_count": 1,
            "membership_sha256_sorted_provider_ids": sha256_json(["001-26-0007"]),
            "membership_sha256_sorted_objectids": sha256_json(["7"]),
            "ordered_capture_index_sha256": sha256_json(index),
        },
        "records": [record],
        "pages": [{"page_number": 1, "record_count": 1, "provider_ids": ["001-26-0007"],
                   "object_ids": [7]}],
        "requests": [{"request_number": 1, "requested_url": "https://gis.example/query",
                      "response_sha256": hashlib.sha256(b"fixture").hexdigest()}],
    }


def test_capture_manifest_preserves_typed_raw_values_and_validates_membership():
    document = _fixture_manifest()
    assert validate_capture_manifest(document) == {"records": 1, "pages": 1, "requests": 1}
    attrs = document["records"][0]["raw_payload"]["attributes"]
    assert attrs["OPPORTUNITYID"] == "001-26-0007"
    assert isinstance(attrs["STARTDATE"], int)
    assert attrs["ENDDATE"] is None
    assert attrs["CITY_ID"] == "005011001"


def test_capture_manifest_rejects_incomplete_or_tampered_capture():
    with pytest.raises(ValueError, match="Incomplete capture"):
        validate_capture_manifest(_fixture_manifest(complete=False))
    document = _fixture_manifest()
    document["records"][0]["raw_payload"]["attributes"]["OPPORTUNITYID"] = "tampered"
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_capture_manifest(document)


def test_capture_script_requires_explicit_read_only_acknowledgement(monkeypatch, tmp_path):
    import sys
    from scripts.capture_furas_national_manifest import main
    monkeypatch.setattr(sys, "argv", ["capture_furas_national_manifest.py", "--output", str(tmp_path / "capture.json")])
    with pytest.raises(SystemExit):
        main()


def test_capture_script_never_overwrites_an_existing_manifest(monkeypatch, tmp_path):
    import sys
    from scripts.capture_furas_national_manifest import main
    destination = tmp_path / "capture.json"
    destination.write_text("existing audit evidence", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["capture_furas_national_manifest.py", "--output", str(destination),
                                       "--confirm-read-only-public-capture"])
    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        main()
    assert destination.read_text(encoding="utf-8") == "existing audit evidence"


def test_repeated_furas_ingestion_is_idempotent_and_keeps_raw_provenance():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = Source(
            source_key="furas", source_name_ar="فرص", organization_name="وزارة البلديات والإسكان",
            base_url="https://furas.momah.gov.sa", opportunities_url="https://furas.momah.gov.sa/ar/list-opportunities",
            priority=1, polling_frequency_minutes=60, enabled=True, extraction_method="fixture",
            notes="", sync_status="HEALTHY", last_record_count=0,
        )
        db.add(source)
        db.flush()
        payload = {"attributes": {"OBJECTID": 77, "OPPORTUNITYID": "01-26-000077", "ENDDATE": None}}
        record = RawOpportunity(
            "01-26-000077", "موقع استثماري للاختبار", "https://furas.momah.gov.sa/ar/opportunity/01-26-000077",
            status="Announced", reference="01-26-000077", deadline=None, location="الأحساء",
            location_source_filtered=True, raw=payload,
        )
        counts = {"raw_count": 0, "ahsa_count": 0, "new_count": 0, "duplicate_count": 0,
                  "update_count": 0, "rejected_count": 0}
        _safe_record(db, source, record, counts)
        db.commit()
        _safe_record(db, source, record, counts)
        db.commit()
        assert db.scalar(select(func.count(SourceOpportunity.id))) == 1
        assert db.scalar(select(func.count(Opportunity.id))) == 1
        row = db.scalar(select(SourceOpportunity))
        assert row.source_opportunity_id == "01-26-000077"
        assert row.raw_data_json == payload
        assert db.scalar(select(func.count(SourceObservation.id))) == 1
    engine.dispose()


def test_same_source_similar_titles_with_different_official_ids_stay_separate():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = Source(
            source_key="furas", source_name_ar="فرص", organization_name="وزارة البلديات والإسكان",
            base_url="https://furas.momah.gov.sa", opportunities_url="https://furas.momah.gov.sa/ar/list-opportunities",
            priority=1, polling_frequency_minutes=60, enabled=True, extraction_method="fixture",
            notes="", sync_status="HEALTHY", last_record_count=0,
        )
        db.add(source)
        db.flush()
        counts = {"raw_count": 0, "ahsa_count": 0, "new_count": 0, "duplicate_count": 0,
                  "update_count": 0, "rejected_count": 0}
        for pid in ("01-26-000101", "01-26-000102"):
            _safe_record(db, source, RawOpportunity(
                pid, "موقع استثماري مشابه", f"https://furas.momah.gov.sa/ar/opportunity/{pid}",
                status="Announced", reference=pid, location="الأحساء", location_source_filtered=True,
                raw={"attributes": {"OPPORTUNITYID": pid}},
            ), counts)
            db.commit()
        assert db.scalar(select(func.count(SourceOpportunity.id))) == 2
        assert db.scalar(select(func.count(Opportunity.id))) == 2
    engine.dispose()


def test_current_durable_capture_manifest_validates():
    """Repository acceptance check; target capture file is checked by the helper, not refetched."""
    from pathlib import Path
    path = Path("docs/validation/deployment/nationwide-source-expansion/FURAS-NATIONAL-DURABLE-CAPTURE-MANIFEST-20261105.json")
    if not path.exists():
        pytest.skip("current public capture manifest is not present in this checkout")
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    result = validate_capture_manifest(document)
    assert result["records"] == 6548
    assert result["pages"] == 66

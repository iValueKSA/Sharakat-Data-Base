"""Test-only server guard and synthetic-reference readiness shim."""
import os
from urllib.parse import urlparse

if os.getenv("ISOLATED_NATIONAL_UI_TEST") != "I_UNDERSTAND_ISOLATED_TEST_ONLY":
    raise RuntimeError("This server helper is isolated-test only")
if os.getenv("ENVIRONMENT") != "isolated_test":
    raise RuntimeError("Unexpected environment")
if os.getenv("NATIONAL_UI_ENABLED", "").lower() != "true" or os.getenv("NATIONAL_MAP_ENABLED", "").lower() != "true":
    raise RuntimeError("National UI and map test flags must be true in the isolated environment")
if os.getenv("NATIONAL_DASHBOARD_ENABLED", "").lower() != "true":
    raise RuntimeError("National dashboard test flag must be true in the isolated environment")
if os.getenv("FURAS_NATIONAL_ENUMERATION_ENABLED", "").lower() != "false":
    raise RuntimeError("Furas national enumeration must remain off")
parsed = urlparse(os.environ["DATABASE_URL"])
if parsed.hostname != "nwx-ui-db" or parsed.path.lstrip("/") not in {"app", "app_nocity"}:
    raise RuntimeError("Database URL did not target the isolated test database")

from sqlalchemy import select, text
from app.database import SessionLocal
from app.geographic_references import validate_reference_payload
from app.models import GeographicReferenceDataset, GeographicReferenceUnit
from app import main

with SessionLocal() as db:
    revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != "0025_source_geographic_coverage":
        raise RuntimeError(f"Unexpected isolated migration revision: {revision}")


def readiness(db):
    dataset = db.scalar(select(GeographicReferenceDataset).where(
        GeographicReferenceDataset.is_current.is_(True)).order_by(
        GeographicReferenceDataset.imported_at.desc(), GeographicReferenceDataset.id.desc()))
    if dataset is None or (dataset.provenance_json or {}).get("test_only") is not True:
        return None, {"ready": False, "reasons": ["test_reference_missing"],
                      "counts_by_level": {"region": 0, "governorate": 0, "city": 0}}
    units = db.scalars(select(GeographicReferenceUnit).where(
        GeographicReferenceUnit.dataset_id == dataset.id).order_by(
        GeographicReferenceUnit.level, GeographicReferenceUnit.external_id)).all()
    level_order = {"country": 0, "region": 1, "governorate": 2, "city": 3}
    units.sort(key=lambda row: (level_order.get(row.level, 99), row.external_id))
    rows = [{"level": row.level, "external_id": row.external_id,
             "parent_external_id": row.parent_external_id, "name_ar": row.name_ar,
             "name_en": row.name_en, "source_record": row.source_record_json} for row in units]
    provenance = dataset.provenance_json or {}
    metadata = {"dataset_key": dataset.dataset_key, "version": dataset.version,
                "operator": dataset.operator, "source_url": dataset.source_url,
                "public_access_verified": provenance.get("public_access_verified") is True,
                "source_authority_verified": provenance.get("source_authority_verified") is True,
                "stable_external_ids": provenance.get("stable_external_ids_verified") is True,
                "parent_relationships_verified": provenance.get("parent_relationships_verified") is True,
                "completeness_verified": provenance.get("completeness_verified") is True,
                "effective_date": dataset.effective_date, "content_sha256": dataset.content_sha256,
                "coverage_by_level": dataset.coverage_json or {},
                "expected_counts": provenance.get("expected_counts") or {}, "test_only": True}
    report = validate_reference_payload(metadata, rows, test_mode=True)
    if not report["valid"]:
        return dataset, {"ready": False, "reasons": report["errors"],
                         "counts_by_level": report["counts_by_level"], "validation": report}
    return dataset, {"ready": True, "reasons": [], "counts_by_level": report["counts_by_level"],
                     "validation": report}


main._geographic_reference_readiness = readiness
_options = main.geographic_reference_options


def options_with_test_alias(*args, **kwargs):
    result = _options(*args, **kwargs)
    if kwargs.get("level") == "governorate" and result.get("items"):
        result["items"] = [dict(item, name_ar="الأحساء") if item["id"] == "TEST_GOV_01" else item
                           for item in result["items"]]
    return result


main.geographic_reference_options = options_with_test_alias
for route in main.app.routes:
    if getattr(route, "path", None) == "/api/geography/options":
        route.endpoint = options_with_test_alias
        route.dependant.call = options_with_test_alias

import uvicorn
uvicorn.run(main.app, host="0.0.0.0", port=8000, log_level="warning")

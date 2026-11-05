import hashlib
import json
import os
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.geographic_references import canonical_dataset_digest, import_reference_dataset
from app.models import GeographicReferenceDataset, GeographicReferenceUnit, Opportunity, OpportunityLocation, Source, SourceOpportunity


mode = os.environ["ISOLATED_SEED_MODE"]
payload = json.load(open("tests/fixtures/geographic-reference-test-only.json", encoding="utf-8"))
units = payload["units"]
metadata = dict(payload["metadata"])
if mode == "nocity":
    units = [row for row in units if row["level"] != "city"]
    units = [dict(row) for row in units]
    metadata["coverage_by_level"] = dict(metadata["coverage_by_level"], city=False)
    metadata["expected_counts"] = dict(metadata["expected_counts"], city=0)
metadata["content_sha256"] = canonical_dataset_digest(units)

with SessionLocal.begin() as db:
    assert not db.scalar(select(GeographicReferenceDataset.id)), "isolated DB must start without a reference"
    imported = import_reference_dataset(db, metadata, units, dry_run=False, test_mode=True)
    reference_units = db.scalars(select(GeographicReferenceUnit).where(
        GeographicReferenceUnit.dataset_id == imported["dataset_id"])).all()
    by_external = {(row.level, row.external_id): row for row in reference_units}
    now = datetime.now(timezone.utc)
    sources = []
    for key, name in (("TEST_SOURCE_A", "مصدر اختباري أ"), ("TEST_SOURCE_B", "مصدر اختباري ب")):
        source = Source(source_key=key, source_name_ar=name, organization_name="Synthetic test fixture",
                        base_url="https://example.invalid", opportunities_url="https://example.invalid/TEST_ONLY",
                        priority=1, enabled=True)
        db.add(source)
        sources.append(source)
    db.flush()

    for index in range(1, 61):
        scope = {1: "SPECIFIC_LOCATION", 2: "MULTIPLE_VERIFIED_LOCATIONS", 3: "REGION_WIDE",
                 4: "NATIONWIDE", 5: "UNSPECIFIED"}.get(index, "SPECIFIC_LOCATION")
        governorate = by_external[("governorate", "TEST_GOV_02" if index % 2 == 0 else "TEST_GOV_01")]
        city = by_external.get(("city", "TEST_CITY_03" if index % 2 == 0 else "TEST_CITY_01"))
        sector = "TEST_SECTOR_A" if index % 2 else "TEST_SECTOR_B"
        status = "متاحة" if index % 3 else "مفتوحة"
        coordinates = index in (1, 2)
        opportunity = Opportunity(
            canonical_id=f"TEST_MASTER_{index:03d}", title_ar=f"فرصة اختبار اصطناعية {index:03d}",
            title_en=f"Synthetic test opportunity {index:03d}", normalized_title=f"test synthetic opportunity {index:03d}",
            reference_number=f"TEST_REF_{index:03d}", reference_number_normalized=f"TEST_REF_{index:03d}",
            opportunity_owner="TEST_OWNER", primary_publication_platform="TEST_SOURCE_A", sector=sector,
            activity="TEST_ACTIVITY", sub_activity="TEST_SUBACTIVITY", subsector="TEST_SUBSECTOR",
            opportunity_type="TEST_OPPORTUNITY", investment_model="TEST_MODEL",
            city=city.external_id if city else "", district="TEST_DISTRICT", status=status,
            short_description="TEST_ONLY synthetic fixture record", geographic_scope=scope,
            geography_reference_unit_id=(city.id if scope in ("SPECIFIC_LOCATION", "MULTIPLE_VERIFIED_LOCATIONS") and city
                                         else governorate.id if scope in ("SPECIFIC_LOCATION", "MULTIPLE_VERIFIED_LOCATIONS", "REGION_WIDE") else None),
            geography_evidence_json={"test_only": True, "fixture": "TEST_ONLY_NATIONWIDE_REFERENCE_FIXTURE"},
            latitude=24.7 + (index % 10) * 0.002 if coordinates else None,
            longitude=46.7 + (index % 10) * 0.002 if coordinates else None,
            coordinate_provenance_json=None,
            first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now,
        )
        if scope in ("REGION_WIDE", "NATIONWIDE", "UNSPECIFIED"):
            opportunity.geography_reference_unit_id = None
        db.add(opportunity)
        db.flush()
        for source in (sources if index == 1 else sources[:1]):
            external_id = f"TEST_SOURCE_{source.source_key}_{index:03d}"
            record = SourceOpportunity(
                source_id=source.id, master_opportunity_id=opportunity.id, source_opportunity_id=external_id,
                official_source_id_original=external_id, official_source_id_normalized=external_id,
                source_title=opportunity.title_ar, normalized_source_title=opportunity.normalized_title,
                source_url=f"https://example.invalid/TEST_ONLY/{external_id}", source_owner="TEST_OWNER",
                source_sector=sector, normalized_sector=sector, raw_location="TEST_ONLY", raw_status=status,
                canonical_status=status, raw_data_json={"test_only": True}, standardized_data_json={"test_only": True},
                first_seen_at=now, last_seen_at=now, content_hash=hashlib.sha256(external_id.encode()).hexdigest(),
                parser_version="TEST_ONLY",
            )
            db.add(record)
            db.flush()
            if index == 2:
                units = ((by_external[("city", "TEST_CITY_01")], by_external[("city", "TEST_CITY_02")])
                         if city else (by_external[("governorate", "TEST_GOV_01")],
                                       by_external[("governorate", "TEST_GOV_02")]))
                for unit in units:
                    db.add(OpportunityLocation(
                        source_opportunity_id=record.id, location_name=unit.external_id,
                        location_scope="MULTIPLE_LOCATIONS", source_location_text=unit.external_id,
                        geography_reference_unit_id=unit.id,
                        source_evidence_json={"test_only": True, "verified": True,
                                             "source_url": "https://example.invalid/TEST_ONLY/location"},
                    ))
        if coordinates:
            source_identity = {"verified": True, "verification_method": "DIRECT_SOURCE_COORDINATE",
                "source_record_identity_matches": True, "source_record_id": record.id,
                "source_opportunity_id": record.source_opportunity_id, "source_url": record.source_url,
                "boundary_validation": {"status": "VERIFIED_IN_SAUDI",
                    "method": "POINT_IN_OFFICIAL_REGION_POLYGON"}, "test_only": True}
            if index == 2:
                opportunity.coordinate_provenance_json = {"test_only": True, "locations": [
                    {**source_identity, "latitude": latitude, "longitude": longitude,
                     "source_latitude": latitude, "source_longitude": longitude}
                    for latitude, longitude in ((24.7, 46.7), (24.702, 46.702))]}
            else:
                opportunity.coordinate_provenance_json = {**source_identity,
                    "source_latitude": opportunity.latitude, "source_longitude": opportunity.longitude}

print(json.dumps({"mode": mode, "dataset_id": imported["dataset_id"], "unit_count": len(units),
                  "masters": 60, "source_opportunities": 61,
                  "city_available": bool(metadata["coverage_by_level"]["city"])}))

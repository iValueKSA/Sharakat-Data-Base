"""Verify existing Furas points against raw records and the imported official polygons.

Default mode is read-only. --apply stores evidence only; it never changes a
coordinate, creates a fallback, or rewrites a source record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import (GeographicReferenceDataset, GeographicReferenceUnit,
                        Opportunity, Source, SourceOpportunity, SystemEvent)
from scripts.import_geographic_reference import verify_backup


def _polygons(geometry: dict) -> list[list[list[list[float]]]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if kind == "Polygon":
        return [coordinates]
    if kind == "MultiPolygon":
        return coordinates
    return []


def _bbox(ring: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in ring]
    ys = [point[1] for point in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _inside_ring(longitude: float, latitude: float, ring: list[list[float]]) -> bool:
    inside = False
    prior = len(ring) - 1
    for index, (x2, y2) in enumerate(ring):
        x1, y1 = ring[prior]
        # Count points on the polygon edge as inside.
        cross = (longitude - x1) * (y2 - y1) - (latitude - y1) * (x2 - x1)
        if abs(cross) < 1e-10 and min(x1, x2) - 1e-10 <= longitude <= max(x1, x2) + 1e-10 \
                and min(y1, y2) - 1e-10 <= latitude <= max(y1, y2) + 1e-10:
            return True
        if (y1 > latitude) != (y2 > latitude):
            if longitude < (x2 - x1) * (latitude - y1) / (y2 - y1) + x1:
                inside = not inside
        prior = index
    return inside


def _inside_polygon(longitude: float, latitude: float, polygon) -> bool:
    if not polygon or not _inside_ring(longitude, latitude, polygon[0]):
        return False
    return not any(_inside_ring(longitude, latitude, hole) for hole in polygon[1:])


def _containing_regions(longitude: float, latitude: float, polygons) -> list[str]:
    found = []
    for unit, (xmin, ymin, xmax, ymax), ring_data in polygons:
        if not (xmin <= longitude <= xmax and ymin <= latitude <= ymax):
            continue
        if _inside_polygon(longitude, latitude, [ring for _, ring in ring_data]):
            found.append(unit.external_id)
    return found


def _geometry_index(units: list[GeographicReferenceUnit]):
    indexed = []
    for unit in units:
        for polygon in _polygons(unit.geometry_json or {}):
            rings = [(_bbox(ring), ring) for ring in polygon if ring]
            if rings:
                outer_bbox = rings[0][0]
                indexed.append((unit, outer_bbox, rings))
    return indexed


def build_report(db) -> tuple[GeographicReferenceDataset, dict]:
    dataset = db.scalar(select(GeographicReferenceDataset).where(
        GeographicReferenceDataset.dataset_key == "saudi_administrative_units",
        GeographicReferenceDataset.is_current.is_(True)))
    if dataset is None:
        raise ValueError("Current official Saudi geography reference is missing")
    furas = db.scalar(select(Source).where(Source.source_key == "furas"))
    if furas is None:
        raise ValueError("Furas source is missing")
    regions = db.scalars(select(GeographicReferenceUnit).where(
        GeographicReferenceUnit.dataset_id == dataset.id,
        GeographicReferenceUnit.level == "region")).all()
    polygons = _geometry_index(regions)
    rows = db.execute(select(SourceOpportunity, Opportunity).join(
        Opportunity, Opportunity.id == SourceOpportunity.master_opportunity_id).where(
        SourceOpportunity.source_id == furas.id, Opportunity.merged_into_id.is_(None))
        .order_by(Opportunity.id, SourceOpportunity.id)).all()
    report = {"furas_linked_source_rows": len(rows), "unique_current_masters": len({m.id for _, m in rows}),
              "direct_furas_coordinates_evaluated": 0, "verified_in_saudi": 0,
              "outside_saudi_review": 0, "invalid_coordinate": 0, "no_coordinate": 0,
              "identity_mismatch": 0, "master_coordinate_mismatch": 0,
              "swapped_order_would_be_inside": 0, "coordinate_duplicates": 0,
              "masters_with_verified_points": 0, "masters_with_unverified_points": 0,
              "masters_with_verified_physical_points": 0,
              "outside_boundary_specific_scope": 0, "outside_boundary_unspecified_scope": 0,
              "geographic_scope_counts": {}, "scope_excluded_from_map": 0,
              "assignments": []}
    scope_counts = Counter()
    coordinate_counts = Counter()
    point_frequency = Counter()
    inside_cache: dict[tuple[float, float], list[str]] = {}
    verified_masters: set[int] = set()
    unverified_masters: set[int] = set()
    for record, master in rows:
        scope_counts[master.geographic_scope or "UNSPECIFIED"] += 1
        raw = record.raw_data_json or {}
        attributes = raw.get("attributes") or {}
        geometry = raw.get("geometry") or {}
        if not geometry or geometry.get("x") is None or geometry.get("y") is None:
            report["no_coordinate"] += 1
            continue
        report["direct_furas_coordinates_evaluated"] += 1
        try:
            longitude = float(geometry["x"])
            latitude = float(geometry["y"])
        except (TypeError, ValueError):
            report["invalid_coordinate"] += 1
            continue
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or (latitude == 0 and longitude == 0):
            report["invalid_coordinate"] += 1
            continue
        point_frequency[(latitude, longitude)] += 1
        if not str(record.source_url or "").startswith("https://furas."):
            report["identity_mismatch"] += 1
            continue
        if str(attributes.get("OPPORTUNITYID") or "").strip() != str(record.source_opportunity_id).strip():
            report["identity_mismatch"] += 1
            continue
        if master.latitude is None or master.longitude is None \
                or abs(float(master.latitude) - latitude) > 1e-7 \
                or abs(float(master.longitude) - longitude) > 1e-7:
            report["master_coordinate_mismatch"] += 1
            continue
        point = (latitude, longitude)
        if point not in inside_cache:
            inside_cache[point] = _containing_regions(longitude, latitude, polygons)
        containing_regions = inside_cache[point]
        if containing_regions:
            report["verified_in_saudi"] += 1
            verified_masters.add(master.id)
            boundary_status = "VERIFIED_IN_SAUDI"
            boundary_method = "POINT_IN_OFFICIAL_REGION_POLYGON"
            if master.geographic_scope in {"SPECIFIC_LOCATION", "MULTIPLE_VERIFIED_LOCATIONS"}:
                report["masters_with_verified_physical_points"] += 1
        else:
            report["outside_saudi_review"] += 1
            unverified_masters.add(master.id)
            scope_key = "outside_boundary_unspecified_scope" if (master.geographic_scope or "UNSPECIFIED") == "UNSPECIFIED" \
                else "outside_boundary_specific_scope" if master.geographic_scope == "SPECIFIC_LOCATION" else None
            if scope_key:
                report[scope_key] += 1
            boundary_status = "SOURCE_COORDINATE_OUTSIDE_SAUDI_REVIEW"
            boundary_method = "POINT_IN_OFFICIAL_REGION_POLYGON"
            swapped = _containing_regions(latitude, longitude, polygons)
            if swapped:
                report["swapped_order_would_be_inside"] += 1
        raw_geometry_digest = hashlib.sha256(json.dumps(
            geometry, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        boundary_evidence = {"status": boundary_status, "method": boundary_method,
            "source_url": dataset.source_url, "reference_dataset_key": dataset.dataset_key,
            "reference_version": dataset.version, "reference_sha256": dataset.content_sha256,
            "containing_region_external_ids": containing_regions,
            "coordinate_order": "raw.geometry.y=latitude; raw.geometry.x=longitude (WGS84 EPSG:4326)"}
        report["assignments"].append({"master_id": master.id, "source_record_id": record.id,
            "source_opportunity_id": record.source_opportunity_id, "latitude": latitude,
            "longitude": longitude, "source_url": record.source_url,
            "source_record_identity_matches": True, "source_geometry_sha256": raw_geometry_digest,
            "verified": bool(containing_regions), "boundary_validation": boundary_evidence,
            "geographic_scope": master.geographic_scope or "UNSPECIFIED"})
    report["geographic_scope_counts"] = dict(sorted(scope_counts.items()))
    report["masters_with_verified_points"] = len(verified_masters)
    report["masters_with_unverified_points"] = len(unverified_masters)
    report["coordinate_duplicates"] = sum(max(0, count - 1) for count in point_frequency.values())
    report["scope_excluded_from_map"] = sum(count for scope, count in scope_counts.items()
        if scope in {"NATIONWIDE", "REGION_WIDE", "UNSPECIFIED"})
    return dataset, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Save verification evidence to existing Master rows")
    parser.add_argument("--backup-manifest", type=Path)
    args = parser.parse_args()
    try:
        backup = verify_backup(args.backup_manifest) if args.apply and args.backup_manifest else None
        if args.apply and not backup:
            raise ValueError("--backup-manifest with passed restore verification is required for --apply")
        with SessionLocal() as db:
            dataset, result = build_report(db)
            if args.apply:
                for row in result["assignments"]:
                    master = db.get(Opportunity, row["master_id"])
                    master.coordinate_provenance_json = {
                        "verified": row["verified"],
                        "verification_method": "DIRECT_SOURCE_COORDINATE",
                        "source_key": "furas", "source_record_id": row["source_record_id"],
                        "source_opportunity_id": row["source_opportunity_id"],
                        "source_record_identity_matches": row["source_record_identity_matches"],
                        "source_geometry_sha256": row["source_geometry_sha256"],
                        "source_url": row["source_url"],
                        "source_field_path_latitude": "raw_data_json.geometry.y",
                        "source_field_path_longitude": "raw_data_json.geometry.x",
                        "source_latitude": row["latitude"], "source_longitude": row["longitude"],
                        "coordinate_order": "raw.geometry.y=latitude; raw.geometry.x=longitude (WGS84 EPSG:4326)",
                        "boundary_validation": row["boundary_validation"],
                        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
                        "verification_actor": "NATIONAL_DATA_READINESS_REMEDIATION"}
                event_payload = {key: value for key, value in result.items() if key != "assignments"}
                event_payload.update({"dataset_version": dataset.version,
                    "reference_sha256": dataset.content_sha256, "backup_sha256": backup["sha256"]})
                db.add(SystemEvent(event_type="FURAS_COORDINATE_BOUNDARY_VERIFICATION",
                    payload=event_payload, created_at=datetime.now(timezone.utc)))
                db.commit()
            else:
                db.rollback()
            result.pop("assignments", None)
            result.update({"mode": "APPLY" if args.apply else "DRY_RUN",
                "writes_performed": result["direct_furas_coordinates_evaluated"] + 1 if args.apply else 0,
                "dataset_version": dataset.version, "reference_sha256": dataset.content_sha256,
                "backup_verification": backup})
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"applied": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())

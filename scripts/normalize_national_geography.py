"""Evidence-based, transactional assignment of existing Masters to an imported public geography reference.

Default mode is read-only. It never edits source payloads, creates Masters, or
uses Furas city text to infer governorates.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import SessionLocal
from app.geography import geography_key
from app.models import (GeographicReferenceDataset, GeographicReferenceUnit,
                        Opportunity, Source, SourceOpportunity, SystemEvent)
from scripts.import_geographic_reference import verify_backup


_ADMIN_PREFIX = re.compile(r"^(?:أمانة|امانة|بلدية)\s+(?:محافظة\s+)?(.+)$")


def _single(index: dict, key: str):
    rows = index.get(key, set())
    return next(iter(rows)) if len(rows) == 1 else None


def _region_candidate(attributes: dict, regions_by_code: dict, region_aliases: dict):
    code = str(attributes.get("REGION_ID") or "").strip()
    label = str(attributes.get("REGIONNAME") or "").strip()
    by_code = None
    if code and code.casefold() not in {"na", "none", "null"}:
        digits = code.lstrip("0") or "0"
        by_code = regions_by_code.get(digits)
    by_name = _single(region_aliases, geography_key(label)) if label and label.casefold() != "na" else None
    if by_code and by_name and by_code.id != by_name.id:
        return None, "REGION_CODE_NAME_CONFLICT"
    if by_code:
        return by_code, "EXACT_OFFICIAL_CODE" if not by_name else "EXACT_OFFICIAL_CODE_AND_NAME"
    if by_name:
        return by_name, "EXACT_NORMALIZED_NAME_OR_KNOWN_ALIAS"
    return None, None


def _governorate_candidates(region: GeographicReferenceUnit, attributes: dict,
                            governorate_aliases: dict) -> tuple[list[GeographicReferenceUnit], list[str]]:
    found: dict[int, tuple[GeographicReferenceUnit, str]] = {}
    raw_values = []
    for field in ("AMANA", "BALADYA", "CITYNAME"):
        raw = str(attributes.get(field) or "").strip()
        if not raw:
            continue
        raw_values.append(f"{field}={raw}")
        if "," in raw or "،" in raw:
            continue
        candidate = _single(governorate_aliases, (region.external_id, geography_key(raw)))
        method = "EXACT_OFFICIAL_NAME_AND_PARENT_REGION_MATCH" if field == "CITYNAME" else \
            "EXACT_NORMALIZED_ADMIN_LABEL_OR_KNOWN_ALIAS"
        if candidate is None and field != "CITYNAME":
            match = _ADMIN_PREFIX.fullmatch(raw)
            if match:
                candidate = _single(governorate_aliases,
                                    (region.external_id, geography_key(match.group(1))))
        if candidate:
            found[candidate.id] = (candidate, method)
    return [value[0] for value in found.values()], raw_values


def build_plan(db) -> tuple[GeographicReferenceDataset, dict]:
    dataset = db.scalar(select(GeographicReferenceDataset).where(
        GeographicReferenceDataset.dataset_key == "saudi_administrative_units",
        GeographicReferenceDataset.is_current.is_(True)))
    if dataset is None:
        raise ValueError("Current saudi_administrative_units reference is missing")
    furas = db.scalar(select(Source).where(Source.source_key == "furas"))
    if furas is None:
        raise ValueError("Furas source is missing")
    units = db.scalars(select(GeographicReferenceUnit).where(
        GeographicReferenceUnit.dataset_id == dataset.id)).all()
    units_by_id = {unit.id: unit for unit in units}
    regions_by_code = {unit.external_id: unit for unit in units if unit.level == "region"}
    region_aliases: dict[str, set] = {}
    governorate_aliases: dict[tuple[str, str], set] = {}
    for unit in units:
        keys = {geography_key(value) for value in (unit.name_ar, unit.name_en, *(unit.aliases_json or [])) if value}
        if unit.level == "region":
            for key in keys:
                region_aliases.setdefault(key, set()).add(unit)
        elif unit.level == "governorate":
            for key in keys:
                governorate_aliases.setdefault((unit.parent_external_id, key), set()).add(unit)
    rows = db.execute(select(SourceOpportunity, Opportunity).join(
        Opportunity, Opportunity.id == SourceOpportunity.master_opportunity_id).where(
        SourceOpportunity.source_id == furas.id, Opportunity.merged_into_id.is_(None))
        .order_by(Opportunity.id, SourceOpportunity.id)).all()
    plan = []
    counts = {"linked_furas_rows": len(rows), "unique_current_masters": len({m.id for _, m in rows}),
              "region_assignments": 0, "governorate_assignments": 0,
              "unmatched_region": 0, "region_conflicts": 0,
              "unmatched_governorate": 0, "ambiguous_governorate": 0,
              "existing_assignment_conflicts": 0, "scope_values_changed": 0,
              "source_payloads_changed": 0}
    unmatched_region_values: dict[str, int] = {}
    furas_masters: set[int] = set()
    for record, master in rows:
        if master.id in furas_masters:
            continue
        furas_masters.add(master.id)
        attrs = ((record.raw_data_json or {}).get("attributes") or {})
        region, region_method = _region_candidate(attrs, regions_by_code, region_aliases)
        if region is None:
            counts["unmatched_region"] += 1
            key = f"REGION_ID={attrs.get('REGION_ID')!r};REGIONNAME={attrs.get('REGIONNAME')!r}"
            unmatched_region_values[key] = unmatched_region_values.get(key, 0) + 1
            if region_method == "REGION_CODE_NAME_CONFLICT":
                counts["region_conflicts"] += 1
            continue
        unit = region
        govs, raw_admin_labels = _governorate_candidates(region, attrs, governorate_aliases)
        gov = govs[0] if len(govs) == 1 else None
        if len(govs) > 1:
            counts["ambiguous_governorate"] += 1
        if gov:
            unit = gov
            counts["governorate_assignments"] += 1
        else:
            counts["region_assignments"] += 1
            if raw_admin_labels:
                counts["unmatched_governorate"] += 1
        if master.geography_reference_unit_id is not None:
            current = units_by_id.get(master.geography_reference_unit_id)
            if current is None:
                current = db.get(GeographicReferenceUnit, master.geography_reference_unit_id)
            if current is None or (current.dataset_id != dataset.id and
                    (current.level != unit.level or current.external_id != unit.external_id)) or \
                    (current.dataset_id == dataset.id and current.id != unit.id):
                counts["existing_assignment_conflicts"] += 1
                continue
        plan.append({"master_id": master.id, "unit_id": unit.id, "unit_level": unit.level,
                     "unit_external_id": unit.external_id, "region_external_id": region.external_id,
                     "source_record_id": record.id, "source_opportunity_id": record.source_opportunity_id,
                     "source_url": record.source_url,
                     "method": "EXACT_OFFICIAL_CODE_AND_NAME" if unit.level == "region" else "EXACT_PARENT_SCOPED_ADMIN_LABEL",
                     "region_code": attrs.get("REGION_ID"), "region_label": attrs.get("REGIONNAME"),
                     "admin_labels": raw_admin_labels})
    assigned_masters = {row["master_id"] for row in plan}
    non_furas_rows = db.execute(select(SourceOpportunity, Opportunity, Source).join(
        Opportunity, Opportunity.id == SourceOpportunity.master_opportunity_id).join(
        Source, Source.id == SourceOpportunity.source_id).where(
        Source.source_key != "furas", Opportunity.merged_into_id.is_(None),
        SourceOpportunity.raw_location.is_not(None)).order_by(Opportunity.id, SourceOpportunity.id)).all()
    for record, master, source in non_furas_rows:
        if master.id in assigned_masters:
            continue
        raw_location = str(record.raw_location or "").strip()
        if not raw_location or "," in raw_location or "،" in raw_location:
            continue
        unit = _single(governorate_aliases, (None, geography_key(raw_location)))
        method = "EXACT_SOURCE_LOCATION_TO_OFFICIAL_GOVERNORATE_ALIAS"
        if unit is None:
            unit = _single(region_aliases, geography_key(raw_location))
            method = "EXACT_SOURCE_LOCATION_TO_OFFICIAL_REGION_ALIAS"
        if unit is None:
            match = _ADMIN_PREFIX.fullmatch(raw_location)
            if match:
                unit = _single(governorate_aliases, (None, geography_key(match.group(1))))
        if unit is None:
            continue
        if master.geography_reference_unit_id is not None:
            current = units_by_id.get(master.geography_reference_unit_id)
            if current is None:
                current = db.get(GeographicReferenceUnit, master.geography_reference_unit_id)
            if current is None or (current.dataset_id != dataset.id and
                    (current.level != unit.level or current.external_id != unit.external_id)) or \
                    (current.dataset_id == dataset.id and current.id != unit.id):
                counts["existing_assignment_conflicts"] += 1
                continue
        parent_external_id = unit.parent_external_id if unit.level == "governorate" else unit.external_id
        plan.append({"master_id": master.id, "unit_id": unit.id, "unit_level": unit.level,
            "unit_external_id": unit.external_id, "region_external_id": parent_external_id,
            "source_record_id": record.id, "source_opportunity_id": record.source_opportunity_id,
            "source_url": record.source_url, "method": method,
            "region_code": None, "region_label": None, "admin_labels": [f"raw_location={raw_location}"]})
        assigned_masters.add(master.id)
        counts["governorate_assignments" if unit.level == "governorate" else "region_assignments"] += 1
    counts["planned_master_assignments"] = len(plan)
    return dataset, {"counts": counts, "plan": plan,
                     "unmatched_region_values": dict(sorted(unmatched_region_values.items(), key=lambda item: -item[1]))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the reviewed plan transactionally")
    parser.add_argument("--backup-manifest", type=Path)
    args = parser.parse_args()
    try:
        backup = verify_backup(args.backup_manifest) if args.apply and args.backup_manifest else None
        if args.apply and not backup:
            raise ValueError("--backup-manifest with a passed restore verification is required for --apply")
        with SessionLocal() as db:
            dataset, result = build_plan(db)
            if args.apply:
                now_event = {"dataset_id": dataset.id, "dataset_key": dataset.dataset_key,
                             "dataset_version": dataset.version, "reference_sha256": dataset.content_sha256,
                             "counts": result["counts"], "backup_sha256": backup["sha256"]}
                for row in result["plan"]:
                    master = db.get(Opportunity, row["master_id"])
                    master.geography_reference_unit_id = row["unit_id"]
                    master.geography_evidence_json = {
                        "verification_method": row["method"], "reference_dataset_key": dataset.dataset_key,
                        "reference_version": dataset.version, "reference_sha256": dataset.content_sha256,
                        "unit_level": row["unit_level"], "unit_external_id": row["unit_external_id"],
                        "parent_region_external_id": row["region_external_id"],
                        "source_key": "furas", "source_record_id": row["source_record_id"],
                        "source_opportunity_id": row["source_opportunity_id"],
                        "source_url": row["source_url"], "region_code": row["region_code"],
                        "raw_region_label": row["region_label"],
                        "raw_administrative_labels": row["admin_labels"],
                        "raw_source_location_preserved": True}
                db.add(SystemEvent(event_type="NATIONAL_GEOGRAPHY_NORMALIZATION",
                    payload=now_event, created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)))
                db.commit()
            else:
                db.rollback()
            result.update({"mode": "APPLY" if args.apply else "DRY_RUN",
                           "writes_performed": len(result["plan"]) + 1 if args.apply else 0,
                           "dataset_version": dataset.version, "reference_sha256": dataset.content_sha256,
                           "backup_verification": backup})
            result.pop("plan", None)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"applied": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())

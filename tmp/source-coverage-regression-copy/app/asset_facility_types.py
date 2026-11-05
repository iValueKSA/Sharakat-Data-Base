"""Conservative, source-scoped Asset / Facility / Site Type standardization."""
from __future__ import annotations

import json
from sqlalchemy import select

from .models import AssetFacilityType, AssetFacilityTypeAlias
from .standardization import comparison_key

ASSET_FACILITY_TYPE_VERSION = "1"
ASSET_FACILITY_TYPE_MISSING_ID = "asset_facility_type:missing"
ASSET_FACILITY_TYPE_MISSING_LABEL = "غير محدد"

ASSET_FACILITY_TYPE_LABELS = {
    "asset_facility_type:mobile_vending_site": "العربات المتنقلة",
    "asset_facility_type:public_park": "الحدائق",
    "asset_facility_type:waterfront": "الشواطئ والواجهات",
    "asset_facility_type:other": "أخرى",
    "asset_facility_type:land": "الاراضي",
    "asset_facility_type:public_square": "الساحات الميادين",
    "asset_facility_type:building": "المباني",
    "asset_facility_type:road_sidewalk": "الطرق والارصفة",
    ASSET_FACILITY_TYPE_MISSING_ID: ASSET_FACILITY_TYPE_MISSING_LABEL,
}


def parse_location_type_values(value: object) -> list[str]:
    """Parse Furas LOCATIONTYPE's JSON-encoded selection list without altering raw data."""
    if value is None:
        return []
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError):
            try:
                decoded = json.loads(f"[{text}]")
            except (TypeError, ValueError):
                decoded = [text]
        values = decoded if isinstance(decoded, list) else [decoded]
    else:
        values = [value]
    output = []
    seen = set()
    for item in values:
        if item is None:
            continue
        label = str(item).strip().strip('"').strip()
        key = comparison_key(label)
        if key and key not in seen:
            output.append(label)
            seen.add(key)
    return output


def source_asset_type_candidates(source_key: str, raw_payload: dict) -> tuple[list[str], str | None]:
    """Return source field and values only where a reviewed structured field exists."""
    if source_key != "furas":
        return [], None
    attrs = raw_payload.get("attributes") if isinstance(raw_payload, dict) else None
    if not isinstance(attrs, dict):
        return [], "LOCATIONTYPE"
    return parse_location_type_values(attrs.get("LOCATIONTYPE")), "LOCATIONTYPE"


def standardize_asset_facility_types(db, source_key: str, raw_payload: dict) -> dict:
    values, source_field = source_asset_type_candidates(source_key, raw_payload)
    if source_field is None:
        return {"version": ASSET_FACILITY_TYPE_VERSION, "assignments": [], "unresolved": []}
    alias_rows = db.scalars(select(AssetFacilityTypeAlias).where(
        AssetFacilityTypeAlias.source_key == source_key,
        AssetFacilityTypeAlias.source_field == source_field,
    )).all()
    aliases = {comparison_key(row.source_value): row.canonical_id for row in alias_rows}
    assignments = []
    unresolved = []
    for value in values:
        canonical_id = aliases.get(comparison_key(value))
        if canonical_id:
            assignments.append({"canonical_id": canonical_id, "label_ar": ASSET_FACILITY_TYPE_LABELS[canonical_id], "raw_value": value, "source_field": source_field})
        else:
            unresolved.append({"raw_value": value, "source_field": source_field})
    return {"version": ASSET_FACILITY_TYPE_VERSION, "assignments": assignments, "unresolved": unresolved}


def canonical_asset_facility_types(db, opportunity_id: int) -> list[dict]:
    # Assignment labels are read through the canonical registry, never raw evidence.
    from .models import OpportunityAssetFacilityType
    rows = db.execute(
        select(AssetFacilityType.canonical_id, AssetFacilityType.label_ar)
        .join(OpportunityAssetFacilityType, OpportunityAssetFacilityType.canonical_id == AssetFacilityType.canonical_id)
        .where(OpportunityAssetFacilityType.opportunity_id == opportunity_id, AssetFacilityType.active.is_(True))
        .distinct()
    ).all()
    return [{"id": canonical_id, "label": label} for canonical_id, label in sorted(rows, key=lambda row: (comparison_key(row[1]), row[0]))]

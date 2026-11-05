"""Meaningful, source-aware comparison for duplicate identity reviews.

The comparison is explainability only: it never merges or resolves a review.
Raw values remain available alongside normalization used for equivalence.
"""
from __future__ import annotations

import re
import unicodedata
import json


MASTER_FIELDS = (
    ("title_ar", "العنوان"), ("normalized_title", "العنوان المعياري"),
    ("opportunity_owner", "الجهة المالكة"),
    ("primary_publication_platform", "منصة النشر"), ("sector", "القطاع"),
    ("activity", "النشاط"), ("sub_activity", "النشاط الفرعي"),
    ("opportunity_type", "نوع الفرصة"), ("investment_model", "نموذج الاستثمار"),
    ("city", "المدينة"), ("district", "الحي"),
    ("location_description", "الموقع التفصيلي"),
    ("latitude", "خط العرض"), ("longitude", "خط الطول"),
    ("land_area_sqm", "المساحة م²"), ("plot_number", "رقم القطعة"),
    ("asset_facility_type", "نوع الأصل/المرفق"),
    ("investment_value", "القيمة الاستثمارية"), ("currency", "العملة"),
    ("contract_duration_years", "مدة العقد"), ("publication_date", "تاريخ النشر"),
    ("submission_deadline", "موعد التقديم"), ("status", "الحالة"),
    ("short_description", "الوصف المختصر"), ("full_description", "الوصف الكامل"),
)

IDENTITY_FIELDS = (
    ("source", "المصدر"), ("official_source_id", "المعرّف الرسمي لدى المصدر"),
    ("source_opportunity_id", "معرّف الفرصة لدى المصدر"),
    ("source_reference_number", "الرقم المرجعي لدى المصدر"),
    ("source_title", "العنوان الخام لدى المصدر"),
    ("source_owner", "الجهة المالكة لدى المصدر"),
    ("raw_location", "الموقع الوارد من المصدر"), ("raw_area", "المساحة الخام"),
    ("raw_value", "القيمة الخام"), ("raw_dates", "تواريخ المصدر"),
    ("source_url", "رابط الفرصة لدى المصدر"),
)
ID_FIELDS = {"official_source_id", "source_opportunity_id", "source_reference_number", "source_url"}
PUNCTUATION = re.compile(r"[\s\u0640،؛؟٬٫,.!:/\\()\[\]{}\-–—_]+")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_identity_value(field: str, value):
    """Normalize harmless presentation variation without erasing raw evidence."""
    if value is None or value == "" or value == [] or value == {}:
        return None
    if isinstance(value, dict):
        normalized = {str(k): normalize_identity_value(str(k), v) for k, v in sorted(value.items())}
        return normalized if any(v is not None for v in normalized.values()) else None
    if isinstance(value, (list, tuple, set)):
        normalized = [normalize_identity_value(field, item) for item in value]
        normalized = [item for item in normalized if item is not None]
        return sorted(normalized, key=lambda item: str(item)) if normalized else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if isinstance(value, float) else value
    text = unicodedata.normalize("NFKC", str(value)).translate(ARABIC_DIGITS).casefold().strip()
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    text = re.sub(r"\s+", " ", text)
    # Identifiers and URLs retain punctuation because it can be identity-bearing.
    if field not in ID_FIELDS:
        text = re.sub(r"(?<=\d)[٬,](?=\d{3}(?:\D|$))", "", text)
        text = re.sub(r"(?<=\d)٫(?=\d)", ".", text)
        text = re.sub(r"(?<=\d)\.(?=\d)", "\ue000", text)
        text = PUNCTUATION.sub(" ", text)
        text = text.replace("\ue000", ".")
        text = re.sub(r"\s+", " ", text).strip()
    return text or None


def compare_duplicate_masters(masters: list[dict], source_records_by_master: dict[int, list[dict]],
                              explanation: dict | None = None) -> dict:
    """Return raw, field-level pair comparison and a governance blocker rationale."""
    if len(masters) != 2:
        return {"matched_fields": [], "different_fields": [], "missing_on_left": [],
                "missing_on_right": [], "blocking_reason": None,
                "classification": "INSUFFICIENT_EVIDENCE"}
    left_master, right_master = masters
    left_sources = source_records_by_master.get(left_master["id"], [])
    right_sources = source_records_by_master.get(right_master["id"], [])
    rows = []

    def add(field, label, left, right, *, identity=False):
        nl, nr = normalize_identity_value(field, left), normalize_identity_value(field, right)
        if nl is None and nr is None:
            return
        state = "MATCH" if nl == nr else "DIFFERENT"
        if nl is None:
            state = "MISSING_LEFT"
        elif nr is None:
            state = "MISSING_RIGHT"
        rows.append({"field": field, "label": label, "left": left, "right": right,
                     "normalized_left": nl, "normalized_right": nr, "state": state,
                     "identity_evidence": identity})

    for field, label in MASTER_FIELDS:
        add(field, label, left_master.get(field), right_master.get(field))

    def values(records, key):
        unique = {}
        for record in records:
            value = record.get(key)
            if value not in (None, ""):
                fingerprint = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
                unique.setdefault(fingerprint, value)
        return [unique[key] for key in sorted(unique)]

    # Compare each source identity dimension as a source-scoped set; the source ID
    # is never treated as globally unique, and source IDs are not discarded as punctuation.
    source_specs = (
        ("source", "المصدر", "source_key"),
        ("publisher", "الناشر", "publisher"),
        ("official_source_id", "المعرّف الرسمي لدى المصدر", "official_source_id_original"),
        ("source_opportunity_id", "معرّف الفرصة لدى المصدر", "source_opportunity_id"),
        ("source_reference_number", "الرقم المرجعي لدى المصدر", "source_reference_number"),
        ("source_title", "العنوان الخام لدى المصدر", "source_title"),
        ("source_owner", "الجهة المالكة لدى المصدر", "source_owner"),
        ("source_sector", "القطاع الوارد من المصدر", "source_sector"),
        ("source_activity", "النشاط الوارد من المصدر", "source_activity"),
        ("source_sub_activity", "النشاط الفرعي الوارد من المصدر", "source_sub_activity"),
        ("source_opportunity_type", "نوع الفرصة الوارد من المصدر", "source_opportunity_type"),
        ("source_investment_model", "نموذج الاستثمار الوارد من المصدر", "source_investment_model"),
        ("raw_location", "الموقع الوارد من المصدر", "raw_location"),
        ("source_coordinates", "إحداثيات المصدر", "source_coordinates"),
        ("source_city", "المدينة الواردة من المصدر", "source_city"),
        ("source_district", "الحي الوارد من المصدر", "source_district"),
        ("raw_area", "المساحة الخام", "raw_area"), ("raw_value", "القيمة الخام", "raw_value"),
        ("raw_dates", "تواريخ المصدر", "raw_dates"),
        ("raw_description", "الوصف الخام لدى المصدر", "raw_description"),
        ("source_asset_facility_type", "نوع الأصل/المرفق الخام لدى المصدر", "source_asset_facility_type"),
        ("source_url", "رابط الفرصة لدى المصدر", "source_url"),
    )
    for field, label, key in source_specs:
        add(field, label, values(left_sources, key), values(right_sources, key), identity=True)

    matched = [row for row in rows if row["state"] == "MATCH"]
    different = [row for row in rows if row["state"] == "DIFFERENT"]
    missing_left = [row for row in rows if row["state"] == "MISSING_LEFT"]
    missing_right = [row for row in rows if row["state"] == "MISSING_RIGHT"]
    identity = (explanation or {}).get("identity_review_decision") or {}
    reason = identity.get("review_reason") or identity.get("basis")
    same_source = identity.get("same_source")
    if same_source is None:
        lkeys, rkeys = set(values(left_sources, "source_key")), set(values(right_sources, "source_key"))
        same_source = bool(lkeys and rkeys and lkeys == rkeys)
    if different or missing_left or missing_right:
        classification = "SAME_SOURCE_AMBIGUOUS" if same_source else "CROSS_SOURCE_AMBIGUOUS"
    elif reason:
        classification = "SAME_SOURCE_AMBIGUOUS" if same_source else "CROSS_SOURCE_AMBIGUOUS"
    else:
        classification = "EXACT_LOOKING_WITHOUT_BLOCKER"
    official_ids_differ = any(row["field"] in {"official_source_id", "source_opportunity_id", "source_reference_number"}
                              for row in different)
    if same_source and official_ids_differ:
        human_reason = ("نفس المصدر لكن أرقام الفرص الرسمية مختلفة؛ هذا سبب لعدم الدمج الآلي، "
                        "ولا يثبت وحده أن الفرصتين مختلفتان. يستطيع المحلل اعتماد أنهما نفس الفرصة عند كفاية الدليل.")
    elif same_source:
        human_reason = ("المصدر واحد، لكن دليل الهوية الحالي لا يكفي للحسم الآلي. "
                        "راجع الفروق وسياق النشر قبل تقرير الدمج أو الفصل.")
    else:
        human_reason = ("مصادر مختلفة ولا يوجد دليل هوية حتمي كافٍ للدمج الآلي. "
                        "راجع الفروق؛ ويمكن للمحلل تقرير أنهما نفس الفرصة إذا دعم الدليل ذلك.")
    blocker = reason or (human_reason if classification != "EXACT_LOOKING_WITHOUT_BLOCKER" else None)
    return {"matched_fields": matched, "different_fields": different,
            "missing_on_left": missing_left, "missing_on_right": missing_right,
            "blocking_reason": blocker, "human_review_reason": human_reason,
            "same_source": bool(same_source),
            "compared_fields": [field for field, _ in MASTER_FIELDS]
                + [field for field, _, _ in source_specs],
            "classification": classification,
            "auto_resolution_allowed": False}


def has_governance_blocker(comparison: dict) -> bool:
    reason = comparison.get("blocking_reason")
    return bool(isinstance(reason, str) and reason.strip())


def compare_duplicate_candidate(db, candidate) -> dict:
    """Load only the two current Masters and their source identity evidence."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from .models import (AssetFacilityType, Opportunity, OpportunityAssetFacilityType,
                         SourceOpportunity)

    masters = []
    source_records_by_master = {}
    master_fields = [name for name, _ in MASTER_FIELDS]
    for master_id in (candidate.left_opportunity_id, candidate.right_opportunity_id):
        master = db.get(Opportunity, master_id)
        if not master or master.merged_into_id is not None:
            continue
        master_comparison = {"id": master.id, **{field: getattr(master, field, None) for field in master_fields}}
        assets = db.scalars(select(OpportunityAssetFacilityType).where(
            OpportunityAssetFacilityType.opportunity_id == master_id).order_by(OpportunityAssetFacilityType.id)).all()
        master_comparison["asset_facility_type"] = [{
            "canonical_id": asset.canonical_id,
            "label_ar": (db.get(AssetFacilityType, asset.canonical_id).label_ar
                         if db.get(AssetFacilityType, asset.canonical_id) else None),
            "raw_value": asset.raw_value,
        } for asset in assets]
        masters.append(master_comparison)
        records = db.scalars(select(SourceOpportunity).where(
            SourceOpportunity.master_opportunity_id == master_id
        ).options(selectinload(SourceOpportunity.source)).order_by(SourceOpportunity.id)).all()
        source_records_by_master[master_id] = []
        for record in records:
            raw = record.raw_data_json if isinstance(record.raw_data_json, dict) else {}
            details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
            standardized = record.standardized_data_json if isinstance(record.standardized_data_json, dict) else {}
            standardized_fields = standardized.get("fields") if isinstance(standardized.get("fields"), dict) else {}
            asset_data = standardized.get("asset_facility_types") if isinstance(standardized.get("asset_facility_types"), dict) else {}
            coordinates = raw.get("coordinates") if isinstance(raw.get("coordinates"), dict) else {}
            source_records_by_master[master_id].append({
                "source_key": record.source.source_key if record.source else None,
                "publisher": record.source.organization_name if record.source else None,
                "official_source_id_original": record.official_source_id_original,
                "source_opportunity_id": record.source_opportunity_id,
                "source_reference_number": record.source_reference_number,
                "source_title": record.source_title, "source_owner": record.source_owner,
                "source_sector": record.source_sector, "source_activity": record.source_activity,
                "source_sub_activity": record.source_sub_activity,
                "source_opportunity_type": (standardized_fields.get("opportunity_type") or {}).get("raw"),
                "source_investment_model": (standardized_fields.get("investment_model") or {}).get("raw"),
                "raw_location": record.raw_location or details.get("الموقع"),
                "source_coordinates": {"latitude": raw.get("latitude", coordinates.get("latitude")),
                                       "longitude": raw.get("longitude", coordinates.get("longitude"))},
                "source_city": raw.get("city") or details.get("المدينة"),
                "source_district": raw.get("district") or details.get("الحي"),
                "raw_area": record.raw_area or details.get("المساحة"),
                "raw_value": record.raw_value,
                "raw_dates": record.raw_dates or {}, "raw_description": raw.get("description"),
                "source_asset_facility_type": {"assignments": asset_data.get("assignments", []),
                                                "unresolved": asset_data.get("unresolved", [])},
                "source_url": record.source_url,
            })
    return compare_duplicate_masters(masters, source_records_by_master, candidate.explanation_json)

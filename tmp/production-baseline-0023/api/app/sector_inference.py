"""Conservative, evidence-traceable sector inference for unspecified Masters."""
from __future__ import annotations

from difflib import SequenceMatcher
from collections import defaultdict
from typing import Any

from .adapters import normalize_sector
from .standardization import (
    _SECTOR_LABELS,
    _SECTOR_WRONG_DIMENSION_KEYS,
    SECTOR_UNSPECIFIED_LABEL,
    canonical_id,
    canonical_value,
    comparison_key,
)

ENGINE_VERSION = "ahda-sector-rules-1.0.0"
SECTOR_LABELS_BY_ID = {f"sector:{key}": value for key, value in _SECTOR_LABELS.items()}

# Exact structured mappings are reviewed data relationships, not substring rules.
SUB_ACTIVITY_RULES = {
    "خدمات الصرافة": ("sector:financial_services", "SUB_ACTIVITY_EXACT_EXCHANGE"),
    "أنشطة تجارة المواد الغذائية": ("sector:commercial", "SUB_ACTIVITY_EXACT_FOOD_RETAIL"),
    "محلات تجارية": ("sector:commercial", "SUB_ACTIVITY_EXACT_RETAIL_SHOPS"),
    "خدمات تعليمية أخرى": ("sector:education", "SUB_ACTIVITY_EXACT_EDUCATIONAL_SERVICES"),
    "أنشطة وخدمات انتاج المواد غير الغذائية": ("sector:industrial", "SUB_ACTIVITY_EXACT_NONFOOD_PRODUCTION"),
}

ACTIVITY_RULES = {
    "الأنشطة الزراعية والحيوانية": "sector:agriculture",
    "الأنشطة المالية": "sector:financial_services",
    "الأنشطة التعليمية": "sector:education",
    "Real Estate & Construction": "sector:real_estate",
}

# A signal is deliberately a full domain phrase. Generic words such as
# investment, project, site, operation, development, and services are absent.
TEXT_SIGNALS = {
    "sector:tourism": (
        "فندق", "فنادق", "منتجع", "منتجعات", "نزل سياحي", "إقامة سياحية",
        "مرافق سياحية", "وجهة سياحية", "قرية سياحية", "ضيافة فندقية",
        "hotel", "hotels", "resort", "tourist accommodation", "hospitality facility",
    ),
    "sector:agriculture": (
        "مزرعة", "مزارع", "نخيل", "نخلة", "تمور", "التمور", "فرز وتعبئة التمور",
        "إنتاج زراعي", "مشاتل", "مشتل", "بيوت محمية", "محاصيل زراعية", "ري زراعي",
        "date palm", "agricultural production", "greenhouse agriculture", "nursery",
    ),
    "sector:industrial": (
        "مصنع", "مصانع", "تصنيع", "خط إنتاج", "إنتاج صناعي", "منشأة صناعية",
        "manufacturing plant", "factory", "production line",
    ),
    "sector:commercial": (
        "تموينات", "محلات تجارية", "متجر تجاري", "تجارة التجزئة", "مكائن بيع ذاتي",
        "جهاز بيع ذاتي", "retail store", "commercial shop",
    ),
    "sector:financial_services": (
        "صراف آلي", "صراف الي", "خدمات الصرافة", "خدمات مصرفية", "بنك تجاري",
        "financial services", "atm machine", "banking services",
    ),
    "sector:real_estate": (
        "تطوير عقاري", "مشروع إسكان", "مشروع سكني", "تطوير عقارات", "عقارات وإنشاءات",
        "real estate development", "housing development", "residential development",
    ),
    "sector:healthcare": (
        "مستشفى", "مستشفيات", "مركز صحي", "مراكز صحية", "عيادة طبية", "رعاية صحية",
        "خدمات طبية", "خدمات صحية", "medical services", "healthcare center", "hospital", "medical clinic",
    ),
    "sector:education": (
        "تعليم", "تعليمي", "مركز تدريب", "مراكز التدريب", "تعليم مهني", "تعليم تقني",
        "educational services", "training center", "vocational education",
    ),
    "sector:logistics": (
        "مستودع", "مستودعات", "مركز لوجستي", "نقل البضائع", "خدمات الشحن", "مناولة البضائع",
        "logistics center", "freight transport", "warehouse facility",
    ),
    "sector:environment": (
        "إعادة تدوير", "تدوير النفايات", "معالجة مياه الصرف", "معالجة النفايات", "محطة معالجة المياه",
        "waste recycling", "wastewater treatment", "water treatment plant",
    ),
    "sector:energy": (
        "محطة طاقة شمسية", "توليد الكهرباء", "الطاقة المتجددة", "محطة كهرباء", "طاقة شمسية",
        "solar power plant", "electricity generation", "renewable energy",
    ),
    "sector:culture": (
        "متحف", "مركز ثقافي", "ترميم موقع أثري", "مركز تراثي", "مرافق ثقافية",
        "museum", "cultural center", "heritage center",
    ),
    "sector:sports": (
        "منشأة رياضية", "مركز رياضي", "مدينة رياضية", "ملعب رياضي", "نادي رياضي",
        "sports facility", "sports center", "stadium", "fitness center",
    ),
    "sector:technology": (
        "مركز بيانات", "خدمات تقنية المعلومات", "اتصالات وتقنية المعلومات", "شبكة اتصالات",
        "برمجيات", "منصة رقمية", "data center", "software platform", "telecommunications network",
    ),
}

GENERIC_OR_WRONG_DIMENSION = _SECTOR_WRONG_DIMENSION_KEYS | {
    comparison_key(value)
    for value in (
        "INVESTMENT_OPPORTUNITY", "LEASE_OPPORTUNITY", "PPP_PROJECT",
        "COMMERCIAL_FACILITY_OPPORTUNITY", "WASTE_SECTOR_INVESTMENT",
    )
}


def _clean(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _has_term(value: str, terms: tuple[str, ...]) -> list[str]:
    normalized = comparison_key(value)
    return [term for term in terms if comparison_key(term) in normalized]


def _sector_text_signals(record: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    fields = {
        "title": _clean(record.get("title_ar")),
        "short_description": _clean(record.get("short_description")),
        "full_description": _clean(record.get("full_description")),
        "asset_facility_type": _clean(record.get("asset_facility_type")),
        "subsector": _clean(record.get("subsector")),
    }
    # Repeated copies of the title in description fields are one signal.
    title_key = comparison_key(fields["title"])
    evidence: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen_descriptions: list[str] = []
    for field, value in fields.items():
        if not value or (field.endswith("description") and comparison_key(value) == title_key):
            continue
        if field.endswith("description"):
            normalized = comparison_key(value)
            if any(normalized.startswith(previous) or previous.startswith(normalized)
                   or SequenceMatcher(None, normalized, previous).ratio() >= .90
                   for previous in seen_descriptions):
                continue
            seen_descriptions.append(normalized)
        for sector_id, terms in TEXT_SIGNALS.items():
            for term in _has_term(value, terms):
                evidence[sector_id].append({"field": field, "signal": term, "value": value[:500]})
    return dict(evidence)


def classify_unspecified(record: dict[str, Any], *, include_official_sources: bool = True) -> dict[str, Any]:
    """Classify only a currently unspecified record; explicit official sectors win."""
    current_sector = record.get("sector")
    if canonical_id("sector", current_sector) != "sector:unspecified":
        return {
            "classification": "EXISTING_CLASSIFIED",
            "sector": canonical_value("sector", current_sector),
            "sector_id": canonical_id("sector", current_sector),
            "confidence": 1.0,
            "rule_key": "PRESERVE_EXISTING_CANONICAL_SECTOR",
            "evidence": [],
        }

    official: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmapped_official: list[dict[str, Any]] = []
    if include_official_sources:
        for source in record.get("sources", []):
            raw_sector = _clean(source.get("source_sector"))
            if not raw_sector or comparison_key(raw_sector) in GENERIC_OR_WRONG_DIMENSION:
                continue
            mapped = normalize_sector(raw_sector)
            if not mapped:
                unmapped_official.append({
                    "source_key": source.get("source_key"),
                    "source_record_id": source.get("source_record_id"),
                    "raw_sector": raw_sector,
                })
                continue
            sector_id = canonical_id("sector", mapped)
            if sector_id == "sector:unspecified":
                continue
            official[sector_id].append({
                "field": "source_sector",
                "source_key": source.get("source_key"),
                "source_record_id": source.get("source_record_id"),
                "signal": raw_sector,
                "value": mapped,
            })

    if len(official) > 1:
        return _result("REVIEW_REQUIRED", None, "CONFLICTING_OFFICIAL_SOURCE_SECTORS", 0.0,
                       [item for group in official.values() for item in group],
                       candidates=sorted(official))
    if unmapped_official:
        return _result("REVIEW_REQUIRED", None, "UNMAPPED_EXPLICIT_OFFICIAL_SECTOR", 0.0,
                       unmapped_official, candidates=[])
    if official:
        sector_id, evidence = next(iter(official.items()))
        label = SECTOR_LABELS_BY_ID[sector_id]
        return _result("HIGH_CONFIDENCE", label, "SOURCE_EXPLICIT_SECTOR", 1.0, evidence,
                       origin="SOURCE_EXPLICIT", sector_id=sector_id)

    signals = _sector_text_signals(record)
    activity = _clean(record.get("activity"))
    sub_activity = _clean(record.get("sub_activity"))
    activity_id = ACTIVITY_RULES.get(activity)
    sub_rule = SUB_ACTIVITY_RULES.get(sub_activity)
    structured: dict[str, list[dict[str, str]]] = defaultdict(list)
    if activity_id:
        structured[activity_id].append({"field": "activity", "signal": activity, "value": activity})
    if sub_rule:
        sub_id, rule = sub_rule
        structured[sub_id].append({"field": "sub_activity", "signal": sub_activity, "value": sub_activity, "rule": rule})

    # Food-service wording can mean retail, dining, or production. Require an
    # explicit commercial activity and a retail signal before selecting Commercial.
    if sub_activity == "منشآت تقديم الغذاء" and activity == "الأنشطة التجارية":
        structured["sector:commercial"].append({
            "field": "sub_activity", "signal": sub_activity,
            "value": sub_activity, "rule": "COMMERCIAL_FOOD_SERVICE_WITH_COMMERCIAL_ACTIVITY",
        })

    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sector_id, items in structured.items():
        candidates[sector_id].extend(items)
    for sector_id, items in signals.items():
        candidates[sector_id].extend(items)

    text_fields = {item["field"] for values in signals.values() for item in values}
    high: list[tuple[str, list[dict[str, Any]], str, float]] = []
    for sector_id, evidence in candidates.items():
        structured_here = [item for item in evidence if item["field"] in {"activity", "sub_activity", "asset_facility_type", "subsector"}]
        text_here = [item for item in evidence if item["field"] in {"title", "short_description", "full_description"}]
        exact_sub = any(item.get("rule") in {
            "SUB_ACTIVITY_EXACT_EXCHANGE", "SUB_ACTIVITY_EXACT_FOOD_RETAIL",
            "SUB_ACTIVITY_EXACT_RETAIL_SHOPS", "SUB_ACTIVITY_EXACT_EDUCATIONAL_SERVICES",
            "SUB_ACTIVITY_EXACT_NONFOOD_PRODUCTION",
        } for item in evidence)
        # A precise, approved sub-activity relation is independently sufficient.
        if exact_sub:
            high.append((sector_id, evidence, "DETERMINISTIC_SUB_ACTIVITY", .96))
        elif structured_here and text_here:
            high.append((sector_id, evidence, "STRUCTURED_ACTIVITY_AND_TEXT_AGREEMENT", .93))
        elif len({item["field"] for item in text_here}) >= 2:
            high.append((sector_id, evidence, "INDEPENDENT_TEXT_FIELD_AGREEMENT", .90))

    distinct_high = {item[0] for item in high}
    if len(distinct_high) > 1 or (distinct_high and set(candidates) - distinct_high):
        return _result("REVIEW_REQUIRED", None, "CONFLICTING_SECTOR_SIGNALS", 0.0,
                       [entry for items in candidates.values() for entry in items],
                       candidates=sorted(set(candidates)))
    if high:
        sector_id, evidence, rule, confidence = high[0]
        return _result("HIGH_CONFIDENCE", SECTOR_LABELS_BY_ID[sector_id], rule, confidence,
                       evidence, origin="INFERRED_RULE", sector_id=sector_id)

    if candidates:
        sector_ids = sorted(candidates)
        status = "REVIEW_REQUIRED" if len(sector_ids) > 1 or any(
            item["field"] in {"title", "short_description", "full_description", "asset_facility_type", "subsector"}
            for items in candidates.values() for item in items
        ) else "INSUFFICIENT_EVIDENCE"
        return _result(status, None, "SINGLE_UNCORROBORATED_SECTOR_SIGNAL", 0.0,
                       [entry for items in candidates.values() for entry in items], candidates=sector_ids)

    return _result("INSUFFICIENT_EVIDENCE", None, "NO_SECTOR_SIGNAL", 0.0, [])


def _result(classification: str, sector: str | None, rule_key: str, confidence: float,
            evidence: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "classification": classification,
        "sector": sector or SECTOR_UNSPECIFIED_LABEL,
        "sector_id": extra.pop("sector_id", canonical_id("sector", sector)),
        "confidence": confidence,
        "rule_key": rule_key,
        "evidence": evidence,
        **extra,
    }


def benchmark_prediction(record: dict[str, Any]) -> dict[str, Any]:
    """Hide the existing Master sector and official source sectors for holdout validation."""
    return classify_unspecified({**record, "sector": SECTOR_UNSPECIFIED_LABEL}, include_official_sources=False)


def is_high_confidence(result: dict[str, Any]) -> bool:
    return result.get("classification") == "HIGH_CONFIDENCE" and result.get("confidence", 0) >= .90


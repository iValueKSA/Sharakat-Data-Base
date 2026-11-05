"""Controlled medium-confidence sector inference for unspecified opportunities.

The established Phase 2 engine remains the source of high-confidence decisions.
This layer admits a small, reviewed set of primary-purpose signals at medium
confidence; generic asset and location wording cannot produce a sector.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .adapters import normalize_sector
from .sector_inference_phase2 import ENGINE_VERSION as BASE_ENGINE_VERSION, classify_phase2
from .sector_inference import GENERIC_OR_WRONG_DIMENSION
from .standardization import canonical_id, comparison_key

ENGINE_VERSION = "ahda-sector-controlled-relaxation-1.0.1"
MEDIUM_MIN_CONFIDENCE = 0.82
MEDIUM_MAX_CONFIDENCE = 0.89

# Each entry is an explicit primary-purpose phrase, not a loose bag of words.
# Phrases are intentionally scoped to sectors already present in the taxonomy.
TITLE_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    "sector:tourism": (
        ("فندق", "MED_TITLE_HOTEL"), ("فنادق", "MED_TITLE_HOTELS"),
        ("منتجع سياحي", "MED_TITLE_TOURIST_RESORT"), ("منتجع", "MED_TITLE_RESORT"),
        ("نزل سياحي", "MED_TITLE_TOURIST_INN"), ("إيواء سياحي", "MED_TITLE_TOURIST_LODGING"),
        ("tourist accommodation", "MED_TITLE_TOURIST_ACCOMMODATION"),
        ("hotel development", "MED_TITLE_HOTEL_DEVELOPMENT"),
    ),
    "sector:agriculture": (
        ("مزرعة", "MED_TITLE_FARM"), ("مشتل", "MED_TITLE_NURSERY"),
        ("مشاتل", "MED_TITLE_NURSERIES"), ("إنتاج زراعي", "MED_TITLE_AGRICULTURAL_PRODUCTION"),
        ("إنتاج التمور", "MED_TITLE_DATE_PRODUCTION"), ("بيوت محمية زراعية", "MED_TITLE_GREENHOUSE"),
        ("agricultural production", "MED_TITLE_AGRICULTURAL_PRODUCTION_EN"),
    ),
    "sector:industrial": (
        ("مصنع", "MED_TITLE_FACTORY"), ("مصانع", "MED_TITLE_FACTORIES"),
        ("إنشاء مصنع", "MED_TITLE_FACTORY_CONSTRUCTION"), ("خط إنتاج", "MED_TITLE_PRODUCTION_LINE"),
        ("منشأة تصنيع", "MED_TITLE_MANUFACTURING_FACILITY"), ("مصنع لل", "MED_TITLE_FACTORY_FOR"),
        ("manufacturing plant", "MED_TITLE_MANUFACTURING_PLANT"), ("factory", "MED_TITLE_FACTORY_EN"),
    ),
    "sector:commercial": (
        ("كشك لبيع", "MED_TITLE_RETAIL_KIOSK"), ("كشك بيع", "MED_TITLE_RETAIL_KIOSK_ALT"),
        ("كشك تجاري", "MED_TITLE_COMMERCIAL_KIOSK"), ("محلات تجارية", "MED_TITLE_RETAIL_SHOPS"),
        ("متاجر عامة", "MED_TITLE_GENERAL_STORES"), ("بيع الألعاب والهدايا والتحف", "MED_TITLE_GIFT_RETAIL"),
        ("بيع الالعاب والهدايا والتحف", "MED_TITLE_GIFT_RETAIL_NORMALIZED"),
        ("مبسط غذائي", "MED_TITLE_FOOD_STALL"), ("عربة أطعمة", "MED_TITLE_FOOD_CART"),
        ("عربة اطعمة", "MED_TITLE_FOOD_CART_NORMALIZED"), ("عربات الأطعمة", "MED_TITLE_FOOD_CARTS"),
        ("عربات الاطعمة", "MED_TITLE_FOOD_CARTS_NORMALIZED"), ("عربة أطعمة متنقلة", "MED_TITLE_MOBILE_FOOD_CART"),
        ("عربة اطعمه", "MED_TITLE_FOOD_CART_ALT"),
        ("عربة آيسكريم", "MED_TITLE_ICE_CREAM_CART"), ("عربة ايسكريم", "MED_TITLE_ICE_CREAM_CART_ALT"),
        ("بسطة لبيع", "MED_TITLE_RETAIL_STALL"), ("بسطه لبيع", "MED_TITLE_RETAIL_STALL_NORMALIZED"),
        ("بسطه بيع", "MED_TITLE_RETAIL_STALL_ALT"), ("لبيع التسالي والشاي", "MED_TITLE_SNACK_RETAIL"),
        ("بيع التسالي والشاي", "MED_TITLE_SNACK_RETAIL_ALT"), ("بيع الاغذيه والمشروبات", "MED_TITLE_FOOD_RETAIL"),
        ("بيع الأغذية والمشروبات", "MED_TITLE_FOOD_RETAIL_AR"), ("مزايدة تأجير موقع مقهى", "MED_TITLE_CAFE_CONCESSION"),
        ("مقهى ومطعم", "MED_TITLE_CAFE_RESTAURANT"),
    ),
    "sector:healthcare": (
        ("إنشاء وتشغيل مستشفى", "MED_TITLE_HOSPITAL_BUILD_OPERATE"), ("إنشاء مستشفى", "MED_TITLE_HOSPITAL_BUILD"),
        ("مستشفى تخصصي", "MED_TITLE_SPECIALTY_HOSPITAL"), ("مركز طبي", "MED_TITLE_MEDICAL_CENTER"),
        ("عيادة طبية", "MED_TITLE_MEDICAL_CLINIC"), ("مختبرات سلامة الغذاء البلدية", "MED_TITLE_MUNICIPAL_FOOD_SAFETY_LABS"),
        ("municipal food safety labs", "MED_TITLE_MUNICIPAL_FOOD_SAFETY_LABS_EN"),
        ("healthcare center", "MED_TITLE_HEALTHCARE_CENTER"), ("medical clinic", "MED_TITLE_MEDICAL_CLINIC_EN"),
    ),
    "sector:education": (
        ("مدرسة أهلية", "MED_TITLE_PRIVATE_SCHOOL"), ("إنشاء مدرسة", "MED_TITLE_SCHOOL_CONSTRUCTION"),
        ("مدرسة", "MED_TITLE_SCHOOL"), ("إنشاء جامعة", "MED_TITLE_UNIVERSITY_CONSTRUCTION"),
        ("إنشاء كلية", "MED_TITLE_COLLEGE_CONSTRUCTION"),
        ("مركز تدريب", "MED_TITLE_TRAINING_CENTER"), ("معهد تدريبي", "MED_TITLE_TRAINING_INSTITUTE"),
    ),
    "sector:logistics": (
        ("مركز لوجستي", "MED_TITLE_LOGISTICS_CENTER"), ("مستودع لوجستي", "MED_TITLE_LOGISTICS_WAREHOUSE"),
        ("مستودعات لوجستية", "MED_TITLE_LOGISTICS_WAREHOUSES"), ("مركز توزيع", "MED_TITLE_DISTRIBUTION_CENTER"),
        ("خدمات الشحن", "MED_TITLE_FREIGHT_SERVICES"), ("نقل البضائع", "MED_TITLE_FREIGHT_TRANSPORT"),
        ("logistics center", "MED_TITLE_LOGISTICS_CENTER_EN"), ("distribution center", "MED_TITLE_DISTRIBUTION_CENTER_EN"),
    ),
    "sector:sports": (
        ("نادي رياضي", "MED_TITLE_SPORTS_CLUB"), ("مركز رياضي", "MED_TITLE_SPORTS_CENTER"),
        ("ملعب رياضي", "MED_TITLE_SPORTS_STADIUM"), ("منشأة رياضية", "MED_TITLE_SPORTS_FACILITY"),
        ("sports club", "MED_TITLE_SPORTS_CLUB_EN"), ("sports facility", "MED_TITLE_SPORTS_FACILITY_EN"),
    ),
    "sector:environment": (
        ("إعادة تدوير النفايات", "MED_TITLE_WASTE_RECYCLING"), ("محطة معالجة مياه الصرف", "MED_TITLE_WASTEWATER_TREATMENT"),
        ("معالجة النفايات", "MED_TITLE_WASTE_TREATMENT"), ("wastewater treatment plant", "MED_TITLE_WASTEWATER_PLANT_EN"),
    ),
    "sector:energy": (
        ("محطة طاقة شمسية", "MED_TITLE_SOLAR_PLANT"), ("توليد الكهرباء", "MED_TITLE_ELECTRICITY_GENERATION"),
        ("محطة كهرباء", "MED_TITLE_POWER_STATION"), ("renewable energy plant", "MED_TITLE_RENEWABLE_ENERGY_EN"),
    ),
    "sector:culture": (
        ("متحف", "MED_TITLE_MUSEUM"), ("مركز ثقافي", "MED_TITLE_CULTURAL_CENTER"),
        ("مركز تراثي", "MED_TITLE_HERITAGE_CENTER"), ("museum", "MED_TITLE_MUSEUM_EN"),
    ),
    "sector:financial_services": (
        ("خدمات مالية", "MED_TITLE_FINANCIAL_SERVICES"), ("خدمات مصرفية", "MED_TITLE_BANKING_SERVICES"),
        ("إنشاء مصرف", "MED_TITLE_BANK"), ("خدمات تمويلية", "MED_TITLE_FINANCING_SERVICES"),
        ("insurance services", "MED_TITLE_INSURANCE_EN"),
    ),
    "sector:technology": (
        ("مركز بيانات", "MED_TITLE_DATA_CENTER"), ("خدمات تقنية المعلومات", "MED_TITLE_IT_SERVICES"),
        ("منصة برمجية", "MED_TITLE_SOFTWARE_PLATFORM"), ("شبكة اتصالات", "MED_TITLE_TELECOM_NETWORK"),
        ("data center", "MED_TITLE_DATA_CENTER_EN"), ("software platform", "MED_TITLE_SOFTWARE_EN"),
    ),
    # Entertainment has no dedicated canonical ID in the accepted taxonomy.
    # These explicitly named public attractions therefore use Other positively,
    # while parks and generic leisure sites remain insufficient.
    "sector:other": (
        ("قطار ترفيهي للأطفال", "MED_TITLE_CHILD_ENTERTAINMENT_TRAIN"),
        ("قطار أطفال", "MED_TITLE_CHILD_TRAIN"), ("ركن ترفيهي يشمل العاب اطفال", "MED_TITLE_FAMILY_ENTERTAINMENT_CORNER"),
        ("ركن ترفيهي يشمل ألعاب أطفال", "MED_TITLE_FAMILY_ENTERTAINMENT_CORNER_AR"),
        ("مركز ترفيه عائلي", "MED_TITLE_FAMILY_ENTERTAINMENT_CENTER"),
        ("amusement facility", "MED_TITLE_AMUSEMENT_FACILITY_EN"),
    ),
}

STRUCTURED_RULES: dict[str, dict[str, str]] = {
    "activity": {
        "الأنشطة الزراعية والحيوانية": "sector:agriculture",
        "الأنشطة المالية": "sector:financial_services",
        "الأنشطة التعليمية": "sector:education",
        "الأنشطة الصناعية": "sector:industrial",
        "صناعي": "sector:industrial",
        "تجاري": "sector:commercial",
    },
    "sub_activity": {
        "خدمات الصرافة": "sector:financial_services",
        "خدمات تعليمية أخرى": "sector:education",
        "محلات تجارية": "sector:commercial",
        "أنشطة تجارة المواد الغذائية": "sector:commercial",
        "أنشطة التجارة العامة": "sector:commercial",
        "أنشطة وخدمات انتاج المواد غير الغذائية": "sector:industrial",
    },
}

ASSET_RULES: dict[str, str] = {
    "مستشفى": "sector:healthcare", "مركز طبي": "sector:healthcare", "عيادة طبية": "sector:healthcare",
    "مدرسة": "sector:education", "مصنع": "sector:industrial", "مشتل زراعي": "sector:agriculture",
    "مزرعة إنتاج": "sector:agriculture", "مستودع لوجستي": "sector:logistics", "مركز لوجستي": "sector:logistics",
    "نادي رياضي": "sector:sports", "ملعب رياضي": "sector:sports", "مركز بيانات": "sector:technology",
}

GENERIC_ONLY = tuple("أرض موقع مبنى تشغيل استثمار تطوير إنشاء تأجير صيانة خدمات مشروع مرفق مجمع".split())
TOURISM_NEGATIVES = ("مطعم", "مطاعم", "مقهى", "كافيه", "restaurant", "cafe", "منتزه عام", "حديقة عامة")
AGRICULTURE_NEGATIVES = ("تموينات", "ميني ماركت", "تجارة المواد الغذائية", "متجر غذائي", "food retail", "grocery store")


def _clean(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _dedup_text_fields(record: dict[str, Any]) -> dict[str, str]:
    title = _clean(record.get("title_ar") or record.get("title"))
    result = {"title": title}
    title_key = comparison_key(title)
    for name in ("short_description", "full_description", "description"):
        value = _clean(record.get(name))
        key = comparison_key(value)
        if value and key and key != title_key and not any(key == comparison_key(v) for k, v in result.items() if k.endswith("description")):
            result[name] = value
    return result


def _generic_primary_title(value: str) -> bool:
    key = comparison_key(value)
    generic = ("فرصة استثمارية", "استثمار موقع", "تأجير موقع", "تأجير مؤقت لموقع", "مزايدة تأجير موقع",
               "استثمار أرض", "تطوير موقع", "موقع استثماري")
    return not key or any(comparison_key(term) in key for term in generic)


def classify_relaxed(record: dict[str, Any]) -> dict[str, Any]:
    """Return a guarded high/medium/review/insufficient decision."""
    base = classify_phase2(record)
    if base["classification"] in {"EXISTING_CLASSIFIED", "HIGH_CONFIDENCE", "REVIEW_REQUIRED"}:
        return base
    if canonical_id("sector", record.get("sector")) != "sector:unspecified":
        return base

    # An unmapped or wrong-dimension source sector is governance evidence, not
    # permission to infer around the source's unresolved assertion.
    for source in record.get("sources") or []:
        raw = _clean(source.get("source_sector"))
        if raw and comparison_key(raw) not in GENERIC_OR_WRONG_DIMENSION and normalize_sector(raw) is None:
            return {**base, "classification": "REVIEW_REQUIRED", "rule_key": "MED_UNMAPPED_SOURCE_CLASSIFICATION_REVIEW",
                    "confidence": 0.0, "confidence_margin": 0.0,
                    "positive_evidence": [{"field": "source_sector", "value": raw, "source_key": source.get("source_key")}],
                    "candidates": []}

    fields = _dedup_text_fields(record)
    title_is_generic = _generic_primary_title(fields["title"])
    evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scores: dict[str, float] = defaultdict(float)
    rule_keys: dict[str, set[str]] = defaultdict(set)
    scored_text_fields: set[tuple[str, str]] = set()
    for sector_id, rules in TITLE_RULES.items():
        for field_name, value in fields.items():
            if field_name.endswith("description") and not title_is_generic:
                continue
            key = comparison_key(value)
            for phrase, rule_key in rules:
                if comparison_key(phrase) in key:
                    # Avoid using a destination/hospital name as a health purpose.
                    if sector_id == "sector:healthcare" and phrase == "مستشفى" and any(
                        comparison_key(neg) in key for neg in ("مقهى مستشفى", "كشك مستشفى", "بالقرب من مستشفى", "بجوار مستشفى")
                    ):
                        continue
                    if sector_id == "sector:healthcare" and phrase in {"مركز طبي", "عيادة طبية", "مختبرات سلامة الغذاء البلدية"} and any(
                        comparison_key(neg) in key for neg in ("مقهى", "كشك", "محل ورود", "موقع ورود", "بيع الهدايا")
                    ):
                        continue
                    # Dates/ingredients mentioning palms do not describe farming.
                    if sector_id == "sector:agriculture" and phrase in {"مزرعة", "نخيل", "إنتاج التمور"} and any(
                        comparison_key(neg) in key for neg in ("المنتجات الثانوية للنخيل", "تحويلية للنخيل", "مستودع أغذية")
                    ):
                        continue
                    if sector_id == "sector:industrial" and phrase in {"مصنع", "إنشاء مصنع", "مصنع لل"} and any(
                        comparison_key(neg) in key for neg in ("ورشة مهنية", "ورشة حرفية", "ورشة مهنيه", "ورشة حرفيه")
                    ):
                        continue
                    evidence[sector_id].append({"field": field_name, "signal": phrase, "value": value[:600], "rule_key": rule_key})
                    # Several aliases may normalize to the same phrase. They
                    # remain traceable evidence, but a single underlying field
                    # contributes only once to confidence.
                    score_key = (sector_id, field_name)
                    if score_key not in scored_text_fields:
                        scores[sector_id] += 4.0 if field_name == "title" else 3.0
                        scored_text_fields.add(score_key)
                    rule_keys[sector_id].add(rule_key)

    activity = _clean(record.get("activity"))
    sub_activity = _clean(record.get("sub_activity"))
    structured_matches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    structured_seen: set[tuple[str, str]] = set()
    for field_name, value in (("activity", activity), ("sub_activity", sub_activity)):
        for source_field in (field_name, "source_" + field_name):
            candidates = [value] if source_field == field_name else [
                _clean(source.get(source_field)) for source in (record.get("sources") or [])
            ]
            for candidate in candidates:
                mapped = STRUCTURED_RULES.get(field_name, {}).get(candidate)
                if mapped:
                    evidence_key = (field_name, comparison_key(candidate))
                    if evidence_key not in structured_seen:
                        structured_matches[mapped].append({"field": source_field, "dimension": field_name,
                            "signal": candidate, "value": candidate,
                            "rule_key": f"MED_EXACT_{field_name.upper()}_SEMANTIC"})
                        structured_seen.add(evidence_key)
    industrial_title = comparison_key(fields["title"])
    if "sector:industrial" in structured_matches and any(comparison_key(term) in industrial_title for term in (
        "ورشة مهنية", "ورشة حرفية", "ورشة مهنيه", "ورشة حرفيه")) and not any(
        comparison_key(term) in industrial_title for term in ("مصنع إنتاج", "مصنع لل", "خط إنتاج")):
        structured_matches.pop("sector:industrial", None)
    for sector_id, items in structured_matches.items():
        evidence[sector_id].extend(items)
        independent_dimensions = {item.get("dimension") for item in items}
        scores[sector_id] += min(4.0, 2.0 * len(independent_dimensions))
        rule_keys[sector_id].add("MED_EXACT_STRUCTURED_SEMANTIC")

    asset_text = _clean(record.get("asset_facility_type"))
    if asset_text:
        asset_id = next((target for phrase, target in ASSET_RULES.items()
                         if comparison_key(phrase) == comparison_key(asset_text)), None)
        if asset_id and asset_id in evidence:
            evidence[asset_id].append({"field": "asset_facility_type", "signal": asset_text,
                                       "value": asset_text, "rule_key": "MED_SPECIFIC_ASSET_TITLE_AGREEMENT"})
            scores[asset_id] += 2.0
            rule_keys[asset_id].add("MED_SPECIFIC_ASSET_TITLE_AGREEMENT")

    # Exact commercial activity plus a cafe/food-service title is a business
    # purpose signal. A cafe mentioned only as a location never reaches here.
    if activity == "الأنشطة التجارية" and sub_activity == "منشآت تقديم الغذاء" and "sector:commercial" not in evidence:
        if any(word in comparison_key(fields["title"]) for word in ("مقهى", "مطعم", "كافتيريا", "عربة اطعمه", "عربة اطعمة")):
            evidence["sector:commercial"].append({"field": "activity+sub_activity+title", "signal": "commercial food-service operation",
                                                   "value": f"{activity} / {sub_activity} / {fields['title'][:500]}",
                                                   "rule_key": "MED_COMMERCIAL_FOOD_SERVICE_PRIMARY_PURPOSE"})
            scores["sector:commercial"] += 7.0
            rule_keys["sector:commercial"].add("MED_COMMERCIAL_FOOD_SERVICE_PRIMARY_PURPOSE")

    # An exact title phrase is enough when it states the investment's primary
    # purpose. Generic tokens are absent from TITLE_RULES by design.
    if not evidence:
        return base

    # Do not let Tourism/Agriculture absorb dining or food retail.
    combined = comparison_key(" ".join(fields.values()))
    for sector_id, negatives in (("sector:tourism", TOURISM_NEGATIVES), ("sector:agriculture", AGRICULTURE_NEGATIVES)):
        if sector_id in evidence and any(comparison_key(term) in combined for term in negatives):
            evidence.pop(sector_id, None)
            scores.pop(sector_id, None)
            rule_keys.pop(sector_id, None)
    if not evidence:
        return base

    ranked = sorted(((score, sector_id) for sector_id, score in scores.items() if sector_id in evidence), reverse=True)
    if len(ranked) > 1:
        first, second = ranked[0], ranked[1]
        margin = first[0] - second[0]
        # Distinct sectors supported by explicit signals require governance review,
        # even where one narrow lexical rule gives a numeric lead.
        candidates = sorted(sector_id for sector_id, items in evidence.items() if items)
        if margin < 3.0 or len(candidates) > 1:
            return {**base, "classification": "REVIEW_REQUIRED", "rule_key": "MED_COMPETING_SECTOR_SIGNALS",
                    "confidence": 0.0, "confidence_margin": round(margin, 3), "positive_evidence": [item for items in evidence.values() for item in items],
                    "confidence_margin_applicability": "APPLICABLE",
                    "top_sector_id": first[1], "top_score": round(first[0], 3),
                    "second_sector_id": second[1], "second_score": round(second[0], 3),
                    "candidates": candidates}

    score, sector_id = ranked[0]
    # Independent structured+title agreement is auditable evidence, not a high
    # confidence result unless the old engine already accepted it.
    fields_supporting = {item["field"] for item in evidence[sector_id]}
    has_competing_sector = len(ranked) > 1
    margin = score - ranked[1][0] if has_competing_sector else None
    confidence = min(MEDIUM_MAX_CONFIDENCE, max(MEDIUM_MIN_CONFIDENCE, 0.82 + min(score, 8.0) * 0.008))
    return {**base, "classification": "MEDIUM_CONFIDENCE", "sector": {
        "sector:tourism": "السياحة", "sector:agriculture": "الزراعة", "sector:industrial": "صناعي",
        "sector:commercial": "تجاري", "sector:healthcare": "الرعاية الصحية", "sector:education": "التعليم",
        "sector:logistics": "الخدمات اللوجستية", "sector:sports": "الرياضة", "sector:environment": "البيئة",
        "sector:energy": "الطاقة", "sector:culture": "الثقافة", "sector:financial_services": "الخدمات المالية",
        "sector:technology": "التقنية والاتصالات", "sector:other": "أخرى",
    }[sector_id], "sector_id": sector_id, "confidence": round(confidence, 3), "total_score": round(confidence * 100, 1),
        "confidence_margin": round(margin, 3) if margin is not None else None,
        "confidence_margin_applicability": "APPLICABLE" if has_competing_sector else "NOT_APPLICABLE",
        "top_sector_id": sector_id, "top_score": round(score, 3),
        "second_sector_id": ranked[1][1] if has_competing_sector else None,
        "second_score": round(ranked[1][0], 3) if has_competing_sector else None,
        "rule_key": sorted(rule_keys[sector_id])[0],
        "rule_keys": sorted(rule_keys[sector_id]), "positive_evidence": evidence[sector_id],
        "negative_evidence": [], "classification_origin": "INFERRED_RULE_MEDIUM", "engine_version": ENGINE_VERSION,
        "evidence_fields": sorted(fields_supporting)}


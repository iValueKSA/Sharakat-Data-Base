"""Governed sector classifier joining the accepted inference layers.

The accepted high and medium confidence engines remain authoritative. This
facade adds a transparent, low-confidence best-fit decision for cases that
those engines intentionally leave unspecified. Raw source payloads are read
only and are never rewritten here.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from .adapters import normalize_sector
from .sector_inference_phase2 import ACTIVITY_MAP, SUBACTIVITY_MAP, STRUCTURED_SUBACTIVITY_SIGNALS
from .sector_inference_relaxed import ENGINE_VERSION as RELAXED_VERSION, STRUCTURED_RULES, classify_relaxed
from .sector_inference import GENERIC_OR_WRONG_DIMENSION, SECTOR_LABELS_BY_ID
from .standardization import canonical_id, comparison_key

ENGINE_VERSION = "ahda-governed-sector-classifier-1.0.0"

# Primary purpose terms, intentionally separate from venue or owner wording.
# Scores are evidence weights, not probabilities.
TEXT_RULES: dict[str, tuple[str, ...]] = {
    "sector:commercial": (
        "مقهى", "كافيه", "مطعم", "عربة أطعمة", "عربة اطعمة", "عربة اطعه", "فود ترك",
        "مبسط غذائي", "بيع الأغذية والمشروبات", "بيع الاغذيه والمشروبات", "خدمات غذائية",
        "بيع الألعاب والهدايا والتحف", "بيع الالعاب والهدايا والتحف", "مزاولة البيع",
        "مقطورة ترويجية", "كشك", "بقالة", "بسطة لبيع", "بسطه لبيع", "بسطه بيع",
        "بيع التسالي والشاي", "بيع التسالي", "تجارة التجزئة", "تجارة المواد الغذائية",
        "تشاليح سيارات", "تأجير موقع مقهى", "تأجير مواقع مؤقته لتقديم الخدمات الغذائية",
        "الأنشطة التجارية", "مواقف سيارات للضيوف", "مواقف السيارات للضيوف", "فحص دوري للمركبات",
        "مركز خدمات سيارات", "مركز خدمات المركبات", "سيارة آيسكريم", "سيارة ايسكريم",
        "عربة آيسكريم", "عربة ايسكريم", "عربه اطعمه",
    ),
    "sector:other": (
        "قطار ترفيهي", "ألعاب مائية", "العاب مائية", "ألعاب هوائية", "العاب هوائية",
        "ألعاب أطفال", "العاب اطفال", "ساحة ألعاب", "ساحة العاب", "دبابات", "اسكوتر",
        "سكوتر", "زحليقة", "عربات مضيئة", "عربات كلاسيك", "عربة نق ترددي",
        "عربات خيل", "حناطير", "مستودع الألعاب المائية", "أكواخ خشبية مؤقتة",
        "amusement", "entertainment attraction",
    ),
    "sector:tourism": (
        "إقامة سياحية", "اقامة سياحية", "إيواء سياحي", "ايواء سياحي", "ضيافة فندقية",
        "سكن سياحي", "مبيت سياحي", "المبيت في شاطئ", "مبيت في شاطئ", "نزل سياحي", "فندق", "منتجع سياحي",
    ),
    "sector:agriculture": (
        "مزرعة", "إنتاج زراعي", "انتاج زراعي", "زراعة", "مشتل زراعي", "نخيل لإنتاج التمور",
    ),
    "sector:industrial": (
        "مصنع", "منشأة صناعية", "تصنيع", "إنتاج صناعي", "انتاج صناعي",
        "منشأة تحويلية", "معالجة المنتجات الثانوية", "خط إنتاج",
    ),
    "sector:real_estate": (
        "مشروع إسكان", "مشروع سكني", "تطوير عقاري", "مبنى تجاري متعدد الانشطة",
        "كرفانات لأغراض سكنية", "كرفانات لاغراض سكنية", "عربات متنقلة لأغراض سكنية",
        "عربات متنقلة لاغراض سكنية",
    ),
    "sector:education": (
        "الخدمات الرقمية للإرشاد والتوجيه المهني", "للإرشاد والتوجيه المهني",
        "خدمات رقمية للإرشاد والتوجيه المهني", "الإرشاد والتوجيه المهني", "خدمات تعليمية",
        "مدرسة", "مركز تدريب", "جامعة", "كلية",
    ),
    "sector:healthcare": (
        "مستشفى", "مركز طبي", "عيادة طبية", "خدمات طبية", "رعاية صحية",
    ),
    "sector:logistics": (
        "مركز لوجستي", "مستودع لوجستي", "خدمات الشحن", "نقل البضائع",
    ),
    "sector:environment": (
        "إعادة تدوير", "معالجة النفايات", "معالجة مياه الصرف", "تدوير النفايات",
    ),
    "sector:energy": ("طاقة شمسية", "توليد الكهرباء", "طاقة متجددة"),
    "sector:culture": ("متحف", "مركز ثقافي", "مركز تراثي"),
    "sector:sports": ("نادي رياضي", "مركز رياضي", "ملعب رياضي", "منشأة رياضية"),
    "sector:financial_services": ("خدمات مصرفية", "خدمات مالية", "خدمات الصرافة", "صراف آلي"),
    "sector:technology": ("خدمات تقنية المعلومات", "منصة برمجية", "مركز بيانات", "شبكة اتصالات"),
}

ACTIVITY_EXACT = {
    **ACTIVITY_MAP,
    "الأنشطة الزراعية والحيوانية": "sector:agriculture",
    "الأنشطة المالية": "sector:financial_services",
    "الأنشطة التعليمية": "sector:education",
    "الأنشطة التجارية": "sector:commercial",
    "الأنشطة الصناعية": "sector:industrial",
    "أنشطة المركبات": "sector:commercial",
    "أنشطة الصيانة والتصليح والتركيب": "sector:commercial",
}
SUBACTIVITY_EXACT = {
    **SUBACTIVITY_MAP,
    **STRUCTURED_SUBACTIVITY_SIGNALS,
    "أنشطة وخدمات انتاج المواد غير الغذائية": "sector:industrial",
    "خدمات تعليمية أخرى": "sector:education",
}

ASSET_EXACT = {
    "العربات المتنقلة": ("sector:commercial", 24.0, "ASSET_MOBILE_VENDING_CONTEXT"),
    "مستودع": ("sector:logistics", 30.0, "ASSET_WAREHOUSE"),
    "مستودع لوجستي": ("sector:logistics", 60.0, "ASSET_LOGISTICS_WAREHOUSE"),
    "مصنع": ("sector:industrial", 60.0, "ASSET_FACTORY"),
    "مزرعة": ("sector:agriculture", 60.0, "ASSET_FARM"),
    "مستشفى": ("sector:healthcare", 60.0, "ASSET_HOSPITAL"),
    "مدرسة": ("sector:education", 60.0, "ASSET_SCHOOL"),
}


def _clean(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _raw_attributes(source: dict[str, Any]) -> dict[str, Any]:
    raw = source.get("raw_data_json") or {}
    return raw.get("attributes") or raw.get("properties") or raw


def _all_text(record: dict[str, Any]) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for name in ("title_ar", "normalized_title", "short_description", "full_description"):
        value = _clean(record.get(name))
        if value:
            fields.append((name, value))
    for index, source in enumerate(record.get("sources") or []):
        for name in ("source_title", "source_activity", "source_sub_activity", "source_subsector"):
            value = _clean(source.get(name))
            if value:
                fields.append((f"source[{index}].{name}", value))
        attrs = _raw_attributes(source)
        for raw_name in ("OPPORTUNITYDESCRIPTION", "ACTIVITYTYPE", "SUBACTIVITYTYPE", "FACILITYTYPE"):
            value = _clean(attrs.get(raw_name))
            if value:
                fields.append((f"source[{index}].raw.{raw_name}", value.strip('" ')))
        for observation_index, observation in enumerate(source.get("observations") or []):
            raw = observation.get("raw_data_json") or observation.get("raw") or {}
            attrs = raw.get("attributes") or raw.get("properties") or raw
            for raw_name in ("OPPORTUNITYDESCRIPTION", "ACTIVITYTYPE", "SUBACTIVITYTYPE", "FACILITYTYPE"):
                value = _clean(attrs.get(raw_name))
                if value:
                    fields.append((f"source[{index}].observation[{observation_index}].{raw_name}", value.strip('" ')))
    # Collapse exact repeated values so copied title/description fields add no weight.
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, value in fields:
        key = comparison_key(value)
        if key and key not in seen:
            seen.add(key)
            unique.append((name, value))
    return unique


def classify_governed(record: dict[str, Any]) -> dict[str, Any]:
    """Return a stable classification with score, alternative, and evidence."""
    current_id = canonical_id("sector", record.get("sector"))
    if current_id != "sector:unspecified":
        return {"classification": "EXISTING_CLASSIFIED", "sector": record.get("sector"),
                "sector_id": current_id, "confidence": 1.0, "method": "PRESERVE_EXISTING",
                "rule_key": "PRESERVE_EXISTING_CANONICAL_SECTOR", "positive_evidence": []}

    accepted = classify_relaxed(record)
    if accepted.get("classification") in {"HIGH_CONFIDENCE", "MEDIUM_CONFIDENCE"}:
        return {**accepted, "method": accepted["classification"], "engine_version": ENGINE_VERSION,
                "top_sector_id": accepted.get("top_sector_id") or accepted.get("sector_id"),
                "top_score": accepted.get("top_score", accepted.get("total_score")),
                "second_sector_id": accepted.get("second_sector_id"),
                "second_score": accepted.get("second_score"),
                "reason": "أدلة مصدر أو قواعد نشاط معتمدة دعمت هذا القطاع.",
                "classification_timestamp": None}

    scores: dict[str, float] = defaultdict(float)
    ev: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add(sector_id: str | None, field: str, signal: str, weight: float, rule: str) -> None:
        if not sector_id or sector_id not in SECTOR_LABELS_BY_ID or sector_id == "sector:unspecified":
            return
        key = (sector_id, field, comparison_key(signal), rule)
        if any((x.get("sector_id"), x.get("field"), comparison_key(x.get("signal")), x.get("rule_key")) == key
               for x in ev[sector_id]):
            return
        duplicate_signal=any(x.get("sector_id")==sector_id
                             and comparison_key(x.get("signal"))==comparison_key(signal) for x in ev[sector_id])
        effective_weight=0.0 if duplicate_signal else weight
        scores[sector_id] += effective_weight
        ev[sector_id].append({"sector_id": sector_id, "field": field, "signal": signal[:240],
                              "rule_key": rule, "weight": effective_weight,
                              "duplicate_representation":duplicate_signal})

    # Exact mapped official values are strongest and are retained as derived evidence.
    for index, source in enumerate(record.get("sources") or []):
        raw_sector = _clean(source.get("source_sector"))
        if raw_sector and comparison_key(raw_sector) not in GENERIC_OR_WRONG_DIMENSION:
            mapped = normalize_sector(raw_sector)
            if mapped:
                add(canonical_id("sector", mapped), f"sources[{index}].source_sector", raw_sector,
                    100.0, "FORCED_EXPLICIT_SOURCE_SECTOR")

    # Structured activity dimensions; generic 'Other' and type/model fields never map.
    for name, mapping, weight in (("activity", ACTIVITY_EXACT, 90.0),
                                  ("sub_activity", SUBACTIVITY_EXACT, 96.0)):
        value = _clean(record.get(name))
        target = mapping.get(value)
        if target and value not in {"أخرى", "غير محدد", "خدمي"}:
            add(target, name, value, weight, f"FORCED_EXACT_{name.upper()}")
    for index, source in enumerate(record.get("sources") or []):
        for field, mapping, weight in (("source_activity", ACTIVITY_EXACT, 90.0),
                                       ("source_sub_activity", SUBACTIVITY_EXACT, 96.0)):
            value = _clean(source.get(field))
            target = mapping.get(value)
            if target and value not in {"أخرى", "غير محدد", "خدمي"}:
                add(target, f"sources[{index}].{field}", value, weight, f"FORCED_EXACT_{field.upper()}")
        attrs = _raw_attributes(source)
        for raw_field, mapping, weight in (("ACTIVITYTYPE", ACTIVITY_EXACT, 84.0),
                                           ("SUBACTIVITYTYPE", SUBACTIVITY_EXACT, 88.0)):
            value = _clean(attrs.get(raw_field)).strip('" ')
            target = mapping.get(value)
            if target and value not in {"أخرى", "غير محدد", "خدمي"}:
                add(target, f"sources[{index}].raw.{raw_field}", value, weight, f"FORCED_RAW_{raw_field}")

    for name, value in _all_text(record):
        key = comparison_key(value)
        for sector_id, terms in TEXT_RULES.items():
            for term in terms:
                if comparison_key(term) not in key:
                    continue
                # Healthcare, tourism, and agriculture require purpose wording;
                # a venue mention alone is not an activity.
                if sector_id == "sector:healthcare" and term in {"مستشفى", "مركز طبي"} and any(
                    comparison_key(x) in key for x in ("كشك", "مقهى", "بالقرب من مستشفى", "بجوار مستشفى", "موقف سيارات")
                ):
                    continue
                if sector_id == "sector:tourism" and term in {"فندق", "منتجع سياحي"} and any(
                    comparison_key(x) in key for x in ("مقهى", "كشك", "مطعم", "بالقرب من", "بجوار")
                ):
                    continue
                if sector_id == "sector:agriculture" and term in {"مزرعة", "زراعة"} and any(
                    comparison_key(x) in key for x in ("المنتجات الثانوية للنخيل", "منشأة تحويلية", "مستودع أغذية")
                ):
                    continue
                weight = 66.0 if name.endswith("title") or name == "title_ar" else 45.0
                add(sector_id, name, term, weight, f"FORCED_PRIMARY_PURPOSE_{sector_id.split(':',1)[1].upper()}")
                break
    # Generic warehouse language can weakly support logistics but cannot create
    # a medium-confidence decision without explicit transport/distribution use.
    for name, value in _all_text(record):
        key=comparison_key(value)
        if "مستودع" in key or "مستودعات" in key:
            add("sector:logistics",name,"مستودع (asset context; logistics use not explicit)",27.0,
                "FORCED_BEST_FIT_GENERIC_WAREHOUSE_CONTEXT")
            break

    # Specific source asset types can support a sector but do not use venue names.
    for index, source in enumerate(record.get("sources") or []):
        attrs = _raw_attributes(source)
        raw_asset = _clean(attrs.get("FACILITYTYPE") or attrs.get("LOCATIONTYPE")).strip('" ')
        asset_key = comparison_key(raw_asset)
        mapped = next((v for k, v in ASSET_EXACT.items() if comparison_key(k) == asset_key), None)
        if mapped:
            sector_id, weight, rule = mapped
            add(sector_id, f"sources[{index}].raw.LOCATIONTYPE", raw_asset, weight, rule)
        for assigned_asset in source.get("assets") or []:
            asset=_clean(assigned_asset)
            mapped=next((v for k,v in ASSET_EXACT.items() if comparison_key(k)==comparison_key(asset)),None)
            if mapped:
                sector_id,weight,rule=mapped
                add(sector_id,f"sources[{index}].asset_assignment",asset,weight,rule)
    asset_value=_clean(record.get("asset_facility_type"))
    asset_key=comparison_key(asset_value)
    if asset_key:
        mapped=next((v for k,v in ASSET_EXACT.items() if comparison_key(k)==asset_key),None)
        if mapped:
            sector_id,weight,rule=mapped
            add(sector_id,"asset_facility_type",asset_value,weight,rule)

    if not scores:
        # Empirical fallback: 28 of the 33 previously classified temporary-rental
        # peers were Commercial (all five Other peers had explicit leisure activity).
        # This is a transparent prior for unresolved concession listings, never an
        # Other fallback. Rows without this source kind use an explicit deterministic
        # best-fit based on the platform's generic investment/concession context.
        same_type = comparison_key(record.get("opportunity_type")) in {
            comparison_key("تأجير مؤقت"), comparison_key("TemporaryRental")}
        if same_type:
            peers = {"sector:commercial": 28, "sector:other": 5}
            add("sector:commercial", "opportunity_type + accepted labeled peers", "temporary rental; 28/33 comparable labeled peers Commercial",
                28.0, "FORCED_BEST_FIT_TEMPORARY_RENTAL_PEER_PRIOR")
            add("sector:other", "accepted labeled peers", "5/33 comparable labeled peers Other; no row-specific positive Other signal",
                5.0, "FORCED_BEST_FIT_PEER_ALTERNATIVE_ONLY")
        else:
            peers = {"sector:commercial": 1}
            add("sector:commercial", "opportunity_type/source context", "current public investment/concession opportunity; no stronger sector-specific evidence",
                10.0, "FORCED_BEST_FIT_GENERIC_INVESTMENT_CONTEXT")

    ranked = sorted(((round(score, 3), sector_id) for sector_id, score in scores.items()),
                    key=lambda row: (-row[0], row[1]))
    top_score, top_id = ranked[0]
    second_score, second_id = ranked[1] if len(ranked) > 1 else (0.0, None)
    evidence = ev[top_id]
    score_margin = round(top_score - second_score, 3)
    authoritative_sectors={sector_id for sector_id, items in ev.items() if any(
        item["rule_key"].startswith(("FORCED_EXPLICIT_SOURCE_SECTOR","FORCED_EXACT_ACTIVITY",
                                    "FORCED_EXACT_SUB_ACTIVITY","FORCED_EXACT_SOURCE_ACTIVITY",
                                    "FORCED_EXACT_SOURCE_SUB_ACTIVITY","FORCED_RAW_ACTIVITYTYPE",
                                    "FORCED_RAW_SUBACTIVITYTYPE")) and item["weight"]>0 for item in items)}
    has_authoritative_conflict=len(authoritative_sectors)>1
    if (not has_authoritative_conflict and top_id in authoritative_sectors
            and (second_score==0 or score_margin>=18)):
        return {
            "classification":"HIGH_CONFIDENCE","method":"HIGH_CONFIDENCE",
            "sector":SECTOR_LABELS_BY_ID[top_id],"sector_id":top_id,"confidence":0.94,
            "confidence_label":"HIGH","confidence_score":0.94,"top_sector_id":top_id,
            "top_score":top_score,"second_sector_id":second_id,"second_score":second_score,
            "confidence_margin":score_margin,"total_score":top_score,"rule_key":evidence[0]["rule_key"],
            "rule_keys":sorted({x["rule_key"] for x in evidence}),"positive_evidence":evidence,
            "negative_evidence":[],"evidence_fields":sorted({x["field"] for x in evidence}),
            "reason":"دليل رسمي أو نشاط/تصنيف منظم صريح يحدد القطاع.","engine_version":ENGINE_VERSION,
            "classification_origin":"SOURCE_EXPLICIT" if top_score>=100 and any(
                x["rule_key"]=="FORCED_EXPLICIT_SOURCE_SECTOR" for x in evidence) else "INFERRED_RULE",
            "classification_timestamp":None,
        }
    primary_purpose_rules={"FORCED_PRIMARY_PURPOSE_"}
    has_primary_purpose=any(any(item["rule_key"].startswith(prefix) and item["weight"]>0
                                for item in items) for prefix in primary_purpose_rules for items in [ev[top_id]])
    if (not has_authoritative_conflict and has_primary_purpose and top_score>=60
            and (second_score==0 or score_margin>=18)):
        return {
            "classification":"MEDIUM_CONFIDENCE","method":"MEDIUM_CONFIDENCE",
            "sector":SECTOR_LABELS_BY_ID[top_id],"sector_id":top_id,"confidence":0.84,
            "confidence_label":"MEDIUM","confidence_score":0.84,"top_sector_id":top_id,
            "top_score":top_score,"second_sector_id":second_id,"second_score":second_score,
            "confidence_margin":score_margin,"total_score":top_score,"rule_key":evidence[0]["rule_key"],
            "rule_keys":sorted({x["rule_key"] for x in evidence}),"positive_evidence":evidence,
            "negative_evidence":[],"evidence_fields":sorted({x["field"] for x in evidence}),
            "reason":"الغرض الاقتصادي مصرح به في بيانات الفرصة، مع بقاء الثقة متوسطة لعدم وجود تصنيف رسمي.",
            "engine_version":ENGINE_VERSION,"classification_origin":"INFERRED_RULE_MEDIUM",
            "classification_timestamp":None,
        }
    return {
        "classification": "FORCED_BEST_FIT", "method": "FORCED_BEST_FIT",
        "sector": SECTOR_LABELS_BY_ID[top_id], "sector_id": top_id,
        "confidence": 0.30, "confidence_label": "LOW", "confidence_score": 0.30,
        "top_sector_id": top_id, "top_score": top_score,
        "second_sector_id": second_id, "second_score": second_score,
        "confidence_margin": score_margin, "total_score": top_score, "rule_key": evidence[0]["rule_key"],
        "rule_keys": sorted({x["rule_key"] for x in evidence}),
        "positive_evidence": evidence, "negative_evidence": [],
        "evidence_fields": sorted({x["field"] for x in evidence}),
        "reason": (
            "اختير القطاع الأعلى دعمًا من الحقول المتاحة بعد تعذر القواعد عالية/المتوسطة؛ "
            "هذا استدلال مشتق منخفض الثقة ولا يمثل تصنيفًا رسميًا للمصدر. البديل الثاني محفوظ للتدقيق."
        ),
        "engine_version": ENGINE_VERSION, "base_engine_version": RELAXED_VERSION,
        "classification_origin": "INFERRED_RULE_FORCED_BEST_FIT",
        "peers": peers if "peers" in locals() else None,
    }


def evidence_fingerprint(record: dict[str, Any], result: dict[str, Any]) -> str:
    relevant_sources=[]
    for source in record.get("sources", []):
        raw=_raw_attributes(source)
        observation_evidence=[]
        for observation in source.get("observations",[]):
            obsraw=observation.get("raw_data_json") or observation.get("raw") or {}
            obsattrs=obsraw.get("attributes") or obsraw.get("properties") or obsraw
            observation_evidence.append({k:obsattrs.get(k) for k in (
                "OPPORTUNITYDESCRIPTION", "ACTIVITYTYPE", "SUBACTIVITYTYPE", "FACILITYTYPE", "LOCATIONTYPE")})
        relevant_sources.append({k:source.get(k) for k in (
            "source_key", "source_sector", "source_activity", "source_sub_activity", "source_subsector",
            "source_title")}|{"assets":source.get("assets",[]),"raw":{k:raw.get(k) for k in (
                "OPPORTUNITYDESCRIPTION", "ACTIVITYTYPE", "SUBACTIVITYTYPE", "FACILITYTYPE", "LOCATIONTYPE")},
            "observations":observation_evidence})
    payload = {"engine_version": ENGINE_VERSION,
               "sector": result.get("sector_id"),
               "rule_key": result.get("rule_key"),
               "evidence": result.get("positive_evidence", []),
               "input": {k: record.get(k) for k in (
                   "activity", "sub_activity", "subsector", "title_ar", "normalized_title",
                   "short_description", "full_description", "opportunity_type", "investment_model",
                   "asset_facility_type")},
               "sources": relevant_sources}
    packed = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()

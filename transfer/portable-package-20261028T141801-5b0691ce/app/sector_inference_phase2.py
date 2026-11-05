"""Evidence-conservative Phase 2 sector inference.

Mappings are trained only from currently classified Masters without a Phase 1
inference event. Text duplicates (normalized title and descriptions that repeat
the title) are collapsed so they cannot inflate confidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any

from .adapters import normalize_sector
from .standardization import canonical_id, canonical_value, comparison_key
from .sector_inference import SECTOR_LABELS_BY_ID

ENGINE_VERSION = "ahda-sector-phase2-1.0.0"
UNSPECIFIED = "sector:unspecified"

# Exact source taxonomy pairs; no mapping is triggered by the value in the
# source_sector field alone. The activity and sub-activity must agree.
EXACT_SUBACTIVITY_RULES = {
    ("الأنشطة التجارية", "أنشطة تجارة المواد الغذائية"): ("sector:commercial", "P2_FURAS_FOOD_RETAIL_EXACT_PAIR"),
    ("الأنشطة التجارية", "محلات تجارية"): ("sector:commercial", "P2_FURAS_RETAIL_SHOPS_EXACT_PAIR"),
    ("الأنشطة المالية", "خدمات الصرافة"): ("sector:financial_services", "P2_FURAS_EXCHANGE_EXACT_PAIR"),
}

# Empirically qualified on 125 non-inferred labeled Masters. A value must have
# >=25 labeled rows and >=98% purity. Sub-activities need >=8 and >=98%.
ACTIVITY_MAP = {
    "صناعي": "sector:industrial",
    "تجاري": "sector:commercial",
}
SUBACTIVITY_MAP = {"أنشطة التجارة العامة": "sector:commercial"}
STRUCTURED_SUBACTIVITY_SIGNALS = {
    "خدمات الصرافة": "sector:financial_services",
    "أنشطة تجارة المواد الغذائية": "sector:commercial",
    "محلات تجارية": "sector:commercial",
    "أنشطة وخدمات انتاج المواد غير الغذائية": "sector:industrial",
}

RAW_SOURCE_MAP = {
    "أنشطة تجارة المواد الغذائية": "sector:commercial",
    "محلات تجارية": "sector:commercial",
    "خدمات الصرافة": "sector:financial_services",
}

PHRASE_RULES = {
    "sector:tourism": {
        "title": ("إنشاء وتشغيل فندق", "إنشاء فندق", "منتجع سياحي", "منشأة ضيافة فندقية", "tourism destination", "hotel development", "resort development"),
        "support": ("فندق", "منتجع", "ضيافة فندقية", "مرفق سياحي", "hotel facility", "hospitality facility"),
    },
    "sector:agriculture": {
        "title": ("استثمار وتشغيل مزرعة", "إنتاج زراعي", "إنتاج التمور", "فرز وتعبئة التمور", "بيوت محمية زراعية", "agricultural production", "greenhouse farming"),
        "support": ("نشاط زراعي", "مزرعة إنتاج", "محاصيل زراعية", "نخيل لإنتاج التمور", "agricultural facility", "date production"),
    },
}

NEGATIVE_RULES = [
    {"key": "P2_CAFE_RESTAURANT_NOT_TOURISM", "phrase_groups": ["مقهى", "مطعم", "مطاعم", "خدمات غذائية", "cafe", "restaurant"], "blocks_alone": ["sector:tourism"]},
    {"key": "P2_FOOD_RETAIL_NOT_AGRICULTURE", "phrase_groups": ["تموينات", "ميني ماركت", "متجر غذائي", "تجارة المواد الغذائية", "food retail", "grocery store"], "blocks_alone": ["sector:agriculture"]},
    {"key": "P2_FOOD_WAREHOUSE_NOT_AGRICULTURE", "phrase_groups": ["مستودع أغذية", "مستودع غذائي", "food warehouse"], "blocks_alone": ["sector:agriculture"]},
    {"key": "P2_GENERIC_PLOT_NOT_REAL_ESTATE", "phrase_groups": ["قطعة رقم", "أرض فضاء", "موقع استثماري"], "blocks_alone": ["sector:real_estate"]},
    {"key": "P2_GENERIC_BUILDING_NOT_REAL_ESTATE", "phrase_groups": ["مبنى", "مكاتب إدارية", "building"], "blocks_alone": ["sector:real_estate"]},
    {"key": "P2_GENERIC_PARKING_NOT_TRANSPORT", "phrase_groups": ["مواقف سيارات", "موقف سيارات", "parking"], "blocks_alone": ["sector:logistics"]},
    {"key": "P2_LOCATION_NAME_NOT_TOURISM", "phrase_groups": ["الأحساء", "الهفوف", "العمران", "العيون"], "blocks_alone": ["sector:tourism"]},
    {"key": "P2_LOCATION_NAME_NOT_AGRICULTURE", "phrase_groups": ["النخيل", "التمور", "واحة الأحساء"], "blocks_alone": ["sector:agriculture"]},
    {"key": "P2_GENERIC_LEASE_NOT_SECTOR", "phrase_groups": ["تأجير", "استثمار", "تشغيل", "lease opportunity", "investment opportunity"], "blocks_alone": ["sector:any"]},
]


def _clean(v: Any) -> str:
    return str(v).strip() if v not in (None, "") else ""


def _norm(v: Any) -> str:
    return comparison_key(_clean(v))


def _field_texts(record: dict[str, Any]) -> dict[str, str]:
    fields = {
        "title": _clean(record.get("title_ar") or record.get("title")),
        "normalized_title": _clean(record.get("normalized_title")),
        "short_description": _clean(record.get("short_description")),
        "full_description": _clean(record.get("full_description")),
        "asset": _clean(record.get("asset_facility_type")),
    }
    title = _norm(fields["title"])
    for key in ("normalized_title", "short_description", "full_description"):
        candidate = _norm(fields[key])
        if not candidate or candidate == title:
            fields[key] = ""
    # De-duplicate repeated descriptions and title variants.
    prior: list[str] = [title] if title else []
    for key in ("short_description", "full_description"):
        value = _norm(fields[key])
        if value and any(value == p or value.startswith(p) or p.startswith(value)
                         or SequenceMatcher(None, value, p).ratio() >= .92 for p in prior):
            fields[key] = ""
        elif value:
            prior.append(value)
    return fields


def _source_evidence(record: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    official: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unknown: list[dict[str, Any]] = []
    for source in record.get("sources") or []:
        raw = _clean(source.get("source_sector"))
        if not raw:
            continue
        # This feed sometimes stores the sub-activity in source_sector. The
        # value is mapped only through the exact structured-pair rule below.
        if _norm(raw) in {_norm(value) for _, value in EXACT_SUBACTIVITY_RULES}:
            continue
        mapped = normalize_sector(raw)
        if mapped and canonical_id("sector", mapped) != UNSPECIFIED:
            official[canonical_id("sector", mapped)].append({
                "field": "official_source_sector", "source_key": source.get("source_key"),
                "value": raw, "mapped": mapped,
            })
        elif _norm(raw) not in {_norm(v) for v in ("خدمي", "LEASE_OPPORTUNITY", "PPP_PROJECT", "GENERAL_ANNOUNCEMENT", "WASTE_SECTOR_INVESTMENT")}:
            unknown.append({"field": "source_sector", "source_key": source.get("source_key"), "value": raw})
    return official, unknown


def classify_phase2(record: dict[str, Any], *, learned_mappings: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """Return HIGH_CONFIDENCE, REVIEW_REQUIRED, INSUFFICIENT_EVIDENCE, or preserve."""
    existing = record.get("sector")
    if canonical_id("sector", existing) != UNSPECIFIED:
        return _result("EXISTING_CLASSIFIED", existing, 1.0, [], [], "P2_PRESERVE_EXISTING_SECTOR")

    official, unknown_official = _source_evidence(record)
    if record.get("source_sector_hidden_with_value_present"):
        return _result("REVIEW_REQUIRED", None, 0.0,
                       [{"field":"official_source_sector","value":"hidden","availability_only":True}], [],
                       "P2_HIDDEN_OFFICIAL_SOURCE_SECTOR_REQUIRES_ADJUDICATION")
    if len(official) > 1:
        return _result("REVIEW_REQUIRED", None, 0.0,
                       [x for group in official.values() for x in group], [], "P2_CONFLICTING_OFFICIAL_SECTORS",
                       candidates=sorted(official))
    if unknown_official:
        # Exact Furas taxonomy pairs remain eligible; other nonempty unmapped
        # source-sector claims are explicitly held for governance review.
        return _result("REVIEW_REQUIRED", None, 0.0, unknown_official, [], "P2_UNMAPPED_OFFICIAL_SECTOR")
    if official:
        sector_id, evidence = next(iter(official.items()))
        return _result("HIGH_CONFIDENCE", SECTOR_LABELS_BY_ID[sector_id], 1.0, evidence, [],
                       "P2_EXPLICIT_OFFICIAL_SECTOR", sector_id=sector_id, classification_origin="SOURCE_EXPLICIT")

    activity = _clean(record.get("activity"))
    sub = _clean(record.get("sub_activity"))
    # Several sources can disagree at a taxonomy level even when the Master
    # projection picks one value. Preserve that conflict for governance.
    source_activities={_norm(x.get("source_activity")) for x in record.get("sources") or [] if _clean(x.get("source_activity"))}
    source_subactivities={_norm(x.get("source_sub_activity")) for x in record.get("sources") or [] if _clean(x.get("source_sub_activity"))}
    if len(source_activities)>1 or len(source_subactivities)>1:
        values=[{"field":"source_activity","value":x.get("source_activity")} for x in record.get("sources") or [] if _clean(x.get("source_activity"))]
        values += [{"field":"source_sub_activity","value":x.get("source_sub_activity")} for x in record.get("sources") or [] if _clean(x.get("source_sub_activity"))]
        return _result("REVIEW_REQUIRED", None, 0.0, values, [], "P2_CONFLICTING_SOURCE_TAXONOMY")
    activity_key, sub_key = _norm(activity), _norm(sub)
    candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    activity_rules = learned_mappings or {"activity": ACTIVITY_MAP, "sub_activity": SUBACTIVITY_MAP}
    activity_id = activity_rules.get("activity", ACTIVITY_MAP).get(activity)
    if activity_id:
        candidate[activity_id].append({"field": "activity", "value": activity, "rule_key": "P2_EMPIRICAL_ACTIVITY_MAPPING"})
    # An agricultural activity paired with the exact industrial by-product
    # sub-activity is a genuine taxonomy contradiction; surface it for review.
    if activity_key == _norm("الأنشطة الزراعية والحيوانية"):
        candidate["sector:agriculture"].append({"field": "activity", "value": activity,
                                               "rule_key": "P2_CURATED_AGRICULTURAL_ACTIVITY_SIGNAL"})
    sub_id = activity_rules.get("sub_activity", SUBACTIVITY_MAP).get(sub)
    if sub_id:
        candidate[sub_id].append({"field": "sub_activity", "value": sub, "rule_key": "P2_EMPIRICAL_SUBACTIVITY_MAPPING"})
    elif sub in STRUCTURED_SUBACTIVITY_SIGNALS:
        signal_id = STRUCTURED_SUBACTIVITY_SIGNALS[sub]
        candidate[signal_id].append({"field": "sub_activity", "value": sub,
                                     "rule_key": "P2_EXACT_SUBACTIVITY_SEMANTIC_SIGNAL"})
    pair_rule = next(((target, rule) for (a, s), (target, rule) in EXACT_SUBACTIVITY_RULES.items()
                      if _norm(a) == activity_key and _norm(s) == sub_key), None)
    if pair_rule:
        target, rule = pair_rule
        candidate[target].append({"field": "activity+sub_activity", "activity": activity,
                                  "sub_activity": sub, "rule_key": rule})

    fields = _field_texts(record)
    combined = " ".join(v for v in fields.values() if v)
    negative = []
    for rule in NEGATIVE_RULES:
        matched = [phrase for phrase in rule["phrase_groups"] if _norm(phrase) in _norm(combined)]
        if matched:
            negative.append({"rule_key": rule["key"], "phrases": matched,
                             "blocks_alone": rule["blocks_alone"]})

    # Phrase evidence is intentionally a cross-field corroborator. A repeated
    # title in descriptions counts once; no single word or generic asset wins.
    phrase_hits: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sector_id, rule_groups in PHRASE_RULES.items():
        title_hits = [p for p in rule_groups["title"] if _norm(p) in _norm(fields["title"])]
        support_hits = []
        for f in ("asset", "short_description", "full_description"):
            support_hits.extend({"field": f, "phrase": p} for p in rule_groups["support"] if _norm(p) in _norm(fields[f]))
        if title_hits:
            phrase_hits[sector_id].extend([{"field": "title", "phrase": p} for p in title_hits])
        if support_hits:
            phrase_hits[sector_id].extend(support_hits)
        if title_hits and support_hits:
            candidate[sector_id].extend(phrase_hits[sector_id])

    if len(candidate) > 1:
        positive = [item for items in candidate.values() for item in items]
        return _result("REVIEW_REQUIRED", None, 0.0, positive, negative,
                       "P2_CONFLICTING_SECTOR_SIGNALS", candidates=sorted(candidate))
    if candidate:
        sector_id, evidence = next(iter(candidate.items()))
        phrase_multisignal = len({e.get("field") for e in evidence if e.get("field") in {"title", "asset", "short_description", "full_description"}}) >= 2
        if any("sector:any" in r["blocks_alone"] for r in negative) and not any(
                e.get("field") in {"activity+sub_activity", "sub_activity", "activity"} for e in evidence) and not phrase_multisignal:
            return _result("INSUFFICIENT_EVIDENCE", None, 0.0, evidence, negative,
                           "P2_GENERIC_LEASE_OR_ASSET_ONLY")
        # A compound-title rule needs independent cross-field support; exact
        # structured mappings are sufficient only in their exact pair.
        exact_pair = any(e.get("field") == "activity+sub_activity" for e in evidence)
        structured_empirical = any(e.get("field") in {"activity", "sub_activity"} for e in evidence)
        is_phrase_corroborated = len({e.get("field") for e in evidence if e.get("field") in {"title", "asset", "short_description", "full_description"}}) >= 2
        if exact_pair or (structured_empirical and not negative) or is_phrase_corroborated:
            confidence = 0.97 if exact_pair else 0.94 if structured_empirical else 0.92
            return _result("HIGH_CONFIDENCE", SECTOR_LABELS_BY_ID[sector_id], confidence,
                           evidence, negative, "P2_EXACT_STRUCTURED_OR_INDEPENDENT_MULTI_SIGNAL",
                           sector_id=sector_id, classification_origin="INFERRED_RULE")
        return _result("REVIEW_REQUIRED", None, 0.0, evidence, negative,
                       "P2_SINGLE_UNCORROBORATED_SIGNAL", candidates=[sector_id])
    if unknown_official:
        return _result("REVIEW_REQUIRED", None, 0.0, unknown_official, negative, "P2_UNMAPPED_OFFICIAL_SECTOR")
    return _result("INSUFFICIENT_EVIDENCE", None, 0.0, [], negative, "P2_INSUFFICIENT_EVIDENCE")


def _result(classification: str, sector: str | None, confidence: float,
            positive: list[dict[str, Any]], negative: list[dict[str, Any]], rule: str, **extra: Any) -> dict[str, Any]:
    label = sector or canonical_value("sector", "غير محدد")
    return {"classification": classification, "sector": label,
            "sector_id": extra.pop("sector_id", canonical_id("sector", label)),
            "total_score": round(confidence * 100, 1), "confidence": confidence,
            "confidence_margin": 1.0 if classification == "HIGH_CONFIDENCE" else 0.0,
            "positive_evidence": positive, "negative_evidence": negative,
            "rule_keys": sorted({rule, *(item.get("rule_key") for item in positive if item.get("rule_key"))}),
            "rule_key": rule, **extra}


def empirical_mappings(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Count non-inferred canonical labels, returning only training counts."""
    output: dict[str, list[dict[str, Any]]] = {}
    for field, minimum, threshold in (("activity", 25, .98), ("sub_activity", 8, .98)):
        grouped: dict[str, Counter[str]] = defaultdict(Counter)
        for row in records:
            if row.get("phase1_inference") or canonical_id("sector", row.get("sector")) == UNSPECIFIED:
                continue
            value = _clean(row.get(field))
            if value:
                grouped[value][canonical_id("sector", row.get("sector"))] += 1
        mappings = []
        for value, counts in sorted(grouped.items()):
            total = sum(counts.values())
            dominant, support = counts.most_common(1)[0]
            purity = support / total
            mappings.append({"source_field": field, "source_value": value,
                             "canonical_sector_id": dominant, "canonical_sector": SECTOR_LABELS_BY_ID.get(dominant, dominant),
                             "total_labeled_records": total, "sector_counts": dict(sorted(counts.items())),
                             "dominant_count": support, "purity_percentage": round(purity * 100, 2),
                             "qualified": total >= minimum and purity >= threshold,
                             "minimum_support": minimum, "minimum_purity_percentage": threshold * 100,
                             "rule_key": f"P2_EMPIRICAL_{field.upper()}_MIN{minimum}_PURITY{int(threshold*100)}"})
        output[field] = mappings
    return output

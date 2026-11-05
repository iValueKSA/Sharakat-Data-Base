"""Central, conservative standardization for opportunity business projections.

Source payloads and SourceOpportunity source columns remain evidence. This module
returns a derived projection plus field-level rule metadata; it never changes raw
input objects or their content fingerprints.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from .geography import canonical_geography_identity

STANDARDIZATION_VERSION = "21"
MISSING_LABEL = "قيمة مفقودة"
OWNER_UNSPECIFIED_LABEL = "غير محدد"
SECTOR_UNSPECIFIED_LABEL = "غير محدد"
ACTIVITY_UNSPECIFIED_LABEL = "غير محدد"
OPPORTUNITY_TYPE_UNSPECIFIED_LABEL = "غير محدد"
INVESTMENT_MODEL_UNSPECIFIED_LABEL = "غير محدد"
_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_SPACE = re.compile(r"\s+")
_FORMAT = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def standardize_text(value: object, *, comparison: bool = False) -> str:
    """Normalize Unicode and spacing safely; preserve ة/ه and ى/ي distinctions."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = _FORMAT.sub("", text).replace("ـ", "")
    text = _DIACRITICS.sub("", text)
    text = _SPACE.sub(" ", text).strip()
    if comparison:
        text = text.translate(_ALEF).casefold()
    return text


def comparison_key(value: object) -> str:
    return standardize_text(value, comparison=True)


def normalize_reference(value: object) -> str | None:
    """Normalize a reference identifier for comparison while preserving its raw value."""
    if value is None or not str(value).strip():
        return None
    text = unicodedata.normalize("NFKC", str(value)).translate(_ARABIC_DIGITS).strip().upper()
    text = "".join(str(unicodedata.digit(char)) if char.isdigit() else char for char in text)
    normalized = "".join(char for char in text if char.isalnum())
    return normalized or None


def _label_key(value: object) -> str:
    return standardize_text(value)


# This registry is intentionally small and explicit. OrganizationAlias and
# TaxonomyMapping remain the persisted source-scoped registries for reviewed
# entity/taxonomy mappings; these entries are globally approved display aliases.
_OTHER_KEYS = {comparison_key(x) for x in ("أخرى", "اخرى", "أخري", "Other", "Others", "غير ذلك")}
_SECTOR_OTHER_KEYS = _OTHER_KEYS | {comparison_key("بقية القطاعات")}
_SECTOR_UNSPECIFIED_KEYS = {comparison_key(x) for x in (SECTOR_UNSPECIFIED_LABEL, MISSING_LABEL, "غير مصنف")}
_SECTOR_WRONG_DIMENSION_KEYS = {comparison_key(x) for x in (
    "فرصة استثمارية", "INVESTMENT_OPPORTUNITY", "GENERAL_ANNOUNCEMENT",
    "INVESTMENT_ANNOUNCEMENT", "INVESTMENT_SECTOR_INFORMATION", "STRATEGIC_PROJECT",
    "LEASE_OPPORTUNITY", "COMMERCIAL_FACILITY_OPPORTUNITY", "PPP_PROJECT",
    "PPP_PROJECT_ANNOUNCEMENT", "WASTE_SECTOR_INVESTMENT",
)}
_SECTOR_LABELS = {
    "environment": "البيئة", "tourism": "السياحة",
    "agriculture": "الزراعة", "healthcare": "الرعاية الصحية", "education": "التعليم",
    "logistics": "الخدمات اللوجستية", "industrial": "صناعي", "commercial": "تجاري",
    "real_estate": "العقارات والإنشاءات", "energy": "الطاقة", "culture": "الثقافة",
    "sports": "الرياضة", "financial_services": "الخدمات المالية", "technology": "التقنية والاتصالات",
    # Explicit NCP portal macro-sectors are retained as distinct canonical
    # values where they do not map faithfully to the narrower legacy taxonomy.
    "hajj_and_umrah": "الحج والعمرة",
    "environment_water_agriculture": "البيئة والمياه والزراعة",
    "municipalities_housing": "البلديات والإسكان",
    "zakat_tax_customs": "الزكاة والضريبة والجمارك",
    "transport_logistics_services": "النقل والخدمات اللوجستية",
}
_SECTOR_LABELS.update({"other": "أخرى", "unspecified": SECTOR_UNSPECIFIED_LABEL})
_SECTOR_KEYS = {}
for _sector_key, _sector_label in _SECTOR_LABELS.items():
    _sector_identity = (f"sector:{_sector_key}", _sector_label)
    _SECTOR_KEYS[comparison_key(_sector_key)] = _sector_identity
    _SECTOR_KEYS[comparison_key(_sector_label)] = _sector_identity

# Opportunity Type aliases are deliberately source-scoped where the same
# technical token can mean different things in different publisher schemas.
# Furas defines TemporaryRental as an offered opportunity kind (temporary
# reservation of an investment site); this does not make it an investment
# model for other sources.
_OPPORTUNITY_TYPE_NON_TYPES = {comparison_key(value) for value in (
    "Investment", "INVESTMENT_OPPORTUNITY", "GENERAL_ANNOUNCEMENT",
    "INVESTMENT_ANNOUNCEMENT", "INVESTMENT_SECTOR_INFORMATION", "STRATEGIC_PROJECT",
    "LEASE_OPPORTUNITY", "PPP_PROJECT", "PPP_PROJECT_ANNOUNCEMENT",
    "COMMERCIAL_FACILITY_OPPORTUNITY", "WASTE_SECTOR_INVESTMENT",
    "الساحات الميادين", "العربات المتنقلة", "المباني", "أخرى",
    "Agriculture", "Commercial", "Culture", "Education", "Energy", "Environment",
    "Healthcare", "Industrial", "Logistics", "Other", "Real Estate",
    "Real Estate & Construction", "Technology", "Tourism",
    "أنشطة تجارة المواد الغذائية", "محلات تجارية",
)}
_OPPORTUNITY_TYPE_REVIEW_KEYS = {comparison_key(value) for value in (
    "COMMERCIAL_FACILITY_OPPORTUNITY", "الساحات الميادين", "العربات المتنقلة", "المباني", "أخرى",
    "Agriculture", "Commercial", "Culture", "Education", "Energy", "Environment",
    "Healthcare", "Industrial", "Logistics", "Other", "Real Estate",
    "Real Estate & Construction", "Technology", "Tourism",
    "أنشطة تجارة المواد الغذائية", "محلات تجارية",
)}
_OPPORTUNITY_TYPE_MODEL_KEYS = {comparison_key(value) for value in (
    "LEASE_OPPORTUNITY", "PPP_PROJECT", "PPP_PROJECT_ANNOUNCEMENT",
)}
_OPPORTUNITY_TYPE_CANONICALS = {
    comparison_key("تأجير مؤقت"): ("opportunity_type:temporary_rental", "تأجير مؤقت"),
}
_INVESTMENT_MODEL_LABELS = {
    "lease": "التأجير",
    "ppp": "الشراكة بين القطاعين العام والخاص",
    "bto": "البناء والنقل والتشغيل",
    "bot": "البناء والتشغيل والنقل",
    "boot": "البناء والتملك والتشغيل والنقل",
    "dbfm": "التصميم والبناء والتمويل والصيانة",
    "dbfom": "التصميم والبناء والتمويل والتشغيل والصيانة",
    "dbfomt": "التصميم والبناء والتمويل والتشغيل والصيانة والنقل",
    "dbfmot": "التصميم والبناء والتمويل والصيانة والتشغيل والنقل",
    "eomt": "التجهيز والتشغيل والصيانة والنقل",
    "romt": "إعادة التأهيل والتشغيل والصيانة والنقل",
    "concession": "الامتياز",
    "revenue_share": "مشاركة الإيرادات",
    "joint_venture": "مشروع مشترك",
    "other": "أخرى",
    "missing": INVESTMENT_MODEL_UNSPECIFIED_LABEL,
}
_INVESTMENT_MODEL_GLOBAL_ALIASES = {
    comparison_key(label): (f"investment_model:{key}", label)
    for key, label in _INVESTMENT_MODEL_LABELS.items()
}
_INVESTMENT_MODEL_GLOBAL_ALIASES.update({
    comparison_key("تأجير"): ("investment_model:lease", _INVESTMENT_MODEL_LABELS["lease"]),
    comparison_key("إيجار"): ("investment_model:lease", _INVESTMENT_MODEL_LABELS["lease"]),
    comparison_key("Other"): ("investment_model:other", _INVESTMENT_MODEL_LABELS["other"]),
    comparison_key("Unknown"): ("investment_model:missing", INVESTMENT_MODEL_UNSPECIFIED_LABEL),
})
_INVESTMENT_MODEL_SOURCE_ALIASES = {
    "ncp": {
        comparison_key(alias): (f"investment_model:{key}", _INVESTMENT_MODEL_LABELS[key])
        for key, aliases in {
            "ppp": ("PPP", "Public-Private Partnership", "Public Private Partnership", "شراكة بين القطاعين العام والخاص"),
            "bto": ("BTO",), "bot": ("BOT",), "boot": ("BOOT",),
            "dbfm": ("DBFM",), "dbfom": ("DBFOM",),
            "dbfomt": ("DBFOMT",), "dbfmot": ("DBFMOT",), "eomt": ("EOMT",),
            "romt": ("ROMT",),
        }.items() for alias in aliases
    },
    "kfu": {comparison_key("LEASE_OPPORTUNITY"): ("investment_model:lease", _INVESTMENT_MODEL_LABELS["lease"])},
    "invest-saudi": {
        comparison_key(alias): (f"investment_model:{key}", _INVESTMENT_MODEL_LABELS[key])
        for key, aliases in {
            "lease": ("Lease",), "ppp": ("PPP", "Public-Private Partnership"),
            "bot": ("BOT",), "boot": ("BOOT",),
            "concession": ("Concession", "Concession Agreement"),
            "joint_venture": ("JV", "Joint Venture"),
        }.items() for alias in aliases
    },
    "ahda": {comparison_key("مشاركة إيرادات"): ("investment_model:revenue_share", _INVESTMENT_MODEL_LABELS["revenue_share"])},
}
_INVESTMENT_MODEL_WRONG_DIMENSION = {comparison_key(value) for value in (
    "TemporaryRental", "TempRental", "تأجير مؤقت", "PPP_PROJECT", "PPP_PROJECT_ANNOUNCEMENT",
    "COMMERCIAL_FACILITY_OPPORTUNITY", "INVESTMENT_OPPORTUNITY", "GENERAL_ANNOUNCEMENT",
    "WASTE_SECTOR_INVESTMENT", "المباني", "محلات تجارية", "الساحات الميادين", "العربات المتنقلة",
    "تشغيل", "Operating",
)}


def _investment_model_identity(value: object, source_key: str = "") -> dict[str, str] | None:
    key = comparison_key(value)
    if not key or key in {comparison_key(x) for x in ("غير محدد", "غير محددة", "قيمة مفقودة", "N/A", "None", "Unknown")}:
        return {"id": "investment_model:missing", "label": INVESTMENT_MODEL_UNSPECIFIED_LABEL}
    if key in _INVESTMENT_MODEL_GLOBAL_ALIASES:
        identifier, label = _INVESTMENT_MODEL_GLOBAL_ALIASES[key]
        return {"id": identifier, "label": label}
    aliases = _INVESTMENT_MODEL_SOURCE_ALIASES.get(str(source_key or "").casefold(), {})
    if key in aliases:
        identifier, label = aliases[key]
        return {"id": identifier, "label": label}
    return None
_SUB_ACTIVITY_ALIASES = {
    comparison_key("أنشطة التجارة العامة"): ("sub_activity:general_trade", "أنشطة التجارة العامة"),
    comparison_key("أنشطة تجارة المواد الغذائية"): ("sub_activity:food_trade", "أنشطة تجارة المواد الغذائية"),
    comparison_key("محلات تجارية"): ("sub_activity:retail_shops", "محلات تجارية"),
    comparison_key("منشآت تقديم الغذاء"): ("sub_activity:food_service_facilities", "منشآت تقديم الغذاء"),
    comparison_key("خدمات الصرافة"): ("sub_activity:money_exchange", "خدمات الصرافة"),
    comparison_key("خدمات تعليمية أخرى"): ("sub_activity:other_educational_services", "خدمات تعليمية أخرى"),
    comparison_key("أنشطة وخدمات انتاج المواد غير الغذائية"): ("sub_activity:non_food_production_services", "أنشطة وخدمات انتاج المواد غير الغذائية"),
    comparison_key("أنشطة و تجارة المعدات الثقيلة"): ("sub_activity:heavy_equipment_trade", "أنشطة و تجارة المعدات الثقيلة"),
    comparison_key("منتزه"): ("sub_activity:park", "منتزه"),
    comparison_key("أخرى"): ("sub_activity:other", "أخرى"),
}
_ACTIVITY_ALIASES = {
    comparison_key("صناعي"): ("activity:industrial", "صناعي"),
    comparison_key("تجاري"): ("activity:commercial", "تجاري"),
    comparison_key("خدمي"): ("activity:service", "خدمي"),
    comparison_key("الأنشطة التجارية"): ("activity:commercial_activities", "الأنشطة التجارية"),
    comparison_key("الأنشطة المالية"): ("activity:financial_activities", "الأنشطة المالية"),
    comparison_key("الأنشطة الصناعية"): ("activity:industrial_activities", "الأنشطة الصناعية"),
    comparison_key("أنشطة الصيانة والتصليح والتركيب"): ("activity:maintenance_repair_installation", "أنشطة الصيانة والتصليح والتركيب"),
    comparison_key("الأنشطة التعليمية"): ("activity:educational_activities", "الأنشطة التعليمية"),
    comparison_key("أنشطة المرافق العامة"): ("activity:public_utilities", "أنشطة المرافق العامة"),
    comparison_key("الأنشطة الزراعية والحيوانية"): ("activity:agriculture_livestock", "الأنشطة الزراعية والحيوانية"),
    comparison_key("الأنشطة الرياضية و الترفيهية"): ("activity:sports_recreation", "الأنشطة الرياضية والترفيهية"),
}


def _include_canonical_labels(aliases: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """Make every approved display label resolve to its own canonical identity."""
    result = dict(aliases)
    for identifier, label in set(aliases.values()):
        key = comparison_key(label)
        existing = result.get(key)
        if existing and existing[0] != identifier:
            raise ValueError(f"Canonical label {label!r} maps to conflicting identities")
        result[key] = (identifier, label)
    return result


# Resolve both source aliases and their canonical display labels through the
# same dimension-scoped registries. This also makes labels safe to pass back
# from filter options as canonical IDs.
_ACTIVITY_ALIASES = _include_canonical_labels(_ACTIVITY_ALIASES)
_SUB_ACTIVITY_ALIASES = _include_canonical_labels(_SUB_ACTIVITY_ALIASES)
_ACTIVITY_UNSPECIFIED_KEYS = {
    comparison_key(value) for value in ("غير محدد", "غير محددة", MISSING_LABEL)
}
_TECHNICAL_ACTIVITY_ENUMS = {comparison_key(value) for value in (
    "INVESTMENT_OPPORTUNITY", "GENERAL_ANNOUNCEMENT", "INVESTMENT_ANNOUNCEMENT",
    "INVESTMENT_SECTOR_INFORMATION", "STRATEGIC_PROJECT", "LEASE_OPPORTUNITY",
    "COMMERCIAL_FACILITY_OPPORTUNITY", "PPP_PROJECT", "PPP_PROJECT_ANNOUNCEMENT",
    "WASTE_SECTOR_INVESTMENT", "PIPELINE_REFERENCE", "SECTOR_INFORMATION",
    "PROCUREMENT_LIKE",
)}
_OWNER_ALIASES = {
    **{comparison_key(x): ("al_ahsa_municipality", "أمانة الأحساء")
       for x in ("أمانة الأحساء", "أمانة محافظة الأحساء", "Al Ahsa Municipality")},
    comparison_key("the Ministry of Municipalities"): ("momah", "وزارة البلديات والإسكان"),
}
_OWNER_UNSPECIFIED_KEYS = {comparison_key(x) for x in ("غير محدد", "غير محددة", MISSING_LABEL, "N/A", "None", "Unknown")}
_OWNER_ALIASES[comparison_key("أمانة الأحساء")] = ("al_ahsa_municipality", "أمانة الأحساء")
_OWNER_ALIASES[comparison_key("وزارة البلديات والإسكان")] = ("momah", "وزارة البلديات والإسكان")
_LOCATION_ALIASES = {
    comparison_key(x): ("al_ahsa_governorate", "الأحساء")
    for x in ("الأحساء", "الاحساء", "Al Ahsa", "Al-Ahsa", "Alhasa")
}
_STATUS_MISSING_ALIASES = {comparison_key(x) for x in ("غير محدد", "غير محددة")}
_STATUS_LABELS = {
    "announced": ("status:available", "متاحة"),
    "published": ("status:available", "متاحة"),
    "منشورة": ("status:available", "متاحة"),
    "available": ("status:available", "متاحة"),
    "active": ("status:available", "متاحة"),
    "متاحة": ("status:available", "متاحة"),
    "expired": ("status:expired", "منتهية"),
    "منتهية": ("status:expired", "منتهية"),
    "removed_from_source": ("status:removed_from_source", "أزيلت من المصدر"),
    "deleted_from_source": ("status:removed_from_source", "أزيلت من المصدر"),
    "deleted": ("status:removed_from_source", "أزيلت من المصدر"),
    "أزيلت من المصدر": ("status:removed_from_source", "أزيلت من المصدر"),
    "ازيلت من المصدر": ("status:removed_from_source", "أزيلت من المصدر"),
    "cancelled": ("status:cancelled", "ملغاة"),
    "canceled": ("status:cancelled", "ملغاة"),
    "ملغاة": ("status:cancelled", "ملغاة"),
    "ملغي": ("status:cancelled", "ملغاة"),
    "awarded": ("status:awarded", "تمت الترسية"),
    "تمت الترسية": ("status:awarded", "تمت الترسية"),
    "غير معروفة": ("status:unknown", "حالة غير معروفة"),
    "حالة غير معروفة": ("status:unknown", "حالة غير معروفة"),
    "غير محددة": ("status:unspecified", "غير محددة"),
    "قيد مراجعة الحالة": ("status:review", "قيد مراجعة الحالة"),
}


def canonical_identity(dimension: str, value: object, *, source_key: str = "") -> dict[str, str] | None:
    """Return a stable ID and approved label, or None for missing values."""
    label = _label_key(value)
    if dimension in {"activity", "sector", "opportunity_type", "type"} and len(label) >= 2:
        for left, right in (("\"", "\""), ("'", "'"), ("“", "”"), ("«", "»")):
            if label.startswith(left) and label.endswith(right):
                label = _label_key(label[1:-1])
                break
    if dimension == "sector" and not label:
        return {"id": "sector:unspecified", "label": SECTOR_UNSPECIFIED_LABEL}
    if dimension == "activity" and not label:
        return {"id": "activity:missing", "label": ACTIVITY_UNSPECIFIED_LABEL}
    if dimension in {"owner", "opportunity_owner"} and not label:
        return {"id": "owner:missing", "label": OWNER_UNSPECIFIED_LABEL}
    if dimension == "investment_model":
        return _investment_model_identity(label, source_key)
    if not label:
        return None
    key = comparison_key(label)
    if dimension in {"owner", "opportunity_owner"} and key in _OWNER_UNSPECIFIED_KEYS:
        return {"id": "owner:missing", "label": OWNER_UNSPECIFIED_LABEL}
    if dimension in {"opportunity_type", "type"}:
        # Until a source-supported type registry is approved, no raw label is
        # promoted to a business category. Unknown inputs retain review status
        # in standardization metadata and raw provenance.
        if key == comparison_key("أخرى"):
            return {"id": "opportunity_type:other", "label": "أخرى"}
        if key in _OPPORTUNITY_TYPE_CANONICALS:
            identifier, canonical = _OPPORTUNITY_TYPE_CANONICALS[key]
            return {"id": identifier, "label": canonical}
        return {"id": "opportunity_type:missing", "label": OPPORTUNITY_TYPE_UNSPECIFIED_LABEL}
    if dimension == "activity" and key in _ACTIVITY_UNSPECIFIED_KEYS:
        return {"id": "activity:missing", "label": ACTIVITY_UNSPECIFIED_LABEL}
    if dimension == "sector" and key in (_SECTOR_UNSPECIFIED_KEYS | _SECTOR_WRONG_DIMENSION_KEYS):
        return {"id": "sector:unspecified", "label": SECTOR_UNSPECIFIED_LABEL}
    if dimension == "sector" and key in _SECTOR_OTHER_KEYS:
        return {"id": "sector:other", "label": "أخرى"}
    if dimension in {"activity", "sector", "type"} and key in _OTHER_KEYS:
        return {"id": f"{dimension}:other", "label": "أخرى"}
    if dimension == "sector" and key in _SECTOR_KEYS:
        identifier, canonical = _SECTOR_KEYS[key]
        return {"id": identifier, "label": canonical}
    if dimension == "sub_activity" and key in _SUB_ACTIVITY_ALIASES:
        identifier, canonical = _SUB_ACTIVITY_ALIASES[key]
        return {"id": identifier, "label": canonical}
    if dimension == "activity" and key in _ACTIVITY_ALIASES:
        identifier, canonical = _ACTIVITY_ALIASES[key]
        return {"id": identifier, "label": canonical}
    if dimension in {"owner", "opportunity_owner"} and key in _OWNER_ALIASES:
        identifier, canonical = _OWNER_ALIASES[key]
        return {"id": identifier, "label": canonical}
    if dimension in {"location", "city"}:
        geography = canonical_geography_identity(label)
        if geography:
            return geography
        if key in _LOCATION_ALIASES:
            identifier, canonical = _LOCATION_ALIASES[key]
            return {"id": identifier, "label": canonical}
    if dimension == "status" and key in _STATUS_MISSING_ALIASES:
        return {"id": "status:missing", "label": "غير محددة"}
    if dimension == "status" and key in _STATUS_LABELS:
        identifier, canonical = _STATUS_LABELS[key]
        return {"id": identifier, "label": canonical}
    if dimension == "status" and label.isascii():
        normalized = label.upper() if label.upper() in {"CANCELLED", "AWARDED", "DELETED_FROM_SOURCE"} else label[:1].upper() + label[1:].lower()
        return {"id": f"status:{comparison_key(normalized).replace(' ', '_')}", "label": normalized}
    return None


def canonical_id(dimension: str, value: object) -> str:
    """Stable query/grouping identity, including a safe ID for unmapped labels."""
    label = _label_key(value)
    identity = canonical_identity(dimension, label)
    if identity:
        return identity["id"]
    if not label:
        if dimension == "sector":
            return "sector:unspecified"
        if dimension == "investment_model":
            return "investment_model:missing"
        return f"{dimension}:missing"
    # Unmapped values keep a conservative, display-normalized identity. Alef
    # folding is useful for candidate discovery but cannot merge an unapproved
    # semantic alias.
    safe_key = standardize_text(label).casefold()
    return f"unmapped:{dimension}:{hashlib.sha256(safe_key.encode()).hexdigest()[:16]}"


def canonical_value(dimension: str, value: object) -> str:
    """Return the canonical display label, retaining unknown values safely."""
    label = _label_key(value)
    # Decorative quotation marks are only removed on taxonomy/category fields.
    if dimension in {"activity", "sector", "opportunity_type", "type"} and len(label) >= 2:
        for left, right in (("\"", "\""), ("'", "'"), ("“", "”"), ("«", "»")):
            if label.startswith(left) and label.endswith(right):
                label = _label_key(label[1:-1])
                break
    identity = canonical_identity(dimension, label)
    if identity:
        return identity["label"]
    if not label:
        if dimension in {"opportunity_type", "type"}:
            return OPPORTUNITY_TYPE_UNSPECIFIED_LABEL
        if dimension == "investment_model":
            return INVESTMENT_MODEL_UNSPECIFIED_LABEL
        return SECTOR_UNSPECIFIED_LABEL if dimension == "sector" else MISSING_LABEL
    return label


def canonical_groups(dimension: str, values: list[object]) -> dict[str, list[object]]:
    groups: dict[str, list[object]] = {}
    for value in values:
        groups.setdefault(canonical_id(dimension, value), []).append(value)
    return groups


def option_labels(dimension: str, values: list[object]) -> list[str]:
    labels = {canonical_value(dimension, value) for value in values if value is not None and _label_key(value)}
    labels.discard(MISSING_LABEL)
    return sorted(labels, key=lambda label: (label == "أخرى", comparison_key(label), label))


def group_counts(dimension: str, pairs: list[tuple[object, int]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for raw, count in pairs:
        identity = canonical_id(dimension, raw)
        labels[identity] = canonical_value(dimension, raw)
        counts[identity] += int(count)
    rows = [{"name": labels[identity], "canonical_id": identity, "filter_value": None if identity.endswith(":missing") else labels[identity], "count": count}
            for identity, count in counts.items()]
    return sorted(rows, key=lambda row: (-row["count"], comparison_key(row["name"])))


def matching_values(dimension: str, selected: str, raw_values: list[object]) -> list[object]:
    identities = {canonical_id(dimension, raw) for raw in raw_values}
    target = selected if selected in identities else canonical_id(dimension, selected)
    return [raw for raw in raw_values if canonical_id(dimension, raw) == target]


def validate_url(value: object) -> tuple[str | None, str | None]:
    """Trim and validate an existing absolute HTTP(S) URL without inventing one."""
    if value is None:
        return None, None
    original = str(value)
    cleaned = standardize_text(original)
    try:
        parts = urlsplit(cleaned)
        scheme = parts.scheme.lower()
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        return None, "invalid_absolute_http_url"
    if scheme not in {"http", "https"} or not parts.netloc or not hostname:
        return None, "invalid_absolute_http_url"
    # Lowercasing scheme/host and removing a default port are safe URL changes.
    host = hostname.lower()
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    normalized = urlunsplit((scheme, host, parts.path or "/", parts.query, parts.fragment))
    return normalized, None


_GROUP_SEPARATOR = "\ue000"
_KNOWN_UNITS = re.compile(r"(?i)(?:SAR|SR|sqm|sq\.?\s*m|m²|m2|م²|م2|ريال(?:\s+سعودي)?|ر\.\s*س|﷼|متر(?:\s+مربع)?|سنوات|سنة|اعوام|عام|أشهر|شهر|أيام|يوم|years?|months?|days?)")


def parse_numeric(value: object) -> float | None:
    """Parse one unambiguous numeric value; unknown units and ambiguous punctuation fail closed."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = unicodedata.normalize("NFKC", str(value)).translate(_ARABIC_DIGITS)
    text = text.replace("٫", ".").replace("٬", _GROUP_SEPARATOR)
    text = _KNOWN_UNITS.sub("", text).strip()
    # No unrecognized letters or more than one numeric token is accepted.
    if re.search(rf"[^0-9+.,\-\s{_GROUP_SEPARATOR}]", text):
        return None
    tokens = re.findall(rf"[+-]?\d[\d.,{_GROUP_SEPARATOR}]*", text)
    if len(tokens) != 1 or "".join(tokens) == "":
        return None
    token = tokens[0]
    token = token.replace(_GROUP_SEPARATOR, ",")
    if "." in token and "," in token:
        # The last separator is decimal; all others must be valid grouping.
        decimal_sep = "." if token.rfind(".") > token.rfind(",") else ","
        grouping_sep = "," if decimal_sep == "." else "."
        integer_part, fractional_part = token.rsplit(decimal_sep, 1)
        groups = integer_part.lstrip("+-").split(grouping_sep)
        if len(groups) > 1 and (not 1 <= len(groups[0]) <= 3 or any(len(group) != 3 for group in groups[1:])):
            return None
        if not fractional_part.isdigit():
            return None
        token = integer_part.replace(grouping_sep, "") + "." + fractional_part
    elif "," in token:
        groups = token.lstrip("+-").split(",")
        if len(groups) > 1 and 1 <= len(groups[0]) <= 3 and all(len(group) == 3 for group in groups[1:]):
            token = token.replace(",", "")
        else:
            return None
    elif token.count(".") > 1:
        groups = token.lstrip("+-").split(".")
        if 1 <= len(groups[0]) <= 3 and all(len(group) == 3 for group in groups[1:]):
            token = token.replace(".", "")
        else:
            return None
    try:
        number = float(Decimal(token))
        return number if math.isfinite(number) else None
    except (InvalidOperation, ValueError):
        return None


def parse_area_sqm(value: object, *, source_key: str, source_payload: dict | None = None) -> float | None:
    """Accept square metres only when the unit is explicit in text or schema."""
    if value is None:
        return None
    text = standardize_text(value, comparison=True)
    if re.search(r"(?:m\s*(?:\^?2|²)|م\s*(?:\^?2|²)|متر\s+مربع|square\s+met(?:er|re)s?)", text, re.I):
        return parse_numeric(value)
    attributes = (source_payload or {}).get("attributes") or {}
    if source_key == "furas" and attributes.get("TOTALSPACEINMETERS") not in (None, ""):
        if str(attributes.get("TOTALSPACEINMETERS")).strip() == str(value).strip():
            return parse_numeric(value)
    return None


def parse_contract_duration_years(value: object) -> float | None:
    """Normalize only explicit years or months; never guess from a bare number."""
    if value is None:
        return None
    text = standardize_text(value, comparison=True)
    amount = parse_numeric(value)
    if amount is None:
        return None
    if re.search(r"\b(?:years?|yrs?)\b|سنة|سنه|سنوات|عام|اعوام", text, re.I):
        return amount
    if re.search(r"\bmonths?\b|شهر|اشهر", text, re.I):
        return amount / 12
    return None


def parse_iso_date(value: object) -> str | None:
    if not value:
        return None
    text = standardize_text(value).translate(_ARABIC_DIGITS)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None
    # Saudi source portals commonly emit day-first slash/dash/dot dates.
    # Keep this parser deterministic (day-first for those forms) and never
    # substitute an observation timestamp when parsing fails.
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None


def canonical_deadline_date(value: object) -> str | None:
    """Normalize a deadline to its Saudi business date without guessing naive times."""
    parsed = parse_iso_date(value)
    if not parsed:
        return None
    if len(parsed) <= 10:
        return parsed
    try:
        parsed_datetime = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed_datetime.tzinfo is None:
        return None
    return parsed_datetime.astimezone(ZoneInfo("Asia/Riyadh")).date().isoformat()


def standardize_field(dimension: str, value: object, *, source_key: str = "") -> dict[str, Any]:
    raw = value
    cleaned = standardize_text(value)
    identity = canonical_identity(dimension, cleaned, source_key=source_key)
    mapped = identity is not None and identity["label"] != cleaned
    canonical = canonical_value(dimension, cleaned) if cleaned or dimension == "sector" else None
    key = comparison_key(cleaned)
    source_scoped_temporary_rental = (
        dimension in {"opportunity_type", "type"}
        and str(source_key or "").casefold() == "furas"
        and key in {comparison_key("TemporaryRental"), comparison_key("TempRental")}
    )
    approved_canonical_type = (
        dimension in {"opportunity_type", "type"}
        and key == comparison_key("تأجير مؤقت")
    )
    if source_scoped_temporary_rental:
        identity = {"id": "opportunity_type:temporary_rental", "label": "تأجير مؤقت"}
    if dimension == "investment_model":
        key = comparison_key(cleaned)
        if not cleaned:
            return {"raw": raw, "normalized": None, "canonical_id": "investment_model:missing",
                    "canonical_label": INVESTMENT_MODEL_UNSPECIFIED_LABEL, "mapping_status": "MISSING", "rule": "investment_model_missing_v15"}
        kfu_lease_classifier = key == comparison_key("LEASE_OPPORTUNITY") and str(source_key or "").casefold() == "kfu"
        if key in _INVESTMENT_MODEL_WRONG_DIMENSION or (key == comparison_key("LEASE_OPPORTUNITY") and not kfu_lease_classifier):
            return {"raw": raw, "normalized": key, "canonical_id": "investment_model:missing",
                    "canonical_label": INVESTMENT_MODEL_UNSPECIFIED_LABEL, "mapping_status": "DIMENSION_REDIRECT",
                    "rule": "investment_model_wrong_dimension_v15"}
        if identity:
            return {"raw": raw, "normalized": key, "canonical_id": identity["id"],
                    "canonical_label": identity["label"], "mapping_status": "MAPPED",
                    "rule": "source_scoped_investment_model_v15" if key in _INVESTMENT_MODEL_SOURCE_ALIASES.get(str(source_key or "").casefold(), {}) else "canonical_investment_model_v15"}
        return {"raw": raw, "normalized": key,
                "canonical_id": f"unmapped:investment_model:{hashlib.sha256(standardize_text(cleaned).casefold().encode()).hexdigest()[:16]}",
                "canonical_label": None, "mapping_status": "UNMAPPED", "rule": "unmapped_investment_model_review_v15"}
    wrong_sector_dimension = dimension == "sector" and comparison_key(cleaned) in _SECTOR_WRONG_DIMENSION_KEYS
    unmapped_sector = dimension == "sector" and bool(cleaned) and identity is None
    if dimension in {"opportunity_type", "type"} and cleaned:
        if source_scoped_temporary_rental:
            rule = "approved_furas_opportunity_type_v11"
        elif approved_canonical_type:
            rule = "approved_canonical_opportunity_type_v11"
        elif key in _OPPORTUNITY_TYPE_REVIEW_KEYS:
            rule = "wrong_dimension_opportunity_type_review_v11"
        elif key in _OPPORTUNITY_TYPE_MODEL_KEYS:
            rule = "opportunity_type_redirected_to_investment_model_v11"
        else:
            rule = "generic_opportunity_type_to_unspecified_v11" if key in _OPPORTUNITY_TYPE_NON_TYPES else "unmapped_opportunity_type_review_v11"
    elif wrong_sector_dimension:
        rule = "wrong_dimension_to_unspecified_v5"
    elif unmapped_sector:
        rule = "unmapped_sector_to_unspecified_v5"
    elif not cleaned:
        rule = "preserve_missing"
    elif mapped:
        rule = "approved_alias_v1"
    elif cleaned != str(raw):
        rule = "safe_text_v1"
    else:
        rule = "unchanged"
    canonical_identifier = identity["id"] if identity else ("sector:unspecified" if unmapped_sector else canonical_id(dimension, cleaned))
    if dimension in {"opportunity_type", "type"}:
        mapping_status = ("MAPPED" if source_scoped_temporary_rental or approved_canonical_type else
                          "MISSING" if not cleaned or (key in _OPPORTUNITY_TYPE_NON_TYPES and key not in _OPPORTUNITY_TYPE_REVIEW_KEYS)
                          else "REVIEW_REQUIRED")
    else:
        mapping_status = "REVIEW_REQUIRED" if wrong_sector_dimension or unmapped_sector else "MAPPED" if identity and cleaned else ("MISSING" if not cleaned else "UNMAPPED")
    if unmapped_sector:
        canonical = SECTOR_UNSPECIFIED_LABEL
    if dimension in {"opportunity_type", "type"}:
        # The general identity helper reserves "أخرى" separately, but the
        # standardizer never approves it without a source-scoped mapping.
        if source_scoped_temporary_rental or approved_canonical_type:
            canonical = identity["label"]
            canonical_identifier = identity["id"]
        else:
            canonical = OPPORTUNITY_TYPE_UNSPECIFIED_LABEL
            canonical_identifier = "opportunity_type:missing"
    return {"raw": raw, "normalized": key, "canonical_id": canonical_identifier,
            "canonical_label": canonical, "mapping_status": mapping_status,
            "rule": rule}


_TEXT_FIELDS = {
    "title_ar": None, "title_en": None, "normalized_title": None, "reference_number": None,
    "opportunity_owner": "owner", "sector": "sector", "activity": "activity", "sub_activity": "sub_activity", "subsector": "subsector",
    "opportunity_type": "opportunity_type", "city": "location", "district": "district",
    "location_description": None, "status": "status", "short_description": None,
    "full_description": None, "primary_publication_platform": "publication_platform",
    "investment_model": "investment_model", "category": "category",
}


def _explicit_source_model(source_key: str, payload: object, title: object = None, description: object = None) -> tuple[str | None, str | None]:
    """Use narrow source-specific offer text only when it names a lease directly."""
    if str(source_key or "").casefold() not in {"kfu", "invest-saudi"}:
        return None, None
    payload = payload if isinstance(payload, dict) else {}
    title_text = standardize_text(title or payload.get("title"))
    description_text = standardize_text(description or payload.get("description"))
    evidence_text = f"{title_text} {description_text}".strip()
    if not evidence_text:
        return None, None
    lease_phrase = re.search(r"(?:تأجير|إيجار)\s+(?:موقع(?:ة|ات)?|مواقع|أرض|أراضٍ|مساحة|مساحات)", evidence_text, re.I)
    if not lease_phrase:
        return None, None
    if str(source_key).casefold() == "kfu":
        source_class = comparison_key(payload.get("content_type") or payload.get("opportunity_type"))
        if source_class != comparison_key("LEASE_OPPORTUNITY"):
            return None, None
    return "تأجير", lease_phrase.group(0)


def _explicit_source_model_options(source_key: str, payload: object, title: object = None, description: object = None) -> tuple[list[str] | None, str | None]:
    """Flag explicit AHDA statements that offer multiple participation models for review."""
    if str(source_key or "").casefold() != "ahda":
        return None, None
    payload = payload if isinstance(payload, dict) else {}
    evidence_text = " ".join(standardize_text(value) for value in (
        title, description, payload.get("description"), payload.get("raw_text"),
    ) if value)
    match = re.search(r"نموذج\s+الاستثمار\s*:\s*خيارات\s+متعددة\s*\(([^)]{1,400})\)", evidence_text, re.I)
    if not match:
        return None, None
    candidates = [standardize_text(item) for item in re.split(r"\s*(?:،|,|أو)\s*", match.group(1))]
    candidates = [item for item in candidates if item]
    return (candidates or None), match.group(0)


def standardize_opportunity(values: dict[str, Any], *, source_key: str = "", source_record: object | None = None) -> dict[str, Any]:
    """Return (standardized values, auditable field metadata and validation issues)."""
    result = dict(values)
    raw_record = source_record or {}
    get_raw = (lambda name: getattr(raw_record, name, None)) if not isinstance(raw_record, dict) else raw_record.get
    fields: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, str]] = []
    payload = get_raw("raw") or {} if not isinstance(raw_record, dict) else raw_record.get("raw", raw_record)
    extracted_model, model_evidence = _explicit_source_model(
        source_key, payload, get_raw("title"), get_raw("description"),
    )
    explicit_model_options, options_evidence = _explicit_source_model_options(
        source_key, payload, get_raw("title"), get_raw("description"),
    )
    if extracted_model and not result.get("investment_model"):
        result["investment_model"] = extracted_model
    for field, dimension in _TEXT_FIELDS.items():
        if field not in result:
            continue
        raw = get_raw({"opportunity_owner": "owner", "activity": "activity", "sector": "sector", "opportunity_type": "opportunity_type", "city": "location", "location_description": "location", "title_ar": "title", "short_description": "description", "full_description": "description", "reference_number": "reference"}.get(field, field))
        value = result[field]
        if dimension == "activity" and comparison_key(value if value is not None else raw) in _TECHNICAL_ACTIVITY_ENUMS:
            technical_value = value if value is not None else raw
            result[field] = None
            fields[field] = {**standardize_field(dimension, technical_value),
                "canonical_id": "activity:missing", "canonical_label": None,
                "mapping_status": "REVIEW_REQUIRED", "rule": "technical_enum_excluded_from_activity_v1"}
            issues.append({"field": field, "code": "TECHNICAL_ENUM_EXCLUDED_FROM_ACTIVITY", "source_key": source_key})
            continue
        if value is None:
            fields[field] = standardize_field(dimension or field, raw, source_key=source_key)
            if field == "investment_model":
                result[field] = None
            if dimension in {"opportunity_type", "type"}:
                result[field] = (fields[field]["canonical_label"]
                                 if fields[field]["mapping_status"] == "MAPPED" else None)
                if raw is not None and str(raw).strip() and fields[field]["mapping_status"] == "REVIEW_REQUIRED":
                    issues.append({"field": field, "code": "OPPORTUNITY_TYPE_DIMENSION_REVIEW", "source_key": source_key})
            continue
        cleaned = standardize_text(value)
        if dimension:
            canonical = canonical_value(dimension, cleaned)
            fields[field] = standardize_field(dimension, raw if raw is not None else value, source_key=source_key)
            if dimension in {"opportunity_type", "type"}:
                canonical = fields[field]["canonical_label"]
                if fields[field]["mapping_status"] == "REVIEW_REQUIRED":
                    issues.append({"field": field, "code": "OPPORTUNITY_TYPE_DIMENSION_REVIEW", "source_key": source_key})
            if dimension == "investment_model":
                canonical = fields[field]["canonical_label"]
                if fields[field]["mapping_status"] in {"UNMAPPED", "DIMENSION_REDIRECT"}:
                    issues.append({"field": field, "code": "INVESTMENT_MODEL_REVIEW_REQUIRED", "source_key": source_key})
            if dimension == "sector" and fields[field]["mapping_status"] == "REVIEW_REQUIRED":
                result[field] = SECTOR_UNSPECIFIED_LABEL
                canonical = SECTOR_UNSPECIFIED_LABEL
                issue_code = "WRONG_DIMENSION_SECTOR_UNSPECIFIED" if comparison_key(cleaned) in _SECTOR_WRONG_DIMENSION_KEYS else "UNMAPPED_SECTOR_REQUIRES_REVIEW"
                issues.append({"field": field, "code": issue_code, "source_key": source_key})
            else:
                result[field] = canonical
            if dimension in {"opportunity_type", "type"}:
                result[field] = canonical if fields[field]["mapping_status"] == "MAPPED" else None
            if dimension == "investment_model":
                result[field] = canonical if fields[field]["mapping_status"] == "MAPPED" else None
            fields[field]["canonical_label"] = canonical
        else:
            result[field] = cleaned
            fields[field] = standardize_field(field, raw if raw is not None else value, source_key=source_key)
            fields[field]["canonical_label"] = cleaned or None
            if cleaned:
                fields[field]["canonical_id"] = f"{field}:{hashlib.sha256(comparison_key(cleaned).encode()).hexdigest()[:16]}"
                fields[field]["mapping_status"] = "NORMALIZED"

    if extracted_model and model_evidence and fields.get("investment_model", {}).get("mapping_status") == "MAPPED":
        fields["investment_model"].update({
            "raw": extracted_model,
            "evidence": model_evidence,
            "evidence_field": "title_or_description",
            "rule": "explicit_source_lease_text_v12",
        })

    model_candidates = (payload.get("investment_model_candidates") if isinstance(payload, dict) else None) or explicit_model_options
    if isinstance(model_candidates, list) and model_candidates:
        fields["investment_model_evidence"] = {
            "raw": model_candidates, "normalized": model_candidates, "evidence": options_evidence,
            "canonical_id": None,
            "canonical_label": None, "mapping_status": "REVIEW_REQUIRED",
            "rule": "explicit_multiple_model_options_v15" if explicit_model_options else "multiple_source_model_candidates_v15",
        }
        issues.append({"field": "investment_model", "code": "INVESTMENT_MODEL_REVIEW_REQUIRED", "source_key": source_key})
    source_class = comparison_key(payload.get("content_type") or payload.get("opportunity_type")) if isinstance(payload, dict) else ""
    if str(source_key or "").casefold() == "kfu" and source_class == comparison_key("COMMERCIAL_FACILITY_OPPORTUNITY"):
        fields["investment_model_evidence"] = {
            "raw": payload.get("content_type") or payload.get("opportunity_type"),
            "normalized": source_class, "candidate_dimension": "asset_facility_or_contract_review",
            "canonical_id": None, "canonical_label": None, "mapping_status": "REVIEW_REQUIRED",
            "rule": "kfu_commercial_facility_not_model_v12",
        }
        issues.append({"field": "investment_model", "code": "INVESTMENT_MODEL_REVIEW_REQUIRED", "source_key": source_key})

    taxonomy_payload=(payload.get("source_taxonomy") or {}) if isinstance(payload,dict) else {}
    sector_evidence=taxonomy_payload.get("sector") or get_raw("activity")
    if sector_evidence and comparison_key(sector_evidence) in _SECTOR_WRONG_DIMENSION_KEYS:
        fields["sector"]=standardize_field("sector",sector_evidence)
        fields["sector"]["canonical_label"]=SECTOR_UNSPECIFIED_LABEL
        issues.append({"field":"sector","code":"WRONG_DIMENSION_SECTOR_UNSPECIFIED","source_key":source_key})

    reference_raw = get_raw("reference")
    if reference_raw is None and isinstance(payload, dict):
        reference_raw = payload.get("official_source_id_original") or payload.get("reference_number")
    if reference_raw is None:
        reference_raw = result.get("reference_number")
    normalized_reference = normalize_reference(reference_raw)
    fields["reference_number"] = {"raw": reference_raw, "normalized": normalized_reference,
        "canonical_id": f"reference:{source_key}:{normalized_reference}" if normalized_reference else None,
        "canonical_label": standardize_text(reference_raw) or None,
        "mapping_status": "VALID" if normalized_reference else ("MISSING" if not reference_raw else "REVIEW_REQUIRED"),
        "rule": "source_reference_id_v1" if normalized_reference else ("preserve_missing" if not reference_raw else "unparseable_identifier_preserved")}

    source_external_id = get_raw("external_id")
    if source_external_id is None and isinstance(raw_record, dict):
        source_external_id = raw_record.get("source_opportunity_id") or raw_record.get("external_id")
    if source_external_id is not None:
        source_id_text = standardize_text(source_external_id)
        fields["source_opportunity_id"] = {"raw": source_external_id, "normalized": source_id_text,
            "canonical_id": f"source_record:{source_key}:{hashlib.sha256(source_id_text.encode()).hexdigest()[:20]}",
            "canonical_label": source_id_text, "mapping_status": "SOURCE_SCOPED_ID",
            "rule": "source_scoped_identifier_v1"}

    for field in ("publication_date", "submission_deadline"):
        value = result.get(field)
        raw_date = get_raw("deadline" if field == "submission_deadline" else field)
        if raw_date is None:
            raw_date = payload.get("publication_date" if field == "publication_date" else "deadline") if isinstance(payload, dict) else None
        parsed = canonical_deadline_date(value) if field == "submission_deadline" else parse_iso_date(value)
        fields[field] = {"raw": raw_date if raw_date is not None else value,
                         "normalized": parsed, "canonical_id": None, "canonical_label": parsed,
                         "mapping_status": "VALID" if parsed else ("MISSING" if not value else "REVIEW_REQUIRED"),
                         "rule": ("saudi_local_deadline_date_v2" if field == "submission_deadline" else "iso_date_v1") if parsed else ("preserve_missing" if not value else "unparsed_date_preserved")}
        if field == "submission_deadline":
            # Canonical deadline values are date-only Saudi business dates;
            # ambiguous or invalid source values remain solely in provenance.
            result[field] = parsed
        if value and not parsed:
            issue_code = "AMBIGUOUS_TIMEZONE_DATE_REVIEW" if field == "submission_deadline" and len(str(value)) > 10 else "UNPARSED_DATE_PRESERVED"
            issues.append({"field": field, "code": issue_code, "source_key": source_key})
    url = get_raw("url")
    if url is None and isinstance(raw_record, dict):
        url = raw_record.get("url")
    if url is not None:
        normalized_url, error = validate_url(url)
        fields["source_url"] = {"raw": url, "normalized": normalized_url, "canonical_id": None,
                                "canonical_label": normalized_url, "mapping_status": "VALID" if not error else "INVALID",
                                "rule": "safe_url_v1" if not error else "invalid_preserved"}
        if error:
            issues.append({"field": "source_url", "code": error, "source_key": source_key})
    # Keep source-specific dimensions in the audit projection without applying
    # universal taxonomy assumptions to their business meaning.
    payload_dimensions = {
        "investment_model": "investment_model", "project_stage": "project_stage",
        "record_semantic_type": "record_semantic_type", "location_scope": "location_scope",
        "source_taxonomy_sector": "source_taxonomy_sector",
        "source_taxonomy_subsector": "source_taxonomy_subsector",
        "opportunity_category": "opportunity_category",
        "opportunity_type": "opportunity_type",
    }
    taxonomy = payload.get("source_taxonomy") or {} if isinstance(payload, dict) else {}
    for raw_key, field_name in payload_dimensions.items():
        raw_value = taxonomy.get("sector" if raw_key == "source_taxonomy_sector" else "subsector") if raw_key.startswith("source_taxonomy_") else (payload.get(raw_key) if isinstance(payload, dict) else None)
        if raw_value is not None:
            fields[f"source:{field_name}"] = standardize_field(field_name, raw_value)
    fields["source_identity"] = {"raw": source_key, "normalized": source_key,
        "canonical_id": f"source:{source_key}" if source_key else None,
        "canonical_label": source_key or None, "mapping_status": "MAPPED" if source_key else "MISSING",
        "rule": "stable_source_key" if source_key else "preserve_missing"}
    raw_numeric_fields = {"land_area_sqm": "area_text", "investment_value": "value_text", "contract_duration_years": "contract_text"}
    for field in ("land_area_sqm", "investment_value", "contract_duration_years", "latitude", "longitude"):
        value = result.get(field)
        raw_numeric = get_raw(raw_numeric_fields[field]) if field in raw_numeric_fields else value
        raw_candidate = raw_numeric if raw_numeric is not None else value
        if field == "land_area_sqm":
            parsed = parse_area_sqm(raw_candidate, source_key=source_key, source_payload=payload)
        elif field == "contract_duration_years":
            parsed = parse_contract_duration_years(raw_candidate)
        else:
            parsed = parse_numeric(raw_candidate)
        valid = parsed is not None
        if field in {"land_area_sqm", "investment_value", "contract_duration_years"}:
            result[field] = parsed if valid else None
        elif raw_numeric is not None and isinstance(raw_numeric, str):
            result[field] = parsed if valid else None
        if value is not None and (not valid or (field in {"land_area_sqm", "investment_value", "contract_duration_years"} and parsed < 0)):
            issues.append({"field": field, "code": "INVALID_NUMERIC_PRESERVED", "source_key": source_key})
        fields[field] = {"raw": raw_numeric if raw_numeric is not None else value, "normalized": parsed if valid else None,
                         "canonical_id": None, "canonical_label": parsed if valid else None,
                         "mapping_status": "VALID" if valid else ("MISSING" if raw_numeric is None and value is None else "REVIEW_REQUIRED"),
                         "rule": "source_unit_verified_numeric_v2" if valid else "preserve_unverified_measure"}
    return {"values": result, "metadata": {"version": STANDARDIZATION_VERSION, "source_key": source_key,
            "fields": fields, "issues": issues}, "issues": issues}

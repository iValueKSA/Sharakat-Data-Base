"""Canonical Saudi geography identities used by filters and presentation.

This is a derived layer. Source-provided place names and raw payloads remain
unchanged; only aliases supported by the existing local source data and the
reviewed locality vocabulary are mapped here.
"""
from __future__ import annotations

import re
import unicodedata

COUNTRY = {"id": "saudi_arabia", "label": "المملكة العربية السعودية", "code": "SA"}
EASTERN_REGION = {"id": "eastern_province", "label": "المنطقة الشرقية"}
AL_AHSA_GOVERNORATE = {"id": "al_ahsa_governorate", "label": "الأحساء"}

_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def geography_key(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = _DIACRITICS.sub("", text)
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"}))
    text = _PUNCTUATION.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


_GOVERNORATE_ALIASES = {
    geography_key(alias)
    for alias in ("الأحساء", "الاحساء", "الاحسا", "Al Ahsa", "Al-Ahsa", "Alahsa", "Al Hasa", "Al-Hasa", "Alhasa", "Al Hasaa")
}
_REGION_ALIASES = {
    geography_key(alias)
    for alias in ("المنطقة الشرقية", "الشرقية", "Eastern Province", "Eastern Region")
}

# Locality aliases are deliberately exact and conservative. These places are
# already present in the project's reviewed location vocabulary/source rows.
_LOCALITIES = {
    "hofuf": ("الهفوف", ("الهفوف", "الهفوف", "Hofuf", "Al Hofuf", "Al-Hofuf", "Alhofuf")),
    "mubarraz": ("المبرز", ("المبرز", "المبرز", "Mubarraz", "Al Mubarraz", "Al-Mubarraz", "Almubarraz")),
    "omran": ("العمران", ("العمران", "العمران", "Omran", "Al Omran", "Al-Omran", "Alomran")),
    "jafr": ("الجفر", ("الجفر", "الجفر", "Jafr", "Al Jafr", "Al-Jafr")),
    "oyoun": ("العيون", ("العيون", "العيون", "Oyoun", "Oyun", "Al Oyoun", "Al-Oyoun", "Al Oyun")),
    "uqair": ("العقير", ("العقير", "العقير", "Uqair", "Al Uqair", "Al-Uqair", "Aqair")),
    "salwa": ("سلوى", ("سلوى", "سلوى", "Salwa")),
    "jarn": ("الجرن", ("الجرن", "Jarn", "Al Jarn", "Al-Jarn")),
    "qarah": ("القارة", ("القارة", "القاره", "Qarah", "Al Qarah", "Al-Qarah")),
    "ghawar": ("الغوار", ("الغوار", "Ghawar", "Al Ghawar", "Al-Ghawar")),
    "ura'ira": ("عريعرة", ("عريعرة", "Uraira", "Uray'irah", "Urayirah")),
    "jawatha": ("جواثا", ("جواثا", "Jawatha", "Juwatha")),
}

_LOCALITY_ALIASES: dict[str, tuple[str, str]] = {}
_GEOGRAPHY_BY_ID: dict[str, dict[str, str | None]] = {}
for slug, (label, aliases) in _LOCALITIES.items():
    locality_id = f"al_ahsa_locality:{slug}"
    identity = {
        "id": locality_id,
        "label": label,
        "country_id": COUNTRY["id"],
        "country": COUNTRY["label"],
        "country_code": COUNTRY["code"],
        "region_id": EASTERN_REGION["id"],
        "region": EASTERN_REGION["label"],
        "governorate_id": AL_AHSA_GOVERNORATE["id"],
        "governorate": AL_AHSA_GOVERNORATE["label"],
        "locality_id": locality_id,
        "locality": label,
    }
    _GEOGRAPHY_BY_ID[locality_id] = identity
    for alias in aliases:
        _LOCALITY_ALIASES[geography_key(alias)] = (locality_id, label)

_GEOGRAPHY_BY_ID[AL_AHSA_GOVERNORATE["id"]] = {
    "id": AL_AHSA_GOVERNORATE["id"], "label": AL_AHSA_GOVERNORATE["label"],
    "country_id": COUNTRY["id"], "country": COUNTRY["label"], "country_code": COUNTRY["code"],
    "region_id": EASTERN_REGION["id"], "region": EASTERN_REGION["label"],
    "governorate_id": AL_AHSA_GOVERNORATE["id"], "governorate": AL_AHSA_GOVERNORATE["label"],
    "locality_id": None, "locality": None,
}
_GEOGRAPHY_BY_ID[EASTERN_REGION["id"]] = {
    "id": EASTERN_REGION["id"], "label": EASTERN_REGION["label"],
    "country_id": COUNTRY["id"], "country": COUNTRY["label"], "country_code": COUNTRY["code"],
    "region_id": EASTERN_REGION["id"], "region": EASTERN_REGION["label"],
    "governorate_id": None, "governorate": None, "locality_id": None, "locality": None,
}


def canonical_geography_identity(value: object) -> dict[str, str] | None:
    key = geography_key(value)
    if not key:
        return None
    if key in _GOVERNORATE_ALIASES:
        return {"id": AL_AHSA_GOVERNORATE["id"], "label": AL_AHSA_GOVERNORATE["label"]}
    if key in _REGION_ALIASES:
        return {"id": EASTERN_REGION["id"], "label": EASTERN_REGION["label"]}
    locality = _LOCALITY_ALIASES.get(key)
    if locality:
        return {"id": locality[0], "label": locality[1]}
    return None


def geography_identity_by_id(identifier: str) -> dict[str, str | None] | None:
    return _GEOGRAPHY_BY_ID.get(identifier)


def locality_alias_projections() -> list[tuple[str, str]]:
    """Return reviewed aliases with their preserved canonical locality label."""
    return [(alias, label) for _, (label, aliases) in _LOCALITIES.items() for alias in aliases]


def aliases_within(*, governorate_id: str | None = None, region_id: str | None = None, country_id: str | None = None) -> set[str]:
    aliases = set(_GOVERNORATE_ALIASES if governorate_id == AL_AHSA_GOVERNORATE["id"] else ())
    aliases.update(_REGION_ALIASES if region_id == EASTERN_REGION["id"] else ())
    for raw_alias, (locality_id, _) in _LOCALITY_ALIASES.items():
        identity = _GEOGRAPHY_BY_ID[locality_id]
        if ((governorate_id and identity["governorate_id"] == governorate_id)
                or (region_id and identity["region_id"] == region_id)
                or (country_id and identity["country_id"] == country_id)):
            aliases.add(raw_alias)
    # Return normalized forms used for comparisons against stored labels.
    return aliases


def resolve_master_geography(city: object, district: object = None, *, status: str | None = None, reason: str | None = None) -> dict:
    city_text = str(city or "").strip()
    district_text = str(district or "").strip()
    district_identity = canonical_geography_identity(district_text)
    city_identity = canonical_geography_identity(city_text)
    chosen = district_identity if district_identity and district_identity["id"].startswith("al_ahsa_locality:") else city_identity or district_identity
    hierarchy = geography_identity_by_id(chosen["id"]) if chosen else None

    location_status = status or ("CONFIRMED" if hierarchy and hierarchy.get("governorate_id") else "LOCATION_UNSPECIFIED")
    if location_status == "LOCATION_UNSPECIFIED":
        # The six AHDA records had a synthetic Master value from publisher
        # scope. Preserve that projection below as evidence, but do not expose
        # it as canonical geography.
        hierarchy = None
    elif location_status == "REGION_ONLY":
        hierarchy = geography_identity_by_id(EASTERN_REGION["id"])

    return {
        "status": location_status,
        "confirmed": location_status == "CONFIRMED" and bool(hierarchy and hierarchy.get("governorate_id")),
        "country_id": hierarchy.get("country_id") if hierarchy else None,
        "country": hierarchy.get("country") if hierarchy else None,
        "country_code": hierarchy.get("country_code") if hierarchy else None,
        "region_id": hierarchy.get("region_id") if hierarchy else None,
        "region": hierarchy.get("region") if hierarchy else None,
        "governorate_id": hierarchy.get("governorate_id") if hierarchy else None,
        "governorate": hierarchy.get("governorate") if hierarchy else None,
        "locality_id": hierarchy.get("locality_id") if hierarchy else None,
        "locality": hierarchy.get("locality") if hierarchy else None,
        "district": district_text or None,
        "reason": reason,
        "source_projection": {"city": city_text or None, "district": district_text or None},
    }

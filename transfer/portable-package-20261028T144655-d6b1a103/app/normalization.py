import re
import unicodedata
from .standardization import normalize_reference as standardize_reference_id, standardize_text
from .geography import locality_alias_projections

TASHKEEL = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_arabic(value: str | None) -> str:
    if not value:
        return ""
    # This is a comparison/title helper, not a display rewrite. It deliberately
    # preserves taa marbuta/haa and alef maqsura/yaa distinctions.
    text = standardize_text(value, comparison=True).translate(ARABIC_DIGITS)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip().casefold()


def normalize_reference(value: str | None) -> str | None:
    """Canonicalize opportunity references while preserving the source's original string separately."""
    return standardize_reference_id(value)


LOCATIONS = {
    "الاحساء": ("الأحساء", 1.0), "الاحسا": ("الأحساء", 1.0),
    "الهفوف": ("الهفوف", .95), "المبرز": ("المبرز", .95),
    "العمران": ("العمران", .95), "الجفر": ("الجفر", .95),
    "العيون": ("العيون", .95), "العقير": ("العقير", .95),
    "سلوى": ("سلوى", .95), "الجرن": ("الجرن", .95), "القاره": ("القارة", .95),
    "الغوار": ("الغوار", .95), "عريعرة": ("عريعرة", .95), "جواثا": ("جواثا", .95),
    "al ahsa": ("الأحساء", 1.0), "al-ahsa": ("الأحساء", 1.0),
    "alahsa": ("الأحساء", 1.0), "al hasa": ("الأحساء", 1.0),
    "al-hasa": ("الأحساء", 1.0), "hofuf": ("الهفوف", .95),
    "al hofuf": ("الهفوف", .95), "al-hofuf": ("الهفوف", .95),
}
LOCATIONS.update({alias: (label, .95) for alias, label in locality_alias_projections()})


def classify_location(*values: str | None) -> tuple[bool, float, str, str]:
    text = " | ".join(v for v in values if v)
    norm = normalize_arabic(text)
    for token, (city, score) in LOCATIONS.items():
        key = normalize_arabic(token)
        if key and key in norm:
            return True, score, city, f"explicit_location:{token}"
    if "المنطقه الشرقيه" in norm or "eastern province" in norm:
        return False, .30, "", "province_only_not_qualified"
    return False, 0.0, "", "no_confirmed_locality"


def parse_number(value: str | None) -> float | None:
    if not value:
        return None
    text = value.translate(ARABIC_DIGITS).replace(",", "").replace("٬", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


_BILINGUAL = {
    "construction": ("إنشاء", "انشاء", "construction", "build", "building"),
    "operation": ("تشغيل", "operation", "operate", "operating"),
    "maintenance": ("صيانة", "maintenance", "maintain"),
    "warehouse": ("مستودع", "warehouse", "storage"),
    "office": ("مكاتب", "مكتب", "offices", "office"),
    "commercial": ("تجاري", "commercial", "commerce"),
    "industrial": ("صناعي", "صناعية", "industrial"),
    "park": ("حديقة", "متنزه", "park", "garden"),
    "market": ("سوق", "market"),
    "restaurant": ("مطعم", "restaurant"),
    "school": ("مدرسة", "school"),
    "hotel": ("فندق", "hotel"),
    "lease": ("تأجير", "استئجار", "lease", "rent"),
    "plot": ("قطعة", "قطعه", "plot"),
    "administrative": ("إدارية", "اداريه", "administrative"),
}


def comparison_title(value: str | None) -> str:
    normalized = normalize_arabic(value)
    tokens = []
    for word in normalized.split():
        if word.startswith("و") and len(word) > 3:
            word = word[1:]
        mapped = next((canonical for canonical, variants in _BILINGUAL.items() if word in {normalize_arabic(v) for v in variants}), word)
        if mapped not in {"a", "an", "and", "of", "for", "the", "في", "من", "على", "ب", "ال", "construction", "operation", "maintenance"}:
            tokens.append(mapped)
    return " ".join(sorted(set(tokens)))

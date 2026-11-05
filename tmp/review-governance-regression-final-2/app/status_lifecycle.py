"""Source-aware, deterministic opportunity status and lifecycle semantics."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

SAUDI_TZ = ZoneInfo("Asia/Riyadh")

AVAILABLE = "متاحة"
PUBLISHED = "منشورة"
EXPIRED = "منتهية"
CANCELLED = "ملغاة"
AWARDED = "تمت الترسية"
REMOVED = "أزيلت من المصدر"
UNKNOWN = "حالة غير معروفة"
UNSPECIFIED = "غير محددة"
STATUS_REVIEW = "قيد مراجعة الحالة"

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_EXPLICIT = {
    "متاحة": AVAILABLE, "available": AVAILABLE, "active": AVAILABLE, "open": AVAILABLE,
    "نشطة": AVAILABLE, "فرصة متاحة": AVAILABLE,
    "announced": PUBLISHED, "published": PUBLISHED, "منشورة": PUBLISHED, "معلن": PUBLISHED,
    "expired": EXPIRED, "closed": EXPIRED, "منتهية": EXPIRED, "منتهي": EXPIRED,
    "ملغاة": CANCELLED, "ملغي": CANCELLED, "cancelled": CANCELLED, "canceled": CANCELLED,
    "award": AWARDED, "awarded": AWARDED, "تم الترسية": AWARDED, "مرسى": AWARDED,
    "deleted": REMOVED, "deleted from source": REMOVED, "removed from source": REMOVED,
    "removed_from_source": REMOVED, "deleted_from_source": REMOVED,
}
_EXPLICIT_CANCEL = {"cancelled", "canceled", "cancel", "ملغاة", "ملغي", "ملغى"}


def _key(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).translate(_ARABIC_DIGITS)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return re.sub(r"\s+", " ", text).strip().casefold()


def local_today(now: datetime | None = None) -> date:
    return (now or datetime.now(SAUDI_TZ)).astimezone(SAUDI_TZ).date()


def parse_deadline(value: object) -> date | None:
    """Parse local-date deadlines; offset datetimes resolve to the Riyadh day."""
    key = _key(value)
    if not key:
        return None
    if len(key) > 10 and key[:10].count("-") == 2:
        try:
            parsed_datetime = datetime.fromisoformat(key.replace("z", "+00:00"))
        except ValueError:
            return None
        # A timezone-naive datetime has no safe local-day interpretation.
        if parsed_datetime.tzinfo is None:
            return None
        return parsed_datetime.astimezone(SAUDI_TZ).date()
    candidate = key[:10].replace("/", "-")
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        pass
    for fmt in ("%d-%m-%Y", "%d-%m-%y", "%Y.%m.%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(key, fmt).date()
        except ValueError:
            continue
    return None


def canonical_source_status(source_key: str, raw_status: object, deadline: object = None,
                            *, now: datetime | None = None) -> tuple[str, list[str]]:
    """Return a canonical source state and review flags; never mutate raw evidence."""
    key = _key(raw_status)
    flags: list[str] = []
    if source_key=="ncp" and key=="identity_alias":
        # NCP's adapter uses this as a source-identity consolidation marker,
        # not as a lifecycle claim. Let official deadline evidence decide.
        state=UNSPECIFIED
        flags.append("IDENTITY_ALIAS_NOT_A_STATUS")
    elif key in _EXPLICIT:
        state = _EXPLICIT[key]
    elif key in {"unknown", "غير معروف", "غير واضحة", "غير واضح"}:
        state = UNKNOWN
    elif key in {"", "none", "null", "غير محددة", "غير محدد", "لا يوجد"}:
        state = UNSPECIFIED
    elif key in {"true", "1"}:
        # Legacy boolean evidence is not enough to distinguish publication from actionability.
        state = UNKNOWN
        flags.append("AMBIGUOUS_BOOLEAN_STATUS")
    elif key in {"false", "0"}:
        state = UNKNOWN
        flags.append("AMBIGUOUS_BOOLEAN_STATUS")
    else:
        state = UNKNOWN
        flags.append("AMBIGUOUS_RAW_STATUS")

    parsed = parse_deadline(deadline)
    if deadline not in (None, "") and parsed is None:
        flags.append("INVALID_DEADLINE")
    if parsed is not None and parsed < local_today(now):
        if state in (UNSPECIFIED, UNKNOWN):
            state = EXPIRED
            flags.append("EXPIRED_BY_PASSED_DATE_ONLY_DEADLINE")
        elif state in (AVAILABLE, PUBLISHED):
            flags.append("STATUS_DEADLINE_CONFLICT")
    elif parsed is not None and state == EXPIRED and parsed >= local_today(now):
        flags.append("STATUS_DEADLINE_CONFLICT")
    if source_key == "" and key:
        flags.append("SOURCE_KEY_MISSING")
    return state, flags


def aggregate_master_status(statuses: list[str]) -> tuple[str, list[str]]:
    """Project linked source states to one Master state without treating removal as cancellation."""
    states = set(statuses)
    flags: list[str] = []
    live = states.intersection({AVAILABLE, PUBLISHED})
    if CANCELLED in states and live:
        return STATUS_REVIEW, ["SOURCE_STATUS_CONFLICT_CANCELLED_AND_LIVE"]
    if AVAILABLE in live:
        if states.intersection({EXPIRED, REMOVED, CANCELLED}):
            flags.append("MULTI_SOURCE_STATUS_CONFLICT")
        return AVAILABLE, flags
    if PUBLISHED in live:
        if states.intersection({EXPIRED, REMOVED, CANCELLED}):
            flags.append("MULTI_SOURCE_STATUS_CONFLICT")
        return PUBLISHED, flags
    if CANCELLED in states:
        return CANCELLED, flags
    if AWARDED in states:
        return AWARDED, flags
    if EXPIRED in states:
        if REMOVED in states:
            flags.append("MULTI_SOURCE_STATUS_CONFLICT")
        return EXPIRED, flags
    if REMOVED in states:
        return REMOVED, flags
    if UNKNOWN in states:
        return UNKNOWN, flags
    return UNSPECIFIED, flags


def status_is_active(status: str | None) -> bool:
    return status in {AVAILABLE, PUBLISHED}


def status_is_historical(status: str | None) -> bool:
    return status in {EXPIRED, CANCELLED, AWARDED, REMOVED}

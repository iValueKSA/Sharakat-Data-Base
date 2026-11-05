"""Technical source-link handling, separate from opportunity lifecycle semantics."""

from __future__ import annotations

import re
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode


UNAVAILABLE_CONFIRMED = "UNAVAILABLE_CONFIRMED"
TEMPORARILY_UNVERIFIABLE = "TEMPORARILY_UNVERIFIABLE"
VALID = "VALID"
REDIRECTED_VALID = "REDIRECTED_VALID"
MISSING = "MISSING"
INVALID = "INVALID"

_FURAS_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{2,199}$")
_TEMP_RENTAL_ALIASES = {"TemporaryRental": "TempRental", "TempRental": "TempRental"}


def furas_detail_url(reference: str | None, opportunity_type: str | None) -> str | None:
    """Build Furas's current public detail route using its source identifiers.

    The ArcGIS data layer calls this type ``TemporaryRental``; the public detail
    route expects the shorter ``TempRental`` value. Investment retains its value.
    """
    ref = str(reference or "").strip()
    if not ref or not _FURAS_REFERENCE.fullmatch(ref):
        return None
    source_type = str(opportunity_type or "").strip()
    if not source_type:
        return None
    route_type = _TEMP_RENTAL_ALIASES.get(source_type, source_type)
    return f"https://furas.momah.gov.sa/index.php/ar/opportunity/{quote(ref, safe='')}?{urlencode({'type': route_type})}"


@lru_cache(maxsize=1)
def _link_health_index() -> dict:
    path = Path(__file__).with_name("source_link_health.json")
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return {int(row["source_record_id"]): row for row in rows
            if isinstance(row, dict) and row.get("source_record_id") is not None}


def resolve_source_link(record, source=None, audited_health: str | None = None) -> dict:
    """Resolve the display/export URL without altering raw or historical values."""
    if source is None:
        source = record.source
    stored_url = (getattr(record, "source_url", None) or "").strip() or None
    raw = getattr(record, "raw_data_json", None) or {}
    attributes = raw.get("attributes") if isinstance(raw, dict) else None
    attributes = attributes if isinstance(attributes, dict) else {}
    canonical_url = None
    if getattr(source, "source_key", None) == "furas":
        reference = (getattr(record, "source_reference_number", None)
                    or attributes.get("OPPORTUNITYID")
                    or getattr(record, "official_source_id_original", None)
                    or getattr(record, "source_opportunity_id", None))
        source_type = attributes.get("OPPORTUNITYTYPE")
        canonical_url = furas_detail_url(reference, source_type)

    current_url = canonical_url or stored_url
    if not current_url:
        health = MISSING
    elif not current_url.startswith(("https://", "http://")):
        health = INVALID
    else:
        health = "UNVERIFIED"
    checked_at = None
    if audited_health is None and current_url:
        audit = _link_health_index().get(int(getattr(record, "id", 0) or 0))
        if audit and audit.get("url_sha256") == hashlib.sha256(current_url.encode("utf-8")).hexdigest():
            audited_health = audit.get("link_health")
            checked_at = audit.get("checked_at")
    health = audited_health or health
    if health not in {VALID, REDIRECTED_VALID, "UNVERIFIED"}:
        return {"url": None, "historical_url": stored_url or current_url,
                "checked_url": current_url,
                "checked_at": checked_at, "stored_url": stored_url, "link_health": health,
                "url_repaired": bool(current_url and current_url != stored_url)}
    return {"url": current_url, "historical_url": stored_url if current_url != stored_url else None,
            "checked_url": current_url,
            "checked_at": checked_at, "stored_url": stored_url, "link_health": health,
            "url_repaired": bool(current_url and current_url != stored_url)}


def resolve_preferred_source_link(records) -> dict:
    """Return the first usable per-source link for the legacy single-URL export field."""
    ordered = sorted(records or [], key=lambda record: (
        getattr(getattr(record, "source", None), "priority", 99),
        getattr(getattr(record, "source", None), "source_key", ""),
        getattr(record, "id", 0),
    ))
    if not ordered:
        return {"url": None, "link_health": MISSING}
    resolutions = [resolve_source_link(record, getattr(record, "source", None)) for record in ordered]
    return next((resolution for resolution in resolutions if resolution.get("url")), resolutions[0])


def classify_http_result(*, status: int | None, identity_match: bool = False,
                         redirected: bool = False, login_required: bool = False,
                         error_page: bool = False, network_error: bool = False) -> str:
    """Classify technical link health; never maps any state to business status."""
    if network_error:
        return TEMPORARILY_UNVERIFIABLE
    if status is None:
        return MISSING
    if status == 404 or status == 410:
        return UNAVAILABLE_CONFIRMED
    if status in (401, 403) or login_required or status >= 500:
        return TEMPORARILY_UNVERIFIABLE
    if status == 200 and (error_page or not identity_match):
        return TEMPORARILY_UNVERIFIABLE
    if status == 200 and identity_match:
        return REDIRECTED_VALID if redirected else VALID
    if redirected and identity_match:
        return REDIRECTED_VALID
    return TEMPORARILY_UNVERIFIABLE


def source_url_history_observation(record, replacement_url: str, observed_at):
    """Build an immutable provenance observation before ingestion replaces a URL."""
    previous_url = (getattr(record, "source_url", None) or "").strip()
    replacement_url = (replacement_url or "").strip()
    if not previous_url or previous_url == replacement_url:
        return None
    payload = {
        "change_type": "CANONICAL_SOURCE_URL_REPLACED",
        "previous_url": previous_url,
        "replacement_url": replacement_url or None,
        "source_opportunity_id": getattr(record, "source_opportunity_id", None),
        "source_reference_number": getattr(record, "source_reference_number", None),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return {
        "source_opportunity_id": int(record.id),
        "dataset_name": "source-url-history",
        "endpoint": previous_url[:600],
        "official_source_id_original": str(
            getattr(record, "official_source_id_original", None)
            or getattr(record, "source_opportunity_id", "unknown")
        )[:200],
        "official_source_id_normalized": str(
            getattr(record, "official_source_id_normalized", None)
            or getattr(record, "source_opportunity_id", "unknown")
        )[:200],
        "raw_data_json": payload,
        "source_updated_at": observed_at.isoformat() if observed_at else None,
        "content_hash": digest,
        "first_seen_at": observed_at,
        "last_seen_at": observed_at,
    }

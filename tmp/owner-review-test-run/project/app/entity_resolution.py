from __future__ import annotations

import difflib
import math
import re
from datetime import datetime, timezone

from .asset_facility_types import source_asset_type_candidates
from .normalization import comparison_title, normalize_arabic, normalize_reference, parse_number


def normalize_owner(value: str | None) -> str:
    """Normalize agency aliases without conflating the source platform with the asset owner."""
    text = normalize_arabic(value)
    text = re.sub(r"\b(امان[هة]|محافظ[هة]|بلدي[هة])\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def lifecycle_status(status: str | None, master_status: str | None = None) -> str:
    """Return a canonical lifecycle label while leaving source status text untouched."""
    value = normalize_arabic(status or master_status)
    if value in {"announced", "منشورة", "published", "متاحة", "available", "active"}:
        return "ACTIVE"
    if value in {"منتهية", "منتهي", "expired", "expired opportunity"}:
        return "EXPIRED"
    if value in {"deleted", "removed from source", "removed_from_source", "أزيلت من المصدر"}:
        return "REMOVED_FROM_SOURCE"
    if value in {"ملغاة", "ملغي", "cancelled", "canceled", "cancel"}:
        return "CANCELLED"
    if value in {"تم الترسية", "مرسى", "awarded", "award"}:
        return "AWARDED"
    if value in {"غير محددة", "unspecified", ""}:
        return "UNSPECIFIED"
    return "UNKNOWN"


def values_equivalent(field: str, left, right) -> bool:
    """Compare canonical values without treating source formatting as a factual conflict."""
    if left == right:
        return True
    if left is None or right is None:
        return False
    if field == "opportunity_owner":
        return normalize_owner(str(left)) == normalize_owner(str(right))
    if field == "status":
        left_status=lifecycle_status(str(left));right_status=lifecycle_status(str(right))
        # An unspecified source value is an absence of evidence, not a competing
        # lifecycle assertion. Unknown evidence remains distinct for review.
        return left_status == right_status or "UNSPECIFIED" in (left_status,right_status)
    if field in {"title_ar", "normalized_title", "short_description", "full_description"}:
        a = re.split(r"\s+-\s*الأنشطة\b", str(left), maxsplit=1)[0]
        b = re.split(r"\s+-\s*الأنشطة\b", str(right), maxsplit=1)[0]
        return _title_similarity(a, b) >= .92
    if field == "reference_number":
        return normalize_reference(str(left)) == normalize_reference(str(right))
    if field in {"land_area_sqm", "latitude", "longitude", "contract_duration_years", "investment_value"}:
        try:
            return abs(float(left) - float(right)) < 1e-6
        except (TypeError, ValueError):
            return False
    return False


def _source_facts(row) -> dict:
    raw = row.raw_data_json or {}
    attrs = raw.get("attributes", {}) if isinstance(raw, dict) else {}
    details = raw.get("details", {}) if isinstance(raw, dict) else {}
    geometry = raw.get("geometry", {}) if isinstance(raw, dict) else {}
    reference = row.source_reference_number
    title = row.source_title or ""
    core_title = re.split(r"\s+-\s*الأنشطة\b", title, maxsplit=1)[0].strip()
    location = " ".join(x for x in (
        row.raw_location,
        str(attrs.get("CITYNAME") or "").strip(),
        str(attrs.get("DISTRICT") or "").strip(),
        str(attrs.get("STREET") or "").strip(),
        str(attrs.get("SUBMUNICIPALITYARNAME") or "").strip(),
    ) if x)
    area = parse_number(row.raw_area)
    furas_months = parse_number(str(attrs.get("DURATION") or ""))
    duration_years = (furas_months / 12) if furas_months is not None else parse_number(details.get("مدة العقد"))
    deadline = (row.raw_dates or {}).get("deadline")
    start_date = attrs.get("STARTDATE")
    published = raw.get("publication_date")
    if not published and start_date:
        try:
            published = datetime.fromtimestamp(float(start_date) / 1000, tz=timezone.utc).date().isoformat()
        except (TypeError, ValueError, OSError):
            published = None
    owner = row.source_owner
    if attrs.get("AMANA"):
        owner = attrs.get("AMANA")
    plot_context = re.search(r"(?:القطع|القطعة|قطعة|للقطع|للقطعة|plot)\s*(?:رقم)?\s*(.*?)(?=\s+(?:لنشاط|بالمخطط|بمدينة|في نشاط)|$)", core_title, re.I)
    plot_text = plot_context.group(0) if plot_context else ""
    plot_tokens = tuple(re.findall(r"\d+\s*(?:/\s*[ء-ي\w]+)?", plot_context.group(1))) if plot_context else ()
    plot_tokens = tuple(re.sub(r"[^0-9ء-ي]", "", normalize_arabic(token)) for token in plot_tokens)
    plan_context = re.search(r"(?:المخطط|مخطط)\s*\(?\s*(?:رقم\s*)?(.*?)(?=\s+(?:بمدينة|بصناعية|لنشاط|في نشاط)|$)", core_title)
    plan_id = "".join(re.findall(r"\d+", plan_context.group(1))) if plan_context else None
    source_key = row.source.source_key if row.source else ""
    asset_values, _ = source_asset_type_candidates(source_key, raw)
    return {
        "source_key": source_key,
        "source_opportunity_id": row.source_opportunity_id,
        "reference": reference,
        "normalized_reference": normalize_reference(reference),
        "title": title,
        "core_title": core_title,
        "location": location,
        "location_norm": normalize_arabic(location),
        "owner": owner or "",
        "owner_norm": normalize_owner(owner),
        "area_sqm": area,
        "duration_years": duration_years,
        "deadline": deadline,
        "publication_date": published,
        "status": row.raw_status,
        "lifecycle_status": lifecycle_status(row.raw_status),
        "activity": details.get("نوع النشاط") or attrs.get("ACTIVITYTYPE") or "",
        "asset_type": " | ".join(asset_values),
        "plot_text": plot_text,
        "plot_tokens": plot_tokens,
        "plan_id": plan_id,
        "latitude": geometry.get("y"),
        "longitude": geometry.get("x"),
        "source_url": row.source_url,
        "raw": raw,
    }


def _title_similarity(a: str, b: str) -> float:
    a = re.split(r"\s+-\s*الأنشطة\b", a, maxsplit=1)[0]
    b = re.split(r"\s+-\s*الأنشطة\b", b, maxsplit=1)[0]
    at = set(comparison_title(a).split())
    bt = set(comparison_title(b).split())
    token = len(at & bt) / len(at | bt) if at and bt else 0.0
    sequence = difflib.SequenceMatcher(None, normalize_arabic(a), normalize_arabic(b)).ratio()
    return round(max(token, sequence), 4)


def _location_similarity(a: dict, b: dict) -> tuple[float, list[str]]:
    an, bn = a["location_norm"], b["location_norm"]
    evidence = []
    if an and bn and an == bn:
        return 1.0, ["same normalized location"]
    # Prefer locality/site names that appear in the other source's title or structured GIS location.
    a_tokens = {t for t in an.split() if t not in {"الاحساء", "احساء", "المنطقه", "الشرقيه"}}
    b_tokens = {t for t in bn.split() if t not in {"الاحساء", "احساء", "المنطقه", "الشرقيه"}}
    at = normalize_arabic(a["title"])
    bt = normalize_arabic(b["title"])
    shared = a_tokens & b_tokens
    if shared:
        evidence.append("shared locality/site tokens: " + ", ".join(sorted(shared)))
    if a_tokens and all(tok in bt for tok in a_tokens):
        return .92, evidence + ["source A locality appears in source B title"]
    if b_tokens and all(tok in at for tok in b_tokens):
        return .92, evidence + ["source B locality appears in source A title"]
    if shared:
        return min(.9, .45 + .45 * len(shared) / max(1, min(len(a_tokens), len(b_tokens)))), evidence
    try:
        if all(a.get(k) is not None and b.get(k) is not None for k in ("latitude", "longitude")):
            lat1, lon1 = math.radians(float(a["latitude"])), math.radians(float(a["longitude"]))
            lat2, lon2 = math.radians(float(b["latitude"])), math.radians(float(b["longitude"]))
            dlat, dlon = lat2-lat1, lon2-lon1
            h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
            meters = 6_371_000 * 2 * math.asin(math.sqrt(h))
            return (1.0 if meters <= 250 else .85 if meters <= 1000 else .5 if meters <= 5000 else .1), [f"coordinates are {meters:.0f} m apart"]
    except (TypeError, ValueError):
        pass
    return 0.0, []


def compare_source_records(left, right) -> dict:
    """Explain a pair without merging it. Missing evidence is left unknown, not treated as a match."""
    a, b = _source_facts(left), _source_facts(right)
    semantic_a=(a["raw"].get("record_semantic_type") or "").strip().upper() if isinstance(a["raw"],dict) else ""
    semantic_b=(b["raw"].get("record_semantic_type") or "").strip().upper() if isinstance(b["raw"],dict) else ""
    semantic_compatible=not semantic_a or not semantic_b or semantic_a==semantic_b
    title = _title_similarity(a["core_title"], b["core_title"])
    location, location_reasons = _location_similarity(a, b)
    if a["area_sqm"] is not None and b["area_sqm"] is not None and max(a["area_sqm"], b["area_sqm"]) > 0:
        area_diff = abs(a["area_sqm"] - b["area_sqm"])
        area_diff_pct = area_diff / max(a["area_sqm"], b["area_sqm"]) * 100
        area_similarity = round(max(0, 1 - area_diff_pct / 100), 4)
    else:
        area_diff = area_diff_pct = area_similarity = None
    exact_ref = bool(a["normalized_reference"] and a["normalized_reference"] == b["normalized_reference"])
    a_plot_numbers = tuple(re.findall(r"\d+", " ".join(a["plot_tokens"])))
    b_plot_numbers = tuple(re.findall(r"\d+", " ".join(b["plot_tokens"])))
    plot_match = bool(a_plot_numbers and b_plot_numbers and a_plot_numbers == b_plot_numbers)
    plan_match = bool(a["plan_id"] and b["plan_id"] and a["plan_id"] == b["plan_id"])
    plot_conflict = bool(a_plot_numbers and b_plot_numbers and a_plot_numbers != b_plot_numbers)
    owner_match = bool(a["owner_norm"] and b["owner_norm"] and a["owner_norm"] == b["owner_norm"])
    duration_match = bool(a["duration_years"] is not None and b["duration_years"] is not None and abs(a["duration_years"]-b["duration_years"]) <= .1)
    deadline_match = bool(a["deadline"] and b["deadline"] and a["deadline"] == b["deadline"])
    title_proxy = title  # Neither current source exposes a distinct, full narrative description.
    weights = {"title_similarity": .35, "location_similarity": .25, "area_similarity": .2,
               "owner_match": .08, "duration_match": .05, "deadline_match": .04, "plot_match": .03}
    values = {"title_similarity": title, "location_similarity": location,
              "area_similarity": area_similarity, "owner_match": float(owner_match),
              "duration_match": float(duration_match), "deadline_match": float(deadline_match),
              "plot_match": float(plot_match or plan_match)}
    used = [(weights[k], float(v)) for k, v in values.items() if v is not None]
    score = sum(w*v for w, v in used) / sum(w for w, _ in used)
    if exact_ref:
        score = max(score, .99)
    positives = []
    contradictions = []
    if exact_ref: positives.append("same normalized official reference")
    if title >= .8: positives.append(f"strong title similarity ({title:.0%})")
    positives.extend(location_reasons)
    if plot_match: positives.append("matching parcel/plot wording")
    if plan_match: positives.append("matching subdivision plan number")
    if area_diff_pct is not None and area_diff_pct <= 2: positives.append(f"area differs by {area_diff_pct:.2f}%")
    elif area_diff_pct is not None and area_diff_pct > 10: contradictions.append(f"area differs by {area_diff_pct:.1f}%")
    if owner_match: positives.append("same normalized owner/municipality")
    if duration_match: positives.append("same contract duration")
    if deadline_match: positives.append("same submission deadline")
    if a["normalized_reference"] and b["normalized_reference"] and a["normalized_reference"] != b["normalized_reference"]:
        # Different platform IDs are not a contradiction when one platform has no propagated reference.
        contradictions.append("source identifiers differ; each belongs to its own platform")
    if plot_conflict:
        contradictions.append("conflicting parcel/plot identifiers")
    owner_conflict = bool(a["owner_norm"] and b["owner_norm"] and a["owner_norm"] != b["owner_norm"])
    if owner_conflict:
        contradictions.append("owner/municipality values differ after normalization")
    if a["area_sqm"] is not None and b["area_sqm"] is not None and area_diff_pct is not None and area_diff_pct <= 2:
        area_compatible = True
    else:
        area_compatible = a["area_sqm"] is None or b["area_sqm"] is None
    # A locality label such as "العيون" is too broad to establish the same site.
    # Require a parcel/plan identity; title plus city/area is not enough.
    strong_site = bool(plot_match or plan_match)
    strong_composite_match = (
        title >= .92 and owner_match and strong_site and not plot_conflict and not owner_conflict and area_compatible
        and (a["duration_years"] is None or b["duration_years"] is None or duration_match)
    )
    auto_merge_safe = exact_ref or (strong_composite_match and score >= .90)
    if not semantic_compatible:
        # Different business entities (for example, a destination and an actual
        # investment offer) must not become fuzzy duplicate candidates.
        score=0.0;auto_merge_safe=False;strong_composite_match=False
    return {
        "source_a": a, "source_b": b,
        "semantic_type_a":semantic_a or None,"semantic_type_b":semantic_b or None,
        "semantic_compatible":semantic_compatible,
        "exact_identifier_match": exact_ref,
        "title_similarity": title,
        "location_similarity": location,
        "location_evidence": location_reasons,
        "area_similarity": area_similarity,
        "area_difference_sqm": area_diff,
        "area_difference_percentage": area_diff_pct,
        "description_similarity": title_proxy,
        "description_similarity_basis": "title proxy; no separate full description exposed",
        "owner_match": owner_match,
        "plot_match": plot_match,
        "plan_match": plan_match,
        "plot_conflict": plot_conflict,
        "duration_match": duration_match,
        "deadline_match": deadline_match,
        "current_duplicate_score": round(score, 4),
        "positive_evidence": positives,
        "contradicting_evidence": contradictions,
        "strong_composite_match": strong_composite_match,
        "auto_merge_safe": auto_merge_safe,
    }

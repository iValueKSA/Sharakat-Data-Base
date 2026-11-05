"""Read-only evidence classification of unlinked Invest Saudi source rows."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select, text

from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity, SourceOpportunityDatasetMembership


GENERIC_TERMS = re.compile(r"\b(?:overview|investment ecosystem|market overview|sector overview|strategic plan|master plan|vision 2030|market report|industry report|investment climate|investment environment)\b|نظرة عامة|منظومة الاستثمار|خطة استراتيجية|الخطة الرئيسية|رؤية 2030|تقرير السوق|مناخ الاستثمار", re.I)
ACTION_TERMS = re.compile(r"\b(?:invest|investment opportunity|establish|develop|build|operate|lease|concession|partner|apply|submit|private sector|investor|investment offering|project opportunity)\b|فرصة استثمارية|استثمر|إنشاء|تطوير|تشغيل|تأجير|امتياز|شريك|التقديم|المستثمر|طرح استثماري", re.I)
EXCLUDED_TERMS = re.compile(r"\b(?:news|press release|event|forum|conference|memorandum of understanding|MOU|statistics|annual report|license|licence)\b|خبر|أخبار|بيان صحفي|ملتقى|مؤتمر|مذكرة تفاهم|إحصاءات|تقرير سنوي|ترخيص", re.I)
ACTIVE_STATUS = re.compile(r"\b(?:active|open|announced|available|accepting applications|published)\b|متاحة|متاح|معلن|مفتوحة|ساري", re.I)
INACTIVE_STATUS = re.compile(r"\b(?:closed|expired|cancelled|canceled|awarded|withdrawn|inactive)\b|منتهية|ملغاة|مرساة|مسحوبة|غير نشطة", re.I)


def clean_url(value):
    value = str(value or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"investsaudi.sa", "www.investsaudi.sa"}:
        return None
    if parsed.path.rstrip("/").casefold() in {"", "/investment-opportunities"}:
        return None
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def classify(row, current_memberships, exact_url_match, exact_reference_matches):
    raw = row.raw_data_json if isinstance(row.raw_data_json, dict) else {}
    title = str(row.source_title or "").strip()
    description = str(raw.get("description") or "").strip()
    combined = f"{title} {description}"
    detail_url = clean_url(row.source_url) or clean_url(raw.get("link"))
    official_id = str(raw.get("official_source_id_original") or "").strip() or None
    dataset = str(raw.get("dataset_name") or "").strip() or None
    family = str(raw.get("source_record_family") or "").strip() or None
    source_status = str(row.raw_status or "").strip()
    reasons = []

    if exact_url_match or exact_reference_matches:
        reasons.append("EXACT_LINKED_SOURCE_EVIDENCE_MATCH")
        category = "D"
    elif not row.source_opportunity_id or not title:
        reasons.append("MISSING_STABLE_ID_OR_TITLE")
        category = "E"
    elif not current_memberships:
        reasons.append("NO_CURRENT_ENDPOINT_MEMBERSHIP")
        category = "E"
    elif source_status and INACTIVE_STATUS.search(source_status):
        reasons.append("SOURCE_STATUS_NOT_ACTIVE")
        category = "E"
    elif GENERIC_TERMS.search(combined) or EXCLUDED_TERMS.search(combined) and not ACTION_TERMS.search(combined):
        reasons.append("GENERIC_OR_PROMOTIONAL_CONTENT_SIGNAL")
        category = "C"
    elif len(description) >= 60 and ACTION_TERMS.search(combined) and official_id:
        reasons.append("SPECIFIC_OFFERING_TEXT_AND_STABLE_SOURCE_ID")
        reasons.append("OFFICIAL_DETAIL_URL_PRESENT" if detail_url else "OFFICIAL_DETAIL_URL_NOT_EXPOSED_IN_RETAINED_RECORD")
        if ACTIVE_STATUS.search(source_status) and detail_url:
            reasons.append("EXPLICIT_ACTIVE_SOURCE_STATUS")
            category = "A"
        else:
            if not source_status:
                reasons.append("RAW_SOURCE_STATUS_MISSING")
            elif not ACTIVE_STATUS.search(source_status):
                reasons.append("SOURCE_STATUS_NOT_EXPLICITLY_ACTIVE")
            if not detail_url:
                reasons.append("OFFICIAL_DETAIL_URL_NOT_EXPOSED_IN_RETAINED_RECORD")
            category = "B"
    else:
        reasons.append("ITEMIZED_RECORD_BUT_INVESTMENT_OFFERING_EVIDENCE_INSUFFICIENT")
        category = "B"

    location = (str(raw.get("location") or "").strip() or str(row.raw_location or "").strip() or None)
    region = str(raw.get("region") or "").strip() or None
    locations = raw.get("opportunity_locations")
    scope_evidence = "EXPLICIT_MULTI_LOCATION_TEXT" if isinstance(locations, list) and len(locations) > 1 else (
        "RAW_LOCATION_AND_REGION_PRESENT" if location and region else "RAW_LOCATION_ONLY" if location else "RAW_REGION_ONLY" if region else "MISSING_GEOGRAPHIC_EVIDENCE")
    coordinates = raw.get("coordinates") or raw.get("Coordinates")
    if isinstance(coordinates, str):
        coordinates = {"raw": coordinates}
    if not isinstance(coordinates, dict):
        coordinates = None
    else:
        coordinates = {key: coordinates.get(key) for key in ("latitude", "longitude") if coordinates.get(key) not in (None, "")}
        if not coordinates:
            coordinates = None

    return {
        "source_opportunity_id": row.id,
        "source_record_key": row.source_opportunity_id,
        "official_source_id_original": official_id,
        "source_record_family": family,
        "dataset_name": dataset,
        "source_detail_url": detail_url,
        "title": title,
        "raw_source_sector": (raw.get("source_taxonomy") or {}).get("sector"),
        "raw_source_subsector": (raw.get("source_taxonomy") or {}).get("subsector"),
        "raw_activity": raw.get("activity"),
        "raw_sub_activity": raw.get("subActivity"),
        "raw_opportunity_type": raw.get("opportunity_type"),
        "investment_offering_evidence": description[:700] or None,
        "raw_source_status": row.raw_status,
        "canonical_source_status": row.canonical_status,
        "current_dataset_memberships": sorted(current_memberships),
        "raw_location": location,
        "raw_region": region,
        "geographic_scope_assessment": scope_evidence,
        "coordinates": coordinates,
        "existing_master_match": ("EXACT_OFFICIAL_URL" if exact_url_match else "EXACT_SOURCE_REFERENCE" if exact_reference_matches else None),
        "existing_master_match_ids": sorted(set(exact_reference_matches)),
        "category": category,
        "category_label": {"A":"LEGITIMATE_CANDIDATE","B":"POTENTIAL_NEEDS_EVIDENCE","C":"GENERIC_OR_PROMOTIONAL","D":"EXACT_EXISTING_MASTER_MATCH","E":"UNSUPPORTED_INVALID_OR_NONQUALIFYING"}[category],
        "evidence_codes": reasons,
        "duplicate_risk": "EXACT_MATCH" if exact_url_match or exact_reference_matches else "TITLE_SIMILARITY_NOT_TREATED_AS_DUPLICATE",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    generated = datetime.now(timezone.utc).isoformat()
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        source = db.scalar(select(Source).where(Source.source_key == "invest-saudi"))
        if not source:
            raise SystemExit("Invest Saudi source not found")
        all_rows = db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id == source.id).order_by(SourceOpportunity.id)).all()
        unlinked = [row for row in all_rows if row.master_opportunity_id is None]
        memberships = defaultdict(set)
        for membership in db.scalars(select(SourceOpportunityDatasetMembership).join(SourceOpportunity).where(
                SourceOpportunity.source_id == source.id, SourceOpportunityDatasetMembership.is_current.is_(True))).all():
            memberships[membership.source_opportunity_id].add(membership.dataset_name)

        linked = db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id.is_not(None))).all()
        linked_urls = defaultdict(set)
        linked_refs = defaultdict(set)
        for row in linked:
            url = clean_url(row.source_url)
            if url:
                linked_urls[url].add(row.master_opportunity_id)
            ref = str(row.source_reference_number_normalized or "").strip().casefold()
            if ref:
                linked_refs[ref].add(row.master_opportunity_id)

        reviewed = []
        for row in unlinked:
            raw = row.raw_data_json if isinstance(row.raw_data_json, dict) else {}
            url = clean_url(row.source_url) or clean_url(raw.get("link"))
            ref = str(row.source_reference_number_normalized or "").strip().casefold()
            exact_refs = linked_refs.get(ref, set()) if ref else set()
            reviewed.append(classify(row, memberships.get(row.id, set()), bool(url and linked_urls.get(url)), exact_refs))

        category_counts = Counter(item["category"] for item in reviewed)
        title_collision = Counter(row.normalized_source_title for row in unlinked if row.normalized_source_title)
        report = {
            "report": "INVEST_SAUDI_NATIONAL_ELIGIBILITY_DRY_RUN",
            "generated_at_utc": generated,
            "read_only": True,
            "source_key": source.source_key,
            "source_record_total": len(all_rows),
            "unlinked_records_assessed": len(unlinked),
            "linked_records_retained": sum(1 for row in all_rows if row.master_opportunity_id is not None),
            "categories": {
                "A_legitimate_candidates": category_counts["A"],
                "B_ambiguous_needing_evidence": category_counts["B"],
                "C_generic_or_promotional": category_counts["C"],
                "D_exact_existing_master_matches": category_counts["D"],
                "E_unsupported_invalid_or_nonqualifying": category_counts["E"],
            },
            "current_endpoint_membership_missing": sum(1 for row in unlinked if not memberships.get(row.id)),
            "missing_geographic_evidence": sum(1 for item in reviewed if item["geographic_scope_assessment"] == "MISSING_GEOGRAPHIC_EVIDENCE"),
            "explicit_coordinates_in_source_payload": sum(1 for item in reviewed if item["coordinates"]),
            "exact_official_url_duplicate_risks": sum(1 for item in reviewed if item["existing_master_match"] == "EXACT_OFFICIAL_URL"),
            "exact_source_reference_duplicate_risks": sum(1 for item in reviewed if item["existing_master_match"] == "EXACT_SOURCE_REFERENCE"),
            "repeated_title_groups_not_deduplicated": sum(1 for count in title_collision.values() if count > 1),
            "proposed_safe_promotion_batches": [],
            "promotions_executed": 0,
            "source_sync_started": False,
            "business_data_changed": 0,
            "review_data_changed": 0,
            "records": reviewed,
            "methodology": [
                "A source API row, its dataset membership, or its internal numeric ID does not alone establish an investable opportunity.",
                "Only exact linked URL/reference evidence is called a duplicate; title similarity remains a review risk.",
                "No regional/city aliases or scope were inferred from an owner or publisher address.",
                "Rows without explicit status or a verified administrative hierarchy are not promoted by this dry-run.",
            ],
        }
        db.rollback()
    text_out=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:
        args.output.write_text(text_out+"\n",encoding="utf-8")
    else:
        print(text_out)


if __name__ == "__main__":
    main()

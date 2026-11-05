"""Promote only pre-adjudicated unique NCP portal records to Master rows.

The JSON comparison is the allow-list. The transaction rechecks every portal UUID,
source-only link state, and identity-review evidence before applying any changes.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.adapters import normalize_arabic
from app.models import FieldProvenance, Opportunity, Source, SourceOpportunity, SystemEvent


ARTIFACT = Path("docs/validation/deployment/nationwide-source-expansion/NCP-INVESTORS-PORTAL-COMPARISON-DRY-RUN-20261103.json")
ELIGIBLE_CATEGORY = "C_NEW_UNIQUE_NCP_OPPORTUNITY"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_allowlist(path: Path) -> tuple[dict, list[dict]]:
    comparison = json.loads(path.read_text(encoding="utf-8"))
    projection = comparison["projection"]
    required_zeroes = (
        "projected_duplicate_masters",
        "projected_broken_ncp_links",
        "projected_invalid_source_duplication",
        "projected_dq_fail",
        "bootstrap_removals",
    )
    if any(projection.get(key) != 0 for key in required_zeroes):
        raise RuntimeError("The dry-run promotion gates are not all zero.")
    if comparison.get("relationship") != "PARTIAL_OVERLAP_WITH_ADDITIONAL_UNIQUE_RECORDS":
        raise RuntimeError("The comparison does not authorize same-source unique-record promotion.")
    if comparison.get("architecture_recommendation") != "SAME_SOURCE_ENRICHMENT":
        raise RuntimeError("Unexpected NCP architecture decision.")
    if not comparison["portal_enumeration"].get("enumeration_complete"):
        raise RuntimeError("The public NCP portal enumeration is incomplete.")
    eligible = [row for row in comparison["records"] if row["category"] == ELIGIBLE_CATEGORY]
    if len(eligible) != projection["high_confidence_new_master_candidates"]:
        raise RuntimeError("The eligible record count disagrees with the dry-run projection.")
    for row in eligible:
        evidence = row.get("identity_evidence") or {}
        if (row.get("confidence", 0) < 0.90 or row.get("review_required")
                or evidence.get("exact_provider_id_match")
                or evidence.get("exact_reference_match")
                or evidence.get("project_identity_candidate_count_across_current_source_rows_and_masters") != 0
                or row.get("stage", {}).get("parent_en") == "Closed Transaction"):
            raise RuntimeError(f"Dry-run evidence no longer qualifies UUID {row['portal_provider_id']}.")
    return comparison, eligible


def detail_from_source(record: SourceOpportunity, provider_id: str) -> dict:
    raw = record.raw_data_json or {}
    portal = raw.get("ncp_portal_record") or {}
    if raw.get("provider_id") != provider_id or portal.get("provider_id") != provider_id:
        raise RuntimeError(f"Source row identity does not match public UUID {provider_id}.")
    detail = portal.get("detail") or {}
    if str(detail.get("id") or "") != provider_id:
        raise RuntimeError(f"Stored detail identity does not match public UUID {provider_id}.")
    return detail


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Commit the allow-listed NCP Master promotions.")
    parser.add_argument("--artifact", type=Path, default=ARTIFACT)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    comparison, eligible = load_allowlist(args.artifact)
    engine = create_engine(database_url, pool_pre_ping=True)
    now = utcnow()
    created: list[dict] = []
    already: list[dict] = []
    with Session(engine) as db, db.begin():
        source = db.scalar(select(Source).where(Source.source_key == "ncp"))
        if source is None:
            raise RuntimeError("Configured NCP source is missing.")
        for item in eligible:
            provider_id = item["portal_provider_id"]
            external_id = f"ncp-portal:{provider_id}"
            record = db.scalar(select(SourceOpportunity).where(
                SourceOpportunity.source_id == source.id,
                SourceOpportunity.source_opportunity_id == external_id,
            ).with_for_update())
            if record is None:
                raise RuntimeError(f"NCP source row is missing for public UUID {provider_id}.")
            detail = detail_from_source(record, provider_id)
            prior_event = db.scalar(select(SystemEvent).where(
                SystemEvent.event_type == "NCP_NATIONAL_MASTER_PROMOTION",
                SystemEvent.payload["portal_provider_id"].as_string() == provider_id,
            ).order_by(SystemEvent.id.desc()).limit(1))
            if record.master_opportunity_id is not None:
                if prior_event and prior_event.payload.get("master_id") == record.master_opportunity_id:
                    if args.apply:
                        from app.service import apply_sector_phase2_after_ingestion
                        existing_master = db.get(Opportunity, record.master_opportunity_id)
                        if existing_master is None:
                            raise RuntimeError(f"UUID {provider_id} links to a missing Master.")
                        if existing_master.sector in (None, "غير محدد", "غير محددة"):
                            apply_sector_phase2_after_ingestion(db, existing_master, source=source,
                                source_record=record, detected_at=now)
                            db.flush()
                        if existing_master.sector in (None, "غير محدد", "غير محددة"):
                            raise RuntimeError(f"Governed sector classification did not resolve UUID {provider_id}.")
                    already.append({"portal_provider_id": provider_id, "master_id": record.master_opportunity_id})
                    continue
                raise RuntimeError(f"UUID {provider_id} already has an unapproved Master link.")
            if prior_event:
                raise RuntimeError(f"UUID {provider_id} has a promotion audit but no matching source link.")
            # Stable portal UUID is the canonical tie-breaker; no location, status,
            # deadline, coordinate, sector, or model is guessed into the Master.
            canonical_id = f"NCP-{provider_id}"
            collision = db.scalar(select(Opportunity).where(Opportunity.canonical_id == canonical_id))
            if collision:
                raise RuntimeError(f"Canonical ID collision for portal UUID {provider_id}.")
            title_ar = str(detail.get("nameAr") or record.source_title or detail.get("nameEn") or "").strip()
            title_en = str(detail.get("nameEn") or "").strip() or None
            owner_ar = str(detail.get("projectOwnerNameAr") or "").strip()
            owner_en = str(detail.get("projectOwnerNameEn") or "").strip()
            owner = owner_ar or owner_en or None
            description_ar = str(detail.get("projectDescriptionAr") or "").strip()
            description_en = str(detail.get("projectDescriptionEn") or "").strip()
            descriptions = [value for value in (description_ar, description_en) if value]
            location = str(detail.get("locationNameAr") or detail.get("locationNameEn") or detail.get("locationDescription") or "").strip()
            full_description = "\n\n".join(descriptions) or None
            master = Opportunity(
                canonical_id=canonical_id,
                title_ar=title_ar,
                title_en=title_en,
                normalized_title=normalize_arabic(title_ar or title_en),
                opportunity_owner=owner,
                primary_publication_platform=source.source_name_ar,
                opportunity_type="PPP_PROJECT",
                city="غير محدد",
                location_description=location or None,
                location_confidence_score=0.0,
                location_detection_method="NCP_PORTAL_LOCATION_UNMAPPED",
                location_evidence=("Public NCP Investors Portal location text retained as raw evidence; "
                                   "administrative geography was not assigned." + (f" Source: {location}" if location else "")),
                geographic_scope="UNSPECIFIED",
                geography_evidence_json={
                    "scope_basis": "NCP public portal national catalogue; record-level administrative geography not adjudicated",
                    "source_url": record.source_url,
                    "raw_location": location or None,
                    "canonical_region_assigned": False,
                    "coordinates_fabricated": False,
                },
                status="حالة غير معروفة",
                short_description=(description_ar or description_en or None),
                full_description=full_description,
                data_quality_score=0.0,
                manual_review_required=True,
                first_seen_at=now,
                last_seen_at=now,
                last_updated_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(master)
            db.flush()
            record.master_opportunity_id = master.id
            record.raw_data_json = {
                **(record.raw_data_json or {}),
                "ncp_master_promotion": {
                    "action": "NEW_MASTER",
                    "comparison_artifact": str(args.artifact).replace("\\", "/"),
                    "category": item["category"],
                    "confidence": item["confidence"],
                    "provider_id": provider_id,
                    "promoted_at_utc": now.isoformat(),
                    "status_deadline_geography_inference": False,
                },
            }
            for field, value in (("title_ar", title_ar), ("title_en", title_en),
                                 ("opportunity_owner", owner), ("location_description", location or None),
                                 ("full_description", full_description)):
                if value is not None:
                    db.add(FieldProvenance(opportunity_id=master.id, field_name=field,
                        selected_value=value, source_id=source.id, source_record_id=record.id,
                        captured_at=now, confidence=min(float(item["confidence"]), 0.95)))
            audit_payload = {
                "action": "NEW_MASTER",
                "portal_provider_id": provider_id,
                "source_key": "ncp",
                "source_opportunity_id": record.id,
                "master_id": master.id,
                "canonical_id": canonical_id,
                "comparison_artifact": str(args.artifact).replace("\\", "/"),
                "comparison_category": item["category"],
                "identity_evidence": item["identity_evidence"],
                "confidence": item["confidence"],
                "review_required": False,
                "geography_assigned": False,
                "status_inferred": False,
                "deadline_inferred": False,
                "owner_basis": "explicit portal projectOwnerName" if owner else "unspecified",
            }
            db.add(SystemEvent(event_type="NCP_NATIONAL_MASTER_PROMOTION", payload=audit_payload, created_at=now))
            from app.service import apply_sector_phase2_after_ingestion
            db.flush()
            apply_sector_phase2_after_ingestion(db, master, source=source, source_record=record, detected_at=now)
            db.flush()
            if master.sector in (None, "غير محدد", "غير محددة"):
                raise RuntimeError(f"Governed sector classification did not resolve UUID {provider_id}.")
            created.append({"portal_provider_id": provider_id, "source_opportunity_id": record.id,
                            "master_id": master.id, "canonical_id": canonical_id})
        if args.apply:
            db.flush()
        else:
            db.rollback()
    print(json.dumps({"mode": "APPLY" if args.apply else "DRY_RUN", "comparison_records": len(comparison["records"]),
        "eligible_new_masters": len(eligible), "created": created, "already_promoted": already,
        "committed": bool(args.apply)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

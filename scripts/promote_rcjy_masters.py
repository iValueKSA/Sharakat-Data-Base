"""Audited one-time promotion of RCJY records approved by the identity dry-run."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Opportunity, Source, SourceOpportunity, GeographicReferenceUnit
from app.adapters import normalize_sector
from app.standardization import canonical_id as sector_canonical_id
from app.normalization import normalize_arabic
from app.security import audit
from app.service import apply_sector_phase2_after_ingestion


DISPOSITIONS = {
    "A_READY_NEW_MASTER", "B_MATCH_EXISTING_MASTER", "C_IDENTITY_REVIEW",
    "D_NOT_QUALIFYING", "E_HISTORICAL_OR_NONCURRENT", "F_SAME_SOURCE_DUPLICATE_REVIEW",
}


def promote_approved_rcjy_rows(db: Session, dry_run: dict, *, apply: bool = False) -> dict:
    """Promote only current, high-confidence A rows with exact reference geography."""
    source = db.scalar(select(Source).where(Source.source_key == "rcjy-investment-opportunities"))
    if source is None:
        raise RuntimeError("RCJY source is not registered")
    approvals = dry_run.get("records") or []
    by_id = {}
    for item in approvals:
        provider_id = str(item.get("provider_id") or "")
        if not provider_id or provider_id in by_id or item.get("disposition") not in DISPOSITIONS:
            raise RuntimeError("Dry-run has a missing/duplicate provider ID or invalid disposition")
        by_id[provider_id] = item
    rows = db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id == source.id)
                      .options(selectinload(SourceOpportunity.opportunity_locations))
                      .order_by(SourceOpportunity.source_opportunity_id)).all()
    if set(by_id) != {row.source_opportunity_id for row in rows}:
        raise RuntimeError("Dry-run provider IDs do not exactly reconcile to the captured RCJY rows")

    actions = []
    for row in rows:
        approval = by_id[row.source_opportunity_id]
        raw = row.raw_data_json or {}
        if approval["disposition"] != "A_READY_NEW_MASTER":
            actions.append({"provider_id": row.source_opportunity_id, "action": "NO_PROMOTION",
                            "disposition": approval["disposition"]})
            continue
        if float(approval.get("confidence") or 0) < .90:
            raise RuntimeError(f"RCJY record {row.source_opportunity_id} is below the .90 promotion threshold")
        if raw.get("source_lifecycle_classification") != "CURRENT":
            raise RuntimeError(f"RCJY record {row.source_opportunity_id} is not explicitly current")
        matches = [place for place in row.opportunity_locations
                   if place.geography_reference_unit_id and
                   (place.source_evidence_json or {}).get("verification_method") == "EXACT_CURRENT_REFERENCE_NAME_OR_ALIAS"]
        if len(matches) != 1:
            raise RuntimeError(f"RCJY record {row.source_opportunity_id} lacks unique exact-reference geography")
        place = matches[0]
        unit = db.get(GeographicReferenceUnit, place.geography_reference_unit_id)
        if not unit or unit.level not in {"city", "governorate"}:
            raise RuntimeError(f"RCJY record {row.source_opportunity_id} has unsupported geography")
        existing = row.master_opportunity_id
        if existing is not None:
            master = db.get(Opportunity, existing)
            raw_sector=(raw.get("source_taxonomy") or {}).get("sector")
            canonical_source_sector=normalize_sector(raw_sector) if raw_sector else None
            if master and (sector_canonical_id("sector", master.sector) == "sector:unspecified"
                           or (canonical_source_sector and master.sector != canonical_source_sector)):
                master.sector = "غير محدد"
                apply_sector_phase2_after_ingestion(db, master, source=source, source_record=row, detected_at=datetime.now(timezone.utc))
                db.flush()
                action = "SECTOR_PIPELINE_APPLIED_TO_EXISTING_LINK"
            else:
                action = "ALREADY_LINKED"
            actions.append({"provider_id": row.source_opportunity_id, "action": action,
                            "master_id": existing})
            continue
        title = row.source_title
        now = datetime.now(timezone.utc)
        region = db.get(GeographicReferenceUnit, unit.parent_id) if unit.parent_id else None
        geo_evidence = {
            "verification_method": "EXACT_CURRENT_REFERENCE_NAME_OR_ALIAS",
            "dataset_id": unit.dataset_id,
            "reference_unit_id": unit.id,
            "reference_level": unit.level,
            "reference_external_id": unit.external_id,
            "reference_name_ar": unit.name_ar,
            "reference_name_en": unit.name_en,
            "parent_region_external_id": region.external_id if region and region.level == "region" else None,
            "parent_region_name_ar": region.name_ar if region and region.level == "region" else None,
            "source_location_text": place.source_location_text,
            "source_url": row.source_url,
        }
        raw_sector=(raw.get("source_taxonomy") or {}).get("sector")
        master = Opportunity(
            canonical_id=f"RCJY-{row.source_opportunity_id}",
            title_ar=title,
            title_en=raw.get("title_en"),
            normalized_title=normalize_arabic(title),
            reference_number=None,
            reference_number_normalized=None,
            opportunity_owner=None,
            primary_publication_platform=source.source_name_ar,
            city="غير محدد",
            location_description=raw.get("industrial_city") or place.source_location_text,
            sector="غير محدد",
            activity=raw_sector,
            sub_activity=(raw.get("source_taxonomy") or {}).get("subsector"),
            status="غير محددة",
            short_description=None,
            full_description=None,
            latitude=None,
            longitude=None,
            land_area_sqm=None,
            location_confidence_score=1.0,
            location_detection_method="EXACT_CURRENT_REFERENCE_NAME_OR_ALIAS",
            location_evidence=f"RCJY public catalog location exactly matched {unit.level} reference {unit.external_id}.",
            geographic_scope="SPECIFIC_LOCATION",
            geography_reference_unit_id=unit.id,
            geography_evidence_json=geo_evidence,
            coordinate_provenance_json=None,
            data_quality_score=.75,
            manual_review_required=True,
            first_seen_at=row.first_seen_at or now,
            last_seen_at=row.last_seen_at or now,
            last_updated_at=now,
            created_at=now,
            updated_at=now,
        )
        if apply:
            db.add(master)
            db.flush()
            row.master_opportunity_id = master.id
            apply_sector_phase2_after_ingestion(db, master, source=source, source_record=row, detected_at=now)
            db.flush()
            audit(db, "RCJY_MASTER_CREATED", entity_type="opportunity", entity_id=str(master.id),
                  before=None, after={"master_id": master.id, "source_record_id": row.id,
                      "provider_id": row.source_opportunity_id, "canonical_id": master.canonical_id,
                      "action": "CREATE_AND_LINK", "identity_evidence": approval.get("identity_evidence"),
                      "confidence": approval.get("confidence"), "geography_evidence": geo_evidence})
            master_id = master.id
        else:
            master_id = None
        actions.append({"provider_id": row.source_opportunity_id,
                        "action": "CREATE_AND_LINK" if apply else "WOULD_CREATE_AND_LINK",
                        "master_id": master_id, "source_record_id": row.id,
                        "geography_reference_unit_id": unit.id})
    if apply:
        db.flush()
    return {"apply": apply, "records_reconciled": len(rows), "actions": actions}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from app.database import SessionLocal
    plan = json.loads(args.dry_run.read_text(encoding="utf-8"))
    with SessionLocal.begin() as db:
        result = promote_approved_rcjy_rows(db, plan, apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

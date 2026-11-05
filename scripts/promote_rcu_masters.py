"""Audited one-time promotion of RCU rows approved by the eligibility dry-run."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import GeographicReferenceUnit, Opportunity, Source, SourceOpportunity
from app.normalization import normalize_arabic
from app.security import audit
from app.status_lifecycle import parse_deadline
from app.service import normalize_reference


def promote_approved_rcu_rows(db: Session, dry_run: dict, *, apply: bool = False) -> dict:
    source=db.scalar(select(Source).where(Source.source_key=="rcu-investment-opportunities"))
    if source is None: raise RuntimeError("RCU source is not registered")
    plans={}
    for item in dry_run.get("records") or []:
        provider_id=str(item.get("provider_id") or "")
        if not provider_id or provider_id in plans:
            raise RuntimeError("RCU dry-run has a missing or duplicate provider UUID")
        plans[provider_id]=item
    rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id)
        .options(selectinload(SourceOpportunity.opportunity_locations)).order_by(SourceOpportunity.source_opportunity_id)).all()
    if set(plans)!={row.source_opportunity_id for row in rows}:
        raise RuntimeError("RCU dry-run provider IDs do not exactly reconcile to live source rows")
    if len({row.source_opportunity_id for row in rows})!=len(rows):
        raise RuntimeError("Duplicate RCU provider keys block promotion")

    actions=[]
    for row in rows:
        plan=plans[row.source_opportunity_id]
        if plan.get("disposition")!="A_READY_NEW_MASTER":
            actions.append({"provider_id":row.source_opportunity_id,"source_opportunity_id":row.id,
                "action":"NO_ACTION","disposition":plan.get("disposition")})
            continue
        if float(plan.get("confidence") or 0)<.90 or plan.get("review_required"):
            raise RuntimeError(f"RCU row {row.source_opportunity_id} is not approved at high confidence")
        raw=row.raw_data_json or {}; lifecycle=raw.get("lifecycle_evidence") or {}
        if lifecycle.get("isClosed") is not False or lifecycle.get("isApplicable") is False:
            raise RuntimeError(f"RCU row {row.source_opportunity_id} lacks explicit current/applicable evidence")
        if raw.get("provider_id")!=row.source_opportunity_id or raw.get("provider")!="RCU":
            raise RuntimeError(f"RCU row {row.source_opportunity_id} has inconsistent provider identity evidence")
        geo_places=[p for p in row.opportunity_locations if p.geography_reference_unit_id and
            (p.source_evidence_json or {}).get("verification_method")=="EXACT_CURRENT_REFERENCE_NAME_OR_ALIAS"]
        if len(geo_places)!=1:
            raise RuntimeError(f"RCU row {row.source_opportunity_id} does not have unique exact AlUla geography")
        unit=db.get(GeographicReferenceUnit,geo_places[0].geography_reference_unit_id)
        if not unit or unit.level!="governorate" or unit.external_id!="302" or unit.name_ar!="العلا":
            raise RuntimeError(f"RCU row {row.source_opportunity_id} is not mapped to AlUla Governorate")
        normalized_ref=normalize_reference(row.source_reference_number)
        if normalized_ref and db.scalar(select(Opportunity.id).where(Opportunity.merged_into_id.is_(None),
                Opportunity.reference_number_normalized==normalized_ref).limit(1)):
            raise RuntimeError(f"RCU display reference {row.source_reference_number} now collides with a Master")
        if row.master_opportunity_id is not None:
            raise RuntimeError(f"RCU row {row.source_opportunity_id} was already linked; dry-run is stale")
        for existing in db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None),
                Opportunity.canonical_id==f"RCU-{row.source_reference_number}")):
            raise RuntimeError(f"RCU canonical ID RCU-{row.source_reference_number} already exists")

        now=datetime.now(timezone.utc)
        description_ar=raw.get("descriptionAR") or ""
        description_en=raw.get("descriptionEN") or ""
        unique_coordinate_count=(dry_run.get("enumeration",{}).get("coordinate_pair_frequencies") or {}).get(
            f"{raw.get('latitude')},{raw.get('longitude')}",0)
        # Coordinates are retained verbatim in raw evidence but not projected to a Master.
        # RCU uses repeated map points for multiple unrelated facilities, and this task did not
        # establish object-level precision from an independent location feature.
        raw_deadline=raw.get("submissionDeadline")
        parsed_deadline=parse_deadline(raw_deadline)
        master=Opportunity(
            canonical_id=f"RCU-{row.source_reference_number}",title_ar=row.source_title,
            title_en=raw.get("titleEN"),normalized_title=normalize_arabic(row.source_title or ""),
            reference_number=row.source_reference_number,reference_number_normalized=normalized_ref,
            opportunity_owner=None,primary_publication_platform=source.source_name_ar,
            city="غير محدد",location_description="العلا",sector=None,
            activity=None,opportunity_type="PPP_PROJECT" if "PPP" in str(raw.get("titleEN") or "").upper() else None,
            investment_model=None,publication_date=raw.get("publishDate"),
            submission_deadline=parsed_deadline.isoformat() if parsed_deadline else None,status="غير محددة",
            short_description=description_ar or None,full_description=description_ar or description_en or None,
            latitude=None,longitude=None,land_area_sqm=None,
            location_confidence_score=.95,location_detection_method="EXPLICIT_PUBLIC_PROJECT_TEXT_AND_CANONICAL_GOVERNORATE",
            location_evidence="RCU opportunity title/description explicitly identifies AlUla; exact Arabic place name maps to the AlUla governorate reference.",
            geographic_scope="SPECIFIC_LOCATION",geography_reference_unit_id=unit.id,
            geography_evidence_json={"verification_method":"EXPLICIT_PROJECT_TEXT_EXACT_GOVERNORATE_REFERENCE",
                "dataset_id":unit.dataset_id,"reference_unit_id":unit.id,"reference_level":unit.level,
                "reference_external_id":unit.external_id,"reference_name_ar":unit.name_ar,"reference_name_en":unit.name_en,
                "source_text_evidence":raw.get("source_geography_evidence"),"source_url":raw.get("source_url")},
            coordinate_provenance_json=None,data_quality_score=.75,manual_review_required=True,
            first_seen_at=row.first_seen_at or now,last_seen_at=row.last_seen_at or now,
            last_updated_at=now,created_at=now,updated_at=now)
        if apply:
            db.add(master);db.flush();row.master_opportunity_id=master.id;db.flush()
            audit(db,"RCU_MASTER_CREATED",entity_type="opportunity",entity_id=str(master.id),before=None,
                after={"master_id":master.id,"source_opportunity_id":row.id,"provider_id":row.source_opportunity_id,
                    "display_reference":row.source_reference_number,"action":"CREATE_AND_LINK",
                    "identity_evidence":plan.get("identity_evidence"),"confidence":plan.get("confidence"),
                    "geography_evidence":master.geography_evidence_json,"coordinate_source_values_retained_only":True,
                    "coordinate_pair_frequency":unique_coordinate_count},
                metadata={"actor":"controlled_rcu_integration","trigger":"manual_wave1_integration"})
            master_id=master.id
        else: master_id=None
        actions.append({"provider_id":row.source_opportunity_id,"display_reference":row.source_reference_number,
            "source_opportunity_id":row.id,"action":"CREATE_AND_LINK" if apply else "WOULD_CREATE_AND_LINK",
            "master_id":master_id,"geography_reference_unit_id":unit.id,"coordinates_projected":False})
    if apply: db.flush()
    return {"apply":apply,"records_reconciled":len(rows),"actions":actions}

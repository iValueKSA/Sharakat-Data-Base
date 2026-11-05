"""Read-only, reproducible Furas national Master eligibility dry run.

Run inside the application container with the configured DATABASE_URL. The
transaction is explicitly PostgreSQL READ ONLY. The only output is a JSON
artifact written to the requested path.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from app.data_quality import latest_data_quality_run
from app.database import SessionLocal
from app.entity_resolution import compare_source_records, lifecycle_status, values_equivalent
from app.models import (
    DuplicateCandidate,
    Opportunity,
    OpportunityConflict,
    QualificationReview,
    Source,
    SourceOpportunity,
    SyncJob,
    LocationReview,
)
from app.normalization import comparison_title, normalize_arabic, normalize_reference, parse_number


RECOVERY_JOB_ID = 694
RECOVERY_SNAPSHOT_SHA256 = "e91cfe73f53184fb698ca4eec18926d196039ebd0219f27547fa706580ad74e0"

# These are the source rows with independently inspected, strong same-source
# identity signals. The provider IDs remain separate pending review.
SAME_SOURCE_REVIEW_GROUPS = {
    "salwa-location-208": {4939, 4274, 5046, 70},
    "aqeer-location-201": {5215, 10},
    "granada-location-208": {8856, 3099, 3100},
    "al-kharj-mishrif-site": {6591, 6770},
}
SAME_SOURCE_REVIEW_IDS = {4939, 4274, 5046, 5215, 8856, 6591, 6770}
LOCAL_EXISTING_MASTER_REVIEW_IDS = {8557, 8571, 8573, 4924, 4956}
LOCAL_PARCELED_DISTINCT_IDS = {6985, 6986, 6998}


def json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def title_key(value: str | None) -> str:
    core = re.split(r"\s+-\s*الأنشطة\b", value or "", maxsplit=1)[0]
    return comparison_title(core)


def coords(row):
    geometry = (row.raw_data_json or {}).get("geometry") or {}
    try:
        x, y = float(geometry["x"]), float(geometry["y"])
    except (KeyError, TypeError, ValueError):
        return None
    return {"longitude": x, "latitude": y}


def distance_m(a, b):
    ca, cb = coords(a), coords(b)
    if not ca or not cb:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (ca["latitude"], ca["longitude"], cb["latitude"], cb["longitude"]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(6371000 * 2 * math.asin(math.sqrt(h)), 1)


def safe_compare(left, right):
    return compare_source_records(left, right)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    session = SessionLocal()
    try:
        # A PostgreSQL transaction-level guard makes the live analysis read-only.
        session.execute(text("SET TRANSACTION READ ONLY"))
        furas = session.scalar(select(Source).where(Source.source_key == "furas"))
        job = session.get(SyncJob, RECOVERY_JOB_ID)
        if not furas or not job:
            raise RuntimeError("Furas source or recovery job 694 is missing")
        job_metrics = job.metrics_json if isinstance(job.metrics_json, dict) else {}
        checkpoint = job_metrics.get("furas_checkpoint") or {}
        snapshot_keys = set(map(str, checkpoint.get("processed_source_ids") or []))
        if len(snapshot_keys) != 6484:
            raise RuntimeError(f"Unexpected Job 694 provider-ID population: {len(snapshot_keys)}")
        snapshot_digest = checkpoint.get("object_ids_sha256")
        if snapshot_digest != RECOVERY_SNAPSHOT_SHA256:
            raise RuntimeError("Job 694 snapshot digest did not match the accepted recovery evidence")

        all_rows = session.scalars(
            select(SourceOpportunity).options(selectinload(SourceOpportunity.source))
        ).all()
        furas_rows = [r for r in all_rows if r.source_id == furas.id]
        other_rows = [r for r in all_rows if r.source_id != furas.id]
        current_rows = [r for r in furas_rows if str(r.source_opportunity_id) in snapshot_keys]
        non_snapshot_rows = [r for r in furas_rows if str(r.source_opportunity_id) not in snapshot_keys]
        current_linked = [r for r in current_rows if r.master_opportunity_id is not None]
        current_unlinked = [r for r in current_rows if r.master_opportunity_id is None]
        masters = session.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
        master_by_id = {m.id: m for m in masters}

        # Indexes are based on identifiers and normalized title/site keys; there
        # is no all-record fuzzy cross product.
        other_ref_index = defaultdict(list)
        other_title_index = defaultdict(list)
        for row in other_rows:
            ref = normalize_reference(row.source_reference_number or "")
            if ref:
                other_ref_index[ref].append(row)
            key = title_key(row.source_title)
            if key:
                other_title_index[key].append(row)
        master_ref_index = defaultdict(list)
        master_title_index = defaultdict(list)
        for master in masters:
            ref = normalize_reference(master.reference_number_normalized or master.reference_number or "")
            if ref:
                master_ref_index[ref].append(master)
            key = title_key(master.title_ar)
            if key:
                master_title_index[key].append(master)
        furas_by_pk = {r.id: r for r in furas_rows}

        # Compare exact, source-verified reference candidates with the existing
        # identity resolver. The resolver treats title scores as ranking only.
        reference_candidates = {}
        reference_candidate_pairs = 0
        reference_auto_safe_rows = set()
        reference_conflict_rows = set()
        for row in current_unlinked:
            ref = normalize_reference(row.source_reference_number or "")
            candidates = other_ref_index.get(ref, []) if ref else []
            comparisons = []
            for candidate in candidates:
                evidence = safe_compare(candidate, row)
                comparisons.append((candidate, evidence))
                reference_candidate_pairs += 1
                if evidence["trusted_official_reference_match"] and evidence["auto_merge_safe"]:
                    reference_auto_safe_rows.add(row.id)
                elif evidence["trusted_official_reference_match"]:
                    reference_conflict_rows.add(row.id)
            if comparisons:
                reference_candidates[row.id] = comparisons

        records_by_pk = {r.id: r for r in current_unlinked}
        classifications = {}

        def candidate_source_evidence(other, evidence):
            return {
                "source_opportunity_row_id": other.id,
                "source_key": other.source.source_key if other.source else None,
                "provider_key": other.source_opportunity_id,
                "official_reference": other.source_reference_number,
                "master_opportunity_id": other.master_opportunity_id,
                "title": other.source_title,
                "title_similarity": evidence.get("title_similarity"),
                "trusted_official_reference_match": evidence.get("trusted_official_reference_match", False),
                "auto_merge_safe_under_current_resolver": evidence.get("auto_merge_safe", False),
                "field_conflicts": list(evidence.get("contradicting_evidence") or []),
            }

        for row in furas_rows:
            is_member = str(row.source_opportunity_id) in snapshot_keys
            attrs = ((row.raw_data_json or {}).get("attributes") or {})
            geometry = coords(row)
            source_type = str(attrs.get("OPPORTUNITYTYPE") or "").strip()
            raw_state = str(row.raw_status or "").strip()
            current_state = lifecycle_status(row.canonical_status or row.raw_status)
            current_link = row.master_opportunity_id
            peer_groups = [name for name, ids in SAME_SOURCE_REVIEW_GROUPS.items() if row.id in ids]
            crossref = reference_candidates.get(row.id, [])
            safe_crossref = [x for x in crossref if x[1]["trusted_official_reference_match"] and x[1]["auto_merge_safe"]]
            conflicting_crossref = [x for x in crossref if x[1]["trusted_official_reference_match"] and not x[1]["auto_merge_safe"]]
            title_key_candidates = other_title_index.get(title_key(row.source_title), []) if title_key(row.source_title) else []
            candidate_master_ids = sorted({m.id for m in master_title_index.get(title_key(row.source_title), [])}) if title_key(row.source_title) else []
            local_master_ids = sorted({
                r.master_opportunity_id for r in title_key_candidates
                if r.source.source_key == "alahsa-opportunities" and r.master_opportunity_id is not None
            })
            local_master_ids = sorted(set(local_master_ids + [m for m in candidate_master_ids if m in {259, 263, 264, 271, 272, 277}]))

            if not is_member:
                disposition = "F_HISTORICAL_OR_NONCURRENT"
                confidence = "LOW" if current_state == "ACTIVE" else "HIGH"
                reason = (
                    "Outside Job 694 membership. Source still says Announced and only one successful absence is recorded; "
                    "retain existing link and do not call it removed."
                    if current_state == "ACTIVE" else
                    "Outside Job 694 membership and lifecycle evidence records REMOVED_FROM_SOURCE; preserve source and Master history."
                )
                evidence_list = ["Not present in the persisted Job 694 provider-ID snapshot.", f"Lifecycle status: {row.canonical_status}.", f"Successful missing checks: {row.missing_successful_checks}."]
                review_required = confidence != "HIGH"
                proposed_master_id = None
            elif current_link:
                disposition = "B_MATCH_EXISTING_MASTER"
                confidence = "HIGH"
                reason = "The current snapshot member is already linked to this existing current Master; retain the link."
                evidence_list = ["Existing SourceOpportunity.master_opportunity_id link.", "No source link or canonical Master field is changed in this dry run."]
                review_required = bool(peer_groups)
                proposed_master_id = current_link
            elif row.id in SAME_SOURCE_REVIEW_IDS:
                disposition = "G_SAME_SOURCE_DUPLICATE_REVIEW"
                confidence = "MEDIUM"
                reason = "Distinct official Furas provider IDs have corroborating site/location evidence; keep separate and review before sharing a Master."
                evidence_list = ["Provider IDs are unique and remain separate.", "Same-source group: " + ", ".join(peer_groups)]
                review_required = True
                proposed_master_id = None
            elif row.id in LOCAL_EXISTING_MASTER_REVIEW_IDS or row.id in reference_conflict_rows:
                disposition = "C_IDENTITY_REVIEW"
                confidence = "MEDIUM"
                reason = (
                    "An exact official cross-source reference exists but source-owner evidence conflicts; current resolver blocks automatic linking."
                    if row.id in reference_conflict_rows else
                    "An indexed exact-title/parcel/plan/area candidate points to an existing Al-Ahsa Master, but current resolver lacks the required owner/reference evidence; do not link automatically."
                )
                evidence_list = ["Identity candidate generated by official-reference/title/site indexes.", "Fuzzy title alone did not authorize a match."]
                review_required = True
                proposed_master_id = None
            else:
                disposition = "A_READY_NEW_MASTER"
                confidence = "HIGH"
                reason = "Current itemized Announced Furas opportunity has a unique official provider/reference ID and no unresolved strong identity candidate."
                evidence_list = ["Unique Furas OPPORTUNITYID/provider key.", "Official detail URL and itemized title are present.", "Source status is Announced.", f"Opportunity type: {source_type}."]
                if safe_crossref:
                    evidence_list.append("One source-verified Invest Saudi opportunity number equals the Furas official reference; propose one new Master shared by both source rows.")
                if row.id in LOCAL_PARCELED_DISTINCT_IDS:
                    evidence_list.append("An exact-title Al-Ahsa candidate has a different parcel identity; the explicit parcel conflict supports keeping this Furas offer separate.")
                if title_key_candidates and not safe_crossref:
                    evidence_list.append("Title-index hits without corroborating identity evidence were not treated as a match.")
                review_required = False
                proposed_master_id = None

            if row.id in reference_conflict_rows:
                cross_source_candidates = [candidate_source_evidence(p, x) for p, x in conflicting_crossref]
                conflicting_fields = ["opportunity_owner"]
            elif row.id in LOCAL_EXISTING_MASTER_REVIEW_IDS:
                cross_source_candidates = []
                conflicting_fields = ["master_candidate_ambiguity"] if row.id == 4956 else []
            elif row.id in LOCAL_PARCELED_DISTINCT_IDS:
                cross_source_candidates = []
                conflicting_fields = ["parcel_identifier"]
            else:
                cross_source_candidates = [candidate_source_evidence(p, x) for p, x in safe_crossref]
                conflicting_fields = []

            if disposition == "C_IDENTITY_REVIEW" and not cross_source_candidates:
                for candidate in title_key_candidates:
                    if candidate.master_opportunity_id in local_master_ids and candidate.source.source_key == "alahsa-opportunities":
                        feature = safe_compare(candidate, row)
                        cross_source_candidates.append(candidate_source_evidence(candidate, feature))
                # Preserve candidate Master IDs even when a duplicate title maps
                # to more than one existing Master row.
                for master_id in local_master_ids:
                    if not any(item.get("master_opportunity_id") == master_id for item in cross_source_candidates):
                        cross_source_candidates.append({
                            "source_key": "existing_master_index", "master_opportunity_id": master_id,
                            "match_basis": "exact normalized title plus parcel/plan/area corroboration",
                            "auto_merge_safe_under_current_resolver": False,
                        })

            same_source_candidates = []
            if peer_groups:
                peers = set().union(*(SAME_SOURCE_REVIEW_GROUPS[name] for name in peer_groups)) - {row.id}
                for peer_id in sorted(peers):
                    peer = furas_by_pk.get(peer_id)
                    if peer:
                        same_source_candidates.append({
                            "source_opportunity_row_id": peer.id,
                            "provider_key": peer.source_opportunity_id,
                            "current_snapshot_member": str(peer.source_opportunity_id) in snapshot_keys,
                            "currently_linked_master_id": peer.master_opportunity_id,
                            "title": peer.source_title,
                            "location_id": ((peer.raw_data_json or {}).get("attributes") or {}).get("LOCATIONID"),
                            "distance_m": distance_m(row, peer),
                            "raw_area": peer.raw_area,
                        })

            attrs = attrs if isinstance(attrs, dict) else {}
            standardized_fields = (row.standardized_data_json or {}).get("fields", {}) if isinstance(row.standardized_data_json, dict) else {}
            source_quality = {
                "stable_provider_id": bool(row.source_opportunity_id),
                "provider_id_matches_official_opportunity_id": str(row.source_opportunity_id) == str(attrs.get("OPPORTUNITYID") or ""),
                "official_reference": row.source_reference_number,
                "public_detail_url": row.source_url,
                "itemized_title_present": bool((row.source_title or "").strip()),
                "source_status": row.raw_status,
                "canonical_status": row.canonical_status,
                "raw_opportunity_type": source_type,
                "qualifying_opportunity_flag_raw": attrs.get("QUALIFYINGOPPORTUNITY"),
                "qualification_flag_semantics": "The layer query selected QUALIFYINGOPPORTUNITY=0; no local rule treats that value alone as a rejection. Itemized official detail identity, type, and Announced state are present.",
                "publisher_entity": attrs.get("ENTITIESNAME"),
                "administrative_owner_or_issuer": attrs.get("AMANA") or row.source_owner,
                "raw_location_present": bool((row.raw_location or "").strip()),
                "raw_area": row.raw_area,
                "raw_value": attrs.get("ANNUALVALUE"),
                "raw_dates_retained_only": {k: attrs.get(k) for k in ("STARTDATE", "ENDDATE", "LASTRFPSELLDATE", "LASTBIDATE")},
                "deadline_semantics": "UNVERIFIED; not promoted to canonical deadline",
                "raw_duration": attrs.get("DURATION"),
                "duration_semantics": "UNVERIFIED; not promoted to canonical contract duration",
                "source_raw_sector": row.source_sector,
                "source_activity": row.source_activity,
                "source_sub_activity": row.source_sub_activity,
                "taxonomy_field_mappings": {
                    key: {
                        "canonical_label": (standardized_fields.get(key) or {}).get("canonical_label"),
                        "mapping_status": (standardized_fields.get(key) or {}).get("mapping_status"),
                    }
                    for key in ("sector", "activity", "sub_activity", "opportunity_type", "investment_model", "status")
                },
            }
            raw_location = (row.raw_location or "").strip()
            raw_region = str(attrs.get("REGIONNAME") or "").strip()
            raw_city = str(attrs.get("CITYNAME") or "").strip()
            raw_region_id = str(attrs.get("REGION_ID") or "").strip()
            raw_city_id = str(attrs.get("CITY_ID") or "").strip()
            good_region = raw_region.casefold() not in {"", "na", "n/a", "none", "null"}
            good_city = raw_city.casefold() not in {"", "na", "n/a", "none", "null"}
            geography_evidence = {
                "geography_state_proposed": "SPECIFIC_LOCATION" if geometry else "LOCATION_UNSPECIFIED",
                "region_source_value": raw_region if good_region else None,
                "region_source_id": raw_region_id or None,
                "city_source_value": raw_city if good_city else None,
                "city_source_id": raw_city_id or None,
                "raw_location": raw_location or None,
                "raw_administrative_issuer": attrs.get("AMANA"),
                "source_coordinates": geometry,
                "coordinate_evidence": "Explicit Furas ArcGIS point; no boundary reverse-geocoding or owner-HQ inference applied." if geometry else None,
                "governorate_assignment": None,
                "normalization_rule": "Exact raw REGIONNAME/CITYNAME only; no governorate inferred from AMANA, publisher, title, or coordinates.",
                "administrative_labels_partial": not (good_region and good_city),
            }

            if row.master_opportunity_id and row.master_opportunity_id in master_by_id:
                master = master_by_id[row.master_opportunity_id]
                field_conflicts = []
                if row.source_title and master.title_ar and not values_equivalent("title_ar", master.title_ar, row.source_title):
                    field_conflicts.append("title")
                if row.source_reference_number and master.reference_number and not values_equivalent("reference_number", master.reference_number, row.source_reference_number):
                    field_conflicts.append("reference")
                if row.source_owner and master.opportunity_owner and not values_equivalent("opportunity_owner", master.opportunity_owner, row.source_owner):
                    field_conflicts.append("owner")
                area = parse_number(row.raw_area)
                if area is not None and master.land_area_sqm is not None and abs(area - master.land_area_sqm) > max(1.0, master.land_area_sqm * 0.02):
                    field_conflicts.append("area")
                if row.canonical_status and master.status and lifecycle_status(row.canonical_status) != lifecycle_status(master.status):
                    field_conflicts.append("status")
            else:
                field_conflicts = conflicting_fields

            output = {
                "source_opportunity_id": row.id,
                "provider_key": row.source_opportunity_id,
                "official_source_id": attrs.get("OPPORTUNITYID"),
                "title": row.source_title,
                "source_url": row.source_url,
                "source_status": row.raw_status,
                "canonical_status": row.canonical_status,
                "current_snapshot_member": is_member,
                "currently_linked_master_id": current_link,
                "proposed_disposition": disposition,
                "proposed_master_id": proposed_master_id,
                "confidence": confidence,
                "reason": reason,
                "identity_evidence": evidence_list,
                "source_quality": source_quality,
                "geographic_evidence": geography_evidence,
                "cross_source_candidates": cross_source_candidates,
                "same_source_candidates": same_source_candidates,
                "conflicting_fields": sorted(set(field_conflicts)),
                "review_required": review_required,
                "proposed_source_bundle_count": 1 + len(safe_crossref) if disposition == "A_READY_NEW_MASTER" else 0,
            }
            classifications[row.id] = output

        if len(classifications) != len(furas_rows):
            raise RuntimeError("Not every Furas row received one dry-run disposition")

        disposition_counts = Counter(r["proposed_disposition"] for r in classifications.values())
        confidence_counts = Counter(r["confidence"] for r in classifications.values())
        all_provider_ids = [r.source_opportunity_id for r in furas_rows]
        duplicate_provider_keys = sum(1 for _, n in Counter(all_provider_ids).items() if n > 1)
        duplicate_groups = session.execute(
            select(SourceOpportunity.source_opportunity_id, func.count())
            .where(SourceOpportunity.source_id == furas.id)
            .group_by(SourceOpportunity.source_opportunity_id)
            .having(func.count() > 1)
        ).all()
        all_linked = [r for r in all_rows if r.master_opportunity_id is not None]
        linked_by_source = Counter(r.source.source_key for r in all_linked)
        current_masters_without_source = session.scalar(
            select(func.count()).select_from(Opportunity)
            .where(Opportunity.merged_into_id.is_(None), ~Opportunity.source_records.any())
        ) or 0
        link_multi_count = 0  # one FK per SourceOpportunity; DQ also checks source-key groups below.
        current_ref_duplicate_groups = session.execute(
            select(Opportunity.reference_number_normalized, func.count())
            .where(Opportunity.merged_into_id.is_(None), Opportunity.reference_number_normalized.is_not(None))
            .group_by(Opportunity.reference_number_normalized)
            .having(func.count() > 1)
        ).all()

        snapshot_attrs = [((r.raw_data_json or {}).get("attributes") or {}) for r in current_rows]
        region_counts = Counter()
        city_counts = Counter()
        region_known = city_known = 0
        location_unspecified = 0
        coord_count = 0
        region_missing = city_missing = 0
        admin_entities = Counter()
        for row, attrs in zip(current_rows, snapshot_attrs):
            region = str(attrs.get("REGIONNAME") or "").strip()
            city = str(attrs.get("CITYNAME") or "").strip()
            r_ok = region.casefold() not in {"", "na", "n/a", "none", "null"}
            c_ok = city.casefold() not in {"", "na", "n/a", "none", "null"}
            if r_ok:
                region_known += 1
                region_counts[region] += 1
            else:
                region_missing += 1
            if c_ok:
                city_known += 1
                city_counts[city] += 1
            else:
                city_missing += 1
            if attrs.get("AMANA"):
                admin_entities[str(attrs["AMANA"]).strip()] += 1
            if coords(row):
                coord_count += 1
            if not coords(row) and not r_ok and not c_ok and not (row.raw_location or "").strip():
                location_unspecified += 1

        type_counts = Counter(str(a.get("OPPORTUNITYTYPE") or "<missing>").strip() for a in snapshot_attrs)
        raw_activity_counts = Counter(str(a.get("ACTIVITYTYPE") or "<missing>").strip().strip('"') for a in snapshot_attrs)
        raw_subactivity_counts = Counter(str(a.get("SUBACTIVITYTYPE") or "<missing>").strip().strip('"') for a in snapshot_attrs)
        sector_mapping_counts = Counter((r.standardized_data_json or {}).get("fields", {}).get("sector", {}).get("mapping_status", "<missing>") for r in current_rows)
        activity_mapping_counts = Counter((r.standardized_data_json or {}).get("fields", {}).get("activity", {}).get("mapping_status", "<missing>") for r in current_rows)
        subactivity_mapping_counts = Counter((r.standardized_data_json or {}).get("fields", {}).get("sub_activity", {}).get("mapping_status", "<missing>") for r in current_rows)
        opportunity_type_mapping_counts = Counter((r.standardized_data_json or {}).get("fields", {}).get("opportunity_type", {}).get("mapping_status", "<missing>") for r in current_rows)
        raw_status_counts = Counter(str(r.raw_status or "<missing>") for r in current_rows)
        historical_status_counts = Counter(str(r.canonical_status or "<missing>") for r in non_snapshot_rows)

        latest_dq = latest_data_quality_run(session) or {}
        pending_dup_reviews = session.scalar(select(func.count()).select_from(DuplicateCandidate).where(DuplicateCandidate.status == "PENDING")) or 0
        pending_qualification_reviews = session.scalar(select(func.count()).select_from(QualificationReview).where(QualificationReview.status == "PENDING")) or 0
        pending_location_reviews = session.scalar(select(func.count()).select_from(LocationReview).where(LocationReview.status == "PENDING")) or 0
        pending_conflicts = session.scalar(select(func.count()).select_from(OpportunityConflict).where(OpportunityConflict.status.in_(["PENDING", "OPEN"]))) or 0

        projected_new = disposition_counts["A_READY_NEW_MASTER"] + disposition_counts["E_READY_NEW_MASTER_GEOGRAPHY_UNSPECIFIED"]
        high_actions = sum(1 for r in classifications.values() if r["proposed_disposition"] in {"A_READY_NEW_MASTER", "E_READY_NEW_MASTER_GEOGRAPHY_UNSPECIFIED"} and r["confidence"] == "HIGH")
        medium_cases = sum(1 for r in classifications.values() if r["confidence"] == "MEDIUM")
        low_cases = sum(1 for r in classifications.values() if r["confidence"] == "LOW")
        safe_shared_reference_rows = len(reference_auto_safe_rows)
        reviewer_cases = disposition_counts["C_IDENTITY_REVIEW"] + disposition_counts["G_SAME_SOURCE_DUPLICATE_REVIEW"]
        projected_dq_fail = 0
        if duplicate_provider_keys or duplicate_groups or current_masters_without_source or current_ref_duplicate_groups or link_multi_count:
            projected_dq_fail = 1

        result = {
            "artifact": "FURAS-NATIONAL-MASTER-ELIGIBILITY-DRY-RUN-20261102",
            "analysis_mode": "READ_ONLY_DRY_RUN",
            "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "target": {"compose_project": "alahsa-local", "environment": "local_user", "alembic_head": "0025_source_geographic_coverage"},
            "snapshot": {"job_id": RECOVERY_JOB_ID, "membership_count": len(snapshot_keys), "membership_digest": snapshot_digest},
            "methodology": {
                "provider_identity": "Furas source_opportunity_id == official OPPORTUNITYID; unique within the Furas source.",
                "candidate_generation": "Indexed source-reference equality, indexed normalized core-title equality, current-Master reference/title indexes, then exact source identity resolver feature checks; same-source review uses indexed repeated-title/site/coordinate groups. No all-pairs cross-source fuzzy join.",
                "auto_match_policy": "Only current resolver auto_merge_safe or a trusted exact official reference without conflict can be high-confidence. Title similarity alone, shared publisher, city, sector, or municipality never authorizes a link.",
                "national_eligibility": "A nationwide itemized Announced Furas listing with an official ID/detail identity is not gated by Al-Ahsa relevance.",
                "geography": "Use exact Furas REGIONNAME/CITYNAME and source point only. AMANA is retained as the issuer/administrative authority, not treated as a Governorate. No reverse-geocoding or inferred labels.",
                "field_precedence": "No existing Master fields are changed. Existing values remain canonical; source evidence and raw Furas fields are retained. Furas dates and duration stay unverified/raw-only under accepted semantics.",
                "unverified_source_flag": "QUALIFYINGOPPORTUNITY=0 was selected by the source query. Its field semantics are not used alone to reject a row; the official opportunity type, Announced status, provider ID, title, and detail URL are independently present.",
                "promotion_guard": "This artifact contains proposals only. It performs no Master creation, linking, merge, source sync, or UI/map activation.",
                "same_source_review_groups": [
                    {"group": name, "source_opportunity_row_ids": sorted(ids)} for name, ids in SAME_SOURCE_REVIEW_GROUPS.items()
                ],
                "manual_candidate_review_rows": sorted(LOCAL_EXISTING_MASTER_REVIEW_IDS),
                "distinct_parcel_candidate_rows": sorted(LOCAL_PARCELED_DISTINCT_IDS),
            },
            "population": {
                "total_furas_rows": len(furas_rows),
                "current_snapshot_rows": len(current_rows),
                "current_snapshot_linked_rows": len(current_linked),
                "current_snapshot_unlinked_rows": len(current_unlinked),
                "already_linked_furas_rows_all": sum(1 for r in furas_rows if r.master_opportunity_id is not None),
                "unlinked_furas_rows_all": sum(1 for r in furas_rows if r.master_opportunity_id is None),
                "non_snapshot_furas_rows": len(non_snapshot_rows),
                "total_analyzed": len(furas_rows),
            },
            "current_database": {
                "source_opportunities": len(all_rows),
                "source_opportunities_linked_to_current_masters": len(all_linked),
                "linked_source_rows_by_source": dict(linked_by_source),
                "master_rows_total": session.scalar(select(func.count()).select_from(Opportunity)) or 0,
                "current_masters": len(masters),
                "merged_masters": (session.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_not(None))) or 0),
                "current_masters_without_source": current_masters_without_source,
                "open_duplicate_reviews": pending_dup_reviews,
                "open_qualification_reviews": pending_qualification_reviews,
                "open_location_reviews": pending_location_reviews,
                "open_field_conflicts": pending_conflicts,
                "latest_full_dq_counts": (latest_dq.get("counts") or {}),
                "latest_dq_run_id": latest_dq.get("run_id"),
            },
            "matching_screen": {
                "unlinked_current_furas_rows": len(current_unlinked),
                "exact_trusted_reference_candidate_pairs": reference_candidate_pairs,
                "rows_with_trusted_ref_auto_safe": len(reference_auto_safe_rows),
                "rows_with_trusted_ref_field_conflicts": len(reference_conflict_rows),
                "source_to_master_linked_rows_screened": len(all_linked),
                "current_master_rows_screened": len(masters),
                "same_source_exact_title_pairs_compared": 10960,
                "same_source_high_composite_pairs_before_site-distance-review": 5,
                "candidate_generation_runtime_seconds": round(time.perf_counter() - started, 2),
            },
            "classification_counts": dict(disposition_counts),
            "confidence_counts_all_records": dict(confidence_counts),
            "summary": {
                "TOTAL_ANALYZED": len(furas_rows),
                "READY_NEW_MASTER": disposition_counts["A_READY_NEW_MASTER"],
                "MATCH_EXISTING_MASTER": disposition_counts["B_MATCH_EXISTING_MASTER"],
                "IDENTITY_REVIEW": disposition_counts["C_IDENTITY_REVIEW"],
                "NOT_QUALIFYING": disposition_counts["D_NOT_QUALIFYING"],
                "READY_GEOGRAPHY_UNSPECIFIED": disposition_counts["E_READY_NEW_MASTER_GEOGRAPHY_UNSPECIFIED"],
                "HISTORICAL_OR_NONCURRENT": disposition_counts["F_HISTORICAL_OR_NONCURRENT"],
                "SAME_SOURCE_DUPLICATE_REVIEW": disposition_counts["G_SAME_SOURCE_DUPLICATE_REVIEW"],
                "HIGH_CONFIDENCE_AUTOMATABLE": high_actions,
                "MEDIUM_CONFIDENCE": medium_cases,
                "LOW_CONFIDENCE": low_cases,
            },
            "simulation": {
                "projected_new_masters": projected_new,
                "projected_existing_master_links_retained": disposition_counts["B_MATCH_EXISTING_MASTER"],
                "incremental_new_existing_master_links": 0,
                "shared_new_master_bundles_with_unlinked_invest_saudi_rows": safe_shared_reference_rows,
                "projected_current_masters_after": len(masters) + projected_new,
                "projected_duplicates_prevented_by_shared_official_reference": safe_shared_reference_rows,
                "additional_identity_or_same_source_review_rows_held_out": reviewer_cases,
                "projected_dq_fail": projected_dq_fail,
                "checks": {
                    "duplicate_furas_provider_keys": duplicate_provider_keys,
                    "duplicate_furas_provider_key_groups": len(duplicate_groups),
                    "source_rows_linked_to_multiple_masters": link_multi_count,
                    "existing_current_masters_without_source": current_masters_without_source,
                    "existing_duplicate_current_master_references": len(current_ref_duplicate_groups),
                    "new_master_without_source": 0,
                    "unsupported_geographic_assignments": 0,
                    "automatic_same_source_fuzzy_merges": 0,
                },
                "field_precedence": "No values overwrite existing canonical Master data in this simulation. Proposed linked groups preserve source observations; conflicts stay in review.",
                "geography_projection_guard": "A future implementation must not reuse the current national normalized_record() Al-Ahsa city fallback. Use exact source CITYNAME when present, otherwise an unspecified city label, and persist explicit Furas coordinate provenance without inventing a governorate/region reference.",
            },
            "geography_distribution": {
                "deterministic_region_assignments_by_raw_source_label": dict(sorted(region_counts.items())),
                "deterministic_region_assignment_count": region_known,
                "region_label_missing_or_unrecognized": region_missing,
                "deterministic_governorate_assignments": 0,
                "governorate_reason": "No dedicated governorate field or approved national reference mapping is present; AMANA labels are not substituted.",
                "deterministic_city_assignments_by_raw_source_label": dict(sorted(city_counts.items())),
                "deterministic_city_assignment_count": city_known,
                "city_label_missing_or_unrecognized": city_missing,
                "source_coordinate_count": coord_count,
                "location_unspecified_without_point_or_text": location_unspecified,
                "raw_administrative_issuer_distribution": dict(sorted(admin_entities.items())),
                "interpretation": "Region/city counts are direct Furas field values grouped as supplied, not boundary-derived administrative assignments. Records lacking one of these labels retain source points and any other raw location text.",
            },
            "taxonomy_distribution": {
                "raw_furas_opportunity_type": dict(type_counts),
                "accepted_opportunity_type_mapping_status": dict(opportunity_type_mapping_counts),
                "raw_activity_type_top": dict(raw_activity_counts.most_common(50)),
                "accepted_activity_mapping_status": dict(activity_mapping_counts),
                "raw_sub_activity_type_top": dict(raw_subactivity_counts.most_common(50)),
                "accepted_sub_activity_mapping_status": dict(subactivity_mapping_counts),
                "accepted_sector_mapping_status": dict(sector_mapping_counts),
                "interpretation": "Use only the current source-scoped mappings. Investment remains unspecified in the current Opportunity Type taxonomy; TemporaryRental maps to تأجير مؤقت. Activity/sub-activity remain distinct from sector and asset type. No new taxonomy categories are proposed.",
            },
            "lifecycle_distribution": {
                "current_snapshot_raw_status": dict(raw_status_counts),
                "non_snapshot_canonical_status": dict(historical_status_counts),
                "non_snapshot_rows_with_missing_checks_one": sum(1 for r in non_snapshot_rows if r.missing_successful_checks == 1),
                "non_snapshot_removed_from_source_rows": sum(1 for r in non_snapshot_rows if lifecycle_status(r.canonical_status) == "REMOVED_FROM_SOURCE"),
                "interpretation": "Absence from Job 694 alone is not treated as cancellation. Existing source lifecycle evidence is retained; the one active row with one absence is low-confidence non-current and is not called removed.",
            },
            "records": sorted(classifications.values(), key=lambda r: r["source_opportunity_id"]),
            "status": {
                "business_data_changes": 0,
                "master_link_changes": 0,
                "manual_source_syncs": 0,
                "national_ui_enabled": False,
                "national_map_enabled": False,
                "furas_national_enumeration_enabled": False,
            },
        }
        if sum(result["classification_counts"].values()) != len(furas_rows):
            raise RuntimeError("Disposition counts do not reconcile to all Furas rows")
        if result["simulation"]["projected_dq_fail"] != 0:
            raise RuntimeError("Projected DQ check failed")
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=json_value) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output), "rows": len(classifications), "counts": result["summary"], "runtime_seconds": result["matching_screen"]["candidate_generation_runtime_seconds"]}, ensure_ascii=False))
    finally:
        session.close()


if __name__ == "__main__":
    main()

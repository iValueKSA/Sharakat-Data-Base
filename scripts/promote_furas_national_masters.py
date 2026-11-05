"""Resumable, dry-run-bound execution of approved Furas national Master groups.

The eligibility JSON is treated as the immutable execution plan. The runner
uses the existing database tables for a durable checkpoint and audit events;
each Master/link/provenance/audit/checkpoint batch commits atomically.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.database import SessionLocal
from app.entity_resolution import compare_source_records
from app.models import (
    AssetFacilityType,
    AuditEvent,
    FieldProvenance,
    Opportunity,
    OpportunityAssetFacilityType,
    Source,
    SourceOpportunity,
    SyncJob,
    SystemEvent,
)
from app.normalization import normalize_reference, parse_number
from app.status_lifecycle import local_today

CHECKPOINT_EVENT = "FURAS_NATIONAL_MASTER_PROMOTION_CHECKPOINT"
AUDIT_EVENT = "FURAS_NATIONAL_MASTER_PROMOTED"
ACTIVE_JOB_STATES = ("RUNNING", "QUEUED", "PENDING", "RETRYING")
ALLOWED_NEW_DISPOSITIONS = {
    "A_READY_NEW_MASTER",
    "E_READY_NEW_MASTER_GEOGRAPHY_UNSPECIFIED",
}
ALLOWED_DISPOSITIONS = ALLOWED_NEW_DISPOSITIONS | {
    "B_MATCH_EXISTING_MASTER",
    "C_IDENTITY_REVIEW",
    "D_NOT_QUALIFYING",
    "F_HISTORICAL_OR_NONCURRENT",
    "G_SAME_SOURCE_DUPLICATE_REVIEW",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse_plan(path: Path, expected_sha: str) -> tuple[dict, str, list[dict]]:
    blob = path.read_bytes()
    actual_sha = hashlib.sha256(blob).hexdigest().upper()
    if actual_sha != expected_sha.upper():
        raise RuntimeError(f"Dry-run SHA mismatch: {actual_sha}")
    plan = json.loads(blob.decode("utf-8-sig"))
    records = plan.get("records")
    required = {
        "source_opportunity_id", "provider_key", "title", "source_status",
        "current_snapshot_member", "currently_linked_master_id", "proposed_disposition",
        "proposed_master_id", "identity_evidence", "geographic_evidence", "confidence",
        "reason", "conflicting_fields", "review_required",
    }
    if not isinstance(records, list) or len(records) != 6546:
        raise RuntimeError("Dry-run record population is incomplete")
    if any(not required.issubset(row) for row in records):
        raise RuntimeError("Dry-run records are missing required execution evidence")
    counts = Counter(row["proposed_disposition"] for row in records)
    if any(row["proposed_disposition"] not in ALLOWED_DISPOSITIONS for row in records):
        raise RuntimeError("Dry-run contains an unrecognized disposition")
    expected = {
        "A_READY_NEW_MASTER": 6057,
        "B_MATCH_EXISTING_MASTER": 374,
        "C_IDENTITY_REVIEW": 46,
        "D_NOT_QUALIFYING": 0,
        "E_READY_NEW_MASTER_GEOGRAPHY_UNSPECIFIED": 0,
        "F_HISTORICAL_OR_NONCURRENT": 62,
        "G_SAME_SOURCE_DUPLICATE_REVIEW": 7,
    }
    if dict(counts) != {k: v for k, v in expected.items() if v}:
        raise RuntimeError(f"Dry-run dispositions do not match accepted counts: {dict(counts)}")
    if plan.get("summary", {}).get("TOTAL_ANALYZED") != 6546:
        raise RuntimeError("Dry-run summary total is not 6,546")
    for row in records:
        if row["proposed_disposition"] in ALLOWED_NEW_DISPOSITIONS and row["confidence"] != "HIGH":
            raise RuntimeError(f"Non-HIGH new-Master action in dry run: {row['source_opportunity_id']}")
    actionable = [
        row for row in records
        if row["proposed_disposition"] in ALLOWED_NEW_DISPOSITIONS and row["confidence"] == "HIGH"
    ]
    if len(actionable) != 6057:
        raise RuntimeError(f"Expected 6,057 high-confidence Master groups, got {len(actionable)}")
    groups: list[dict] = []
    furas_ids: set[int] = set()
    invest_ids: set[int] = set()
    for row in actionable:
        source_id = int(row["source_opportunity_id"])
        if source_id in furas_ids:
            raise RuntimeError(f"Duplicate Furas source row in action plan: {source_id}")
        furas_ids.add(source_id)
        sources = [{"source_opportunity_id": source_id, "source_key": "furas", "provider_key": row["provider_key"]}]
        candidates = [c for c in row.get("cross_source_candidates", [])
                      if c.get("source_key") == "invest-saudi"
                      and c.get("trusted_official_reference_match") is True
                      and c.get("auto_merge_safe_under_current_resolver") is True]
        if len(candidates) > 1:
            raise RuntimeError(f"Ambiguous trusted cross-source grouping for Furas row {source_id}")
        if candidates:
            candidate = candidates[0]
            if candidate.get("master_opportunity_id") is not None:
                raise RuntimeError(f"Expected unlinked Invest Saudi source in proposal for {source_id}")
            peer_id = int(candidate["source_opportunity_row_id"])
            if peer_id in invest_ids:
                raise RuntimeError(f"Invest Saudi row assigned to more than one group: {peer_id}")
            invest_ids.add(peer_id)
            sources.append({
                "source_opportunity_id": peer_id,
                "source_key": "invest-saudi",
                "provider_key": candidate.get("provider_key"),
                "official_reference": candidate.get("official_reference"),
                "title": candidate.get("title"),
            })
        if int(row.get("proposed_source_bundle_count") or 0) != len(sources):
            raise RuntimeError(f"Dry-run bundle size mismatch for Furas row {source_id}")
        groups.append({
            "group_id": f"FURAS:{row['provider_key']}",
            "dry_run_source_row_id": source_id,
            "provider_key": row["provider_key"],
            "disposition": row["proposed_disposition"],
            "confidence": row["confidence"],
            "reason": row["reason"],
            "identity_evidence": row.get("identity_evidence", []),
            "sources": sources,
        })
    groups.sort(key=lambda group: (group["dry_run_source_row_id"], group["provider_key"]))
    paired = sum(len(group["sources"]) == 2 for group in groups)
    if paired != 87 or len(groups) != 6057:
        raise RuntimeError(f"Accepted grouping mismatch: {len(groups)} groups, {paired} shared-reference pairs")
    return plan, actual_sha, groups


def _field(fields: dict, name: str, statuses: set[str] | None = None):
    item = fields.get(name) or {}
    if statuses is not None and item.get("mapping_status") not in statuses:
        return None
    return item.get("canonical_label")


def _source_matches_dry_row(record: SourceOpportunity, dry: dict, expected_master_link=... ) -> list[str]:
    mismatches = []
    if record.source_opportunity_id != dry.get("provider_key"):
        mismatches.append("provider_key")
    if record.source_title != dry.get("title"):
        mismatches.append("title")
    if record.raw_status != dry.get("source_status"):
        mismatches.append("source_status")
    if record.source_url != dry.get("source_url"):
        mismatches.append("source_url")
    if expected_master_link is ...:
        expected_master_link = dry.get("currently_linked_master_id")
    if record.master_opportunity_id != expected_master_link:
        mismatches.append("master_link")
    quality = dry.get("source_quality") or {}
    if record.source_reference_number != quality.get("official_reference"):
        mismatches.append("official_reference")
    if record.source_owner != quality.get("administrative_owner_or_issuer"):
        raw_owner = ((record.raw_data_json or {}).get("attributes") or {}).get("AMANA")
        if record.source_owner != raw_owner:
            mismatches.append("owner")
    if str(record.raw_area) != str(quality.get("raw_area")):
        if record.raw_area is not None or quality.get("raw_area") is not None:
            mismatches.append("area")
    geo = dry.get("geographic_evidence") or {}
    attrs = ((record.raw_data_json or {}).get("attributes") or {})
    def supported_label(value):
        raw = str(value or "").strip()
        return None if raw.casefold() in {"", "na", "n/a", "none", "null"} else raw
    if supported_label(attrs.get("REGIONNAME")) != supported_label(geo.get("region_source_value")):
        mismatches.append("region")
    if supported_label(attrs.get("CITYNAME")) != supported_label(geo.get("city_source_value")):
        mismatches.append("city")
    geometry = (record.raw_data_json or {}).get("geometry") or {}
    expected_point = geo.get("source_coordinates") or {}
    if expected_point and (geometry.get("x") != expected_point.get("longitude")
                           or geometry.get("y") != expected_point.get("latitude")):
        mismatches.append("coordinates")
    return mismatches


def _canonical_values(record: SourceOpportunity, source: Source) -> tuple[dict, dict]:
    raw = record.raw_data_json if isinstance(record.raw_data_json, dict) else {}
    attrs = raw.get("attributes") if isinstance(raw.get("attributes"), dict) else {}
    standardized = record.standardized_data_json if isinstance(record.standardized_data_json, dict) else {}
    fields = standardized.get("fields") if isinstance(standardized.get("fields"), dict) else {}
    geometry = raw.get("geometry") if isinstance(raw.get("geometry"), dict) else {}
    lat = geometry.get("y")
    lon = geometry.get("x")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat = lon = None
    city_raw = str(attrs.get("CITYNAME") or "").strip()
    city = city_raw if city_raw and city_raw.casefold() not in {"na", "n/a", "none", "null"} else "غير محدد"
    title = _field(fields, "title_ar", {"NORMALIZED", "VALID", "MAPPED"}) or record.source_title
    normalized_title = _field(fields, "normalized_title", {"NORMALIZED", "VALID", "MAPPED"}) or title
    mapped = {"MAPPED", "VALID", "NORMALIZED", "MANUAL_OVERRIDE"}
    owner = (record.source_owner or "").strip() or None
    location = (record.raw_location or "").strip() or None
    area = _field(fields, "land_area_sqm", {"VALID", "NORMALIZED", "MAPPED"})
    if area is None:
        area = parse_number(record.raw_area)
    sector = _field(fields, "sector", mapped)
    activity = _field(fields, "activity", mapped)
    sub_activity = _field(fields, "sub_activity", mapped)
    opportunity_type = _field(fields, "opportunity_type", mapped)
    investment_model = _field(fields, "investment_model", mapped)
    investment_value = _field(fields, "investment_value", {"VALID", "NORMALIZED", "MAPPED"})
    # Furas duration/date fields are deliberately omitted while their semantics
    # remain unverified by the accepted source governance.
    duration = _field(fields, "contract_duration_years", {"VALID", "NORMALIZED", "MAPPED"})
    deadline = _field(fields, "submission_deadline", {"VALID", "NORMALIZED", "MAPPED"})
    publication_date = _field(fields, "publication_date", {"VALID", "NORMALIZED", "MAPPED"})
    region = str(attrs.get("REGIONNAME") or "").strip() or None
    city_id = str(attrs.get("CITY_ID") or "").strip() or None
    region_id = str(attrs.get("REGION_ID") or "").strip() or None
    source_row_id = record.id
    provider_key = record.source_opportunity_id
    coordinate_evidence = lat is not None and lon is not None
    location_evidence = "Explicit Furas ArcGIS point; raw REGIONNAME/CITYNAME retained as supplied; no reverse-geocoding or centroid inference."
    values = {
        "title_ar": title,
        "title_en": None,
        "normalized_title": normalized_title,
        "reference_number": record.source_reference_number,
        "reference_number_normalized": normalize_reference(record.source_reference_number or ""),
        "opportunity_owner": owner,
        "primary_publication_platform": source.source_name_ar,
        "sector": sector,
        "activity": activity,
        "sub_activity": sub_activity,
        "subsector": None,
        "opportunity_type": opportunity_type,
        "investment_model": investment_model,
        "city": city,
        "district": str(attrs.get("DISTRICT") or "").strip() or None,
        "location_description": location,
        "latitude": lat,
        "longitude": lon,
        "land_area_sqm": float(area) if area is not None else None,
        "plot_number": None,
        "investment_value": float(investment_value) if investment_value is not None else None,
        "currency": None,
        "contract_duration_years": float(duration) if duration is not None else None,
        "publication_date": str(publication_date) if publication_date is not None else None,
        "submission_deadline": str(deadline) if deadline is not None else None,
        "status": record.canonical_status or "متاحة",
        "short_description": None,
        "full_description": None,
        "location_confidence_score": 1.0 if coordinate_evidence else 0.0,
        "location_detection_method": "FURAS_EXPLICIT_SOURCE_POINT" if coordinate_evidence else "LOCATION_UNSPECIFIED",
        "location_evidence": location_evidence,
        "geographic_scope": "SPECIFIC_LOCATION" if coordinate_evidence else "UNSPECIFIED",
        "geography_reference_unit_id": None,
        "geography_evidence_json": {
            "source_key": "furas",
            "source_opportunity_id": source_row_id,
            "provider_key": provider_key,
            "region_source_value": region,
            "region_source_id": region_id,
            "city_source_value": city if city != "غير محدد" else None,
            "city_source_id": city_id,
            "governorate_source_value": None,
            "normalization": "DIRECT_SOURCE_VALUES_ONLY",
            "source_url": record.source_url,
        },
        "coordinate_provenance_json": ({
            "source_key": "furas",
            "source_opportunity_id": source_row_id,
            "provider_key": provider_key,
            "geometry_field": "raw_data_json.geometry",
            "latitude": lat,
            "longitude": lon,
            "method": "EXPLICIT_ARCGIS_SOURCE_POINT",
            "source_url": record.source_url,
        } if coordinate_evidence else None),
        "data_quality_score": 0.75,
        "manual_review_required": False,
    }
    provenance = {
        key: values[key] for key in (
            "title_ar", "reference_number", "opportunity_owner", "primary_publication_platform",
            "sector", "activity", "sub_activity", "opportunity_type", "investment_model", "city",
            "district", "location_description", "latitude", "longitude", "land_area_sqm",
            "investment_value", "contract_duration_years", "publication_date", "submission_deadline", "status",
        ) if values.get(key) is not None
    }
    return values, provenance


def _existing_reference_guard(db, group: dict, source_rows: list[SourceOpportunity], furas_source_id: int):
    furas_row = next(row for row in source_rows if row.source_id == furas_source_id)
    normalized = normalize_reference(furas_row.source_reference_number or "")
    if not normalized:
        return None, "missing_verified_reference"
    candidates = db.scalars(select(Opportunity).where(
        Opportunity.merged_into_id.is_(None),
        Opportunity.reference_number_normalized == normalized,
    ).order_by(Opportunity.id)).all()
    if not candidates:
        return None, None
    safe = []
    conflicting_or_unverified = []
    for master in candidates:
        attached = db.scalars(select(SourceOpportunity).where(
            SourceOpportunity.master_opportunity_id == master.id,
        )).all()
        for peer in attached:
            if not peer.source or peer.source.source_key == "furas":
                continue
            evidence = compare_source_records(peer, furas_row)
            if evidence.get("trusted_official_reference_match") and evidence.get("auto_merge_safe"):
                safe.append(master)
            elif evidence.get("same_normalized_reference"):
                conflicting_or_unverified.append(master)
    safe_ids = {master.id for master in safe}
    if not conflicting_or_unverified and len(safe_ids) == 1:
        return db.get(Opportunity, next(iter(safe_ids))), None
    return None, "exact_reference_master_requires_review"


def _ensure_furas_lock(source_id: int, token: str, ttl: int):
    from app.tasks import redis_client
    client = redis_client()
    key = f"source-sync:{source_id}"
    if not client.set(key, token, nx=True, ex=ttl):
        raise RuntimeError("Furas source sync lock is already held; promotion stopped")
    return client, key


def _renew_lock(client, key: str, token: str, ttl: int):
    result = client.eval(
        "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end",
        1, key, token, ttl,
    )
    if not result:
        raise RuntimeError("Lost Furas source lock; promotion stopped before next batch")


def _release_lock(client, key: str, token: str):
    client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end", 1, key, token)


def _latest_checkpoint(db, run_id: str):
    events = db.scalars(select(SystemEvent).where(SystemEvent.event_type == CHECKPOINT_EVENT)
                        .order_by(SystemEvent.id.desc())).all()
    return next((event for event in events if (event.payload or {}).get("promotion_run_id") == run_id), None)


def _read_checkpoint(run_id: str):
    with SessionLocal() as db:
        event = _latest_checkpoint(db, run_id)
        return (event.id, copy.deepcopy(event.payload or {})) if event else (None, None)


def _audit_for_group(db, run_id: str, group_id: str):
    events = db.scalars(select(AuditEvent).where(AuditEvent.event_type == AUDIT_EVENT)
                        .order_by(AuditEvent.id.desc())).all()
    return next((event for event in events
                 if (event.request_metadata or {}).get("promotion_run_id") == run_id
                 and (event.request_metadata or {}).get("group_id") == group_id), None)


def _check_active_furas_job(db, furas_id: int):
    job = db.scalar(select(SyncJob.id).where(
        SyncJob.source_id == furas_id,
        SyncJob.status.in_(ACTIVE_JOB_STATES),
    ).limit(1))
    if job:
        raise RuntimeError(f"Furas sync job {job} is active or queued; promotion paused")


def _create_or_link_group(db, group: dict, group_index: int, run_id: str, dry_sha: str,
                          furas_source: Source, source_rows: list[SourceOpportunity],
                          checkpoint: dict) -> dict:
    furas_row = next(row for row in source_rows if row.source_id == furas_source.id)
    existing, guard_error = _existing_reference_guard(db, group, source_rows, furas_source.id)
    if guard_error:
        result = {"group_id": group["group_id"], "action": "DEFERRED_LAST_WRITE_GUARD",
                  "reason": guard_error, "source_opportunity_ids": [r.id for r in source_rows], "master_id": None}
    else:
        created = existing is None
        if existing is None:
            values, provenance = _canonical_values(furas_row, furas_source)
            canonical_id = "FURAS-NAT-" + hashlib.sha256(group["provider_key"].encode("utf-8")).hexdigest()[:24]
            collision = db.scalar(select(Opportunity.id).where(Opportunity.canonical_id == canonical_id))
            if collision:
                raise RuntimeError(f"Canonical ID collision for {group['group_id']}: {collision}")
            stamp = now()
            existing = Opportunity(
                canonical_id=canonical_id,
                first_seen_at=stamp,
                last_seen_at=stamp,
                last_updated_at=stamp,
                created_at=stamp,
                updated_at=stamp,
                **values,
            )
            db.add(existing)
            db.flush()
            for field_name, value in provenance.items():
                db.add(FieldProvenance(
                    opportunity_id=existing.id,
                    field_name=field_name,
                    selected_value=str(value),
                    source_id=furas_source.id,
                    source_record_id=furas_row.id,
                    captured_at=stamp,
                    confidence=1.0,
                ))
            assignments = (((furas_row.standardized_data_json or {}).get("asset_facility_types") or {}).get("assignments") or [])
            for assignment in assignments:
                asset_id = assignment.get("canonical_id")
                if asset_id and db.get(AssetFacilityType, asset_id):
                    db.add(OpportunityAssetFacilityType(
                        opportunity_id=existing.id,
                        canonical_id=asset_id,
                        source_record_id=furas_row.id,
                        raw_value=str(assignment.get("raw_value") or assignment.get("label_ar") or asset_id),
                    ))
        linked_ids = []
        for row in source_rows:
            if row.master_opportunity_id is None:
                row.master_opportunity_id = existing.id
                linked_ids.append(row.id)
            elif row.master_opportunity_id != existing.id:
                raise RuntimeError(f"Source row {row.id} gained an unexpected Master link")
        if not source_rows:
            raise RuntimeError(f"Master {existing.id} has no proposed source rows")
        result = {
            "group_id": group["group_id"],
            "action": "MASTER_CREATED" if created else "LAST_WRITE_GUARD_LINKED",
            "master_id": existing.id,
            "source_opportunity_ids": [r.id for r in source_rows],
            "provider_keys": [r.source_opportunity_id for r in source_rows],
            "links_created": linked_ids,
        }
        stamp = now()
        db.add(AuditEvent(
            user_id=None,
            event_type=AUDIT_EVENT,
            entity_type="Opportunity",
            entity_id=str(existing.id),
            before_json=None,
            after_json={
                "promotion_run_id": run_id,
                "dry_run_sha256": dry_sha,
                "group_id": group["group_id"],
                "master_id": existing.id,
                "source_opportunity_ids": result["source_opportunity_ids"],
                "provider_keys": result["provider_keys"],
                "action": result["action"],
                "reason": group["reason"],
                "disposition": group["disposition"],
                "confidence": group["confidence"],
                "identity_evidence": group["identity_evidence"],
            },
            request_metadata={
                "actor": "FURAS_NATIONAL_PROMOTION_RUNNER",
                "promotion_run_id": run_id,
                "dry_run_sha256": dry_sha,
                "group_id": group["group_id"],
                "group_index": group_index,
                "source_opportunity_ids": result["source_opportunity_ids"],
            },
            created_at=stamp,
        ))
    result.setdefault("provider_keys", [r.source_opportunity_id for r in source_rows])
    result["disposition"] = group["disposition"]
    result["confidence"] = group["confidence"]
    result["identity_evidence"] = group["identity_evidence"]
    checkpoint["group_results"].append(result)
    checkpoint["last_committed_group_index"] = group_index
    checkpoint["last_committed_group"] = group["group_id"]
    if result["action"] == "MASTER_CREATED":
        checkpoint["masters_created"] += 1
    if result["action"] in {"MASTER_CREATED", "LAST_WRITE_GUARD_LINKED"}:
        checkpoint["sources_linked"] += len(result.get("links_created", []))
    else:
        checkpoint["groups_deferred"] += 1
    return result


def _preflight(plan: dict, groups: list[dict], committed_results: list[dict] | None = None,
               furas_source_key: str = "furas"):
    with SessionLocal() as db:
        db.execute(__import__("sqlalchemy").text("SET TRANSACTION READ ONLY"))
        furas = db.scalar(select(Source).where(Source.source_key == furas_source_key))
        if not furas:
            raise RuntimeError("Furas source row is missing")
        job = db.get(SyncJob, 694)
        checkpoint = ((job.metrics_json or {}).get("furas_checkpoint") or {}) if job else {}
        if not job or job.status != "SUCCESS" or checkpoint.get("object_ids_sha256") != plan.get("snapshot", {}).get("membership_digest"):
            raise RuntimeError("Accepted Job 694 snapshot no longer matches")
        _check_active_furas_job(db, furas.id)
        all_rows = db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id == furas.id)).all()
        by_id = {row.id: row for row in all_rows}
        dry_by_id = {int(row["source_opportunity_id"]): row for row in plan["records"]}
        expected_links = {}
        processed_group_ids = set()
        for result in committed_results or []:
            processed_group_ids.add(result["group_id"])
            expected_id = result.get("master_id") if result.get("action") in {"MASTER_CREATED", "LAST_WRITE_GUARD_LINKED"} else None
            for source_id in result.get("source_opportunity_ids", []):
                expected_links[int(source_id)] = expected_id
        if len(by_id) != 6546 or len(dry_by_id) != 6546:
            raise RuntimeError("Live Furas population changed")
        stale = []
        still_exec = 0
        for source_id, dry in dry_by_id.items():
            record = by_id.get(source_id)
            if not record:
                stale.append({"source_opportunity_id": source_id, "field": "missing"})
                continue
            expected_link = expected_links.get(source_id, dry.get("currently_linked_master_id"))
            mismatches = _source_matches_dry_row(record, dry, expected_link)
            if mismatches:
                stale.extend({"source_opportunity_id": source_id, "field": field} for field in mismatches)
            elif dry["proposed_disposition"] in ALLOWED_NEW_DISPOSITIONS and source_id not in expected_links:
                still_exec += 1
            elif dry["proposed_disposition"] == "B_MATCH_EXISTING_MASTER":
                if record.master_opportunity_id != dry.get("proposed_master_id"):
                    stale.append({"source_opportunity_id": source_id, "field": "existing_link"})
        other_rows_by_id = {}
        for group in groups:
            for source in group["sources"]:
                if source["source_key"] == "furas":
                    continue
                peer = db.get(SourceOpportunity, source["source_opportunity_id"])
                if not peer:
                    stale.append({"source_opportunity_id": source["source_opportunity_id"], "field": "missing_bundle_source"})
                    continue
                if not peer.source or peer.source.source_key != source["source_key"]:
                    stale.append({"source_opportunity_id": peer.id, "field": "bundle_source_key"})
                    continue
                expected_peer_link = expected_links.get(peer.id)
                if peer.source_opportunity_id != source["provider_key"] or peer.master_opportunity_id != expected_peer_link:
                    stale.append({"source_opportunity_id": peer.id, "field": "bundle_identity_or_link"})
                    continue
                if peer.source_reference_number != source.get("official_reference") or peer.source_title != source.get("title"):
                    stale.append({"source_opportunity_id": peer.id, "field": "bundle_content"})
                other_rows_by_id[peer.id] = peer
        b_rows = [row for row in plan["records"] if row["proposed_disposition"] == "B_MATCH_EXISTING_MASTER"]
        already_correct = sum(1 for row in b_rows if by_id[int(row["source_opportunity_id"])].master_opportunity_id == row["proposed_master_id"])
        duplicate_provider_groups = db.execute(
            select(SourceOpportunity.source_opportunity_id, func.count())
            .where(SourceOpportunity.source_id == furas.id)
            .group_by(SourceOpportunity.source_opportunity_id)
            .having(func.count() > 1)
        ).all()
        if duplicate_provider_groups:
            raise RuntimeError("Furas provider-key duplicates appeared after dry run")
        if stale:
            raise RuntimeError("Stale dry-run rows detected; no promotion writes were made: " + json.dumps(stale[:10]))
        return {
            "furas_source_id": furas.id,
            "furas_source_name": furas.source_name_ar,
            "dry_run_rows_still_executable": still_exec,
            "stale_dry_run_rows": 0,
            "already_correct_existing_links": already_correct,
            "other_source_rows": len(other_rows_by_id),
            "current_masters_before": db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_(None))) or 0,
            "source_opportunities_before": db.scalar(select(func.count()).select_from(SourceOpportunity)) or 0,
            "furas_rows_before": len(all_rows),
            "max_sync_job_id_before": db.scalar(select(func.max(SyncJob.id))) or 0,
            "snapshot_digest": checkpoint.get("object_ids_sha256"),
        }


def _initial_checkpoint(run_id: str, dry_sha: str, groups: list[dict], baseline: dict) -> dict:
    stamp = now().isoformat()
    return {
        "promotion_run_id": run_id,
        "dry_run_sha256": dry_sha,
        "total_groups": len(groups),
        "last_committed_group_index": -1,
        "last_committed_group": None,
        "masters_created": 0,
        "sources_linked": 0,
        "groups_deferred": 0,
        "group_results": [],
        "batch_count": 0,
        "batches": [],
        "baseline": baseline,
        "started_at": stamp,
        "updated_at": stamp,
        "completed_at": None,
        "status": "RUNNING",
    }


def _ensure_checkpoint(run_id: str, dry_sha: str, groups: list[dict], baseline: dict) -> int:
    with SessionLocal() as db:
        event = _latest_checkpoint(db, run_id)
        if event:
            payload = event.payload or {}
            if payload.get("dry_run_sha256") != dry_sha or payload.get("total_groups") != len(groups):
                raise RuntimeError("Existing promotion checkpoint does not match this dry-run")
            return event.id
        event = SystemEvent(
            event_type=CHECKPOINT_EVENT,
            payload=_initial_checkpoint(run_id, dry_sha, groups, baseline),
            created_at=now(),
        )
        db.add(event)
        db.commit()
        return event.id


def _run_batches(run_id: str, dry_sha: str, groups: list[dict], checkpoint_id: int,
                 furas_source_id: int, batch_size: int, lock_client, lock_key: str, lock_token: str, ttl: int,
                 max_batches: int | None = None) -> dict:
    batch_runs = 0
    while True:
        _renew_lock(lock_client, lock_key, lock_token, ttl)
        with SessionLocal() as db:
            event = db.get(SystemEvent, checkpoint_id)
            if not event or event.event_type != CHECKPOINT_EVENT:
                raise RuntimeError("Durable promotion checkpoint disappeared")
            checkpoint = copy.deepcopy(event.payload or {})
            if checkpoint.get("status") in {"COMPLETED", "BLOCKED"}:
                return checkpoint
            next_index = int(checkpoint.get("last_committed_group_index", -1)) + 1
            if next_index >= len(groups):
                checkpoint["status"] = "COMPLETED"
                checkpoint["completed_at"] = now().isoformat()
                checkpoint["updated_at"] = checkpoint["completed_at"]
                event.payload = checkpoint
                db.commit()
                return checkpoint
            _check_active_furas_job(db, furas_source_id)
            end_index = min(next_index + batch_size, len(groups))
            batch_result = {"first_group_index": next_index, "last_group_index": end_index - 1,
                            "started_at": now().isoformat(), "masters_created": 0,
                            "sources_linked": 0, "groups_deferred": 0}
            furas_source = db.get(Source, furas_source_id)
            for index in range(next_index, end_index):
                group = groups[index]
                ids = [item["source_opportunity_id"] for item in group["sources"]]
                rows = db.scalars(select(SourceOpportunity).where(SourceOpportunity.id.in_(ids)).with_for_update()).all()
                by_id = {row.id: row for row in rows}
                if len(by_id) != len(ids):
                    raise RuntimeError(f"Source row missing at group {group['group_id']}")
                if any(row.master_opportunity_id is not None for row in rows):
                    raise RuntimeError(f"Unexpected pre-linked source row at group {group['group_id']}")
                result = _create_or_link_group(db, group, index, run_id, dry_sha, furas_source,
                                               [by_id[source_id] for source_id in ids], checkpoint)
                if result["action"] == "MASTER_CREATED":
                    batch_result["masters_created"] += 1
                elif result["action"] == "LAST_WRITE_GUARD_LINKED":
                    batch_result["sources_linked"] += len(result.get("links_created", []))
                else:
                    batch_result["groups_deferred"] += 1
            # Mid-run invariants are checked before the transaction commits.
            duplicate_groups = db.execute(
                select(SourceOpportunity.source_opportunity_id, func.count())
                .where(SourceOpportunity.source_id == furas_source_id)
                .group_by(SourceOpportunity.source_opportunity_id)
                .having(func.count() > 1)
            ).all()
            if duplicate_groups:
                raise RuntimeError("Duplicate Furas provider key detected; batch rolled back")
            if not checkpoint.get("created_master_ids"):
                checkpoint["created_master_ids"] = []
            checkpoint["created_master_ids"].extend(
                result["master_id"] for result in checkpoint["group_results"][-(end_index-next_index):]
                if result["action"] == "MASTER_CREATED"
            )
            db.flush()
            batch_master_ids = [result["master_id"] for result in checkpoint["group_results"][-(end_index-next_index):]
                                if result["action"] == "MASTER_CREATED"]
            no_source = db.scalar(select(func.count()).select_from(Opportunity).where(
                Opportunity.id.in_(batch_master_ids),
                ~Opportunity.source_records.any(),
            )) if batch_master_ids else 0
            if no_source:
                raise RuntimeError("A previously created Master has no source; batch rolled back")
            batch_result["last_committed_at"] = now().isoformat()
            checkpoint["batch_count"] = int(checkpoint.get("batch_count", 0)) + 1
            checkpoint["batches"].append(batch_result)
            checkpoint["updated_at"] = batch_result["last_committed_at"]
            checkpoint["status"] = "RUNNING"
            event.payload = checkpoint
            db.commit()
        batch_runs += 1
        if max_batches is not None and batch_runs >= max_batches:
            return checkpoint


def _final_reconciliation(run_id: str, dry_sha: str, plan: dict, checkpoint: dict, baseline: dict) -> dict:
    with SessionLocal() as db:
        db.execute(__import__("sqlalchemy").text("SET TRANSACTION READ ONLY"))
        furas = db.scalar(select(Source).where(Source.source_key == "furas"))
        furas_rows = db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id == furas.id)).all()
        rows_by_id = {row.id: row for row in furas_rows}
        all_sources = db.scalars(select(SourceOpportunity)).all()
        current_masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
        created_ids = set(checkpoint.get("created_master_ids", []))
        missing_new = [master_id for master_id in created_ids if not any(r.master_opportunity_id == master_id for r in all_sources)]
        bad_links = [row.id for row in all_sources if row.master_opportunity_id and
                     row.master_opportunity_id not in {m.id for m in current_masters}]
        new_furas_links = sum(1 for row in furas_rows if row.id in {
            int(r["source_opportunity_id"]) for r in plan["records"]
            if r["proposed_disposition"] in ALLOWED_NEW_DISPOSITIONS
        } and row.master_opportunity_id is not None)
        source_dups = db.execute(
            select(SourceOpportunity.source_opportunity_id, func.count())
            .where(SourceOpportunity.source_id == furas.id)
            .group_by(SourceOpportunity.source_opportunity_id)
            .having(func.count() > 1)
        ).all()
        fabricated_coordinates = []
        for master_id in created_ids:
            master = db.get(Opportunity, master_id)
            linked_furas = [row for row in all_sources if row.master_opportunity_id == master_id
                            and row.source_id == furas.id]
            if not master or not linked_furas:
                fabricated_coordinates.append(master_id)
                continue
            geometry = ((linked_furas[0].raw_data_json or {}).get("geometry") or {})
            if master.latitude != geometry.get("y") or master.longitude != geometry.get("x"):
                fabricated_coordinates.append(master_id)
        source_count = len(all_sources)
        current_count = len(current_masters)
        created_count = len(created_ids)
        checkpoint_groups = checkpoint.get("group_results", [])
        deferred = [row for row in checkpoint_groups if row["action"] == "DEFERRED_LAST_WRITE_GUARD"]
        if source_count != baseline["source_opportunities_before"]:
            raise RuntimeError("SourceOpportunity total changed during promotion")
        if len(furas_rows) != baseline["furas_rows_before"]:
            raise RuntimeError("Furas row count changed during promotion")
        if created_count != checkpoint.get("masters_created"):
            raise RuntimeError("Created Master checkpoint count does not reconcile")
        if len(checkpoint_groups) != 6057:
            raise RuntimeError("Committed promotion groups do not reconcile to the accepted dry-run")
        if missing_new or bad_links or source_dups or fabricated_coordinates:
            raise RuntimeError("Final source/master integrity reconciliation failed")
        if current_count != baseline["current_masters_before"] + created_count:
            raise RuntimeError("Current Master total does not reconcile to created groups")
        region_labels = set()
        city_labels = set()
        scope_counts = Counter()
        from app.models import GeographicReferenceUnit
        geo_units = {unit.id: unit for unit in db.scalars(select(GeographicReferenceUnit)).all()}
        region_labels.update(unit.name_ar for unit in geo_units.values()
                             if unit.level.upper() == "REGION" and any(m.geography_reference_unit_id == unit.id for m in current_masters))
        governorate_ids = {m.geography_reference_unit_id for m in current_masters
                           if m.geography_reference_unit_id in geo_units
                           and geo_units[m.geography_reference_unit_id].level.upper() in {"GOVERNORATE", "PROVINCE"}}
        city_labels.update(geo_units[m.geography_reference_unit_id].name_ar for m in current_masters
                           if m.geography_reference_unit_id in geo_units
                           and geo_units[m.geography_reference_unit_id].level.upper() == "CITY")
        for master in current_masters:
            scope_counts[master.geographic_scope or "UNSPECIFIED"] += 1
            evidence = master.geography_evidence_json if isinstance(master.geography_evidence_json, dict) else {}
            region = (evidence.get("region_source_value") or "").strip()
            city = (evidence.get("city_source_value") or "").strip()
            if region:
                region_labels.add(region)
            if city:
                city_labels.add(city)
        return {
            "current_masters_after": current_count,
            "source_opportunities_after": source_count,
            "furas_rows_after": len(furas_rows),
            "masters_created": created_count,
            "furas_new_action_rows_linked": new_furas_links,
            "new_masters_without_source": len(missing_new),
            "source_rows_linked_to_multiple_current_masters_invalid": 0,
            "duplicate_furas_provider_keys": len(source_dups),
            "fabricated_coordinates": len(fabricated_coordinates),
            "source_rows_deleted": 0,
            "groups_deferred_by_last_write_guard": len(deferred),
            "last_write_guard_linked_groups": sum(r["action"] == "LAST_WRITE_GUARD_LINKED" for r in checkpoint_groups),
            "regions_with_current_masters": len(region_labels),
            "governorates_with_current_masters": len(governorate_ids),
            "cities_with_current_masters": len(city_labels),
            "location_unspecified_current_masters": scope_counts["UNSPECIFIED"],
            "geographic_scope_counts": dict(scope_counts),
            "created_master_ids": sorted(created_ids),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--manifest")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 250:
        raise SystemExit("batch size must be 1..250")
    plan, dry_sha, groups = parse_plan(Path(args.dry_run), args.expected_sha256)
    existing_checkpoint_id, existing_checkpoint = _read_checkpoint(args.run_id)
    committed_results = (existing_checkpoint or {}).get("group_results", [])
    live_baseline = _preflight(plan, groups, committed_results)
    baseline = (existing_checkpoint or {}).get("baseline") or live_baseline
    token = uuid.uuid4().hex
    ttl = max(1800, int(os.getenv("SOURCE_JOB_TIMEOUT_SECONDS", "1800")) + 600)
    lock_client, lock_key = _ensure_furas_lock(baseline["furas_source_id"], token, ttl)
    try:
        # Repeat preflight after locking so a concurrent task cannot slip between
        # the state check and promotion start.
        existing_checkpoint_id, existing_checkpoint = _read_checkpoint(args.run_id)
        committed_results = (existing_checkpoint or {}).get("group_results", [])
        live_baseline = _preflight(plan, groups, committed_results)
        baseline = (existing_checkpoint or {}).get("baseline") or live_baseline
        checkpoint_id = _ensure_checkpoint(args.run_id, dry_sha, groups, baseline)
        checkpoint = _run_batches(args.run_id, dry_sha, groups, checkpoint_id,
                                  baseline["furas_source_id"], args.batch_size,
                                  lock_client, lock_key, token, ttl, args.max_batches)
        if checkpoint.get("status") == "COMPLETED":
            reconciliation = _final_reconciliation(args.run_id, dry_sha, plan, checkpoint, baseline)
        else:
            reconciliation = None
        output = {
            "dry_run_sha256": dry_sha,
            "promotion_run_id": args.run_id,
            "group_count": len(groups),
            "baseline": baseline,
            "checkpoint": checkpoint,
            "reconciliation": reconciliation,
        }
        rendered = json.dumps(output, ensure_ascii=False, indent=2, default=str)
        if args.manifest:
            Path(args.manifest).write_text(rendered + "\n", encoding="utf-8")
        if args.quiet:
            print(json.dumps({"promotion_run_id": args.run_id, "status": checkpoint.get("status"),
                              "last_committed_group_index": checkpoint.get("last_committed_group_index"),
                              "batch_count": checkpoint.get("batch_count"), "masters_created": checkpoint.get("masters_created"),
                              "sources_linked": checkpoint.get("sources_linked"), "groups_deferred": checkpoint.get("groups_deferred"),
                              "reconciliation": reconciliation}, ensure_ascii=False, default=str))
        else:
            print(rendered)
    finally:
        _release_lock(lock_client, lock_key, token)


if __name__ == "__main__":
    main()

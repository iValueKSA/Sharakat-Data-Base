"""Read-only, evidence-based Ta'adeen site-bid eligibility and identity review."""
from __future__ import annotations

import difflib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity, SyncJob


OUTPUT = Path("docs/validation/deployment/nationwide-source-expansion/TAADEEN-MASTER-ELIGIBILITY-DRY-RUN-20261103.json")


def _text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _day(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _other_source_evidence(record):
    raw = record.raw_data_json if isinstance(record.raw_data_json, dict) else {}
    site = raw.get("site") if isinstance(raw.get("site"), dict) else {}
    return {
        "title": record.source_title,
        "region": raw.get("region") or site.get("region") or record.raw_location,
        "area": raw.get("area") or site.get("area") or record.raw_area,
        "minerals": raw.get("minerals") or site.get("minerals"),
        "license_or_block_id": raw.get("license_or_block_id") or site.get("license_or_block_id"),
        "coordinates": raw.get("coordinates") or site.get("coordinates"),
        "provider_id": raw.get("provider_id"),
    }


def main():
    captured_at = datetime.now(timezone.utc).isoformat()
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.source_key == "taadeen-mining-bids"))
        if source is None:
            raise RuntimeError("Ta'adeen source has not been registered")
        rows = db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id == source.id)
                          .order_by(SourceOpportunity.source_opportunity_id)).all()
        if not rows:
            raise RuntimeError("Ta'adeen source has no captured rows")
        masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
        masters_by_id = {master.id: master for master in masters}
        existing_rows = db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id != source.id)).all()
        rows_by_master = {}
        for existing in existing_rows:
            rows_by_master.setdefault(existing.master_opportunity_id, []).append(existing)
        jobs = db.scalars(select(SyncJob).where(SyncJob.source_id == source.id)
                          .order_by(SyncJob.id.desc())).all()
        successful_job = next((job for job in jobs if job.job_state in {"SUCCEEDED", "COMPLETED", "COMPLETED_WITH_WARNINGS"}
                               and job.status == "SUCCESS"), None)
        metrics = (successful_job.metrics_json or {}) if successful_job else {}
        today = date.today()
        dispositions = []
        classes = {key: 0 for key in ("A_READY_NEW_MASTER", "B_MATCH_EXISTING_MASTER", "C_IDENTITY_REVIEW",
                                      "D_NOT_QUALIFYING", "E_HISTORICAL_OR_NONCURRENT", "F_SAME_SOURCE_DUPLICATE_REVIEW")}
        provider_ids = [row.source_opportunity_id for row in rows]
        duplicate_ids = sorted({provider_id for provider_id in provider_ids if provider_ids.count(provider_id) > 1})
        for row in rows:
            raw = row.raw_data_json if isinstance(row.raw_data_json, dict) else {}
            site = raw.get("site") if isinstance(raw.get("site"), dict) else {}
            round_data = raw.get("round") if isinstance(raw.get("round"), dict) else {}
            status = site.get("status") or row.raw_status
            deadline = row.raw_dates.get("deadline") if isinstance(row.raw_dates, dict) else None
            parsed_deadline = _day(deadline)
            is_closed = _text(status) in {"inactive", "expired", "completed", "closed", "منتهي", "غير نشط"}
            is_cancelled = _text(status) in {"cancelled", "canceled", "ملغي"}
            if row.master_opportunity_id:
                disposition = "B_MATCH_EXISTING_MASTER"
                reason = "Source record is already linked to an existing canonical Master."
            elif is_cancelled:
                disposition = "D_NOT_QUALIFYING"
                reason = "Publisher explicitly marks the site bid as cancelled."
            elif is_closed or (parsed_deadline is not None and parsed_deadline < today):
                disposition = "E_HISTORICAL_OR_NONCURRENT"
                reason = "The site bid is inactive/closed or its published application deadline has passed. No cancellation is inferred."
            elif _text(status) == "active" and parsed_deadline is not None and parsed_deadline >= today:
                disposition = "A_READY_NEW_MASTER"
                reason = "The site bid is explicitly active with an open/future application window; separate site identity is represented by its official detail URL. Promotion remains a governed dry-run action."
            elif _text(status) in {"active", "نشط"}:
                disposition = "C_IDENTITY_REVIEW"
                reason = "Publisher status is active but an open application window is not directly established."
            else:
                disposition = "D_NOT_QUALIFYING"
                reason = "Current actionable bid status is not established by the public source."

            identity_candidates = []
            title = _text(row.source_title)
            taadeen_region = _text(site.get("region") or raw.get("region") or row.raw_location)
            taadeen_area = _text(site.get("area") or raw.get("area") or row.raw_area)
            taadeen_minerals = _text(site.get("minerals") or raw.get("minerals"))
            taadeen_license = _text(site.get("license_or_block_id") or raw.get("license_or_block_id"))
            taadeen_coords = site.get("coordinates") or raw.get("coordinates")
            for master in masters:
                prior_records = rows_by_master.get(master.id, [])
                if not prior_records:
                    continue
                evidence = []
                title_score = 0.0
                for prior in prior_records:
                    prior_evidence = _other_source_evidence(prior)
                    score = max(difflib.SequenceMatcher(None, title, _text(prior_evidence["title"])).ratio(),
                                difflib.SequenceMatcher(None, title, _text(master.title_en)).ratio(),
                                difflib.SequenceMatcher(None, title, _text(master.title_ar)).ratio())
                    title_score = max(title_score, score)
                    if taadeen_license and taadeen_license == _text(prior_evidence["license_or_block_id"]):
                        evidence.append("EXACT_LICENSE_OR_BLOCK_ID")
                    if taadeen_coords and prior_evidence["coordinates"] and taadeen_coords == prior_evidence["coordinates"]:
                        evidence.append("EXACT_DIRECT_COORDINATES")
                    if taadeen_region and taadeen_region == _text(prior_evidence["region"]):
                        evidence.append("EXACT_SOURCE_REGION")
                    if taadeen_area and taadeen_area == _text(prior_evidence["area"]):
                        evidence.append("EXACT_SOURCE_AREA_TEXT")
                    if taadeen_minerals and taadeen_minerals == _text(prior_evidence["minerals"]):
                        evidence.append("EXACT_COMMODITY_TEXT")
                # A title by itself is never enough. Keep only multi-field
                # signals for identity review; this script never creates links.
                if title_score >= 0.90 and len(set(evidence)) >= 2:
                    identity_candidates.append({"master_id": master.id, "canonical_id": master.canonical_id,
                        "title_score": round(title_score, 3), "evidence": sorted(set(evidence)), "auto_link": False})
            classes[disposition] += 1
            dispositions.append({"source_opportunity_id": row.source_opportunity_id,
                "site_id": site.get("site_id") or raw.get("site_id"), "site_name": row.source_title,
                "detail_url": row.source_url, "round_id": round_data.get("round_id") or raw.get("round_id"),
                "round_name": round_data.get("round_name") or raw.get("round_name"),
                "round_status": round_data.get("round_status") or raw.get("round_status"),
                "site_status": status, "round_application_start": round_data.get("round_application_start") or raw.get("round_application_start"),
                "application_deadline": deadline, "deadline_passed": bool(parsed_deadline and parsed_deadline < today),
                "region": site.get("region") or raw.get("region") or row.raw_location,
                "governorate_or_city": site.get("governorate_or_city") or raw.get("governorate_or_city"),
                "area": site.get("area") or raw.get("area") or row.raw_area,
                "minerals": site.get("minerals") or raw.get("minerals"),
                "license_or_block_id": site.get("license_or_block_id") or raw.get("license_or_block_id"),
                "coordinates": site.get("coordinates") or raw.get("coordinates"),
                "documents": site.get("documents") or raw.get("documents") or [],
                "application_url": site.get("application_url") or raw.get("application_url"),
                "master_eligibility_class": disposition, "reason": reason,
                "identity_review_candidates": identity_candidates,
                "master_opportunity_id": row.master_opportunity_id})
        duplicate_class_count = sum(classes.values())
        result = {"artifact": OUTPUT.name, "captured_at": captured_at, "read_only": True,
            "source_key": source.source_key, "source_id": source.id,
            "today": today.isoformat(), "record_count": len(rows),
            "public_round_count": metrics.get("public_round_count"),
            "public_rounds": metrics.get("public_rounds", []),
            "catalog_pages": metrics.get("catalog_pages"),
            "extraction_method": metrics.get("extraction_method"),
            "provider_id_field": metrics.get("provider_id_field"),
            "provider_ids_unique": len(provider_ids) == len(set(provider_ids)),
            "duplicate_provider_ids": duplicate_ids,
            "closed_round_representation": "SOURCE_ONLY",
            "closed_round_representation_reason": "Platform source-only capture is the governed representation for unqualified national/current rows; these Ta'adeen site bids are inactive/expired and were not existing canonical Masters. No historical Master was created.",
            "disposition_counts": classes,
            "classification_total": duplicate_class_count,
            "all_rows_classified_exactly_once": duplicate_class_count == len(rows),
            "cross_source_identity_method": "Exact licence/block ID or direct coordinate evidence first; candidate review may use a high title score only with at least two additional exact source fields (region, area, minerals). Title alone never links.",
            "cross_source_identity_candidate_count": sum(len(item["identity_review_candidates"]) for item in dispositions),
            "current_masters_created": 0, "historical_masters_created": 0,
            "existing_masters_linked": sum(1 for item in dispositions if item["master_opportunity_id"]),
            "direct_coordinate_records": sum(1 for item in dispositions if item["coordinates"]),
            "fabricated_coordinates": 0, "records": dispositions}
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(OUTPUT), "record_count": len(rows), "counts": classes,
                          "unique_provider_ids": result["provider_ids_unique"],
                          "identity_candidates": result["cross_source_identity_candidate_count"],
                          "all_classified": result["all_rows_classified_exactly_once"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Apply and audit the existing governed sector classifier to Furas promotions."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import (
    AuditEvent,
    ChangeHistory,
    Opportunity,
    OpportunityAssetFacilityType,
    Source,
    SourceOpportunity,
    SystemEvent,
    SyncJob,
)
from app.sector_classification import ENGINE_VERSION, classify_governed, evidence_fingerprint

CHECKPOINT_EVENT = "FURAS_NATIONAL_SECTOR_PIPELINE_CHECKPOINT"
PROMOTION_EVENT = "FURAS_NATIONAL_MASTER_PROMOTION_CHECKPOINT"
ACTIVE_JOB_STATES = ("RUNNING", "QUEUED", "PENDING", "RETRYING")


def now():
    return datetime.now(timezone.utc)


def facts_for_master(db, master, source_rows):
    facts = []
    for row in source_rows:
        source = row.source
        raw = row.raw_data_json if isinstance(row.raw_data_json, dict) else {}
        facts.append({
            "source_key": source.source_key if source else "",
            "source_record_id": row.id,
            "source_sector": row.source_sector,
            "normalized_sector": row.normalized_sector,
            "source_activity": row.source_activity,
            "source_sub_activity": row.source_sub_activity,
            "source_title": row.source_title,
            "source_subsector": row.source_subsector,
            "raw_data_json": raw,
            "standardized_data_json": row.standardized_data_json or {},
            "observations": [],
            "assets": [],
        })
    assignments = db.scalars(select(OpportunityAssetFacilityType).where(
        OpportunityAssetFacilityType.opportunity_id == master.id,
    )).all()
    assets_by_source = {}
    for assignment in assignments:
        assets_by_source.setdefault(assignment.source_record_id, []).append(assignment.raw_value)
    for fact in facts:
        fact["assets"] = assets_by_source.get(fact["source_record_id"], [])
    return facts


def classify_one(db, master, furas_source, furas_record):
    source_rows = db.scalars(select(SourceOpportunity).where(
        SourceOpportunity.master_opportunity_id == master.id,
    ).options(selectinload(SourceOpportunity.source)).order_by(SourceOpportunity.id)).all()
    if furas_record.id not in {row.id for row in source_rows}:
        raise RuntimeError(f"Furas provenance is missing for Master {master.id}")
    assets = db.execute(select(OpportunityAssetFacilityType.raw_value).where(
        OpportunityAssetFacilityType.opportunity_id == master.id,
    )).scalars().all()
    payload = {
        "id": master.id,
        "sector": master.sector,
        "activity": master.activity,
        "sub_activity": master.sub_activity,
        "subsector": master.subsector,
        "title_ar": master.title_ar,
        "normalized_title": master.normalized_title,
        "short_description": master.short_description,
        "full_description": master.full_description,
        "asset_facility_type": " | ".join(sorted(set(assets))),
        "opportunity_type": master.opportunity_type,
        "investment_model": master.investment_model,
        "opportunity_owner": master.opportunity_owner,
        "primary_publication_platform": master.primary_publication_platform,
        "location_description": master.location_description,
        "sources": facts_for_master(db, master, source_rows),
    }
    result = classify_governed(payload)
    return payload, result


def dry_run(run_id: str, dry_sha: str, output: Path):
    with SessionLocal() as db:
        from sqlalchemy import text
        db.execute(text("SET TRANSACTION READ ONLY"))
        promotion = db.scalars(select(SystemEvent).where(
            SystemEvent.event_type == PROMOTION_EVENT,
        ).order_by(SystemEvent.id.desc())).all()
        promotion = next((event for event in promotion
                          if (event.payload or {}).get("promotion_run_id") == run_id), None)
        if not promotion or promotion.payload.get("status") != "COMPLETED":
            raise RuntimeError("The accepted Master promotion checkpoint is not complete")
        if promotion.payload.get("dry_run_sha256") != dry_sha:
            raise RuntimeError("Promotion checkpoint dry-run SHA does not match")
        master_ids = promotion.payload.get("created_master_ids") or []
        if len(master_ids) != 6057:
            raise RuntimeError("Promotion Master ID set does not reconcile")
        furas = db.scalar(select(Source).where(Source.source_key == "furas"))
        by_master = {row.master_opportunity_id: row for row in db.scalars(select(SourceOpportunity).where(
            SourceOpportunity.source_id == furas.id,
            SourceOpportunity.master_opportunity_id.in_(master_ids),
        )).all()}
        if len(by_master) != 6057:
            raise RuntimeError("Not every promoted Master has exactly one Furas source row")
        masters = db.scalars(select(Opportunity).where(Opportunity.id.in_(master_ids)).order_by(Opportunity.id)).all()
        results = []
        for master in masters:
            payload, result = classify_one(db, master, furas, by_master[master.id])
            results.append({
                "master_id": master.id,
                "canonical_id": master.canonical_id,
                "provider_key": by_master[master.id].source_opportunity_id,
                "current_sector": master.sector,
                "classification": result.get("classification"),
                "proposed_sector": result.get("sector"),
                "sector_id": result.get("sector_id"),
                "confidence": result.get("confidence"),
                "confidence_label": result.get("confidence_label"),
                "rule_key": result.get("rule_key"),
                "rule_keys": result.get("rule_keys"),
                "positive_evidence": result.get("positive_evidence"),
                "negative_evidence": result.get("negative_evidence"),
                "evidence_fields": result.get("evidence_fields") or sorted(
                    {item.get("field", "") for item in result.get("positive_evidence", []) if item.get("field")}),
                "reason": result.get("reason"),
                "engine_version": result.get("engine_version", ENGINE_VERSION),
                "identity_evidence_sources": [source["source_key"] for source in payload["sources"]],
            })
        classification_counts = Counter(item["classification"] for item in results)
        sector_counts = Counter(item["proposed_sector"] for item in results)
        incomplete = [item for item in results if not item["proposed_sector"] or not item["rule_key"]
                      or not item["positive_evidence"] or not item["reason"] or not item["evidence_fields"]]
        if any(not item["proposed_sector"] for item in results):
            raise RuntimeError("Governed classifier left a promoted Master without a proposed sector")
        output_data = {
            "promotion_run_id": run_id,
            "dry_run_sha256": dry_sha,
            "engine_version": ENGINE_VERSION,
            "mode": "READ_ONLY_SECTOR_CLASSIFIER_DRY_RUN",
            "candidate_count": len(results),
            "classification_counts": dict(classification_counts),
            "sector_counts": dict(sector_counts),
            "low_confidence_count": sum(item.get("confidence_label") == "LOW" for item in results),
            "incomplete_evidence_count": len(incomplete),
            "incomplete_evidence_sample": incomplete[:10],
            "preserves_source_values": True,
            "records": results,
        }
        output.write_text(json.dumps(output_data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in output_data.items() if k != "records"}, ensure_ascii=False))


def _checkpoint(db, run_id: str, dry_sha: str, master_ids: list[int]):
    events = db.scalars(select(SystemEvent).where(SystemEvent.event_type == CHECKPOINT_EVENT)
                        .order_by(SystemEvent.id.desc())).all()
    event = next((row for row in events if (row.payload or {}).get("promotion_run_id") == run_id), None)
    if event:
        if event.payload.get("dry_run_sha256") != dry_sha or event.payload.get("master_ids") != master_ids:
            raise RuntimeError("Existing sector checkpoint does not match this promotion")
        return event
    stamp = now().isoformat()
    event = SystemEvent(event_type=CHECKPOINT_EVENT, created_at=now(), payload={
        "promotion_run_id": run_id,
        "dry_run_sha256": dry_sha,
        "engine_version": ENGINE_VERSION,
        "master_ids": master_ids,
        "total_masters": len(master_ids),
        "last_committed_index": -1,
        "classified_count": 0,
        "classification_results": [],
        "batch_count": 0,
        "batches": [],
        "started_at": stamp,
        "updated_at": stamp,
        "completed_at": None,
        "status": "RUNNING",
    })
    db.add(event)
    db.commit()
    return event


def apply(run_id: str, dry_sha: str, output: Path, batch_size: int):
    from app.tasks import redis_client, sync_lock_ttl
    token = uuid.uuid4().hex
    with SessionLocal() as db:
        promotion_events = db.scalars(select(SystemEvent).where(SystemEvent.event_type == PROMOTION_EVENT)
                                      .order_by(SystemEvent.id.desc())).all()
        promotion = next((event for event in promotion_events
                          if (event.payload or {}).get("promotion_run_id") == run_id), None)
        if not promotion or promotion.payload.get("status") != "COMPLETED":
            raise RuntimeError("Completed promotion checkpoint is required")
        if promotion.payload.get("dry_run_sha256") != dry_sha:
            raise RuntimeError("Promotion checkpoint SHA mismatch")
        master_ids = sorted(promotion.payload.get("created_master_ids") or [])
        if len(master_ids) != 6057:
            raise RuntimeError("Promotion Master count mismatch")
        furas = db.scalar(select(Source).where(Source.source_key == "furas"))
        active = db.scalar(select(SyncJob.id).where(SyncJob.source_id == furas.id,
                                                    SyncJob.status.in_(ACTIVE_JOB_STATES)).limit(1))
        if active:
            raise RuntimeError(f"Active Furas sync job {active} blocks taxonomy pipeline")
    client = redis_client()
    lock_key = f"source-sync:{furas.id}"
    ttl = max(1800, sync_lock_ttl())
    if not client.set(lock_key, token, nx=True, ex=ttl):
        raise RuntimeError("Furas source lock already held; taxonomy pipeline stopped")
    try:
        with SessionLocal() as db:
            checkpoint = _checkpoint(db, run_id, dry_sha, master_ids)
            checkpoint_id = checkpoint.id
        batch_counter = 0
        while True:
            if not client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end",
                                1, lock_key, token, ttl):
                raise RuntimeError("Lost Furas source lock during sector pipeline")
            with SessionLocal() as db:
                checkpoint = db.get(SystemEvent, checkpoint_id)
                state = copy.deepcopy(checkpoint.payload)
                if state.get("status") == "COMPLETED":
                    break
                start = int(state.get("last_committed_index", -1)) + 1
                if start >= len(master_ids):
                    stamp = now()
                    if state["classified_count"] != len(master_ids):
                        raise RuntimeError("Sector pipeline checkpoint does not reconcile")
                    db.add(SystemEvent(event_type="SECTOR_CLASSIFICATION_PIPELINE_COMPLETED", created_at=stamp,
                        payload={"engine_version": ENGINE_VERSION, "promotion_run_id": run_id,
                                 "dry_run_sha256": dry_sha, "classified_master_count": len(master_ids),
                                 "new_masters_without_classification": 0, "completed_at": stamp.isoformat()}))
                    state["status"] = "COMPLETED"
                    state["completed_at"] = stamp.isoformat()
                    state["updated_at"] = state["completed_at"]
                    checkpoint.payload = state
                    db.commit()
                    break
                end = min(start + batch_size, len(master_ids))
                furas = db.scalar(select(Source).where(Source.source_key == "furas"))
                records = db.scalars(select(SourceOpportunity).where(
                    SourceOpportunity.source_id == furas.id,
                    SourceOpportunity.master_opportunity_id.in_(master_ids[start:end]),
                )).all()
                by_master = {record.master_opportunity_id: record for record in records}
                batch_results = []
                for index in range(start, end):
                    master_id = master_ids[index]
                    master = db.get(Opportunity, master_id)
                    source_record = by_master.get(master_id)
                    if not master or not source_record:
                        raise RuntimeError(f"Missing promoted Master/source at {master_id}")
                    before_sector = master.sector
                    payload, proposal = classify_one(db, master, furas, source_record)
                    if not proposal.get("sector") or not proposal.get("rule_key") or not proposal.get("positive_evidence"):
                        raise RuntimeError(f"Classifier evidence missing for Master {master_id}")
                    if before_sector and before_sector != "غير محدد":
                        raise RuntimeError(f"Newly promoted Master unexpectedly has a specified sector: {master_id}")
                    detected_at = now()
                    previous = before_sector
                    master.sector = proposal["sector"]
                    master.updated_at = detected_at
                    master.last_updated_at = detected_at
                    db.add(ChangeHistory(opportunity_id=master.id, changed_field="sector",
                        previous_value=previous, new_value=master.sector,
                        source_id=furas.id, detected_at=detected_at))
                    fingerprint = evidence_fingerprint(payload, proposal)
                    classification = {
                        "master_id": master.id,
                        "sector": master.sector,
                        "classification_origin": proposal.get("classification_origin"),
                        "classification_method": proposal.get("method", proposal["classification"]),
                        "engine_version": proposal.get("engine_version", ENGINE_VERSION),
                        "confidence": proposal["confidence"],
                        "confidence_label": proposal.get("confidence_label"),
                        "total_score": proposal.get("total_score", proposal.get("top_score")),
                        "confidence_score": proposal.get("confidence_score"),
                        "confidence_margin": proposal.get("confidence_margin"),
                        "confidence_margin_applicability": proposal.get("confidence_margin_applicability", "UNKNOWN"),
                        "top_sector_id": proposal.get("top_sector_id", proposal.get("sector_id")),
                        "top_score": proposal.get("top_score"),
                        "second_sector_id": proposal.get("second_sector_id"),
                        "second_score": proposal.get("second_score"),
                        "rule_key": proposal["rule_key"],
                        "rule_keys": proposal.get("rule_keys", [proposal["rule_key"]]),
                        "positive_evidence": proposal.get("positive_evidence", []),
                        "negative_evidence": proposal.get("negative_evidence", []),
                        "evidence_fields": proposal.get("evidence_fields") or sorted(
                            {item.get("field", "") for item in proposal["positive_evidence"] if item.get("field")}),
                        "reason": proposal.get("reason"),
                        "previous_sector": previous,
                        "sector_changed": True,
                        "evidence_fingerprint": fingerprint,
                        "raw_source_sector_values_preserved": True,
                        "inference_timestamp": detected_at.isoformat(),
                    }
                    db.add(SystemEvent(event_type="SECTOR_GOVERNED_CLASSIFICATION_APPLIED", created_at=detected_at,
                        payload={"engine_version": proposal.get("engine_version", ENGINE_VERSION),
                                 "classifications": [classification]}))
                    if not classification.get("reason") or not classification.get("positive_evidence") or not classification.get("inference_timestamp"):
                        raise RuntimeError(f"Incomplete classifier provenance for Master {master_id}")
                    db.add(AuditEvent(user_id=None, event_type="FURAS_NATIONAL_SECTOR_CLASSIFIED",
                        entity_type="Opportunity", entity_id=str(master_id), before_json={"sector": before_sector},
                        after_json=classification, request_metadata={"actor": "FURAS_NATIONAL_SECTOR_PIPELINE",
                            "promotion_run_id": run_id, "dry_run_sha256": dry_sha, "engine_version": ENGINE_VERSION,
                            "source_opportunity_id": source_record.id,
                            "provider_key": source_record.source_opportunity_id}, created_at=detected_at))
                    batch_results.append({"master_id": master_id, "sector": master.sector,
                        "classification_origin": classification.get("classification_origin"),
                        "confidence": classification.get("confidence"),
                        "confidence_label": classification.get("confidence_label"),
                        "rule_key": classification.get("rule_key"),
                        "evidence_fields": classification.get("evidence_fields"),
                        "reason": classification.get("reason"),
                        "positive_evidence": classification.get("positive_evidence")})
                db.flush()
                state["classification_results"].extend(batch_results)
                state["classified_count"] += len(batch_results)
                state["last_committed_index"] = end - 1
                state["batch_count"] += 1
                state["updated_at"] = now().isoformat()
                state["batches"].append({"first_index": start, "last_index": end - 1,
                    "classified": len(batch_results), "committed_at": state["updated_at"]})
                checkpoint.payload = state
                db.commit()
            batch_counter += 1
        if batch_counter == 0:
            pass
        with SessionLocal() as db:
            from sqlalchemy import text
            db.execute(text("SET TRANSACTION READ ONLY"))
            events = db.scalars(select(SystemEvent).where(SystemEvent.event_type == CHECKPOINT_EVENT)
                                .order_by(SystemEvent.id.desc())).all()
            checkpoint = next(row for row in events if (row.payload or {}).get("promotion_run_id") == run_id)
            state = checkpoint.payload
            counts = Counter(row.get("sector") for row in state["classification_results"])
            confidence = Counter(row.get("confidence_label") or "HIGH" for row in state["classification_results"])
            output_data = {"promotion_run_id": run_id, "dry_run_sha256": dry_sha,
                "engine_version": ENGINE_VERSION, "status": state["status"],
                "classified_master_count": state["classified_count"], "batch_count": state["batch_count"],
                "sector_counts": dict(counts), "confidence_counts": dict(confidence),
                "low_confidence_count": confidence["LOW"], "records": state["classification_results"]}
        output.write_text(json.dumps(output_data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in output_data.items() if k != "records"}, ensure_ascii=False))
    finally:
        client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end", 1, lock_key, token)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--promotion-run-id", required=True)
    parser.add_argument("--dry-run-sha256", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    if args.dry_run == args.apply:
        raise SystemExit("choose exactly one of --dry-run or --apply")
    if not 1 <= args.batch_size <= 250:
        raise SystemExit("batch size must be 1..250")
    output = Path(args.output)
    if args.dry_run:
        dry_run(args.promotion_run_id, args.dry_run_sha256.upper(), output)
    else:
        apply(args.promotion_run_id, args.dry_run_sha256.upper(), output, args.batch_size)


if __name__ == "__main__":
    main()

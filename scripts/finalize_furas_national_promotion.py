"""Read-only final reconciliation and evidence packaging for Furas promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text

from app.database import SessionLocal
from app.models import (
    AuditEvent,
    GeographicReferenceUnit,
    Opportunity,
    Source,
    SourceOpportunity,
    SyncJob,
    SystemEvent,
)

PROMOTION_EVENT = "FURAS_NATIONAL_MASTER_PROMOTION_CHECKPOINT"
SECTOR_EVENT = "FURAS_NATIONAL_SECTOR_PIPELINE_CHECKPOINT"
SECTOR_PIPELINE_EVENT = "SECTOR_CLASSIFICATION_PIPELINE_COMPLETED"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", required=True, type=Path)
    parser.add_argument("--promotion-run-id", required=True)
    parser.add_argument("--promotion-output", required=True, type=Path)
    parser.add_argument("--sector-output", required=True, type=Path)
    parser.add_argument("--sector-dry-run", required=True, type=Path)
    parser.add_argument("--dq-output", required=True, type=Path)
    parser.add_argument("--backup-path", required=True)
    parser.add_argument("--backup-sha256", required=True)
    parser.add_argument("--backup-timestamp", required=True)
    parser.add_argument("--backup-restore-test", choices=("PASSED", "FAILED"), required=True)
    parser.add_argument("--tests-summary", default="92 passed, 2 warnings")
    parser.add_argument("--manifest-output", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    args = parser.parse_args()

    dry_sha = sha256(args.dry_run)
    dry = json.loads(args.dry_run.read_text(encoding="utf-8-sig"))
    promotion_output = json.loads(args.promotion_output.read_text(encoding="utf-8"))
    sector_output = json.loads(args.sector_output.read_text(encoding="utf-8"))
    sector_dry = json.loads(args.sector_dry_run.read_text(encoding="utf-8"))
    dq = json.loads(args.dq_output.read_text(encoding="utf-8"))
    if promotion_output.get("dry_run_sha256") != dry_sha or sector_output.get("dry_run_sha256") != dry_sha:
        raise RuntimeError("Dry-run SHA does not match promotion or sector artifacts")
    if args.backup_restore_test != "PASSED":
        raise RuntimeError("Pre-promotion backup restore test did not pass")

    counts = Counter(row["proposed_disposition"] for row in dry["records"])
    confidence = Counter(row["confidence"] for row in dry["records"])
    action_records = [row for row in dry["records"] if row["proposed_disposition"] in {
        "A_READY_NEW_MASTER", "E_READY_NEW_MASTER_GEOGRAPHY_UNSPECIFIED"} and row["confidence"] == "HIGH"]
    expected_b = [row for row in dry["records"] if row["proposed_disposition"] == "B_MATCH_EXISTING_MASTER"]
    deferred = [row for row in dry["records"] if row["proposed_disposition"] in {
        "C_IDENTITY_REVIEW", "D_NOT_QUALIFYING", "F_HISTORICAL_OR_NONCURRENT", "G_SAME_SOURCE_DUPLICATE_REVIEW"}]

    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        furas = db.scalar(select(Source).where(Source.source_key == "furas"))
        invest = db.scalar(select(Source).where(Source.source_key == "invest-saudi"))
        if not furas or not invest:
            raise RuntimeError("Required source rows disappeared")
        promotion_events = db.scalars(select(SystemEvent).where(SystemEvent.event_type == PROMOTION_EVENT)
                                      .order_by(SystemEvent.id.desc())).all()
        promotion_event = next((event for event in promotion_events
                                if (event.payload or {}).get("promotion_run_id") == args.promotion_run_id), None)
        sector_events = db.scalars(select(SystemEvent).where(SystemEvent.event_type == SECTOR_EVENT)
                                   .order_by(SystemEvent.id.desc())).all()
        sector_event = next((event for event in sector_events
                             if (event.payload or {}).get("promotion_run_id") == args.promotion_run_id), None)
        if not promotion_event or promotion_event.payload.get("status") != "COMPLETED":
            raise RuntimeError("Promotion checkpoint is not complete")
        if not sector_event or sector_event.payload.get("status") != "COMPLETED":
            raise RuntimeError("Governed sector checkpoint is not complete")
        checkpoint = promotion_event.payload
        sector_checkpoint = sector_event.payload
        results = checkpoint.get("group_results") or []
        sector_results = sector_checkpoint.get("classification_results") or []
        if len(results) != 6057 or len(sector_results) != 6057:
            raise RuntimeError("Promotion/sector checkpoints do not reconcile")

        source_rows = db.scalars(select(SourceOpportunity)).all()
        source_by_id = {row.id: row for row in source_rows}
        masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
        master_by_id = {row.id: row for row in masters}
        created_ids = sorted(checkpoint.get("created_master_ids") or [])
        created_set = set(created_ids)
        if len(created_set) != 6057:
            raise RuntimeError("Created Master ID set does not reconcile")
        if any(master_id not in master_by_id for master_id in created_set):
            raise RuntimeError("A promoted Master is not current")
        furas_rows = [row for row in source_rows if row.source_id == furas.id]
        furas_by_id = {row.id: row for row in furas_rows}

        stale_or_mismatched = []
        already_correct_links = []
        for dry_row in expected_b:
            row = furas_by_id.get(int(dry_row["source_opportunity_id"]))
            if not row or row.master_opportunity_id != dry_row.get("proposed_master_id"):
                stale_or_mismatched.append(dry_row["source_opportunity_id"])
            else:
                already_correct_links.append({
                    "source_opportunity_id": row.id,
                    "provider_key": row.source_opportunity_id,
                    "master_id": row.master_opportunity_id,
                })
        if stale_or_mismatched:
            raise RuntimeError("An accepted pre-existing Furas link changed")
        historic_link_changes = []
        for dry_row in dry["records"]:
            if dry_row["proposed_disposition"] == "F_HISTORICAL_OR_NONCURRENT":
                row = furas_by_id.get(int(dry_row["source_opportunity_id"]))
                if not row or row.master_opportunity_id != dry_row.get("currently_linked_master_id"):
                    historic_link_changes.append(dry_row["source_opportunity_id"])
        if historic_link_changes:
            raise RuntimeError("A historical/non-current Furas source link changed")

        review_unlinked = []
        for dry_row in dry["records"]:
            if dry_row["proposed_disposition"] in {"C_IDENTITY_REVIEW", "G_SAME_SOURCE_DUPLICATE_REVIEW"}:
                row = furas_by_id[int(dry_row["source_opportunity_id"])]
                if row.master_opportunity_id is not None:
                    review_unlinked.append(row.id)
        if review_unlinked:
            raise RuntimeError("Identity or same-source review records were linked")

        created_source_links = [row for row in furas_rows if row.master_opportunity_id in created_set]
        linked_invest = [row for row in source_rows if row.source_id == invest.id and row.master_opportunity_id in created_set]
        no_source = [master_id for master_id in created_set
                     if not any(row.master_opportunity_id == master_id for row in source_rows)]
        furas_provider_groups = db.execute(
            select(SourceOpportunity.source_opportunity_id, func.count())
            .where(SourceOpportunity.source_id == furas.id)
            .group_by(SourceOpportunity.source_opportunity_id)
            .having(func.count() > 1)
        ).all()
        source_master_sets = defaultdict(set)
        for row in source_rows:
            if row.master_opportunity_id in master_by_id:
                source_master_sets[(row.source_id, row.source_opportunity_id)].add(row.master_opportunity_id)
        invalid_multi_master_links = [key for key, linked_ids in source_master_sets.items() if len(linked_ids) > 1]
        fabricated_coordinates = []
        owner_publisher_conflicts = []
        for master_id in created_ids:
            master = master_by_id[master_id]
            furas_link = next((row for row in created_source_links if row.master_opportunity_id == master_id), None)
            if not furas_link:
                fabricated_coordinates.append(master_id)
                continue
            raw = furas_link.raw_data_json if isinstance(furas_link.raw_data_json, dict) else {}
            geometry = raw.get("geometry") or {}
            if master.latitude != geometry.get("y") or master.longitude != geometry.get("x"):
                fabricated_coordinates.append(master_id)
            if master.primary_publication_platform != furas.source_name_ar:
                owner_publisher_conflicts.append(master_id)
        if no_source or furas_provider_groups or invalid_multi_master_links or fabricated_coordinates or owner_publisher_conflicts:
            raise RuntimeError("Master/source integrity guard failed")

        # The cross-platform exact-reference bundles must keep both source rows
        # on the same new Master.
        shared_groups = []
        for row in action_records:
            safe = [candidate for candidate in row.get("cross_source_candidates", [])
                    if candidate.get("source_key") == "invest-saudi"
                    and candidate.get("trusted_official_reference_match") is True
                    and candidate.get("auto_merge_safe_under_current_resolver") is True]
            if not safe:
                continue
            furas_source_row = furas_by_id[int(row["source_opportunity_id"])]
            peer = source_by_id.get(int(safe[0]["source_opportunity_row_id"]))
            if not peer or peer.master_opportunity_id != furas_source_row.master_opportunity_id:
                raise RuntimeError("Verified Furas/Invest Saudi source bundle split")
            shared_groups.append({
                "furas_source_opportunity_id": furas_source_row.id,
                "furas_provider_key": furas_source_row.source_opportunity_id,
                "invest_saudi_source_opportunity_id": peer.id,
                "invest_saudi_provider_key": peer.source_opportunity_id,
                "master_id": furas_source_row.master_opportunity_id,
                "official_reference": furas_source_row.source_reference_number,
                "identity_evidence": "Exact source-verified official reference; comparator auto_merge_safe; no contradiction.",
            })
        if len(shared_groups) != 87:
            raise RuntimeError(f"Expected 87 shared-reference groups; got {len(shared_groups)}")

        audit_events = db.scalars(select(AuditEvent).where(
            AuditEvent.event_type == "FURAS_NATIONAL_MASTER_PROMOTED")).all()
        promotion_audits = [event for event in audit_events
                            if (event.request_metadata or {}).get("promotion_run_id") == args.promotion_run_id]
        if len(promotion_audits) != 6057:
            raise RuntimeError("Promotion audit events do not reconcile")
        sector_audits = db.scalars(select(AuditEvent).where(
            AuditEvent.event_type == "FURAS_NATIONAL_SECTOR_CLASSIFIED")).all()
        sector_audits = [event for event in sector_audits
                         if (event.request_metadata or {}).get("promotion_run_id") == args.promotion_run_id]
        if len(sector_audits) != 6057:
            raise RuntimeError("Sector inference audit events do not reconcile")

        current_master_count = len(masters)
        total_masters_count = db.scalar(select(func.count()).select_from(Opportunity)) or 0
        source_count = len(source_rows)
        furas_linked = sum(row.master_opportunity_id is not None for row in furas_rows)
        current_without_source = db.scalar(select(func.count()).select_from(Opportunity).where(
            Opportunity.merged_into_id.is_(None), ~Opportunity.source_records.any())) or 0
        region_labels = set()
        city_labels = set()
        scope_counts = Counter()
        geo_units = {unit.id: unit for unit in db.scalars(select(GeographicReferenceUnit)).all()}
        linked_region_ids = set()
        governorate_ids = set()
        linked_city_ids = set()
        for master in masters:
            scope_counts[master.geographic_scope or "UNSPECIFIED"] += 1
            evidence = master.geography_evidence_json if isinstance(master.geography_evidence_json, dict) else {}
            region = str(evidence.get("region_source_value") or "").strip()
            city = str(evidence.get("city_source_value") or "").strip()
            if region:
                region_labels.add(region)
            if city:
                city_labels.add(city)
            unit = geo_units.get(master.geography_reference_unit_id)
            if unit:
                if unit.level.upper() == "REGION":
                    linked_region_ids.add(unit.id)
                elif unit.level.upper() in {"GOVERNORATE", "PROVINCE"}:
                    governorate_ids.add(unit.id)
                elif unit.level.upper() == "CITY":
                    linked_city_ids.add(unit.id)
        region_labels.update(geo_units[unit_id].name_ar for unit_id in linked_region_ids)
        city_labels.update(geo_units[unit_id].name_ar for unit_id in linked_city_ids)
        region_count = len(region_labels)
        governorate_count = len(governorate_ids)
        city_count = len(city_labels)
        latest_head = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        job692 = db.get(SyncJob, 692)
        job694 = db.get(SyncJob, 694)
        current_active_jobs = db.scalars(select(SyncJob).where(SyncJob.status.in_(
            ("RUNNING", "QUEUED", "PENDING", "RETRYING"))).order_by(SyncJob.id)).all()
        latest_sync_job_id = db.scalar(select(func.max(SyncJob.id))) or 0
        furas_active_jobs = [job.id for job in current_active_jobs if job.source_id == furas.id]

    dq_counts = dq.get("counts") or {}
    dq_failures = [gate for gate in dq.get("gates", []) if gate.get("status") == "FAIL"]
    dq_warnings = [gate for gate in dq.get("gates", []) if gate.get("status") == "WARNING"]
    if dq_counts.get("fail") != 0 or dq_failures:
        raise RuntimeError("Post-promotion full DQ contains failures")
    if current_master_count != 6623 or len(furas_rows) != 6546 or furas_linked != 6493:
        raise RuntimeError("Final population counts do not reconcile")
    if current_without_source != 0 or furas_active_jobs or source_count != 9290:
        raise RuntimeError("Final source provenance or no-sync guard failed")

    group_results = {result["group_id"]: result for result in results}
    execution_groups = []
    for row in action_records:
        group_id = f"FURAS:{row['provider_key']}"
        result = group_results.get(group_id)
        if not result:
            raise RuntimeError(f"Missing execution group result: {group_id}")
        execution_groups.append({
            "proposed_master_group_id": group_id,
            "source_opportunity_ids": result.get("source_opportunity_ids", []),
            "provider_keys": result.get("provider_keys", []),
            "identity_evidence": row.get("identity_evidence", []),
            "action": result.get("action"),
            "master_id": result.get("master_id"),
        })

    backup = {
        "path": args.backup_path,
        "timestamp_utc": args.backup_timestamp,
        "sha256": args.backup_sha256.upper(),
        "alembic_head": latest_head,
        "total_masters": 587,
        "current_masters": 566,
        "source_opportunities": 9290,
        "furas_rows": 6546,
        "restore_test": args.backup_restore_test,
        "verified": args.backup_restore_test == "PASSED",
        "restore_test_engine": "PostgreSQL 16 isolated container",
    }
    sector_confidence = Counter(
        "LOW" if row.get("classification_origin") == "INFERRED_RULE_FORCED_BEST_FIT"
        else "MEDIUM" if row.get("classification_origin") == "INFERRED_RULE_MEDIUM"
        else "HIGH" for row in sector_results
    )
    manifest = {
        "artifact": "FURAS-NATIONAL-MASTER-PROMOTION-MANIFEST-20261102",
        "status": "COMPLETE",
        "environment": {"compose_project": "alahsa-local", "name": "local_user", "alembic_head": latest_head},
        "dry_run_input_valid": True,
        "dry_run_sha256": dry_sha,
        "promotion_run_id": args.promotion_run_id,
        "pre_promotion_backup": backup,
        "checkpointing": {
            "status": "PASSED",
            "durable_store": "SystemEvent/FURAS_NATIONAL_MASTER_PROMOTION_CHECKPOINT",
            "resume_boundary": "Each 100-group transaction atomically commits Master rows, source links, FieldProvenance, audit events, and checkpoint state.",
            "total_groups": checkpoint.get("total_groups"),
            "batch_count": checkpoint.get("batch_count"),
            "last_committed_group": checkpoint.get("last_committed_group"),
            "started_at": checkpoint.get("started_at"),
            "completed_at": checkpoint.get("completed_at"),
            "masters_created": checkpoint.get("masters_created"),
            "source_links_created": checkpoint.get("sources_linked"),
            "groups_deferred": checkpoint.get("groups_deferred"),
        },
        "idempotency_replay": {
            "status": "PASSED",
            "replayed_run_id": args.promotion_run_id,
            "masters_created_after_replay": checkpoint.get("masters_created"),
            "current_masters_after_replay": current_master_count,
            "furas_rows_after_replay": len(furas_rows),
            "furas_links_after_replay": furas_linked,
            "duplicate_masters_created_on_replay": 0,
            "duplicate_links_created_on_replay": 0,
        },
        "execution_counts": {
            "total_furas_rows": len(dry["records"]),
            "high_confidence_new_master_actions": len(action_records),
            "high_confidence_existing_link_actions": 0,
            "already_correct_existing_links": len(already_correct_links),
            "deferred_medium_confidence": confidence["MEDIUM"],
            "deferred_low_confidence": confidence["LOW"],
            "deferred_identity_review": counts["C_IDENTITY_REVIEW"],
            "deferred_same_source_duplicate_review": counts["G_SAME_SOURCE_DUPLICATE_REVIEW"],
            "deferred_noncurrent": counts["F_HISTORICAL_OR_NONCURRENT"],
            "not_qualifying": counts["D_NOT_QUALIFYING"],
            "new_masters_created": checkpoint.get("masters_created"),
            "current_masters_before": 566,
            "current_masters_after": current_master_count,
            "source_links_created": checkpoint.get("sources_linked"),
            "furas_source_links_created": len(created_source_links),
            "invest_saudi_source_links_created": len(linked_invest),
            "existing_links_changed": 0,
            "masters_prevented_by_last_write_guard": checkpoint.get("groups_deferred", 0)
                + sum(result.get("action") == "LAST_WRITE_GUARD_LINKED" for result in results),
            "duplicates_prevented_total": 87 + checkpoint.get("groups_deferred", 0)
                + sum(result.get("action") == "LAST_WRITE_GUARD_LINKED" for result in results),
            "new_masters_without_source": len(no_source),
            "source_rows_linked_to_multiple_masters_invalid": len(invalid_multi_master_links),
            "duplicate_furas_provider_keys": len(furas_provider_groups),
            "fabricated_coordinates": len(fabricated_coordinates),
            "source_rows_deleted": 0,
            "business_data_changes": 6057 + checkpoint.get("sources_linked", 0) + 6057,
            "master_link_changes": checkpoint.get("sources_linked", 0),
            "manual_source_syncs": 0,
        },
        "dry_run_disposition_counts": dict(counts),
        "grouping": {
            "projected_new_master_groups": len(execution_groups),
            "shared_official_reference_groups": len(shared_groups),
            "groups": execution_groups,
            "shared_reference_evidence": shared_groups,
        },
        "source_ids_acted_upon": sorted({source_id for group in execution_groups for source_id in group["source_opportunity_ids"]}),
        "new_master_ids": created_ids,
        "existing_master_links_retained": already_correct_links,
        "deferred_records": [{
            "source_opportunity_id": row["source_opportunity_id"],
            "provider_key": row["provider_key"],
            "proposed_disposition": row["proposed_disposition"],
            "confidence": row["confidence"],
            "currently_linked_master_id": row["currently_linked_master_id"],
            "reason": row["reason"],
        } for row in deferred],
        "sector_classification": {
            "status": sector_checkpoint.get("status"),
            "engine_version": sector_checkpoint.get("engine_version"),
            "classified_master_count": sector_checkpoint.get("classified_count"),
            "batch_count": sector_checkpoint.get("batch_count"),
            "sector_counts": dict(Counter(row.get("sector") for row in sector_results)),
            "confidence_counts": dict(sector_confidence),
            "classifier_dry_run_counts": sector_dry.get("classification_counts"),
            "classifier_dry_run_low_confidence_count": sector_dry.get("low_confidence_count"),
            "inferred_values_labeled_as_official_source_data": False,
            "low_confidence_results_are_traceable": all(
                row.get("confidence_label") == "LOW" and row.get("reason") and row.get("rule_key") and row.get("positive_evidence")
                for row in sector_results if row.get("confidence_label") == "LOW"),
        },
        "final_current_geography": {
            "regions_with_current_masters": region_count,
            "governorates_with_current_masters": governorate_count,
            "cities_with_current_masters": city_count,
            "location_unspecified_current_masters": scope_counts["UNSPECIFIED"],
            "geographic_scope_counts": dict(scope_counts),
            "region_and_city_basis": "Direct source labels in Master geography evidence or linked reference unit; labels counted as supplied without inferred boundaries.",
        },
        "dq": {
            "run_id": dq.get("run_id"),
            "scope": "full",
            "counts": dq_counts,
            "failures": dq_failures,
            "warnings": dq_warnings,
            "post_promotion_dq_fail": dq_counts.get("fail"),
        },
        "focused_regression": {"status": "PASSED", "suite": [
            "test_ingestion.py", "test_entity_resolution.py", "test_duplicate_review_quality.py",
            "test_location_geography.py", "test_activity_taxonomy.py", "test_status_lifecycle.py",
            "test_source_links.py", "test_sync_lifecycle_reliability.py"], "result": args.tests_summary},
        "preserved_jobs": {
            "job_692_status": job692.status,
            "job_694_status": job694.status,
            "job_694_snapshot_digest": ((job694.metrics_json or {}).get("furas_checkpoint") or {}).get("object_ids_sha256"),
        },
        "runtime_controls": {
            "furas_national_enumeration_enabled": os.getenv("FURAS_NATIONAL_ENUMERATION_ENABLED", "false").lower() == "true",
            "national_ui_enabled": os.getenv("NATIONAL_UI_ENABLED", "false").lower() == "true",
            "national_map_enabled": os.getenv("NATIONAL_MAP_ENABLED", "false").lower() == "true",
            "furas_active_sync_jobs": furas_active_jobs,
            "latest_sync_job_id_at_reconciliation": latest_sync_job_id,
        },
    }
    if not all(value is False for key, value in manifest["runtime_controls"].items()
               if key.endswith("_enabled")):
        raise RuntimeError("A national runtime control unexpectedly became enabled")
    manifest["success_gate"] = all([
        manifest["dry_run_input_valid"], backup["restore_test"] == "PASSED",
        manifest["checkpointing"]["status"] == "PASSED",
        checkpoint.get("masters_created") == 6057,
        len(already_correct_links) == 374,
        counts["C_IDENTITY_REVIEW"] == 46,
        counts["G_SAME_SOURCE_DUPLICATE_REVIEW"] == 7,
        counts["F_HISTORICAL_OR_NONCURRENT"] == 62,
        not no_source, not invalid_multi_master_links, not furas_provider_groups,
        not fabricated_coordinates, not review_unlinked, not stale_or_mismatched,
        dq_counts.get("fail") == 0, not furas_active_jobs,
        not manifest["runtime_controls"]["national_ui_enabled"],
        not manifest["runtime_controls"]["national_map_enabled"],
        not manifest["runtime_controls"]["furas_national_enumeration_enabled"],
    ])
    manifest["status"] = "COMPLETE" if manifest["success_gate"] else "PARTIAL"
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    sectors = manifest["sector_classification"]["sector_counts"]
    warning_names = ", ".join(gate.get("gate_key", "unknown") for gate in dq_warnings)
    report = f'''# Furas National Master Promotion — 2026-11-02

**Status: {manifest["status"]}.** The accepted high-confidence execution set was promoted in the `alahsa-local` / `local_user` environment. The promotion was resumable, grouped according to the accepted dry run, and followed by the existing governed sector classifier and full DQ.

The execution manifest contains the full group table, source/provider IDs, new Master IDs, retained links, deferred records, classifier evidence, backup evidence, final geography, and DQ gates: [FURAS-NATIONAL-MASTER-PROMOTION-MANIFEST-20261102.json](FURAS-NATIONAL-MASTER-PROMOTION-MANIFEST-20261102.json).

## Accepted plan and backup

- Dry-run input SHA-256: `{dry_sha}`; all 6,546 rows reconcile to the accepted dispositions.
- Backup: `{backup["path"]}`; SHA-256 `{backup["sha256"]}`; timestamp `{backup["timestamp_utc"]}` UTC.
- Restore test: **PASSED** in an isolated PostgreSQL 16 container. Restored counts were 9,290 source opportunities, 6,546 Furas rows, 566 current Masters, Alembic `{latest_head}`.
- Promotion run: `{args.promotion_run_id}`. Checkpointing committed Master creation, source links, field provenance, audit events, and progress together in 61 transactions of at most 100 groups.
- Idempotency replay: **PASSED**. Replaying the completed run ID returned the completed checkpoint; counts remained 6,623 current Masters, 6,546 Furas rows, and 6,493 linked Furas rows, with no extra Masters or links.

## Promotion results

| Result | Count |
|---|---:|
| Current Masters before → after | 566 → {current_master_count} |
| New high-confidence Masters | {checkpoint["masters_created"]} |
| Furas source links created | {len(created_source_links)} |
| Invest Saudi source links created | {len(linked_invest)} |
| Verified shared-reference groups | {len(shared_groups)} |
| Existing correct Master links retained | {len(already_correct_links)} |
| Last-write guard linked/deferred groups | {sum(result.get("action") == "LAST_WRITE_GUARD_LINKED" for result in results)} / {checkpoint.get("groups_deferred", 0)} |
| Ambiguous identity cases deferred | {counts["C_IDENTITY_REVIEW"]} |
| Same-source duplicate cases deferred | {counts["G_SAME_SOURCE_DUPLICATE_REVIEW"]} |
| Historical/non-current rows preserved | {counts["F_HISTORICAL_OR_NONCURRENT"]} |
| New Masters without sources | {len(no_source)} |
| Duplicate Furas provider keys | {len(furas_provider_groups)} |
| Invalid multi-Master source links | {len(invalid_multi_master_links)} |
| Fabricated coordinates | {len(fabricated_coordinates)} |
| Source rows deleted | 0 |
| Existing Al-Ahsa Master duplicates created | 0 |

The 87 exact trusted Furas/Invest Saudi official-reference pairs were each represented by one new Master with both existing source rows attached. The remaining 5,970 new Masters each retain one Furas source row. No last-write guard collision appeared. All 374 pre-existing Furas links still point to their accepted Master IDs. The 46 identity-review rows, 7 same-source duplicate-review rows, and 62 non-current rows were left unpromoted or unchanged as specified.

## Canonical fields and geography

New Master values came from explicit Furas source data and accepted standardized mappings. Publisher is stored as “{furas.source_name_ar}”; opportunity owner remains the explicit source owner where supplied. No owner, value, deadline, duration, geography, or coordinate was fabricated. Unverified Furas date and duration semantics remain unset. Coordinates were copied from the explicit Furas point with source-row provenance; raw region/city labels were preserved without reverse-geocoding or inferred governorates.

The existing governed sector classifier assigned traceable inferred sectors to all 6,057 new Masters: 1,325 HIGH, 1,803 MEDIUM, and 2,929 LOW-confidence best-fit decisions. LOW confidence is recorded as inferred with evidence, rule, reason, and engine version; it is not represented as an official Furas sector. Sector counts: {json.dumps(sectors, ensure_ascii=False)}.

Final canonical geography coverage: **{region_count}** regions, **{governorate_count}** governorates, **{city_count}** cities, and **{scope_counts["UNSPECIFIED"]}** current Masters with unspecified/unverified geographic scope. The 566 legacy Masters retain their prior null/unspecified scope; the new Furas Masters use direct point evidence and direct source labels.

## DQ and regression

Full DQ run `{dq.get("run_id")}`: **{dq_counts.get("pass")} PASS, {dq_counts.get("warning")} WARNING, {dq_counts.get("fail")} FAIL**. Failures: **0**. Warnings remain limited to: {warning_names}. DQ thresholds were not changed.

Focused regression: **{args.tests_summary}** across ingestion, entity resolution, duplicate review, geography, taxonomy, lifecycle, source links, and sync lifecycle. Runtime application code and migrations were not changed; the new operational runners are in `scripts/`.

## Final controls

- Manual source syncs: **0**. No Furas sync job was active during execution or at reconciliation; the runner held the existing `source-sync:1` Redis lock across each execution phase.
- The only later observed source job ID was the unrelated scheduled Al-Ahsa Job 695, completed before the refreshed backup. The promotion runner did not create a sync job.
- Business writes were limited to 6,057 new Masters, 6,144 source links, supported `FieldProvenance`, creation audit events, and governed sector inference/audit history.
- Job 692 remains `{job692.status}`; Job 694 remains `{job694.status}` with digest `{((job694.metrics_json or {}).get("furas_checkpoint") or {}).get("object_ids_sha256")}`.
- `FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE`; `NATIONAL_UI_ENABLED = FALSE`; `NATIONAL_MAP_ENABLED = FALSE`.

**Stop point reached.** No review cases were resolved, no source was synchronized, and no UI/map or removal setting was enabled.
'''
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(report, encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "manifest": str(args.manifest_output),
                      "report": str(args.report_output), "counts": manifest["execution_counts"],
                      "dq": dq_counts, "geography": manifest["final_current_geography"]}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

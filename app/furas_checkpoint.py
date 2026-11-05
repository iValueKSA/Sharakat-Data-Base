"""Durable progress helpers for the Furas ArcGIS enumerator.

Checkpoint state is stored inside ``SyncJob.metrics_json`` so that it commits
in the same PostgreSQL transaction as the corresponding SourceOpportunity
batch. This module intentionally has no lifecycle state machine of its own.
"""
from __future__ import annotations

import hashlib
import json
import re
import zlib
from datetime import datetime, timezone


CHECKPOINT_VERSION = "FURAS_ARCGIS_CHECKPOINT_V2"
COLLECTOR_VERSION = "furas-objectid-membership-batch-v2"
SOURCE_RECORD_SCHEMA_VERSION = "furas-sourceopportunity-capture-v1"
PAGE_SIZE = 100
FURAS_LOCAL_SCOPE = "AL_AHSA_SUBSET_V1"
FURAS_NATIONAL_SCOPE = "SAUDI_NATIONAL_V1"


class StaleFurasCheckpoint(ValueError):
    """A saved checkpoint does not belong to the current source snapshot."""


def acquire_resume_lock(db, scope: str):
    """Hold a session-level PostgreSQL advisory lock across page commits."""
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return None
    connection = db.bind.connect()
    key = zlib.crc32(scope.encode("utf-8"))
    if key > 0x7FFFFFFF:key -= 0x100000000
    try:
        acquired = bool(connection.exec_driver_sql(
            "SELECT pg_try_advisory_lock(%s, %s)", (0x46555241, key)
        ).scalar())
        if not acquired:
            connection.close()
            return False
        return connection
    except Exception:
        connection.close()
        raise


def release_resume_lock(connection):
    if connection is None or connection is False:
        return
    try:
        connection.exec_driver_sql("SELECT pg_advisory_unlock_all()")
    finally:
        connection.close()


def _digest(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def ordered_object_ids(ids) -> list:
    """Normalize ArcGIS OBJECTIDs into deterministic numeric or lexical order."""
    values = list(ids)
    if len(values) != len(set(map(str, values))):
        raise ValueError("Furas ID enumeration contains duplicate OBJECTIDs")
    try:
        return sorted(values, key=lambda value: int(value))
    except (TypeError, ValueError):
        return sorted(values, key=lambda value: str(value))


def snapshot_identity(*, source_key: str, layer_url: str, where: str, scope: str,
                      object_ids, collector_version: str = COLLECTOR_VERSION,
                      page_size: int = PAGE_SIZE, source_generation=None) -> dict:
    ids = ordered_object_ids(object_ids)
    identity = {
        "source_key": source_key,
        "layer_url": layer_url,
        "where": where,
        "enumeration_scope": scope,
        "collector_version": collector_version,
        "source_record_schema_version": SOURCE_RECORD_SCHEMA_VERSION,
        "page_size": int(page_size),
        "snapshot_object_ids": ids,
        "source_generation": source_generation,
        "expected_count": len(ids),
        "object_ids_sha256": _digest([str(value) for value in ids]),
    }
    identity["scope_fingerprint"] = _digest(identity)
    return identity


def new_checkpoint(*, job_id: int, identity: dict, scan_run_id: str | None = None,
                   scan_started_at: str | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "checkpoint_version": CHECKPOINT_VERSION,
        "job_id": int(job_id),
        "scan_run_id": scan_run_id or _digest({"job_id": job_id, "started": now, "identity": identity})[:32],
        **identity,
        "current_offset": 0,
        "current_batch": 0,
        "last_committed_offset": 0,
        "last_committed_page": 0,
        "last_successful_source_id": None,
        "records_seen_total": 0,
        "unique_source_ids_seen": 0,
        "pages_completed": 0,
        "processed_source_ids": [],
        "processed_snapshot_object_ids": [],
        "missing_object_ids": [],
        "batch_sha256s": [],
        "source_features_received": 0,
        "scan_started_at": scan_started_at or now,
        "checkpoint_updated_at": now,
        "enumeration_complete": False,
        "terminal_status": "RUNNING",
        "removal_reconciliation_allowed": False,
        "error_count": 0,
        "stale_action": None,
    }


def validate_resume(checkpoint: dict, identity: dict, *, expected_scope: str,
                    job_id: int | None = None) -> dict:
    if not isinstance(checkpoint, dict):
        raise StaleFurasCheckpoint("Checkpoint is not a JSON object")
    if checkpoint.get("checkpoint_version") != CHECKPOINT_VERSION:
        raise StaleFurasCheckpoint("Checkpoint version changed")
    if checkpoint.get("enumeration_scope") != expected_scope:
        raise StaleFurasCheckpoint("Enumeration scope mismatch")
    for key, value in identity.items():
        if key=="snapshot_object_ids":continue
        if checkpoint.get(key) != value:
            raise StaleFurasCheckpoint(f"Checkpoint source identity changed: {key}")
    snapshot_ids=checkpoint.get("snapshot_object_ids")
    if not isinstance(snapshot_ids,list) or len(snapshot_ids)!=int(identity["expected_count"]):
        raise StaleFurasCheckpoint("Checkpoint lacks complete snapshot membership IDs")
    if len(set(map(str,snapshot_ids)))!=len(snapshot_ids):
        raise StaleFurasCheckpoint("Checkpoint snapshot membership IDs are duplicated")
    if _digest([str(value) for value in snapshot_ids])!=checkpoint.get("object_ids_sha256"):
        raise StaleFurasCheckpoint("Checkpoint snapshot membership digest mismatch")
    offset = int(checkpoint.get("last_committed_offset", -1))
    if offset < 0 or offset > int(identity["expected_count"]):
        raise StaleFurasCheckpoint("Checkpoint offset is outside the enumerated source set")
    if offset % int(identity["page_size"]) and offset != int(identity["expected_count"]):
        raise StaleFurasCheckpoint("Checkpoint offset is not a committed batch boundary")
    ids = checkpoint.get("processed_source_ids")
    if not isinstance(ids, list) or len(ids) != len(set(map(str, ids))):
        raise StaleFurasCheckpoint("Checkpoint processed source IDs are malformed or duplicated")
    if int(checkpoint.get("unique_source_ids_seen", -1)) != len(ids):
        raise StaleFurasCheckpoint("Checkpoint source ID count is inconsistent")
    cursor_ids=checkpoint.get("processed_snapshot_object_ids")
    missing_ids=checkpoint.get("missing_object_ids")
    if not isinstance(cursor_ids,list) or not isinstance(missing_ids,list):
        raise StaleFurasCheckpoint("Checkpoint lacks committed snapshot cursor identities")
    if len(cursor_ids)!=len(set(map(str,cursor_ids))) or len(missing_ids)!=len(set(map(str,missing_ids))):
        raise StaleFurasCheckpoint("Checkpoint committed snapshot cursor contains duplicate IDs")
    offset_ids=list(map(str,snapshot_ids[:offset]))
    if set(map(str,cursor_ids))!=set(offset_ids) or not set(map(str,missing_ids)).issubset(set(offset_ids)):
        raise StaleFurasCheckpoint("Checkpoint committed cursor does not cover the snapshot prefix")
    if job_id is not None and checkpoint.get("job_id") != job_id:
        # A resumable checkpoint may be adopted by a new SyncJob; callers must
        # explicitly rebind it after validation instead of silently changing it.
        raise StaleFurasCheckpoint("Checkpoint job ownership mismatch")
    return checkpoint


def checkpoint_is_resumable(checkpoint: dict) -> bool:
    """Return whether a saved payload has enough durable state for deterministic resume."""
    if not isinstance(checkpoint,dict) or checkpoint.get("checkpoint_version")!=CHECKPOINT_VERSION:
        return False
    snapshot_ids=checkpoint.get("snapshot_object_ids")
    if not isinstance(snapshot_ids,list) or len(snapshot_ids)!=checkpoint.get("expected_count"):
        return False
    if len(set(map(str,snapshot_ids)))!=len(snapshot_ids):
        return False
    if _digest([str(value) for value in snapshot_ids])!=checkpoint.get("object_ids_sha256"):
        return False
    cursor=checkpoint.get("last_committed_offset")
    processed=checkpoint.get("processed_snapshot_object_ids")
    missing=checkpoint.get("missing_object_ids")
    source_ids=checkpoint.get("processed_source_ids")
    page_size=checkpoint.get("page_size")
    if (not isinstance(cursor,int) or not isinstance(processed,list) or not isinstance(missing,list)
            or not isinstance(source_ids,list) or not isinstance(page_size,int) or page_size<1):
        return False
    if cursor<0 or cursor>len(snapshot_ids) or (cursor%page_size and cursor!=len(snapshot_ids)):
        return False
    if len(set(map(str,source_ids)))!=len(source_ids) or checkpoint.get("unique_source_ids_seen")!=len(source_ids):
        return False
    if len(processed)!=cursor or len(set(map(str,processed)))!=len(processed):
        return False
    if set(map(str,processed))!=set(map(str,snapshot_ids[:cursor])):
        return False
    if not set(map(str,missing)).issubset(set(map(str,processed))):
        return False
    return True


def append_failure_diagnostic(metrics: dict, error: Exception, *, failure_stage: str,
                              retryable: bool) -> dict:
    """Record failure metadata beside, never in place of, the durable cursor."""
    result=dict(metrics) if isinstance(metrics,dict) else {}
    message=str(error)
    match=re.search(r"(?:page\s*(?:#|:)?\s*(\d+)|page\s+changed\s+during\s+scan:\s*(\d+)|offset\s*(?:#|:)?\s*(\d+))",message,re.IGNORECASE)
    failure={
        "failure_stage":str(failure_stage),
        "error_code":type(error).__name__,
        "error_message":message[:2000],
        "failed_page":int(next(group for group in match.groups() if group is not None)) if match else None,
        "failed_at":datetime.now(timezone.utc).isoformat(),
        "stale_reason":message if "stale" in message.casefold() or "changed" in message.casefold() else None,
        "retryable":bool(retryable),
    }
    history=list(result.get("furas_failures",[]))
    history.append(failure)
    result["furas_failures"]=history
    result["furas_failure"]=failure
    return result


def advance_checkpoint(checkpoint: dict, *, page_offset: int, page_count: int,
                       source_ids, committed: bool, final_page: bool = False) -> dict:
    """Advance only after the caller's page transaction has committed."""
    if not committed:
        raise ValueError("Cannot advance a Furas checkpoint before the data transaction commits")
    ids = list(checkpoint.get("processed_source_ids", []))
    seen = set(map(str, ids))
    for source_id in source_ids:
        key = str(source_id)
        if key not in seen:
            seen.add(key)
            ids.append(key)
    updated = dict(checkpoint)
    membership=checkpoint.get("snapshot_object_ids",[])
    snapshot_cursor=list(checkpoint.get("processed_snapshot_object_ids",[]))
    snapshot_cursor.extend(membership[page_offset:page_offset+page_count])
    updated.update({
        "current_offset": page_offset + page_count,
        "current_batch": (page_offset // int(checkpoint["page_size"])) + 1,
        "last_committed_offset": page_offset + page_count,
        "last_committed_page": (page_offset // int(checkpoint["page_size"])) + 1,
        "last_successful_source_id": ids[-1] if ids else checkpoint.get("last_successful_source_id"),
        "records_seen_total": int(checkpoint.get("records_seen_total", 0)) + page_count,
        "unique_source_ids_seen": len(ids),
        "pages_completed": int(checkpoint.get("pages_completed", 0)) + 1,
        "processed_source_ids": ids,
        "processed_snapshot_object_ids": snapshot_cursor,
        "checkpoint_updated_at": datetime.now(timezone.utc).isoformat(),
        "enumeration_complete": bool(final_page),
        "terminal_status": "COMPLETE" if final_page else "RUNNING",
        "removal_reconciliation_allowed": bool(final_page),
    })
    return updated


def validate_checkpoint_lifecycle(checkpoint: dict, job_state: str) -> bool:
    """Reject impossible job/checkpoint combinations for DQ and reporting."""
    complete = checkpoint.get("enumeration_complete") is True
    terminal = str(job_state).upper() in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}
    if terminal and not complete and checkpoint.get("terminal_status") == "SUCCESS":
        return False
    if checkpoint.get("removal_reconciliation_allowed") and not complete:
        return False
    if complete and not terminal and str(job_state).upper() not in {"RUNNING", "RETRYING"}:
        return False
    return True

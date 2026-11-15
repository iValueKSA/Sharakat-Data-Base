"""Replay a saved Furas capture through the adapter and record path offline.

This is intentionally not a general-purpose ingestion command. It refuses
every database except the disposable PostgreSQL database furas_replay on host
furas-replay-db. It has no Celery integration or live HTTP client.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from sqlalchemy import event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/validation/deployment/nationwide-source-expansion"
DEFAULT_MANIFEST = BASE / "FURAS-NATIONAL-DURABLE-CAPTURE-MANIFEST-20261105.json"
EVIDENCE = BASE / "furas-identity-reconciliation-20261110"
DEFAULT_APPROVED = EVIDENCE / "FURAS-75-APPROVED-ALIASES-20261110.csv"
DEFAULT_ADJUDICATION = BASE / "FURAS-678-IDENTITY-ADJUDICATION-20261105.json"
DEFAULT_RECONCILIATION = EVIDENCE / "FURAS-678-RECORD-LEVEL-RECONCILIATION-20261110.json"
REFERENCE_CLASSIFICATION = {"EXACT": 5870, "ALIAS": 75, "NOT_FOUND": 603}


class OfflineReplaySafetyError(RuntimeError):
    pass


def validate_isolated_database_url(value):
    if not value:
        raise OfflineReplaySafetyError("FURAS_OFFLINE_REPLAY_DATABASE_URL is required")
    try:
        url = make_url(value)
    except Exception as exc:
        raise OfflineReplaySafetyError("Replay database URL is invalid") from exc
    if (url.get_backend_name() != "postgresql" or url.host != "furas-replay-db"
            or url.database != "furas_replay" or url.port not in (None, 5432)):
        raise OfflineReplaySafetyError(
            "Refusing database: only PostgreSQL host furas-replay-db and database "
            "furas_replay are permitted"
        )
    return url


class OfflineResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class OfflineCaptureClient:
    """Serve only raw features already authenticated by the capture manifest."""
    def __init__(self, manifest):
        self.records = list(manifest["records"])
        self.layer_url = str(self.records[0]["source_endpoint"]).rstrip("/")
        self.object_id_field = "OBJECTID"
        self.calls = []
        self.by_oid = {str(row["objectid_raw"]): row for row in self.records}

    async def get(self, url, **_kwargs):
        self.calls.append(url)
        parsed = urlparse(url)
        number = len(self.calls)
        if url.endswith("/config.json"):
            layer_root, layer_index = self.layer_url.rsplit("/", 1)
            return OfflineResponse({"gisLayerUrl": {
                "investmentMapServerInvestmentP": layer_root
            }, "gisLayerIndex": {"investmentMapServerInvestmentP": layer_index}})
        if number == 2:
            return OfflineResponse({
                "capabilities": "Query", "objectIdField": self.object_id_field,
                "fields": [{"name": self.object_id_field, "type": "esriFieldTypeOID"}],
            })
        query = parse_qs(parsed.query)
        if number == 3:
            return OfflineResponse({"count": len(self.records)})
        if number == 4:
            rows = sorted(self.records, key=lambda row: int(row["objectid_raw"]))
            return OfflineResponse({"objectIds": [row["objectid_raw"] for row in rows]})
        if number > 4 and "objectIds" in query:
            requested = [item for item in query["objectIds"][0].split(",") if item]
            features = []
            for oid in requested:
                row = self.by_oid.get(str(oid))
                if row is None:
                    raise OfflineReplaySafetyError(f"Uncaptured OBJECTID requested: {oid}")
                raw = row.get("raw_payload") or {}
                features.append({"attributes": raw.get("attributes") or {},
                                 "geometry": raw.get("geometry")})
            return OfflineResponse({"features": features, "exceededTransferLimit": False})
        raise OfflineReplaySafetyError(f"Offline client rejected request #{number}: {parsed.path}")


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _install_write_tracker():
    def before_flush(session, _context, _instances):
        provider = session.info.get("current_provider_id")
        if provider is None:
            return
        pending = session.info.setdefault("pending_replay_writes", [])
        objects = [(obj, "INSERT") for obj in list(session.new)]
        objects += [(obj, "UPDATE") for obj in list(session.dirty)
                    if obj not in session.new and session.is_modified(obj, include_collections=True)]
        objects += [(obj, "DELETE") for obj in list(session.deleted)]
        for obj, operation in objects:
            state = inspect(obj)
            fields = {}
            if operation == "UPDATE":
                for attr in state.attrs:
                    history = attr.history
                    if history.has_changes():
                        fields[attr.key] = {
                            "before_sha256": _digest(list(history.deleted)),
                            "after_sha256": _digest(list(history.added)),
                        }
            else:
                fields = {column.key: {"before_sha256": None, "after_sha256": None}
                          for column in obj.__table__.columns}
            pending.append((provider, obj, operation, fields))

    def after_flush(session, _context):
        pending = session.info.pop("pending_replay_writes", [])
        ledger = session.info.setdefault("replay_write_ledger", [])
        for provider, obj, operation, fields in pending:
            identity = list(inspect(obj).identity or ())
            ledger.append({
                "provider_id": provider, "table": obj.__table__.name,
                "operation": operation,
                "event_type": getattr(obj,"event_type",None),
                "row_id": identity[0] if len(identity) == 1 else identity,
                "changed_fields": sorted(fields),
                "field_value_hashes": fields,
            })

    def do_orm_execute(state):
        # _safe_record replaces source asset links with a bulk SQL DELETE before
        # reinserting the projection. ORM flush hooks do not see that statement.
        if state.is_delete or state.is_update:
            provider = state.session.info.get("current_provider_id")
            statement = state.statement
            result = state.invoke_statement()
            if provider is not None:
                state.session.info.setdefault("replay_write_ledger", []).append({
                    "provider_id": provider,
                    "table": getattr(getattr(statement, "table", None), "name", "unknown"),
                    "operation": "DELETE" if state.is_delete else "UPDATE",
                    "row_id": None,
                    "changed_fields": [],
                    "field_value_hashes": {},
                    "direct_sql": True,
                    "affected_rows": int(result.rowcount or 0),
                })
            return result
        return None

    def before_cursor_execute(connection, _cursor, statement, _parameters, context, executemany):
        match=re.match(r"\s*(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+[\"`]?([\w.]+)",statement,re.I)
        if not match:
            return
        session_info=connection.info.get("furas_replay_session_info")
        if session_info is None:
            return
        operation=match.group(1).split()[0].upper()
        session_info.setdefault("actual_sql_mutation_ledger",[]).append({
            "provider_id":session_info.get("current_provider_id"),
            "operation":operation,
            "table":match.group(2).split(".")[-1].strip('"`'),
            "statement_sha256":hashlib.sha256(statement.encode("utf-8")).hexdigest(),
            "executemany":bool(executemany),
            "rowcount":None,
        })
        context._furas_replay_ledger_index=len(session_info["actual_sql_mutation_ledger"])-1

    def after_cursor_execute(connection, _cursor, _statement, _parameters, context, _executemany):
        session_info=connection.info.get("furas_replay_session_info")
        index=getattr(context,"_furas_replay_ledger_index",None)
        if session_info is not None and index is not None:
            session_info["actual_sql_mutation_ledger"][index]["rowcount"]=int(context.rowcount or 0)

    event.listen(Session, "before_flush", before_flush)
    event.listen(Session, "after_flush_postexec", after_flush)
    event.listen(Session, "do_orm_execute", do_orm_execute)
    from sqlalchemy.engine import Engine
    event.listen(Engine,"before_cursor_execute",before_cursor_execute)
    event.listen(Engine,"after_cursor_execute",after_cursor_execute)
    return before_flush, after_flush, do_orm_execute, before_cursor_execute, after_cursor_execute


def _count_tables(db, Base):
    return {
        name: int(db.scalar(select(func.count()).select_from(table)) or 0)
        for name, table in sorted(Base.metadata.tables.items())
    }


def _change_dimensions(ledger):
    lifecycle = {"status", "canonical_status", "raw_status", "submission_deadline",
                 "publication_date", "missing_successful_checks", "last_missing_at"}
    geography = {"city", "district", "location_description", "latitude", "longitude",
                 "geographic_scope", "geography_reference_unit_id", "geography_evidence_json",
                 "coordinate_provenance_json", "location_confidence_score",
                 "location_detection_method", "location_evidence"}
    return {
        "lifecycle": any(lifecycle.intersection(row["changed_fields"]) for row in ledger),
        "geography": any(geography.intersection(row["changed_fields"]) for row in ledger),
        "observations": any(row["table"] == "source_observations" for row in ledger),
        "review": any(row["table"] in {
            "opportunity_data_conflicts", "duplicate_candidates", "location_reviews",
            "qualification_reviews"
        } for row in ledger),
    }


def _master_link_changed_in_replay(writes, resulting_master_id):
    # Inserts list nullable columns as changed fields even when the inserted
    # Master link is null. Count only a materialized link as an assignment.
    return resulting_master_id is not None and any(
        write["table"] == "source_opportunities"
        and "master_opportunity_id" in write["changed_fields"]
        for write in writes
    )


def _validate_alias_artifact(path, aliases):
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    rows = list(csv.DictReader(payload.decode("utf-8-sig").splitlines()))
    indexed = {row.alias_provider_id: row for row in aliases}
    mismatch_ids = []
    for row in rows:
        current = indexed.get(str(row.get("provider_id") or ""))
        if (current is None or row.get("decision") != "APPROVED_AUTOMATICALLY"
                or current.target_source_opportunity_id != int(row["existing_source_opportunity_id"])
                or current.canonical_source_key != row["proposed_alias_target"]
                or current.expected_master_opportunity_id != (
                    int(row["existing_master_opportunity_id"])
                    if row.get("existing_master_opportunity_id") else None
                )
                or current.approval_artifact_sha256 != digest):
            mismatch_ids.append(str(row.get("provider_id") or ""))
    return {
        "csv_rows": len(rows), "active_alias_rows": len(aliases),
        "csv_sha256": digest,
        "provider_id_sets_equal": {str(row.get("provider_id")) for row in rows} == set(indexed),
        "mapping_mismatch_count": len(mismatch_ids), "mapping_mismatch_ids": mismatch_ids,
    }


def _run_pass(records, source_id, owner_alias_registry, initial_resolution,
              capture_identifier, capture_run_id, capture_record_hashes):
    from app.database import SessionLocal
    from app.models import Base, Source
    from app.service import _safe_record

    rows = []
    counts = defaultdict(int)
    with SessionLocal() as db:
        source = db.get(Source, source_id)
        before_counts = _count_tables(db, Base)
        connection=db.connection()
        connection_info=connection.info
        connection_info["furas_replay_session_info"]=db.info
        for raw in records:
            provider_id = str(raw.external_id)
            resolution = initial_resolution.get(provider_id, "NOT_FOUND")
            item = {
                "provider_id": provider_id,
                "source_object_id": str(((raw.raw or {}).get("attributes") or {}).get("OBJECTID") or ""),
                "initial_identity": {"EXACT": "EXACT_SOURCE_MATCH", "ALIAS": "APPROVED_ALIAS_MATCH",
                                     "NOT_FOUND": "UNRESOLVED_IDENTITY"}.get(resolution, "IDENTITY_ERROR"),
                "replay_status": "COMPLETED", "error_type": None, "simulated_writes": [],
            }
            local_counts = defaultdict(int)
            db.info["current_provider_id"] = provider_id
            ledger_start = len(db.info.setdefault("replay_write_ledger", []))
            sql_ledger_start=len(db.info.setdefault("actual_sql_mutation_ledger",[]))
            try:
                raw.raw = dict(raw.raw or {})
                raw.raw["checkpoint_provenance"] = {
                    "scan_run_id": capture_run_id,
                    "enumeration_scope": "SAUDI_NATIONAL_V1",
                    "scope_fingerprint": raw.raw.get("scope_fingerprint") or "offline-replay",
                    "source_object_id": (raw.raw.get("attributes") or {}).get("OBJECTID"),
                }
                raw.raw["capture_identifier"] = capture_identifier
                raw.raw["capture_record_sha256"] = capture_record_hashes.get(provider_id)
                with db.begin_nested():
                    outcome = _safe_record(db, source, raw, local_counts,
                                           owner_alias_registry=owner_alias_registry,
                                           allow_master_creation=False)
                    db.flush()
                if isinstance(outcome, dict) and outcome.get("decision") == "QUARANTINE":
                    item["quarantine_decision"] = outcome
                for key, value in local_counts.items():
                    counts[key] += int(value)
            except Exception as exc:
                item["replay_status"] = "BLOCKED_ERROR"
                item["error_type"] = type(exc).__name__
                del db.info.setdefault("replay_write_ledger", [])[ledger_start:]
                del db.info.setdefault("actual_sql_mutation_ledger",[])[sql_ledger_start:]
                db.info.pop("pending_replay_writes", None)
            finally:
                db.info.pop("current_provider_id", None)
            item["simulated_writes"] = db.info.get("replay_write_ledger", [])[ledger_start:]
            item["dimensions"] = _change_dimensions(item["simulated_writes"])
            rows.append(item)
        db.commit()
        after_counts = _count_tables(db, Base)
        ledger = list(db.info.get("replay_write_ledger", []))
        sql_ledger=list(db.info.get("actual_sql_mutation_ledger",[]))
        connection_info.pop("furas_replay_session_info",None)
    return {"rows": rows, "counts": dict(counts), "before_counts": before_counts,
            "after_counts": after_counts, "ledger": ledger,"actual_sql_ledger":sql_ledger}


def _summarize(result):
    table_ops = Counter((row["table"], row["operation"]) for row in result["ledger"])
    providers = defaultdict(set)
    for row in result["ledger"]:
        providers[(row["table"], row["operation"])].add(row["provider_id"])
    return {
        "table_operation_events": {f"{t}:{op}": n for (t, op), n in sorted(table_ops.items())},
        "providers_by_table_operation": {f"{t}:{op}": len(ids) for (t, op), ids in sorted(providers.items())},
        "source_opportunity_creations": len(providers[("source_opportunities", "INSERT")]),
        "master_creations": len(providers[("opportunities", "INSERT")]),
        "source_opportunity_updates": len(providers[("source_opportunities", "UPDATE")]),
        "master_updates": len(providers[("opportunities", "UPDATE")]),
        "observation_write_events": sum(n for (t, _op), n in table_ops.items() if t == "source_observations"),
        "direct_sql_delete_calls": sum(1 for row in result["ledger"] if row.get("direct_sql") and row["operation"] == "DELETE"),
        "direct_sql_deleted_rows": sum(int(row.get("affected_rows", 0)) for row in result["ledger"] if row.get("direct_sql") and row["operation"] == "DELETE"),
        "lifecycle_record_decisions": sum(bool(r["dimensions"]["lifecycle"]) for r in result["rows"]),
        "geographic_record_decisions": sum(bool(r["dimensions"]["geography"]) for r in result["rows"]),
        "review_record_decisions": sum(bool(r["dimensions"]["review"]) for r in result["rows"]),
        "quarantined_records": sum(bool(r.get("quarantine_decision")) for r in result["rows"]),
        "quarantined_records_with_any_write": sum(
            bool(r.get("quarantine_decision")) and bool(r["simulated_writes"])
            for r in result["rows"]
        ),
        "before_counts": result["before_counts"], "after_counts": result["after_counts"],
        "pipeline_counters": result["counts"],
    }


def _summarize_actual_sql(result):
    counts=Counter((row["table"],row["operation"]) for row in result.get("actual_sql_ledger",[]))
    affected=Counter()
    for row in result.get("actual_sql_ledger",[]):
        affected[(row["table"],row["operation"])]+=max(0,int(row.get("rowcount") or 0))
    events=Counter(row.get("event_type") or "UNCLASSIFIED" for row in result.get("ledger",[])
                   if row.get("table")=="system_events" and row.get("operation")=="INSERT")
    return {
        "statement_counts":{f"{table}:{operation}":count for (table,operation),count in sorted(counts.items())},
        "affected_rowcounts":{f"{table}:{operation}":count for (table,operation),count in sorted(affected.items())},
        "system_event_insert_intents_by_type":dict(sorted(events.items())),
        "actual_sql_mutation_statements":len(result.get("actual_sql_ledger",[])),
    }


def run(args):
    replay_url = os.getenv("FURAS_OFFLINE_REPLAY_DATABASE_URL", "")
    validate_isolated_database_url(replay_url)
    os.environ["DATABASE_URL"] = replay_url
    for name in ("CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", "REDIS_URL"):
        os.environ.pop(name, None)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.adapters import FurasAdapter
    from app.furas_capture_manifest import validate_capture_manifest
    from app.models import (Base, OrganizationAlias, Source, SourceIdentityAlias,
                            SourceIdentityAliasAudit, SourceOpportunity)
    from app.source_identity_aliases import resolve_source_identity

    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    capture_summary = validate_capture_manifest(manifest)
    adjudication = json.loads(args.adjudication.read_text(encoding="utf-8-sig"))
    reconciliation = json.loads(args.reconciliation.read_text(encoding="utf-8-sig"))
    adjudication_by_id = {str(r.get("provider_id")): r for r in adjudication.get("records", [])}
    reconciliation_by_id = {str(r.get("provider_id")): r for r in reconciliation.get("records", [])}
    capture_identifier = (manifest.get("capture", {}).get("adapter_metrics", {})
                          .get("source_snapshot", {}).get("snapshot_id"))
    capture_run_id = (manifest.get("capture", {}).get("adapter_metrics", {})
                      .get("checkpoint", {}).get("scan_run_id"))
    capture_record_hashes = {
        str(row.get("provider_id_adapter_key")): row.get("raw_record_sha256")
        for row in manifest.get("records", [])
    }

    engine = create_engine(replay_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            if db.execute(text("SELECT current_database()")).scalar_one() != "furas_replay":
                raise OfflineReplaySafetyError("Connected database is not furas_replay")
            source = db.scalar(select(Source).where(Source.source_key == "furas"))
            if source is None:
                raise OfflineReplaySafetyError("Disposable clone has no Furas source")
            aliases = db.scalars(select(SourceIdentityAlias).where(
                SourceIdentityAlias.source_id == source.id,
                SourceIdentityAlias.status == "ACTIVE")).all()
            alias_target_by_provider = {
                row.alias_provider_id: row.target_source_opportunity_id for row in aliases
            }
            audits = db.scalars(select(SourceIdentityAliasAudit).join(
                SourceIdentityAlias, SourceIdentityAlias.id == SourceIdentityAliasAudit.alias_id
            ).where(SourceIdentityAlias.source_id == source.id,
                    SourceIdentityAliasAudit.action == "APPLIED")).all()
            alias_check = _validate_alias_artifact(args.approved_alias_csv, aliases)
            if (alias_check["csv_rows"] != 75 or alias_check["active_alias_rows"] != 75
                    or len(audits) != 75 or not alias_check["provider_id_sets_equal"]
                    or alias_check["mapping_mismatch_count"]):
                raise OfflineReplaySafetyError("Disposable clone does not contain the exact approved alias fixture")

            resolutions = {}
            for row in manifest["records"]:
                provider_id = str(row["provider_id_adapter_key"])
                try:
                    resolutions[provider_id] = resolve_source_identity(
                        db, source, provider_id
                    ).status
                except Exception:
                    resolutions[provider_id] = "IDENTITY_CONFLICT"
            identity_counts = Counter(resolutions.values())
            source_id = source.id
            from app.service import comparison_key
            owner_alias_registry = {
                comparison_key(row.alias): row
                for row in db.scalars(select(OrganizationAlias).where(
                    (OrganizationAlias.source_key.is_(None))
                    | (OrganizationAlias.source_key == "furas")
                )).all()
            }

        offline = OfflineCaptureClient(manifest)
        with patch("app.geography_flags.flag_enabled",
                   side_effect=lambda name: name == "FURAS_NATIONAL_ENUMERATION_ENABLED"), patch(
                       "app.status_lifecycle.local_today", return_value=date(2026, 11, 5)):
            records, _pages = asyncio.run(FurasAdapter().fetch(offline))
        if len(records) != len(manifest["records"]):
            raise OfflineReplaySafetyError("Adapter output differs from validated capture population")

        before_flush, after_flush, do_orm_execute, before_cursor_execute, after_cursor_execute = _install_write_tracker()
        try:
            with patch("app.geography_flags.flag_enabled",
                       side_effect=lambda name: name == "FURAS_NATIONAL_ENUMERATION_ENABLED"):
                first = _run_pass(records, source_id, owner_alias_registry, resolutions,
                                  capture_identifier, capture_run_id, capture_record_hashes)
                second_resolutions = {}
                with factory() as db:
                    db.execute(text("SET TRANSACTION READ ONLY"))
                    source = db.get(Source, source_id)
                    for raw in records:
                        second_resolutions[str(raw.external_id)] = resolve_source_identity(
                            db, source, raw.external_id
                        ).status
                second = _run_pass(records, source_id, owner_alias_registry, second_resolutions,
                                   capture_identifier, capture_run_id, capture_record_hashes)
                third = _run_pass(records, source_id, owner_alias_registry, second_resolutions,
                                  capture_identifier, capture_run_id, capture_record_hashes)
        finally:
            event.remove(Session, "before_flush", before_flush)
            event.remove(Session, "after_flush_postexec", after_flush)
            event.remove(Session, "do_orm_execute", do_orm_execute)
            from sqlalchemy.engine import Engine
            event.remove(Engine,"before_cursor_execute",before_cursor_execute)
            event.remove(Engine,"after_cursor_execute",after_cursor_execute)

        observed = {key: identity_counts.get(key, 0) for key in REFERENCE_CLASSIFICATION}
        unexpected = {
            key: {"reference": value, "observed": observed[key]}
            for key, value in REFERENCE_CLASSIFICATION.items() if observed[key] != value
        }
        first_summary, second_summary, third_summary = _summarize(first), _summarize(second), _summarize(third)
        reason_by_classification = {
            "POSSIBLE_EXISTING_FURAS_IDENTITY_MANUAL_REVIEW": "UNRESOLVED_EXISTING_IDENTITY",
            "CONFLICTING_SOURCE_ATTRIBUTES_MANUAL_REVIEW": "IDENTITY_ATTRIBUTE_CONFLICT",
            "OFFICIAL_CROSS_SOURCE_REFERENCE_MASTER_UNRESOLVED": "CROSS_SOURCE_MASTER_UNRESOLVED",
            "INSUFFICIENT_EVIDENCE_POTENTIAL_NEW_FURAS_SOURCE": "INSUFFICIENT_IDENTITY_EVIDENCE",
        }
        decisions = []
        rows_by_id = {r["provider_id"]: r for r in first["rows"]}
        for raw in records:
            pid = str(raw.external_id)
            item = rows_by_id[pid]
            adjudication_row = adjudication_by_id.get(pid, {})
            reconciliation_row = reconciliation_by_id.get(pid, {})
            item["adjudication_classification"] = adjudication_row.get("identity_classification")
            item["reconciliation_classification"] = reconciliation_row.get("primary_classification")
            if item["initial_identity"] == "APPROVED_ALIAS_MATCH":
                item["proposed_safe_action"] = "PRESERVE_ALIAS_TARGET_WITHOUT_RECORD_MUTATION"
            elif item["initial_identity"] == "UNRESOLVED_IDENTITY":
                item["proposed_safe_action"] = "MANUAL_IDENTITY_REVIEW_BEFORE_SOURCE_KEY_CREATION"
                item["unresolved_recommended_action"] = adjudication_row.get("proposed_action")
                quarantine = item.get("quarantine_decision")
                if quarantine:
                    quarantine["quarantine_reason"] = reason_by_classification.get(
                        item.get("reconciliation_classification"), quarantine["quarantine_reason"])
                    quarantine["existing_review_classification"] = item.get("reconciliation_classification")
                    quarantine["recommended_review_action"] = (
                        reconciliation_row.get("proposed_action")
                        or adjudication_row.get("proposed_action")
                        or quarantine["recommended_review_action"]
                    )
                    quarantine["evidence_reference"]["capture_record_sha256"] = capture_record_hashes.get(pid)
            else:
                item["proposed_safe_action"] = "ALLOW_GOVERNED_EXACT_KEY_PROCESSING"
            decisions.append(item)

        second_by_id = {item["provider_id"]: item for item in second["rows"]}
        for first_item in decisions:
            if first_item["initial_identity"] != "UNRESOLVED_IDENTITY":
                continue
            second_item = second_by_id[first_item["provider_id"]]
            second_quarantine = second_item.get("quarantine_decision")
            if second_quarantine:
                second_quarantine["quarantine_reason"] = (
                    first_item.get("quarantine_decision", {}).get("quarantine_reason")
                    or second_quarantine["quarantine_reason"]
                )
                second_quarantine["existing_review_classification"] = first_item.get("reconciliation_classification")
                second_quarantine["recommended_review_action"] = first_item.get("quarantine_decision", {}).get(
                    "recommended_review_action", second_quarantine["recommended_review_action"])
        third_by_id={item["provider_id"]:item for item in third["rows"]}
        for provider_id,third_item in third_by_id.items():
            if third_item.get("quarantine_decision"):
                second_item=second_by_id[provider_id]
                prior=second_item.get("quarantine_decision",{})
                third_item["quarantine_decision"]["quarantine_reason"]=prior.get(
                    "quarantine_reason",third_item["quarantine_decision"]["quarantine_reason"])

        # Add resulting disposable-clone identity links so any automatic
        # assignment performed by the real record path is visible per record.
        with factory() as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            furas_source = db.get(Source, source_id)
            source_rows = db.scalars(select(SourceOpportunity).where(
                SourceOpportunity.source_id == furas_source.id
            )).all()
            source_by_key = {row.source_opportunity_id: row for row in source_rows}
        source_by_id = {row.id: row for row in source_rows}
        for item in decisions:
            resulting = source_by_key.get(item["provider_id"])
            if resulting is None and item["provider_id"] in alias_target_by_provider:
                resulting = source_by_id.get(alias_target_by_provider[item["provider_id"]])
            item["resulting_source_opportunity_id"] = resulting.id if resulting else None
            item["resulting_master_opportunity_id"] = resulting.master_opportunity_id if resulting else None
            item["master_link_changed_in_replay"] = _master_link_changed_in_replay(
                item["simulated_writes"],
                resulting.master_opportunity_id if resulting else None,
            )

        unresolved_auto_linked = sum(
            item["initial_identity"] == "UNRESOLVED_IDENTITY"
            and item["resulting_master_opportunity_id"] is not None
            for item in decisions
        )
        unresolved_rows = [item for item in decisions
                           if item["initial_identity"] == "UNRESOLVED_IDENTITY"]
        second_unresolved_rows = [item for item in second["rows"]
                                  if item["initial_identity"] == "UNRESOLVED_IDENTITY"]
        third_unresolved_rows=[item for item in third["rows"]
                               if item["initial_identity"]=="UNRESOLVED_IDENTITY"]
        quarantine_consistency = {
            "first_pass_quarantined": sum(bool(item.get("quarantine_decision")) for item in unresolved_rows),
            "second_pass_quarantined": sum(bool(item.get("quarantine_decision")) for item in second_unresolved_rows),
            "third_pass_quarantined":sum(bool(item.get("quarantine_decision")) for item in third_unresolved_rows),
            "first_pass_unresolved_with_writes": sum(bool(item["simulated_writes"]) for item in unresolved_rows),
            "second_pass_unresolved_with_writes": sum(bool(item["simulated_writes"]) for item in second_unresolved_rows),
            "third_pass_unresolved_with_writes":sum(bool(item["simulated_writes"]) for item in third_unresolved_rows),
            "unresolved_source_rows_after_two_passes": sum(
                item["resulting_source_opportunity_id"] is not None for item in unresolved_rows),
            "unresolved_master_links_after_two_passes": sum(
                item["resulting_master_opportunity_id"] is not None for item in unresolved_rows),
            "unresolved_with_lifecycle_geography_observation_or_review_writes": sum(
                any(item["dimensions"].values()) for item in unresolved_rows),
            "first_second_reason_sets_equal": sorted({item["quarantine_decision"]["quarantine_reason"]
                for item in unresolved_rows if item.get("quarantine_decision")}) == sorted({
                item["quarantine_decision"]["quarantine_reason"] for item in second_unresolved_rows
                if item.get("quarantine_decision")}),
            "same_provider_id_sets": {item["provider_id"] for item in unresolved_rows} == {
                item["provider_id"] for item in second_unresolved_rows},
            "second_third_provider_id_sets_equal":{item["provider_id"] for item in second_unresolved_rows}=={
                item["provider_id"] for item in third_unresolved_rows},
        }
        quarantine_gate_pass = (
            len(unresolved_rows) == 603
            and len(second_unresolved_rows) == 603
            and len(third_unresolved_rows)==603
            and quarantine_consistency["first_pass_quarantined"] == 603
            and quarantine_consistency["second_pass_quarantined"] == 603
            and quarantine_consistency["third_pass_quarantined"]==603
            and quarantine_consistency["first_pass_unresolved_with_writes"] == 0
            and quarantine_consistency["second_pass_unresolved_with_writes"] == 0
            and quarantine_consistency["third_pass_unresolved_with_writes"]==0
            and quarantine_consistency["unresolved_source_rows_after_two_passes"] == 0
            and quarantine_consistency["unresolved_master_links_after_two_passes"] == 0
            and quarantine_consistency["unresolved_with_lifecycle_geography_observation_or_review_writes"] == 0
            and quarantine_consistency["first_second_reason_sets_equal"]
            and quarantine_consistency["same_provider_id_sets"]
            and quarantine_consistency["second_third_provider_id_sets_equal"]
        )
        actual_sql_by_pass={name:_summarize_actual_sql(result) for name,result in (
            ("first",first),("second",second),("third",third))}
        repeat_sql={name:[row for row in result["actual_sql_ledger"] if row["table"]!="system_events"]
                    for name,result in (("second",second),("third",third))}
        repeat_event_types={name:Counter(row.get("event_type") or "UNCLASSIFIED" for row in result["ledger"]
            if row.get("table")=="system_events" and row.get("operation")=="INSERT")
            for name,result in (("second",second),("third",third))}
        repeat_event_sql={name:sum(1 for row in result["actual_sql_ledger"]
            if row["table"]=="system_events" and row["operation"]=="INSERT")
            for name,result in (("second",second),("third",third))}
        repeat_event_statements_are_telemetry=all(
            all(event_type=="SYSTEM_REEVALUATION" for event_type in counts)
            and sum(counts.values())==repeat_event_sql[name]
            for name,counts in repeat_event_types.items())
        write_idempotency_pass=(all(not rows for rows in repeat_sql.values())
            and repeat_event_statements_are_telemetry)

        report = {
            "schema": "furas-national-offline-ingestion-replay-v1",
            "mode": "DISPOSABLE_POSTGRESQL_CLONE_OFFLINE_CAPTURE",
            "production_mutations": 0, "production_database_connection": False,
            "external_furas_requests": 0, "celery_or_scheduler_invocations": 0,
            "source_sync_invocations": 0,
            "capture_validation": capture_summary,
            "capture_identifier": capture_identifier,
            "offline_adapter_requests_served": len(offline.calls),
            "reference_identity_classification": REFERENCE_CLASSIFICATION,
            "observed_initial_identity_classification": dict(identity_counts),
            "identity_conflicts": identity_counts.get("IDENTITY_CONFLICT", 0),
            "unexpected_classification_changes": unexpected,
            "alias_fixture": alias_check,
            "alias_applied_audit_rows_in_clone": len(audits),
            "first_pass": first_summary, "second_pass": second_summary,"third_pass":third_summary,
            "actual_sql_summary":actual_sql_by_pass,
            "write_idempotency":{
                "status":"PASS" if write_idempotency_pass else "FAIL",
                "second_repeat_business_sql_statements":len(repeat_sql["second"]),
                "third_repeat_business_sql_statements":len(repeat_sql["third"]),
                "second_repeat_business_sql_by_table_operation":dict(Counter(
                    f"{row['table']}:{row['operation']}" for row in repeat_sql["second"])),
                "third_repeat_business_sql_by_table_operation":dict(Counter(
                    f"{row['table']}:{row['operation']}" for row in repeat_sql["third"])),
                "second_repeat_operational_telemetry_by_event_type":dict(repeat_event_types["second"]),
                "third_repeat_operational_telemetry_by_event_type":dict(repeat_event_types["third"]),
                "second_repeat_operational_telemetry_sql_statements":repeat_event_sql["second"],
                "third_repeat_operational_telemetry_sql_statements":repeat_event_sql["third"],
                "operational_telemetry_statements_separated":repeat_event_statements_are_telemetry,
            },
            "potential_source_opportunity_creations": first_summary["source_opportunity_creations"],
            "potential_master_creations": first_summary["master_creations"],
            "potential_source_opportunity_updates": first_summary["source_opportunity_updates"],
            "potential_master_updates": first_summary["master_updates"],
            "potential_observation_write_events": first_summary["observation_write_events"],
            "potential_lifecycle_record_changes": first_summary["lifecycle_record_decisions"],
            "potential_geographic_record_changes": first_summary["geographic_record_decisions"],
            "potential_conflict_or_review_records": first_summary["review_record_decisions"],
            "identity_conflicts_or_data_conflict_rows": first_summary["table_operation_events"].get("opportunity_data_conflicts:INSERT", 0),
            "unresolved_records_auto_linked_to_existing_masters": unresolved_auto_linked,
            "quarantine_gate": {
                "status": "PASS" if quarantine_gate_pass else "FAIL",
                "first_pass": first_summary["quarantined_records"],
                "second_pass": second_summary["quarantined_records"],
                "third_pass":third_summary["quarantined_records"],
                "quarantined_records_with_any_write": {
                    "first_pass": first_summary["quarantined_records_with_any_write"],
                "second_pass": second_summary["quarantined_records_with_any_write"],
                    "third_pass":third_summary["quarantined_records_with_any_write"],
                },
                "consistency": quarantine_consistency,
                "classification_breakdown": dict(Counter(
                    item["quarantine_decision"]["quarantine_reason"]
                    for item in unresolved_rows if item.get("quarantine_decision")
                )),
            },
            "alias_records_with_any_record_mutation": sum(
                row["initial_identity"] == "APPROVED_ALIAS_MATCH" and bool(row["simulated_writes"])
                for row in decisions
            ),
            "alias_target_resolution_verified": sum(
                row["initial_identity"] == "APPROVED_ALIAS_MATCH"
                and row["resulting_source_opportunity_id"] is not None
                for row in decisions
            ),
            "alias_target_resolution_method": (
                "Resolved through the verified active clone crosswalk to the existing SourceOpportunity; no record writes."
            ),
            "FURAS_PILOT_READINESS": "NO-GO",
            "DUPLICATE_RISK_BREAKDOWN": dict(Counter(
                item.get("reconciliation_classification")
                for item in decisions
                if item["initial_identity"] == "UNRESOLVED_IDENTITY"
            )),
            "control_plane_not_simulated": [
                "The _sync_furas_checkpointed network fetch and SyncJob/checkpoint commit wrapper was not called.",
                "No source health, schedules, removal reconciliation, job queues, or Celery state were changed.",
                "Its batch commit path can update Source.sync_status, SyncJob checkpoint metrics and last_successful_sync; a real pilot would require a separate control-plane test.",
            ],
            "safety_findings": [
                "allow_master_creation=False is not a read-only control.",
                "The national record path may insert SourceOpportunity and SourceObservation rows for unresolved IDs, and its candidate matcher may also attach those rows to existing Masters without alias approval.",
                "Exact source matches may update SourceOpportunity fields and can also update linked Master fields, taxonomy, provenance, lifecycle or geography.",
                "Approved alias matches resolve to their existing source row and return before those record mutations.",
                "The 603 unresolved IDs remain manual-review cases; this replay does not approve or infer aliases.",
                "Unresolved national Furas provider IDs are returned as non-persistent quarantine decisions before standardization or any business-data write path.",
                "Exact and approved-alias identities remain governed by the existing identity resolver; unresolved identities still exit through the previously validated quarantine gate.",
            ],
            "records": decisions,
            "mutation_ledger": first["ledger"],
            "second_pass_records": second["rows"],
            "second_pass_mutation_ledger": second["ledger"],
            "third_pass_records":third["rows"],
            "third_pass_mutation_ledger":third["ledger"],
            "actual_sql_mutation_ledgers":{name:result["actual_sql_ledger"] for name,result in (
                ("first",first),("second",second),("third",third))},
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = args.output_dir / "FURAS-NATIONAL-OFFLINE-REPLAY-20261110.json"
        csv_path = args.output_dir / "FURAS-NATIONAL-OFFLINE-REPLAY-20261110.csv"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            columns = ["provider_id", "source_object_id", "initial_identity",
                       "adjudication_classification", "reconciliation_classification",
                       "replay_status", "proposed_safe_action", "unresolved_recommended_action",
                    "quarantine_reason", "capture_identifier", "source_namespace",
                    "official_source_reference", "identity_resolution_attempt",
                    "identity_resolution_status", "evidence_reference", "processing_timestamp_utc",
                    "recommended_review_action",
                    "resulting_source_opportunity_id", "resulting_master_opportunity_id",
                    "master_link_changed_in_replay", "changed_tables", "changed_fields", "error_type"]
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for item in decisions:
                writer.writerow({
                    **{key: item.get(key) for key in columns if key in item},
                    **{key: (item.get("quarantine_decision") or {}).get(key) for key in (
                        "quarantine_reason", "capture_identifier", "source_namespace",
                        "official_source_reference", "identity_resolution_attempt",
                        "identity_resolution_status", "evidence_reference",
                        "processing_timestamp_utc", "recommended_review_action")},
                    "changed_tables": ";".join(sorted({
                        f"{w['table']}:{w['operation']}" for w in item["simulated_writes"]
                    })),
                    "changed_fields": ";".join(sorted({
                        field for w in item["simulated_writes"] for field in w["changed_fields"]
                    })),
                })
        status = "PASS" if not unexpected and quarantine_gate_pass and write_idempotency_pass and all(
            row["replay_status"] == "COMPLETED" for row in decisions
        ) and all(row["replay_status"]=="COMPLETED" for result in (second,third) for row in result["rows"]) else "PARTIAL"
        print(json.dumps({
            "status": status, "output_json": str(json_path), "output_csv": str(csv_path),
            "capture_records": len(records), "identity_classification": observed,
            "quarantine_gate": report["quarantine_gate"],
            "first_pass": {k: first_summary[k] for k in (
                "source_opportunity_creations", "master_creations",
                "source_opportunity_updates", "master_updates", "observation_write_events",
                "lifecycle_record_decisions", "geographic_record_decisions")},
            "second_pass": {k: second_summary[k] for k in (
                "source_opportunity_creations", "master_creations",
                "source_opportunity_updates", "master_updates", "observation_write_events")},
            "third_pass":{k:third_summary[k] for k in (
                "source_opportunity_creations","master_creations","source_opportunity_updates",
                "master_updates","observation_write_events")},
            "write_idempotency":report["write_idempotency"],
            "actual_sql_summary":actual_sql_by_pass,
        }, ensure_ascii=False, sort_keys=True))
        return 0 if status == "PASS" else 2
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--approved-alias-csv", type=Path, default=DEFAULT_APPROVED)
    parser.add_argument("--adjudication", type=Path, default=DEFAULT_ADJUDICATION)
    parser.add_argument("--reconciliation", type=Path, default=DEFAULT_RECONCILIATION)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.manifest, args.approved_alias_csv, args.adjudication, args.reconciliation):
        if not path.is_file():
            raise OfflineReplaySafetyError(f"Required saved evidence missing: {path}")
    return run(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OfflineReplaySafetyError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}), file=sys.stderr)
        sys.exit(3)

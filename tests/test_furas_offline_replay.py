from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, delete, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from scripts.dry_run_furas_national_offline_replay import (
    OfflineCaptureClient,
    OfflineReplaySafetyError,
    _change_dimensions,
    _install_write_tracker,
    _master_link_changed_in_replay,
    validate_isolated_database_url,
)


def test_replay_url_accepts_only_named_disposable_postgres():
    url = validate_isolated_database_url(
        "postgresql+psycopg://offline@furas-replay-db:5432/furas_replay"
    )
    assert url.database == "furas_replay"
    for forbidden in (
        "postgresql://user@localhost/production",
        "postgresql://user@prod-db/furas_replay",
        "sqlite:///production.db",
        "postgresql://user@furas-replay-db/other",
    ):
        with pytest.raises(OfflineReplaySafetyError):
            validate_isolated_database_url(forbidden)


def test_offline_capture_client_serves_only_saved_manifest_features():
    manifest = {
        "capture": {},
        "records": [{
            "source_endpoint": "https://example.invalid/MapServer/0",
            "objectid_raw": 44,
            "raw_payload": {"attributes": {"OBJECTID": 44, "OPPORTUNITYID": "furas-44"},
                            "geometry": {"x": 1, "y": 2}},
        }],
    }
    client = OfflineCaptureClient(manifest)

    async def replay():
        config = await client.get("https://example.invalid/config.json")
        metadata = await client.get("https://example.invalid/proxy?metadata")
        count = await client.get("https://example.invalid/query?returnCountOnly=true")
        ids = await client.get("https://example.invalid/query?returnIdsOnly=true")
        features = await client.get("https://example.invalid/query?objectIds=44")
        return config.json(), metadata.json(), count.json(), ids.json(), features.json()

    config, metadata, count, ids, features = asyncio.run(replay())
    assert config["gisLayerIndex"]["investmentMapServerInvestmentP"] == "0"
    assert metadata["objectIdField"] == "OBJECTID"
    assert count["count"] == 1
    assert ids["objectIds"] == [44]
    assert features["features"][0]["attributes"]["OPPORTUNITYID"] == "furas-44"
    assert len(client.calls) == 5

    with pytest.raises(OfflineReplaySafetyError, match="Uncaptured OBJECTID"):
        asyncio.run(client.get("https://example.invalid/query?objectIds=999"))


def test_write_ledger_dimensions_distinguish_lifecycle_geography_and_observations():
    ledger = [
        {"table": "source_opportunities", "changed_fields": ["canonical_status"]},
        {"table": "opportunity_locations", "changed_fields": ["location_name"]},
        {"table": "source_observations", "changed_fields": ["content_hash"]},
    ]
    assert _change_dimensions(ledger) == {
        "lifecycle": True, "geography": False, "observations": True, "review": False,
    }
    geo = [{"table": "opportunities", "changed_fields": ["latitude", "longitude"]}]
    assert _change_dimensions(geo)["geography"] is True


def test_null_inserted_master_link_is_not_reported_as_an_assignment():
    writes = [{"table": "source_opportunities", "changed_fields": ["master_opportunity_id"]}]
    assert _master_link_changed_in_replay(writes, None) is False
    assert _master_link_changed_in_replay(writes, 321) is True


def test_write_ledger_captures_bulk_sql_deletes():
    class MiniBase(DeclarativeBase):
        pass

    class MiniRow(MiniBase):
        __tablename__ = "offline_replay_tracker_fixture"
        id: Mapped[int] = mapped_column(primary_key=True)

    engine = create_engine("sqlite://")
    MiniBase.metadata.create_all(engine)
    before_flush, after_flush, do_orm_execute, before_cursor_execute, after_cursor_execute = _install_write_tracker()
    try:
        with Session(engine) as db:
            connection=db.connection()
            connection.info["furas_replay_session_info"]=db.info
            db.add(MiniRow())
            db.commit()
            db.info["current_provider_id"] = "saved-provider-id"
            db.execute(delete(MiniRow).where(MiniRow.id == 1))
            writes = db.info["replay_write_ledger"]
            assert writes == [{
                "provider_id": "saved-provider-id",
                "table": "offline_replay_tracker_fixture",
                "operation": "DELETE",
                "row_id": None,
                "changed_fields": [],
                "field_value_hashes": {},
                "direct_sql": True,
                "affected_rows": 1,
            }]
            assert db.info["actual_sql_mutation_ledger"][-1]["operation"]=="DELETE"
            assert db.info["actual_sql_mutation_ledger"][-1]["table"]=="offline_replay_tracker_fixture"
            assert db.info["actual_sql_mutation_ledger"][-1]["rowcount"]==1
    finally:
        event.remove(Session, "before_flush", before_flush)
        event.remove(Session, "after_flush_postexec", after_flush)
        event.remove(Session, "do_orm_execute", do_orm_execute)
        from sqlalchemy.engine import Engine
        event.remove(Engine,"before_cursor_execute",before_cursor_execute)
        event.remove(Engine,"after_cursor_execute",after_cursor_execute)
        engine.dispose()


def test_concurrent_replay_of_same_known_furas_record_is_write_idempotent():
    url=os.getenv("FURAS_OFFLINE_REPLAY_DATABASE_URL")
    if not url:
        pytest.skip("FURAS_OFFLINE_REPLAY_DATABASE_URL is not configured for isolated concurrent replay")
    validate_isolated_database_url(url)
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from app.adapters import FurasAdapter
    from app.models import Source, SourceOpportunity
    from app.service import _safe_record

    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/"docs/validation/deployment/nationwide-source-expansion/FURAS-NATIONAL-DURABLE-CAPTURE-MANIFEST-20261105.json").read_text(encoding="utf-8-sig"))
    records,_=asyncio.run(FurasAdapter().fetch(OfflineCaptureClient(manifest)))
    capture_identifier=(manifest.get("capture",{}).get("adapter_metrics",{}).get("source_snapshot",{}).get("snapshot_id"))
    capture_run_id=(manifest.get("capture",{}).get("adapter_metrics",{}).get("checkpoint",{}).get("scan_run_id"))
    capture_hashes={str(row.get("provider_id_adapter_key")):row.get("raw_record_sha256")
                    for row in manifest.get("records",[])}
    engine=create_engine(url,pool_size=5,max_overflow=0)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    try:
        with factory() as db:
            source=db.scalar(select(Source).where(Source.source_key=="furas"))
            existing_rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id,
                SourceOpportunity.master_opportunity_id.is_not(None)).order_by(SourceOpportunity.id)).all()
        raw_by_id={str(item.external_id):item for item in records}

        # Bring one bounded existing record in the disposable restore to the
        # saved capture before measuring duplicate replay writes. The restore
        # can be newer than this offline manifest; that first reconciliation
        # is setup, not part of the concurrency assertion. This is deliberately
        # one known record, never a replay of the national manifest.
        existing=next((row for row in existing_rows if row.source_opportunity_id in raw_by_id),None)
        assert existing is not None, "No captured Furas record matches an existing linked test row"
        raw=copy.deepcopy(raw_by_id[existing.source_opportunity_id])
        raw.raw=dict(raw.raw or {})
        raw.raw["checkpoint_provenance"]={"scan_run_id":capture_run_id,"enumeration_scope":"SAUDI_NATIONAL_V1",
            "scope_fingerprint":raw.raw.get("scope_fingerprint") or "offline-replay",
            "source_object_id":(raw.raw.get("attributes") or {}).get("OBJECTID")}
        raw.raw["capture_identifier"]=capture_identifier
        raw.raw["capture_record_sha256"]=capture_hashes.get(existing.source_opportunity_id)
        with patch("app.geography_flags.flag_enabled",side_effect=lambda name:False), \
                patch("app.status_lifecycle.local_today",return_value=date(2026,11,5)):
            with factory() as db:
                source=db.scalar(select(Source).where(Source.source_key=="furas"))
                with db.begin_nested():
                    _safe_record(db,source,raw,defaultdict(int),allow_master_creation=False)
                    db.flush()
                db.commit()

        statements=[]
        def capture(_connection,_cursor,statement,_parameters,_context,_executemany):
            match=re.match(r"\s*(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+[\"`]?([\w.]+)",statement,re.I)
            if match: statements.append((match.group(1).split()[0].upper(),match.group(2).split(".")[-1].strip('"`')))
        event.listen(engine,"before_cursor_execute",capture)
        barrier=Barrier(2)
        def process_once():
            with factory() as db:
                source=db.scalar(select(Source).where(Source.source_key=="furas"))
                barrier.wait(timeout=20)
                with db.begin_nested():
                    outcome=_safe_record(db,source,copy.deepcopy(raw),defaultdict(int),allow_master_creation=False)
                    db.flush()
                db.commit()
                return outcome.id if outcome is not None else existing.id
        try:
            with patch("app.geography_flags.flag_enabled",side_effect=lambda name:False), \
                    patch("app.status_lifecycle.local_today",return_value=date(2026,11,5)):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    outcomes=list(executor.map(lambda _index:process_once(),range(2)))
        finally:
            event.remove(engine,"before_cursor_execute",capture)
        assert outcomes==[existing.id,existing.id]
        assert statements==[]
    finally:
        engine.dispose()

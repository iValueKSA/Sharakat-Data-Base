from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (Base, Opportunity, Source, SourceIdentityAlias, SourceIdentityAliasAudit,
                        SourceObservation, SourceOpportunity)
from app.source_identity_aliases import (SourceIdentityAliasError, apply_approved_alias_batch,
                                         resolve_source_identity, rollback_alias_batch)


NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
ARTIFACT_SHA = "c" * 64


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def _enable_fks(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    result = sessionmaker(bind=engine, expire_on_commit=False)
    yield result
    engine.dispose()


def add_pair(db, *, source=None, key="old-furas-key", master_name="A"):
    source = source or Source(source_key="furas", source_name_ar="فرص", organization_name="جهة",
        base_url="https://furas.example", opportunities_url="https://furas.example/list", priority=1)
    if source.id is None:
        db.add(source)
        db.flush()
    common = dict(city="الأحساء", status="متاحة", location_confidence_score=.9,
        location_detection_method="fixture", location_evidence="fixture", data_quality_score=.9,
        manual_review_required=False, first_seen_at=NOW, last_seen_at=NOW,
        last_updated_at=NOW, created_at=NOW, updated_at=NOW)
    master = Opportunity(canonical_id=f"F-{master_name}", title_ar=f"فرصة {master_name}",
        normalized_title=f"فرصة {master_name}", primary_publication_platform="فرص", **common)
    db.add(master); db.flush()
    record = SourceOpportunity(source_id=source.id, master_opportunity_id=master.id,
        source_opportunity_id=key, source_reference_number=key, source_reference_number_normalized=key,
        source_title=f"فرصة {master_name}", normalized_source_title=f"فرصة {master_name}",
        source_url=f"https://furas.example/opportunity/{key}", source_owner="جهة", raw_location="الأحساء",
        raw_dates={}, raw_status="Announced", canonical_status="متاحة", raw_data_json={"attributes":{"OPPORTUNITYID":key}},
        standardized_data_json={}, standardization_version="test-v1", first_seen_at=NOW, last_seen_at=NOW,
        content_hash=("d" if master_name == "A" else "e")*64, parser_version="test-v1")
    db.add(record); db.flush()
    return source, master, record


def decision(record, master, provider="new-provider-id", *, source_key="furas"):
    return {"provider_id":provider, "decision":"APPROVED_AUTOMATICALLY",
        "proposed_alias_target":record.source_opportunity_id,
        "existing_source_opportunity_id":record.id,
        "existing_master_opportunity_id":master.id,
        "official_reference":provider,
        "processing_timestamp_utc":NOW.isoformat(),
        "approval_method":"EVIDENCE_BASED_AUTOMATED_VALIDATION",
        "approval_authority":"USER_AUTHORIZED_AUTOMATED_PROCESS",
        "identity_policy_version":"FURAS_IDENTITY_ALIAS_RULESET_V1.0.0",
        "decision_fingerprint_sha256":"a"*64,
        "evidence_references":{"record_sha256":"b"*64,
            "investsaudi_official_number":provider,"source_namespace":source_key}}


def apply(factory, row, *, count=1, batch="batch-1", source_key="furas"):
    with factory() as db:
        return apply_approved_alias_batch(db, source_key, row if isinstance(row,list) else [row],
            expected_count=count, application_batch_id=batch,
            approved_artifact_reference="approved.csv", approved_artifact_sha256=ARTIFACT_SHA)


def test_valid_alias_application_resolves_existing_row_without_business_mutations(factory):
    with factory() as db:
        source, master, record = add_pair(db)
        db.add(SourceObservation(source_opportunity_id=record.id, dataset_name="fixture",
            endpoint=record.source_url, official_source_id_original=record.source_opportunity_id,
            official_source_id_normalized=record.source_opportunity_id, raw_data_json={"version":1},
            content_hash="f"*64, first_seen_at=NOW, last_seen_at=NOW))
        db.commit(); ids=(source.id, master.id, record.id)
    result=apply(factory, decision(record,master))
    assert result["applied_count"]==1
    with factory() as db:
        source=db.get(Source,ids[0]); master=db.get(Opportunity,ids[1]); record=db.get(SourceOpportunity,ids[2])
        resolved=resolve_source_identity(db,source,"new-provider-id")
        assert resolved.status=="ALIAS" and resolved.record.id==ids[2]
        assert resolved.record.source_opportunity_id=="old-furas-key"
        assert resolved.record.master_opportunity_id==ids[1]
        assert master.canonical_id=="F-A" and master.merged_into_id is None
        assert db.scalar(select(func.count(SourceOpportunity.id)))==1
        assert db.scalar(select(func.count(SourceObservation.id)))==1
        assert db.scalar(select(func.count(SourceIdentityAliasAudit.id)))==1
        db.delete(record)
        with pytest.raises(IntegrityError): db.commit()


def test_exact_source_key_remains_first_class_and_unsupported_key_is_unresolved(factory):
    with factory() as db:
        source, master, record=add_pair(db); db.commit()
    with factory() as db:
        source=db.get(Source,source.id)
        assert resolve_source_identity(db,source,"old-furas-key").status=="EXACT"
        assert resolve_source_identity(db,source,"unapproved-provider-id").status=="NOT_FOUND"


def test_application_is_idempotent_across_retries_and_batch_ids(factory):
    with factory() as db:
        _,master,record=add_pair(db);db.commit()
    row=decision(record,master)
    assert apply(factory,row,batch="batch-a")["applied_count"]==1
    again=apply(factory,row,batch="batch-b")
    assert again["applied_count"]==0 and again["idempotent_count"]==1
    with factory() as db:
        assert db.scalar(select(func.count(SourceIdentityAlias.id)))==1
        assert db.scalar(select(func.count(SourceIdentityAliasAudit.id)))==1


def test_conflicting_reassignment_rejects_whole_batch_atomically(factory):
    with factory() as db:
        source,master1,record1=add_pair(db,key="old-1",master_name="A")
        _,master2,record2=add_pair(db,source=source,key="old-2",master_name="B")
        db.commit()
    first=decision(record1,master1,"alias-1")
    apply(factory,first,batch="batch-original")
    new_row=decision(record2,master2,"alias-2")
    conflict=decision(record2,master2,"alias-1")
    with factory() as db, pytest.raises(SourceIdentityAliasError,match="conflicting assignment"):
        apply_approved_alias_batch(db,"furas",[new_row,conflict],expected_count=2,
            application_batch_id="batch-conflict",approved_artifact_reference="approved.csv",
            approved_artifact_sha256=ARTIFACT_SHA)
    with factory() as db:
        assert db.scalar(select(func.count(SourceIdentityAlias.id)))==1
        assert db.scalar(select(SourceIdentityAlias).where(SourceIdentityAlias.alias_provider_id=="alias-1")).target_source_opportunity_id==record1.id
        assert db.scalar(select(SourceIdentityAlias.id).where(SourceIdentityAlias.alias_provider_id=="alias-2")) is None


def test_missing_target_and_incomplete_batch_fail_closed(factory):
    with factory() as db:
        _,master,record=add_pair(db);db.commit()
    absent=decision(record,master,"missing-target");absent["existing_source_opportunity_id"]=999999
    with factory() as db, pytest.raises(SourceIdentityAliasError,match="missing SourceOpportunity"):
        apply_approved_alias_batch(db,"furas",[absent],expected_count=1,application_batch_id="missing",
            approved_artifact_reference="approved.csv",approved_artifact_sha256=ARTIFACT_SHA)
    with factory() as db, pytest.raises(SourceIdentityAliasError,match="Incomplete alias batch"):
        apply_approved_alias_batch(db,"furas",[decision(record,master)],expected_count=75,application_batch_id="partial",
            approved_artifact_reference="approved.csv",approved_artifact_sha256=ARTIFACT_SHA)


def test_wrong_namespace_is_rejected_before_assignment(factory):
    with factory() as db:
        furas,master,record=add_pair(db)
        other,master2,other_record=add_pair(db,source=Source(source_key="other-source",source_name_ar="مصدر",organization_name="جهة",
            base_url="https://other.example",opportunities_url="https://other.example/list",priority=2),key="other-key",master_name="B")
        db.commit()
    with factory() as db, pytest.raises(SourceIdentityAliasError,match="outside the namespace"):
        apply_approved_alias_batch(db,"furas",[decision(other_record,master2,"wrong-namespace")],expected_count=1,
            application_batch_id="wrong-namespace",approved_artifact_reference="approved.csv",approved_artifact_sha256=ARTIFACT_SHA)


def test_existing_canonical_key_collision_is_rejected(factory):
    with factory() as db:
        source,master,record=add_pair(db,key="canonical-key",master_name="A")
        _,master2,record2=add_pair(db,source=source,key="collision-key",master_name="B")
        db.commit()
    row=decision(record,master,"collision-key")
    with factory() as db, pytest.raises(SourceIdentityAliasError,match="collides with an existing canonical"):
        apply_approved_alias_batch(db,"furas",[row],expected_count=1,application_batch_id="canonical-collision",
            approved_artifact_reference="approved.csv",approved_artifact_sha256=ARTIFACT_SHA)


def test_database_constraints_reject_duplicate_alias_and_cross_namespace_target(factory):
    with factory() as db:
        source,master,record=add_pair(db,key="furas-key",master_name="A")
        other,master2,other_record=add_pair(db,source=Source(source_key="other",source_name_ar="مصدر",organization_name="جهة",
            base_url="https://other.example",opportunities_url="https://other.example/list",priority=2),key="other-key",master_name="B")
        db.commit(); sid=source.id; oid=other.id; rid=record.id; mid=master.id; rid2=other_record.id; mid2=master2.id
    apply(factory,decision(record,master,"db-unique"))
    with factory() as db:
        alias=db.scalar(select(SourceIdentityAlias).where(SourceIdentityAlias.alias_provider_id=="db-unique"))
        duplicate=SourceIdentityAlias(source_id=sid,source_namespace="furas",alias_provider_id="db-unique",
            target_source_opportunity_id=rid,canonical_source_key="furas-key",expected_master_opportunity_id=mid,
            evidence_reference_json={},approval_artifact_reference="a",approval_artifact_sha256=ARTIFACT_SHA,
            approval_decision_fingerprint="e"*64,approval_method="EVIDENCE_BASED_AUTOMATED_VALIDATION",
            approval_authority="USER_AUTHORIZED_AUTOMATED_PROCESS",approval_timestamp=NOW,application_timestamp=NOW,
            application_batch_id="dup",status="ACTIVE",audit_metadata_json={},created_at=NOW)
        db.add(duplicate)
        with pytest.raises(IntegrityError): db.flush()
        db.rollback()
    with factory() as db:
        invalid=SourceIdentityAlias(source_id=sid,source_namespace="furas",alias_provider_id="cross-ns",
            target_source_opportunity_id=rid2,canonical_source_key="other-key",expected_master_opportunity_id=mid2,
            evidence_reference_json={},approval_artifact_reference="a",approval_artifact_sha256=ARTIFACT_SHA,
            approval_decision_fingerprint="f"*64,approval_method="EVIDENCE_BASED_AUTOMATED_VALIDATION",
            approval_authority="USER_AUTHORIZED_AUTOMATED_PROCESS",approval_timestamp=NOW,application_timestamp=NOW,
            application_batch_id="cross",status="ACTIVE",audit_metadata_json={},created_at=NOW)
        db.add(invalid)
        with pytest.raises(IntegrityError): db.flush()
        db.rollback()
    with factory() as db:
        invalid_namespace=SourceIdentityAlias(source_id=sid,source_namespace="other",alias_provider_id="wrong-namespace",
            target_source_opportunity_id=rid,canonical_source_key="furas-key",expected_master_opportunity_id=mid,
            evidence_reference_json={},approval_artifact_reference="a",approval_artifact_sha256=ARTIFACT_SHA,
            approval_decision_fingerprint="1"*64,approval_method="EVIDENCE_BASED_AUTOMATED_VALIDATION",
            approval_authority="USER_AUTHORIZED_AUTOMATED_PROCESS",approval_timestamp=NOW,application_timestamp=NOW,
            application_batch_id="wrong-namespace",status="ACTIVE",audit_metadata_json={},created_at=NOW)
        db.add(invalid_namespace)
        with pytest.raises(IntegrityError): db.flush()


def test_inactive_alias_and_changed_master_relationship_fail_resolution(factory):
    with factory() as db:
        _,master,record=add_pair(db);db.commit(); target_id=record.id; master_id=master.id
    apply(factory,decision(record,master,"retired-alias"))
    with factory() as db:
        other_master=Opportunity(canonical_id="F-B",title_ar="B",normalized_title="b",primary_publication_platform="ف",
            city="الأحساء",status="متاحة",location_confidence_score=.9,location_detection_method="f",location_evidence="f",
            data_quality_score=.9,manual_review_required=False,first_seen_at=NOW,last_seen_at=NOW,last_updated_at=NOW,created_at=NOW,updated_at=NOW)
        db.add(other_master);db.flush();db.get(Opportunity,master_id).merged_into_id=other_master.id;db.commit()
    with factory() as db:
        source=db.scalar(select(Source).where(Source.source_key=="furas"))
        with pytest.raises(SourceIdentityAliasError,match="Master is missing or merged"):
            resolve_source_identity(db,source,"retired-alias")


def test_rollback_deactivates_without_deleting_and_is_idempotent(factory):
    with factory() as db:
        source,master,record=add_pair(db);db.commit(); source_id=source.id;record_id=record.id;master_id=master.id
    apply(factory,decision(record,master,"rollback-me"),batch="batch-to-rollback")
    with factory() as db:
        result=rollback_alias_batch(db,"furas","batch-to-rollback",expected_count=1,
            rollback_batch_id="rollback-1",reason="isolated rollback test")
        assert result["rolled_back_count"]==1
    with factory() as db:
        alias=db.scalar(select(SourceIdentityAlias).where(SourceIdentityAlias.alias_provider_id=="rollback-me"))
        assert alias.status=="INACTIVE" and alias.deactivation_reason=="isolated rollback test"
        assert db.get(SourceOpportunity,record_id).source_opportunity_id=="old-furas-key"
        assert db.get(SourceOpportunity,record_id).master_opportunity_id==master_id
        source=db.get(Source,source_id)
        with pytest.raises(SourceIdentityAliasError,match="inactive alias"):
            resolve_source_identity(db,source,"rollback-me")
        assert db.scalar(select(func.count(SourceIdentityAliasAudit.id)))==2
    with factory() as db:
        again=rollback_alias_batch(db,"furas","batch-to-rollback",expected_count=1,
            rollback_batch_id="rollback-2",reason="repeat")
        assert again["idempotent"] is True and again["rolled_back_count"]==0


def test_alias_resolution_in_ingestion_path_is_lookup_only(factory):
    from app.adapters import RawOpportunity
    from app.service import _safe_record
    with factory() as db:
        source,master,record=add_pair(db);db.commit();source_id=source.id;record_id=record.id;master_id=master.id
    apply(factory,decision(record,master,"ingest-alias"))
    with factory() as db:
        source=db.get(Source,source_id);before=db.get(SourceOpportunity,record_id)
        before_title=before.source_title;before_hash=before.content_hash;before_status=before.canonical_status
        before_master=db.get(Opportunity,master_id);master_title=before_master.title_ar;master_status=before_master.status
        counts={"raw_count":0,"unchanged_count":0}
        raw=RawOpportunity(external_id="ingest-alias",title="different incoming title",
            url="https://furas.example/opportunity/ingest-alias",owner="different owner",location="الرياض",
            status="Cancelled",reference="ingest-alias",latitude=24.0,longitude=46.0,
            raw={"attributes":{"OPPORTUNITYID":"ingest-alias","OPPORTUNITYTYPE":"Investment"}})
        result1=_safe_record(db,source,raw,counts,allow_master_creation=False)
        result2=_safe_record(db,source,raw,counts,allow_master_creation=False)
        assert result1.id==record_id and result2.id==record_id  # resolved target, not a new SourceOpportunity
        assert counts["alias_resolved_count"]==2 and counts["raw_count"]==2
        assert db.get(SourceOpportunity,record_id).source_title==before_title
        assert db.get(SourceOpportunity,record_id).content_hash==before_hash
        assert db.get(SourceOpportunity,record_id).canonical_status==before_status
        assert db.get(SourceOpportunity,record_id).source_opportunity_id=="old-furas-key"
        assert db.get(SourceOpportunity,record_id).master_opportunity_id==master_id
        assert db.get(Opportunity,master_id).title_ar==master_title
        assert db.get(Opportunity,master_id).status==master_status
        assert db.scalar(select(func.count(SourceObservation.id)))==0


def test_all_75_approved_aliases_apply_resolve_and_rollback_in_isolated_postgres():
    url=os.getenv("FURAS_ALIAS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FURAS_ALIAS_TEST_DATABASE_URL is not configured for isolated 75-row integration test")
    if os.getenv("FURAS_ALIAS_TEST_ISOLATED")!="1" or "furas_alias_test" not in url:
        pytest.fail("75-row integration test requires an explicitly isolated furas_alias_test database")
    import csv
    import hashlib
    import json
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    approved_file=root/"docs/validation/deployment/nationwide-source-expansion/furas-identity-reconciliation-20261110/FURAS-75-APPROVED-ALIASES-20261110.csv"
    artifact_sha=hashlib.sha256(approved_file.read_bytes()).hexdigest()
    with approved_file.open("r",encoding="utf-8-sig",newline="") as stream:
        decisions=list(csv.DictReader(stream))
    assert len(decisions)==75
    for row in decisions: row["evidence_references"]=json.loads(row["evidence_references"])
    engine=create_engine(url,pool_size=5,max_overflow=0)
    pg_factory=sessionmaker(bind=engine,expire_on_commit=False)
    with pg_factory() as db:
        assert db.scalar(select(func.count(Source.id)))==0, "isolated 75-row fixture database must be empty"
        source=Source(id=1,source_key="furas",source_name_ar="فرص",organization_name="fixture",
            base_url="https://furas.test",opportunities_url="https://furas.test/list",priority=1)
        db.add(source);db.flush()
        now=datetime(2026,11,10,tzinfo=timezone.utc)
        for index,row in enumerate(decisions):
            target_id=int(row["existing_source_opportunity_id"])
            master_id=int(row["existing_master_opportunity_id"])
            master=Opportunity(id=master_id,canonical_id=f"FURAS-FIXTURE-{master_id}",
                title_ar="Sanitized approved Master fixture",normalized_title="sanitized approved master fixture",
                primary_publication_platform="fixture",city="",status="fixture",location_confidence_score=0,
                location_detection_method="fixture",location_evidence="sanitized identity-only fixture",
                data_quality_score=0,manual_review_required=False,first_seen_at=now,last_seen_at=now,
                last_updated_at=now,created_at=now,updated_at=now)
            db.add(master)
            record=SourceOpportunity(id=target_id,source_id=source.id,master_opportunity_id=master_id,
                source_opportunity_id=row["proposed_alias_target"],source_reference_number=row["proposed_alias_target"],
                source_reference_number_normalized=row["proposed_alias_target"],source_title="Sanitized source fixture",
                normalized_source_title="sanitized source fixture",source_url="https://furas.test/fixture",
                source_owner="fixture",raw_location="",raw_dates={},raw_status="fixture",canonical_status="fixture",
                raw_data_json={"fixture":True},standardized_data_json={},standardization_version="fixture",
                first_seen_at=now,last_seen_at=now,content_hash=f"{index:064x}",parser_version="fixture")
            db.add(record)
        db.commit()
        before=[(int(r["existing_source_opportunity_id"]),int(r["existing_master_opportunity_id"]),r["proposed_alias_target"]) for r in decisions]
    batch_id=f"isolated-75-{uuid.uuid4().hex}"
    with pg_factory() as db:
        applied=apply_approved_alias_batch(db,"furas",decisions,expected_count=75,
            application_batch_id=batch_id,approved_artifact_reference=str(approved_file),
            approved_artifact_sha256=artifact_sha,actor="isolated-acceptance-test")
    assert applied["applied_count"]==75 and applied["idempotent_count"]==0
    with pg_factory() as db:
        repeated=apply_approved_alias_batch(db,"furas",decisions,expected_count=75,
            application_batch_id=f"retry-{batch_id}",approved_artifact_reference=str(approved_file),
            approved_artifact_sha256=artifact_sha,actor="isolated-acceptance-test")
    assert repeated["applied_count"]==0 and repeated["idempotent_count"]==75
    with pg_factory() as db:
        source=db.scalar(select(Source).where(Source.source_key=="furas"))
        assert db.scalar(select(func.count(SourceIdentityAlias.id)))==75
        assert db.scalar(select(func.count(SourceIdentityAliasAudit.id)))==75
        assert db.scalar(select(func.count(SourceOpportunity.id)))==75
        assert db.scalar(select(func.count(Opportunity.id)))==75
        for row in decisions:
            target_id=int(row["existing_source_opportunity_id"])
            resolved=resolve_source_identity(db,source,row["provider_id"])
            assert resolved.status=="ALIAS"
            assert resolved.record.id==target_id
            assert resolved.record.master_opportunity_id==int(row["existing_master_opportunity_id"])
            assert resolved.record.source_opportunity_id==row["proposed_alias_target"]
        after=[(int(r["existing_source_opportunity_id"]),int(r["existing_master_opportunity_id"]),r["proposed_alias_target"]) for r in decisions]
        assert after==before
    rollback_batch=f"isolated-rollback-{uuid.uuid4().hex}"
    with pg_factory() as db:
        rolled=rollback_alias_batch(db,"furas",batch_id,expected_count=75,
            rollback_batch_id=rollback_batch,reason="isolated 75-row rollback acceptance test",
            actor="isolated-acceptance-test")
    assert rolled["rolled_back_count"]==75
    with pg_factory() as db:
        source=db.scalar(select(Source).where(Source.source_key=="furas"))
        assert db.scalar(select(func.count(SourceIdentityAlias.id)))==75
        assert db.scalar(select(func.count(SourceIdentityAliasAudit.id)))==150
        assert db.scalar(select(func.count(SourceOpportunity.id)))==75
        assert db.scalar(select(func.count(Opportunity.id)))==75
        for row in decisions:
            with pytest.raises(SourceIdentityAliasError,match="inactive alias"):
                resolve_source_identity(db,source,row["provider_id"])
            record=db.get(SourceOpportunity,int(row["existing_source_opportunity_id"]))
            assert record.source_opportunity_id==row["proposed_alias_target"]
            assert record.master_opportunity_id==int(row["existing_master_opportunity_id"])
    engine.dispose()


def test_concurrent_application_has_one_mapping_and_one_application_audit():
    url=os.getenv("FURAS_ALIAS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FURAS_ALIAS_TEST_DATABASE_URL is not configured for isolated PostgreSQL concurrency test")
    if os.getenv("FURAS_ALIAS_TEST_ISOLATED")!="1" or "furas_alias_test" not in url:
        pytest.fail("Concurrency test requires an explicitly isolated furas_alias_test database")
    engine=create_engine(url,pool_size=5,max_overflow=0)
    factory_pg=sessionmaker(bind=engine,expire_on_commit=False)
    token=uuid.uuid4().hex[:12]
    with factory_pg() as db:
        source=db.scalar(select(Source).where(Source.source_key=="furas"))
        if source is None:
            source=Source(id=1,source_key="furas",source_name_ar="ف",organization_name="جهة",
                base_url="https://furas.test",opportunities_url="https://furas.test",priority=1)
            db.add(source);db.flush()
        common=dict(city="الأحساء",status="متاحة",location_confidence_score=.9,location_detection_method="fixture",
            location_evidence="fixture",data_quality_score=.9,manual_review_required=False,first_seen_at=NOW,last_seen_at=NOW,
            last_updated_at=NOW,created_at=NOW,updated_at=NOW)
        master=Opportunity(id=900001,canonical_id=f"F-{token}",title_ar="م",normalized_title="م",primary_publication_platform="ف",**common)
        db.add(master);db.flush()
        record=SourceOpportunity(source_id=source.id,master_opportunity_id=master.id,source_opportunity_id=f"old-{token}",
            source_reference_number=f"old-{token}",source_reference_number_normalized=f"old-{token}",source_title="م",
            normalized_source_title="م",source_url="https://furas.test/old",source_owner="جهة",raw_location="",
            raw_dates={},raw_status="Announced",canonical_status="متاحة",raw_data_json={},standardized_data_json={},
            standardization_version="test",first_seen_at=NOW,last_seen_at=NOW,content_hash=token.ljust(64,"0"),parser_version="test")
        db.add(record);db.commit(); source_key=source.source_key; row=decision(record,master,f"new-{token}",source_key=source_key)
    barrier=threading.Barrier(2)
    def insert(batch_id):
        barrier.wait()
        with factory_pg() as db:
            return apply_approved_alias_batch(db,source_key,[row],expected_count=1,
                application_batch_id=batch_id,approved_artifact_reference="isolated-concurrency.csv",
                approved_artifact_sha256=ARTIFACT_SHA)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(insert,[f"race-a-{token}",f"race-b-{token}"]))
    assert sum(r["applied_count"] for r in results)==1
    assert sum(r["idempotent_count"] for r in results)==1
    with factory_pg() as db:
        alias=db.scalar(select(SourceIdentityAlias).where(SourceIdentityAlias.alias_provider_id==f"new-{token}"))
        assert alias is not None
        assert db.scalar(select(func.count(SourceIdentityAliasAudit.id)).where(
            SourceIdentityAliasAudit.alias_id==alias.id,SourceIdentityAliasAudit.action=="APPLIED"))==1
    engine.dispose()

import asyncio
import os
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.adapters import FurasAdapter, RawOpportunity, normalized_record
from app.database import Base
from app.geographic_references import (canonical_dataset_digest, import_reference_dataset,
                                       resolve_reference_alias, rollback_reference_import, validate_reference_payload)
from app.geography_flags import geographic_feature_state
from app.models import GeographicReferenceDataset, GeographicReferenceUnit, Opportunity, Source, SourceOpportunity, SyncJob
from app.furas_checkpoint import (StaleFurasCheckpoint, advance_checkpoint, new_checkpoint,
    acquire_resume_lock, release_resume_lock, snapshot_identity, validate_checkpoint_lifecycle, validate_resume,
    checkpoint_is_resumable, append_failure_diagnostic)
from app import service as sync_service
from fastapi.testclient import TestClient
from app.service import (FURAS_LOCAL_SCOPE, FURAS_NATIONAL_SCOPE, acquire_sync_ingestion_lock,
                         assess_furas_reconciliation_scope, reconcile_furas_missing_records, source_presence_ids)


def make_db():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def make_source(db):
    source=Source(source_key="furas",source_name_ar="فرص",organization_name="وزارة البلديات والإسكان",
        base_url="https://furas.momah.gov.sa",opportunities_url="https://furas.momah.gov.sa/ar/list-opportunities",
        priority=1,polling_frequency_minutes=60,enabled=True,extraction_method="ArcGIS REST",notes="",
        technical_health="HEALTHY",coverage_status="COMPLETE_PUBLIC_SOURCE",coverage_notes="",
        sync_status="HEALTHY",last_record_count=0,missing_confirmation_threshold=3)
    db.add(source);db.flush();return source


def make_job(db,source,scope=None,status="RUNNING",pagination_complete=False):
    job=SyncJob(source_id=source.id,started_at=datetime.now(timezone.utc),status=status,
        pages_scanned=0,raw_count=0,ahsa_count=0,new_count=0,duplicate_count=0,update_count=0,
        rejected_count=0,unchanged_count=0,metrics_json={"enumeration_scope":scope} if scope else {},
        job_state="RUNNING",trigger_type="scheduled",attempt_number=1,pagination_complete=pagination_complete)
    db.add(job);db.flush();return job


def make_test_units(*,include_governorate=True):
    rows=[{"level":"country","external_id":"TEST_COUNTRY_01","name_ar":"بلد اختباري اصطناعي","source_record":{"test_only":True}},
        {"level":"region","external_id":"TEST_REGION_01","parent_external_id":"TEST_COUNTRY_01","name_ar":"منطقة اختبار اصطناعية","source_record":{"test_only":True}}]
    if include_governorate:
        rows.append({"level":"governorate","external_id":"TEST_GOV_01","parent_external_id":"TEST_REGION_01","name_ar":"محافظة اختبار اصطناعية","source_record":{"test_only":True}})
    return rows


def make_test_metadata(units, *, coverage=None):
    counts={level:sum(row["level"]==level for row in units) for level in ("country","region","governorate","city")}
    return {"dataset_key":"TEST_ONLY_REFERENCE","version":"TEST_FIXTURE_01","operator":"Synthetic test fixture authority",
        "source_url":"https://example.invalid/TEST_ONLY/geography","license_name":"TEST_ONLY_LICENSE",
        "license_url":"https://example.invalid/TEST_ONLY/license","license_evidence_url":"https://example.invalid/TEST_ONLY/license-evidence",
        "license_verified":False,"public_access_verified":True,"source_authority_verified":True,
        "stable_external_ids":True,"parent_relationships_verified":True,"completeness_verified":True,
        "effective_date":"TEST_ONLY_NOT_AN_EFFECTIVE_DATE","coverage_by_level":coverage or {"country":True,"region":True,"governorate":True,"city":False},
        "expected_counts":counts,"test_only":True,"content_sha256":canonical_dataset_digest(units)}


def test_geographic_feature_flags_fail_closed_until_reference_is_ready():
    enabled={"NATIONAL_UI_ENABLED":"true","NATIONAL_MAP_ENABLED":"true","NATIONAL_DASHBOARD_ENABLED":"true"}
    blocked=geographic_feature_state(False,enabled)
    assert blocked["national_ui_enabled"] is False
    assert blocked["national_map_enabled"] is False
    assert blocked["national_dashboard_enabled"] is False
    ready=geographic_feature_state(True,enabled)
    assert ready["national_ui_enabled"] is True and ready["national_map_enabled"] is True
    assert geographic_feature_state(True,{})["national_ui_enabled"] is False


def test_synthetic_reference_fixture_is_test_only_and_rejected_by_production_validation():
    import json
    from pathlib import Path
    payload=json.loads((Path(__file__).parent/"fixtures"/"geographic-reference-test-only.json").read_text(encoding="utf-8"))
    units=payload["units"];metadata=payload["metadata"]
    assert validate_reference_payload(metadata,units,test_mode=True)["valid"] is True
    production=validate_reference_payload(metadata,units,test_mode=False)
    assert any(error.startswith("TEST_FIXTURE_NOT_ALLOWED:") for error in production["errors"])
    assert all(row["external_id"].startswith("TEST_") for row in units)
    assert not any("geometry" in row for row in units)


def test_geographic_reference_digest_is_independent_of_unit_transport_order():
    units=make_test_units()
    assert canonical_dataset_digest(units)==canonical_dataset_digest(list(reversed(units)))


def test_verified_map_points_require_source_evidence_and_never_use_broad_scope():
    from app.main import _verified_coordinate_points
    base=dict(latitude=24.7,longitude=46.7,coordinate_provenance_json={
        "verified":True,"verification_method":"DIRECT_SOURCE_COORDINATE",
        "source_url":"https://official.example/record","source_key":"furas",
        "source_record_id":12,"source_opportunity_id":"furas-12",
        "source_record_identity_matches":True,"source_latitude":24.7,"source_longitude":46.7,
        "boundary_validation":{"status":"VERIFIED_IN_SAUDI","method":"POINT_IN_OFFICIAL_REGION_POLYGON"}})
    specific=SimpleNamespace(geographic_scope="SPECIFIC_LOCATION",**base)
    assert _verified_coordinate_points(specific)==[(24.7,46.7)]
    for scope in ("NATIONWIDE","REGION_WIDE","UNSPECIFIED"):
        assert _verified_coordinate_points(SimpleNamespace(geographic_scope=scope,**base))==[]
    assert _verified_coordinate_points(SimpleNamespace(geographic_scope="SPECIFIC_LOCATION",latitude=24.7,
        longitude=46.7,coordinate_provenance_json={"verified":True,"source_url":"http://unverified.example"}))==[]
    assert _verified_coordinate_points(SimpleNamespace(geographic_scope="SPECIFIC_LOCATION",latitude=24.7,
        longitude=46.7,coordinate_provenance_json={"verified":True,"source_url":"https://source.example/record"}))==[]


def test_geographic_search_scope_parity_across_table_dashboard_csv_and_xlsx(monkeypatch):
    import io
    from openpyxl import load_workbook
    from sqlalchemy.orm import sessionmaker
    from app import main
    engine=make_db();factory=sessionmaker(engine,expire_on_commit=False);monkeypatch.setattr(main,"SessionLocal",factory)
    monkeypatch.setattr(main,"engine",engine);now=datetime.now(timezone.utc)
    with factory.begin() as db:
        for key,title,scope in (("MATCH-1","اختبار وطني مطابق","NATIONWIDE"),("MISS-1","فرصة أخرى","NATIONWIDE"),("LOCAL-1","اختبار محلي","SPECIFIC_LOCATION")):
            db.add(Opportunity(canonical_id=key,title_ar=title,normalized_title=title,primary_publication_platform="اختبار",
                city="",status="متاحة",geographic_scope=scope,first_seen_at=now,last_seen_at=now,last_updated_at=now,
                created_at=now,updated_at=now))
    client=TestClient(main.app);params={"q":"اختبار","geographic_scope":"NATIONWIDE"}
    table=client.get("/api/opportunities",params=params)
    dashboard=client.get("/api/data-dashboard",params=params)
    csv_response=client.get("/api/export.csv",params=params)
    xlsx_response=client.get("/api/export.xlsx",params=params)
    map_response=client.get("/api/data-dashboard/geography",params=params)
    assert table.status_code==200 and table.json()["total"]==1
    assert dashboard.status_code==200 and dashboard.json()["kpis"]["total"]==1
    assert "اختبار وطني مطابق" in csv_response.content.decode("utf-8-sig")
    assert "فرصة أخرى" not in csv_response.content.decode("utf-8-sig")
    workbook=load_workbook(io.BytesIO(xlsx_response.content),read_only=True)
    exported=[value for row in workbook["الفرص الاستثمارية"].iter_rows(values_only=True) for value in row if isinstance(value,str)]
    workbook.close()
    assert exported.count("اختبار وطني مطابق")==1 and "فرصة أخرى" not in exported
    assert map_response.status_code==200 and map_response.json()["counts"]["total"]==1


def test_furas_national_enumeration_is_separate_from_master_geography():
    national=RawOpportunity("furas:outside","مشروع وطني","https://furas.test/item",location="الرياض",
        raw={"enumeration_scope":FURAS_NATIONAL_SCOPE,"source_scope":"NATIONAL_ENUMERATION_ONLY",
             "location_evidence":"text only"})
    local=RawOpportunity("furas:local","موقع بالأحساء","https://furas.test/local",location="الأحساء",
        raw={"enumeration_scope":FURAS_NATIONAL_SCOPE,"source_scope":"SOURCE_SCOPE_AL_AHSA",
             "location_detection_method":"FURAS_VERIFIED_CITY_ID","location_evidence":"verified CITY_ID"},
        location_source_filtered=True)
    assert normalized_record(national)["relevant"] is False
    assert normalized_record(national)["location_confidence_score"] == 0
    assert normalized_record(national)["location_detection_method"] == "UNVERIFIED_NATIONAL_LOCATION"
    assert normalized_record(local)["relevant"] is True


def test_source_presence_uses_full_national_furas_enumeration_not_only_local_masters():
    rows=[RawOpportunity("national:1","x","https://x.test",location_source_filtered=False),
          RawOpportunity("local:2","y","https://y.test",location_source_filtered=True)]
    assert source_presence_ids("furas",[rows[1]],rows)=={"national:1","local:2"}


def test_partial_national_scan_cannot_reconcile_absent_records():
    engine=make_db()
    with Session(engine) as db:
        source=make_source(db);job=make_job(db,source,FURAS_NATIONAL_SCOPE)
        result,guard=reconcile_furas_missing_records(db,source,{"present"},datetime.now(timezone.utc),job,
            {"enumeration_scope":FURAS_NATIONAL_SCOPE,"pagination_complete":False,"reconciliation_scope_complete":False},False)
        assert result==[] and guard["safe"] is False
        assert guard["reason"]=="SCAN_NOT_COMPLETE_AND_VERIFIED"


def test_regional_subset_after_national_scan_is_blocked_from_reconciliation():
    engine=make_db()
    with Session(engine) as db:
        source=make_source(db)
        make_job(db,source,FURAS_NATIONAL_SCOPE,status="SUCCESS",pagination_complete=True)
        current=make_job(db,source,FURAS_LOCAL_SCOPE)
        guard=assess_furas_reconciliation_scope(db,source,current,{"enumeration_scope":FURAS_LOCAL_SCOPE,
            "pagination_complete":True,"reconciliation_scope_complete":True},True)
        assert guard["safe"] is False
        assert guard["reason"]=="CURRENT_SCOPE_IS_NARROWER_THAN_PRIOR_SCOPE"


def test_complete_national_scan_covers_previous_verified_al_ahsa_subset():
    engine=make_db()
    with Session(engine) as db:
        source=make_source(db)
        make_job(db,source,FURAS_LOCAL_SCOPE,status="SUCCESS",pagination_complete=True)
        current=make_job(db,source,FURAS_NATIONAL_SCOPE)
        guard=assess_furas_reconciliation_scope(db,source,current,{"enumeration_scope":FURAS_NATIONAL_SCOPE,
            "pagination_complete":True,"reconciliation_scope_complete":True},True)
        assert guard["safe"] is True


def test_zero_page_or_empty_furas_scan_never_ages_existing_source_or_master():
    engine=make_db()
    with Session(engine) as db:
        source=make_source(db);now=datetime.now(timezone.utc)
        master=Opportunity(canonical_id="MASTER-1",title_ar="فرصة قائمة",normalized_title="فرصة قائمة",
            primary_publication_platform="فرص",city="الأحساء",status="متاحة",first_seen_at=now,last_seen_at=now,
            last_updated_at=now,created_at=now,updated_at=now)
        db.add(master);db.flush()
        row=SourceOpportunity(source_id=source.id,master_opportunity_id=master.id,source_opportunity_id="FURAS-1",
            source_title=master.title_ar,normalized_source_title=master.normalized_title,source_url="https://furas.test/1",
            raw_dates={},raw_data_json={},standardized_data_json={},first_seen_at=now,last_seen_at=now,
            content_hash="a"*64,parser_version="test",canonical_status="متاحة",missing_successful_checks=0)
        db.add(row);db.flush()
        current=make_job(db,source,FURAS_NATIONAL_SCOPE)
        result,guard=reconcile_furas_missing_records(db,source,set(),now,current,{"enumeration_scope":FURAS_NATIONAL_SCOPE,
            "pagination_complete":True,"reconciliation_scope_complete":True},True)
        assert result==[] and guard["safe"] is False
        assert row.missing_successful_checks==0 and row.canonical_status=="متاحة"
        assert db.get(Opportunity,master.id).id==master.id


def test_failed_pagination_and_deadlock_rollback_leave_removal_ineligible():
    engine=make_db()
    with Session(engine) as db:
        source=make_source(db);job=make_job(db,source,FURAS_NATIONAL_SCOPE)
        guard=assess_furas_reconciliation_scope(db,source,job,{"enumeration_scope":FURAS_NATIONAL_SCOPE,
            "pagination_complete":False,"reconciliation_scope_complete":False},False)
        assert guard["safe"] is False
        # The production adapter applies the complete snapshot in one transaction;
        # a PostgreSQL deadlock rolls back that transaction before failure recording.
        assert db.in_transaction() is True


def test_deadlock_rollback_then_safe_retry_does_not_remove_an_unchanged_opportunity():
    engine=make_db();now=datetime.now(timezone.utc)
    with Session(engine) as db:
        source=make_source(db)
        master=Opportunity(canonical_id="RETRY-1",title_ar="فرصة ثابتة",normalized_title="فرصة ثابتة",
            primary_publication_platform="فرص",city="الأحساء",status="متاحة",first_seen_at=now,last_seen_at=now,
            last_updated_at=now,created_at=now,updated_at=now)
        db.add(master);db.flush()
        row=SourceOpportunity(source_id=source.id,master_opportunity_id=master.id,source_opportunity_id="FURAS-RETRY",
            source_title=master.title_ar,normalized_source_title=master.normalized_title,source_url="https://furas.test/retry",
            raw_dates={},raw_data_json={},standardized_data_json={},first_seen_at=now,last_seen_at=now,
            content_hash="b"*64,parser_version="test",canonical_status="متاحة",missing_successful_checks=2)
        db.add(row);db.commit()
        first=make_job(db,source,FURAS_NATIONAL_SCOPE)
        # Simulate a successful reconciliation write followed by PostgreSQL's
        # transaction abort on deadlock. The full transaction is discarded.
        reconcile_furas_missing_records(db,source,{"NOT-PRESENT"},now,first,{"enumeration_scope":FURAS_NATIONAL_SCOPE,
            "pagination_complete":True,"reconciliation_scope_complete":True},True)
        db.flush()
        assert db.get(SourceOpportunity,row.id).missing_successful_checks==3
        db.rollback()
        retained=db.get(SourceOpportunity,row.id)
        assert retained.missing_successful_checks==2 and retained.canonical_status=="متاحة"
        retry=make_job(db,source,FURAS_NATIONAL_SCOPE)
        removed,guard=reconcile_furas_missing_records(db,source,{"FURAS-RETRY"},now,retry,
            {"enumeration_scope":FURAS_NATIONAL_SCOPE,"pagination_complete":True,"reconciliation_scope_complete":True},True)
        assert guard["safe"] is True and removed==[]
        db.flush()
        retained=db.get(SourceOpportunity,row.id)
        assert retained.missing_successful_checks==0 and retained.canonical_status=="متاحة"
        assert db.get(Opportunity,master.id).merged_into_id is None


def test_all_sync_writers_use_same_cross_process_postgresql_advisory_lock():
    class FakeDB:
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        def __init__(self):self.calls=[]
        def execute(self,statement,params):self.calls.append((str(statement),params))
    first=FakeDB();second=FakeDB()
    assert acquire_sync_ingestion_lock(first) is True
    assert acquire_sync_ingestion_lock(second) is True
    assert first.calls==second.calls
    assert "pg_advisory_xact_lock" in first.calls[0][0]
    sqlite=SimpleNamespace(bind=SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))
    assert acquire_sync_ingestion_lock(sqlite) is False


class FakeFurasClient:
    def __init__(self,features,reported_count=None,returned_features=None):
        self.features=features;self.returned_features=returned_features if returned_features is not None else features
        self.reported_count=len(features) if reported_count is None else reported_count
        self.urls=[]
    async def get(self,url,headers=None):
        self.urls.append(url);parsed=urlparse(unquote(url));query=parse_qs(parsed.query)
        if url.endswith("config.json"):
            return FakeResponse({"gisLayerUrl":{"investmentMapServerInvestmentP":"https://layer.test/MapServer"},
                "gisLayerIndex":{"investmentMapServerInvestmentP":0}})
        if "returnCountOnly" in query:
            return FakeResponse({"count":self.reported_count})
        if "returnIdsOnly" in query:
            return FakeResponse({"objectIds":[(f.get("attributes") or {}).get("OBJECTID") for f in self.features]})
        if "objectIds" in query:
            wanted=set(query["objectIds"][0].split(","))
            return FakeResponse({"features":[f for f in self.features if str(f["attributes"]["OBJECTID"]) in wanted]})
        if not parsed.path.endswith("/query"):
            return FakeResponse({"currentVersion":10.81,"objectIdField":"OBJECTID","capabilities":"Map,Query,Data",
                "fields":[{"name":"OBJECTID","type":"esriFieldTypeOID"}]})
        return FakeResponse({"features":self.returned_features})


class FakeResponse:
    def __init__(self,payload):self.payload=payload
    def raise_for_status(self):return None
    def json(self):return self.payload


def fake_feature(object_id,city_id):
    return {"attributes":{"OBJECTID":object_id,"OPPORTUNITYID":f"OFF-{object_id}","CITY_ID":city_id,
        "CITYNAME":"الرياض" if city_id!="9" else "الأحساء","OPPORTUNITYDESCRIPTION":f"فرصة {object_id}",
        "AMANA":"","ENTITIESNAME":"جهة حكومية","ACTIVITYTYPE":"تجاري","SUBACTIVITYTYPE":"تجزئة",
        "OPPORTUNITYACTIVESTATUS":"Announced","QualifyingOpportunity":0},"geometry":{"x":46.7,"y":24.7}}


def test_checkpoint_cursor_advances_only_after_commit_and_is_scope_bound():
    ids=list(range(1,206));identity=snapshot_identity(source_key="furas",layer_url="layer",
        where="national-filter-v1",scope=FURAS_NATIONAL_SCOPE,object_ids=ids)
    checkpoint=new_checkpoint(job_id=7,identity=identity)
    with pytest.raises(ValueError,match="before the data transaction commits"):
        advance_checkpoint(checkpoint,page_offset=0,page_count=100,source_ids=["F-1"],committed=False)
    checkpoint=advance_checkpoint(checkpoint,page_offset=0,page_count=100,source_ids=[f"F-{i}" for i in range(100)],committed=True)
    assert checkpoint["last_committed_offset"]==100 and checkpoint["last_committed_page"]==1
    assert checkpoint["enumeration_complete"] is False and checkpoint["removal_reconciliation_allowed"] is False
    validate_resume(checkpoint,identity,expected_scope=FURAS_NATIONAL_SCOPE)
    with pytest.raises(StaleFurasCheckpoint,match="scope mismatch"):
        validate_resume(checkpoint,identity,expected_scope=FURAS_LOCAL_SCOPE)


def test_checkpoint_rejects_collector_or_source_snapshot_change():
    ids=list(range(1,5));identity=snapshot_identity(source_key="furas",layer_url="layer",where="v1",
        scope=FURAS_NATIONAL_SCOPE,object_ids=ids,collector_version="collector-1")
    checkpoint=new_checkpoint(job_id=4,identity=identity)
    changed=snapshot_identity(source_key="furas",layer_url="layer",where="v1",
        scope=FURAS_NATIONAL_SCOPE,object_ids=ids,collector_version="collector-2")
    with pytest.raises(StaleFurasCheckpoint,match="collector_version"):
        validate_resume(checkpoint,changed,expected_scope=FURAS_NATIONAL_SCOPE)
    changed_source=snapshot_identity(source_key="furas",layer_url="layer",where="v1",
        scope=FURAS_NATIONAL_SCOPE,object_ids=[1,2,3,5],collector_version="collector-1")
    with pytest.raises(StaleFurasCheckpoint,match="object_ids_sha256"):
        validate_resume(checkpoint,changed_source,expected_scope=FURAS_NATIONAL_SCOPE)


def test_legacy_failed_checkpoint_summary_is_never_resumable():
    job_692_summary={"stale_action":"REJECT","stale_reason":"Source feature page changed during scan: 31",
        "enumeration_complete":False,"removal_reconciliation_allowed":False,"terminal_status":"FAILED"}
    assert checkpoint_is_resumable(job_692_summary) is False


def test_checkpoint_lifecycle_integrity_requires_complete_cursor_for_success():
    identity=snapshot_identity(source_key="furas",layer_url="layer",where="v1",scope=FURAS_NATIONAL_SCOPE,object_ids=[1])
    checkpoint=new_checkpoint(job_id=1,identity=identity)
    checkpoint["terminal_status"]="SUCCESS"
    assert not validate_checkpoint_lifecycle(checkpoint,"COMPLETED")
    checkpoint["enumeration_complete"]=True;checkpoint["removal_reconciliation_allowed"]=True
    assert validate_checkpoint_lifecycle(checkpoint,"COMPLETED")


class FakePagedFurasClient(FakeFurasClient):
    def __init__(self,features,reported_count=None,*,empty_object_ids=None):
        super().__init__(features,reported_count=reported_count)
        self.empty_object_ids=set(map(str,empty_object_ids or []))
        self.after_ids=None
    async def get(self,url,headers=None):
        if url.endswith("config.json"):
            return FakeResponse({"gisLayerUrl":{"investmentMapServerInvestmentP":"https://layer.test/MapServer"},
                "gisLayerIndex":{"investmentMapServerInvestmentP":0}})
        parsed=urlparse(unquote(url));query=parse_qs(parsed.query)
        if "returnCountOnly" in query:return FakeResponse({"count":self.reported_count})
        if "returnIdsOnly" in query:
            response=FakeResponse({"objectIds":[(item.get("attributes") or {}).get("OBJECTID") for item in self.features]})
            callback=self.after_ids;self.after_ids=None
            if callback:callback(self)
            return response
        if "objectIds" in query:
            wanted=set(query["objectIds"][0].split(","))
            return FakeResponse({"features":[item for item in self.features
                if str(item["attributes"]["OBJECTID"]) in wanted and str(item["attributes"]["OBJECTID"]) not in self.empty_object_ids]})
        return FakeResponse({"currentVersion":10.81,"objectIdField":"OBJECTID","capabilities":"Map,Query,Data",
            "fields":[{"name":"OBJECTID","type":"esriFieldTypeOID"}],"geometryType":"esriGeometryPoint"})


class FakeAsyncClientContext:
    def __init__(self,client):self.client=client
    async def __aenter__(self):return self.client
    async def __aexit__(self,*args):return False


def test_sync_source_interrupts_after_commit_then_resumes_without_duplicates_or_masters(monkeypatch):
    from sqlalchemy.orm import sessionmaker
    engine=make_db();factory=sessionmaker(engine,expire_on_commit=False)
    with Session(engine) as db:
        source=make_source(db);source_id=source.id
        prior=make_job(db,source,FURAS_LOCAL_SCOPE,status="SUCCESS",pagination_complete=True)
        prior.job_state="COMPLETED"
        now=datetime.now(timezone.utc)
        db.add(SourceOpportunity(source_id=source.id,source_opportunity_id="LOCAL-ABSENT",
            source_title="Existing local source row",normalized_source_title="existing local source row",
            source_url="https://furas.test/local-absent",canonical_status="غير محددة",
            raw_data_json={},standardized_data_json={},first_seen_at=now,last_seen_at=now,
            content_hash="a"*64,parser_version="test",missing_successful_checks=0))
        db.commit()
    features=[fake_feature(i,"9" if i%2 else "OTHER") for i in range(1,121)]
    client=FakePagedFurasClient(features);monkeypatch.setattr(sync_service,"SessionLocal",factory)
    monkeypatch.setattr(sync_service.httpx,"AsyncClient",lambda *args,**kwargs:FakeAsyncClientContext(client))
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    monkeypatch.setattr("app.data_quality.evaluate_data_quality",lambda *args,**kwargs:{"run_id":1,"counts":{"pass":1,"warning":0,"fail":0},"failed_gates":[]})
    original=FurasAdapter.fetch
    async def stop_after_first(self,client,**kwargs):
        kwargs["stop_after_batches"]=1
        return await original(self,client,**kwargs)
    monkeypatch.setattr(FurasAdapter,"fetch",stop_after_first)
    first=asyncio.run(sync_service.sync_source("furas"))
    assert first["status"]=="FAILED"
    with Session(engine) as db:
        failed=db.scalar(select(SyncJob).order_by(SyncJob.id.desc()).limit(1))
        assert "furas_checkpoint" in failed.metrics_json, (first,failed.metrics_json)
        checkpoint=failed.metrics_json["furas_checkpoint"]
        assert checkpoint["last_committed_offset"]==100 and checkpoint["last_committed_page"]==1
        assert checkpoint["terminal_status"]=="RUNNING" and checkpoint["removal_reconciliation_allowed"] is False
        assert failed.metrics_json["furas_failure"]["failure_stage"]=="SOURCE_CAPTURE_OR_FINALIZATION"
        assert checkpoint_is_resumable(checkpoint) is True
        assert db.scalar(select(func.count(SourceOpportunity.id)).where(SourceOpportunity.source_id==source_id))==101
        assert db.scalar(select(func.count(Opportunity.id)))==0
    monkeypatch.setattr(FurasAdapter,"fetch",original)
    second=asyncio.run(sync_service.sync_source("furas"))
    assert second["status"]=="SUCCESS"
    with Session(engine) as db:
        jobs=db.scalars(select(SyncJob).order_by(SyncJob.id)).all()
        assert "furas_checkpoint" in jobs[-1].metrics_json, (second,jobs[-1].metrics_json)
        final=jobs[-1].metrics_json["furas_checkpoint"]
        ids=db.scalars(select(SourceOpportunity.source_opportunity_id).where(SourceOpportunity.source_id==source_id)).all()
        assert jobs[0].job_state=="COMPLETED" and jobs[1].job_state=="FAILED" and jobs[-1].job_state=="COMPLETED"
        assert len(ids)==len(set(ids))==121
        assert final["last_committed_offset"]==120 and final["enumeration_complete"] is True
        assert final["removal_reconciliation_allowed"] is False
        assert jobs[-1].metrics_json["first_national_bootstrap"] is True
        assert jobs[-1].metrics_json["bootstrap_removal_guard"]["withheld"] is True
        assert jobs[-1].metrics_json["reconciliation_executed"] is False
        old_row=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_opportunity_id=="LOCAL-ABSENT"))
        assert old_row is not None and old_row.missing_successful_checks==0
        assert final["scan_run_id"]==checkpoint["scan_run_id"]
        assert db.scalar(select(func.count(Opportunity.id)))==0
        assert jobs[-1].removed_records_count==0
    engine.dispose()


def test_national_removals_stay_disabled_after_a_prior_national_baseline(monkeypatch):
    from sqlalchemy.orm import sessionmaker
    engine=make_db();factory=sessionmaker(engine,expire_on_commit=False)
    with Session(engine) as db:
        source=make_source(db);source_id=source.id
        prior=make_job(db,source,FURAS_NATIONAL_SCOPE,status="SUCCESS",pagination_complete=True)
        prior.job_state="COMPLETED";prior.finished_at=datetime.now(timezone.utc)
        db.add(SourceOpportunity(source_id=source.id,source_opportunity_id="OLD-NATIONAL",
            source_title="Existing national baseline row",normalized_source_title="existing national baseline row",
            source_url="https://furas.test/old",canonical_status="غير محددة",raw_data_json={},standardized_data_json={},
            first_seen_at=datetime.now(timezone.utc),last_seen_at=datetime.now(timezone.utc),content_hash="c"*64,
            parser_version="test",missing_successful_checks=0))
        db.commit()
    client=FakePagedFurasClient([fake_feature(1,"OTHER")]);monkeypatch.setattr(sync_service,"SessionLocal",factory)
    monkeypatch.setattr(sync_service.httpx,"AsyncClient",lambda *args,**kwargs:FakeAsyncClientContext(client))
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    monkeypatch.setenv("FURAS_NATIONAL_REMOVAL_RECONCILIATION_ENABLED","false")
    monkeypatch.setattr("app.data_quality.evaluate_data_quality",lambda *args,**kwargs:{"run_id":9,"counts":{"pass":1,"warning":0,"fail":0},"failed_gates":[]})
    result=asyncio.run(sync_service.sync_source("furas"))
    assert result["status"]=="SUCCESS"
    with Session(engine) as db:
        job=db.scalar(select(SyncJob).order_by(SyncJob.id.desc()).limit(1))
        old=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_opportunity_id=="OLD-NATIONAL"))
        assert job.removed_records_count==0
        assert old is not None and old.missing_successful_checks==0
        assert job.metrics_json["removal_reconciliation_enabled"] is False
        assert job.metrics_json["reconciliation_executed"] is False
        assert job.metrics_json["furas_checkpoint"]["removal_reconciliation_allowed"] is False
        assert db.scalar(select(func.count(Opportunity.id)))==0
    engine.dispose()


def test_sync_source_failure_before_first_commit_replays_the_uncommitted_page(monkeypatch):
    from sqlalchemy.orm import sessionmaker
    engine=make_db();factory=sessionmaker(engine,expire_on_commit=False)
    with Session(engine) as db:
        source=make_source(db);db.commit();source_id=source.id
    client=FakePagedFurasClient([fake_feature(i,"OTHER") for i in range(1,121)])
    monkeypatch.setattr(sync_service,"SessionLocal",factory)
    monkeypatch.setattr(sync_service.httpx,"AsyncClient",lambda *args,**kwargs:FakeAsyncClientContext(client))
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    monkeypatch.setattr("app.data_quality.evaluate_data_quality",lambda *args,**kwargs:{"run_id":2,"counts":{"pass":1,"warning":0,"fail":0},"failed_gates":[]})
    original=sync_service._safe_record
    def fail_before_commit(*args,**kwargs):raise RuntimeError("simulated failure before batch commit")
    monkeypatch.setattr(sync_service,"_safe_record",fail_before_commit)
    first=asyncio.run(sync_service.sync_source("furas"))
    assert first["status"]=="FAILED"
    with Session(engine) as db:
        failed=db.scalar(select(SyncJob).order_by(SyncJob.id.desc()).limit(1))
        assert not (failed.metrics_json or {}).get("furas_checkpoint")
        assert db.scalar(select(func.count(SourceOpportunity.id)).where(SourceOpportunity.source_id==source_id))==0
    monkeypatch.setattr(sync_service,"_safe_record",original)
    replay=asyncio.run(sync_service.sync_source("furas"))
    assert replay["status"]=="SUCCESS"
    with Session(engine) as db:
        assert db.scalar(select(func.count(SourceOpportunity.id)).where(SourceOpportunity.source_id==source_id))==120
        assert db.scalar(select(func.count(Opportunity.id)))==0
    engine.dispose()


def test_adapter_page_cursor_is_saved_only_after_callback_commit_and_before_next_fetch(monkeypatch):
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    client=FakePagedFurasClient([fake_feature(i,"OTHER") for i in range(1,121)])
    persisted={"checkpoint":None,"calls":0}
    async def fail_before_commit(records,candidate):
        raise RuntimeError("simulated database failure before commit")
    with pytest.raises(RuntimeError,match="before commit"):
        asyncio.run(FurasAdapter().fetch(client,on_batch=fail_before_commit))
    assert persisted["checkpoint"] is None
    async def commit_then_interrupt(records,candidate):
        persisted["checkpoint"]=candidate;persisted["calls"]+=1
    with pytest.raises(RuntimeError,match="after committed batch 1"):
        asyncio.run(FurasAdapter().fetch(client,on_batch=commit_then_interrupt,stop_after_batches=1))
    assert persisted["calls"]==1
    assert persisted["checkpoint"]["last_committed_offset"]==100
    assert persisted["checkpoint"]["enumeration_complete"] is False
    assert persisted["checkpoint"]["removal_reconciliation_allowed"] is False


def test_adapter_halfway_interruption_resumes_without_duplicate_official_ids(monkeypatch):
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    client=FakePagedFurasClient([fake_feature(i,"OTHER") for i in range(1,201)])
    committed={};processed=[];completed={}
    async def first_commit(records,candidate):committed.update(candidate);processed.extend(r.external_id for r in records)
    with pytest.raises(RuntimeError,match="after committed batch 1"):
        asyncio.run(FurasAdapter().fetch(client,on_batch=first_commit,stop_after_batches=1))
    assert committed["last_committed_offset"]==100 and committed["expected_count"]==200
    assert len(processed)==100
    async def resume_commit(records,candidate):processed.extend(r.external_id for r in records)
    async def finish(checkpoint):completed.update(checkpoint)
    remaining,_=asyncio.run(FurasAdapter().fetch(client,checkpoint=committed,on_batch=resume_commit,on_complete=finish))
    assert len(remaining)==100
    assert len(processed)==200 and len(set(processed))==200
    assert completed["enumeration_complete"] is True
    assert completed["last_committed_offset"]==200


def test_membership_snapshot_defers_new_ids_to_next_scan(monkeypatch):
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    client=FakePagedFurasClient([fake_feature(i,"OTHER") for i in range(1,121)])
    client.after_ids=lambda c:c.features.append(fake_feature(121,"OTHER"))
    first=FurasAdapter();first_records,_=asyncio.run(first.fetch(client))
    assert first.metrics["snapshot_membership_complete"] is True
    assert first.metrics["source_snapshot"]["expected_count"]==120
    assert len(first_records)==120
    next_scan=FurasAdapter();next_records,_=asyncio.run(next_scan.fetch(client))
    assert next_scan.metrics["source_snapshot"]["expected_count"]==121
    assert len(next_records)==121


def test_membership_snapshot_ignores_content_edits_and_page_order_drift(monkeypatch):
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    client=FakePagedFurasClient([fake_feature(i,"OTHER") for i in range(1,121)])
    client.after_ids=lambda c:(
        c.features.__setitem__(0,{**c.features[0],"attributes":{**c.features[0]["attributes"],"OPPORTUNITYDESCRIPTION":"updated after snapshot"}}),
        c.features.reverse())
    adapter=FurasAdapter();records,_=asyncio.run(adapter.fetch(client))
    assert adapter.metrics["snapshot_membership_complete"] is True
    assert adapter.metrics["page_hashes_diagnostic_only"] is True
    assert len(records)==120
    assert len({record.external_id for record in records})==120
    assert next(record for record in records if record.external_id=="OFF-1").title=="updated after snapshot"


def test_membership_snapshot_is_stable_when_records_move_between_query_batches(monkeypatch):
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    client=FakePagedFurasClient([fake_feature(i,"OTHER") for i in range(1,202)])
    def reverse_between_reads(c):c.features.reverse()
    client.after_ids=reverse_between_reads
    adapter=FurasAdapter();records,_=asyncio.run(adapter.fetch(client))
    assert adapter.metrics["snapshot_membership_complete"] is True
    assert adapter.metrics["source_snapshot"]["expected_count"]==201
    assert len(records)==201 and len({record.external_id for record in records})==201


def test_resume_uses_initial_membership_and_accepts_changed_committed_content(monkeypatch):
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    features=[fake_feature(i,"OTHER") for i in range(1,121)];client=FakePagedFurasClient(features)
    saved={}
    async def commit(records,candidate):saved.update(candidate)
    with pytest.raises(RuntimeError,match="after committed batch 1"):
        asyncio.run(FurasAdapter().fetch(client,on_batch=commit,stop_after_batches=1))
    changed=[dict(item) for item in features]
    changed[0]={**changed[0],"attributes":{**changed[0]["attributes"],"OPPORTUNITYDESCRIPTION":"changed after interruption"}}
    client.features=changed
    completed={}
    records,_=asyncio.run(FurasAdapter().fetch(client,checkpoint=saved,on_complete=lambda cp:completed.update(cp)))
    assert len(records)==20
    assert completed["enumeration_complete"] is True
    assert completed["snapshot_membership_complete"] is True
    assert completed["batch_sha256s"]==saved["batch_sha256s"]+[completed["batch_sha256s"][-1]]


def test_interrupted_resume_matches_uninterrupted_fixed_fixture(monkeypatch):
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    features=[fake_feature(i,"OTHER") for i in range(1,122)]
    uninterrupted=FurasAdapter()
    all_records,_=asyncio.run(uninterrupted.fetch(FakePagedFurasClient(features)))
    assert uninterrupted.metrics["pagination_complete"] is True
    saved={};committed_prefix=[]
    async def commit_prefix(records,checkpoint):
        committed_prefix.extend(records)
        saved.update(checkpoint)
    with pytest.raises(RuntimeError,match="after committed batch 1"):
        asyncio.run(FurasAdapter().fetch(FakePagedFurasClient(features),on_batch=commit_prefix,stop_after_batches=1))
    resumed=FurasAdapter();suffix,_=asyncio.run(resumed.fetch(FakePagedFurasClient(features),checkpoint=saved))
    combined=committed_prefix+suffix
    assert resumed.metrics["pagination_complete"] is True
    assert len(combined)==len(all_records)==121
    assert len({record.external_id for record in combined})==121
    to_payload=lambda records:[(r.external_id,r.raw["attributes"],r.raw["geometry"]) for r in records]
    assert to_payload(combined)==to_payload(all_records)


@pytest.mark.parametrize("stage,error,retryable",[
    ("BATCH_VALIDATION",ValueError("invalid feature batch"),True),
    ("HTTP_REQUEST",RuntimeError("HTTP 503"),True),
    ("STALE_SNAPSHOT",StaleFurasCheckpoint("stale snapshot membership"),False),
    ("DATABASE_COMMIT",RuntimeError("database commit failed"),True),
    ("WORKER_SHUTDOWN",RuntimeError("worker shutdown"),True),
    ("FINAL_RECONCILIATION",RuntimeError("reconciliation failed"),True),
])
def test_failure_diagnostics_never_replace_durable_checkpoint(stage,error,retryable):
    identity=snapshot_identity(source_key="furas",layer_url="layer",where="national-v1",
        scope=FURAS_NATIONAL_SCOPE,object_ids=list(range(1,121)))
    checkpoint=new_checkpoint(job_id=12,identity=identity)
    checkpoint.update({"last_committed_offset":100,"processed_snapshot_object_ids":list(range(1,101)),
        "processed_source_ids":[f"F-{i}" for i in range(1,101)],"unique_source_ids_seen":100,
        "batch_sha256s":["a"*64],"pages_completed":1})
    before=dict(checkpoint)
    metrics=append_failure_diagnostic({"furas_checkpoint":checkpoint},error,failure_stage=stage,retryable=retryable)
    assert metrics["furas_checkpoint"]==before
    assert checkpoint_is_resumable(metrics["furas_checkpoint"]) is True
    assert metrics["furas_failure"]["failure_stage"]==stage
    assert metrics["furas_failure"]["retryable"] is retryable


def test_worker_lifecycle_heartbeat_keeps_api_readiness_independent_of_beat(monkeypatch):
    import json, redis
    from app.celery_app import start_worker_ready_heartbeat, clear_worker_ready_heartbeat
    from app import main as main_module
    store={}
    class FakeRedis:
        def set(self,key,value,ex=None):store[key]=(value,ex)
        def delete(self,key):store.pop(key,None)
        def ping(self):return True
        def scan_iter(self,match=None,count=None):return iter(list(store))
    client=FakeRedis()
    monkeypatch.setenv("REDIS_URL","redis://test")
    monkeypatch.setattr(redis.Redis,"from_url",staticmethod(lambda *args,**kwargs:client))
    monkeypatch.setattr("app.celery_app.socket.gethostname",lambda:"isolated-worker")
    start_worker_ready_heartbeat()
    assert store["worker:heartbeat:isolated-worker"][1]==120
    class FakeDB:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,*args):return None
    monkeypatch.setattr(main_module,"SessionLocal",FakeDB)
    response=main_module.health_ready()
    body=json.loads(response.body)
    assert response.status_code==200 and body["checks"]["worker"]=="ok"
    clear_worker_ready_heartbeat()
    assert "worker:heartbeat:isolated-worker" not in store
    response=main_module.health_ready()
    assert response.status_code==503 and json.loads(response.body)["checks"]["worker"]=="error"


def test_duplicate_official_ids_are_deduplicated_and_prevent_completion(monkeypatch):
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    features=[fake_feature(i,"OTHER") for i in range(1,102)]
    features[-1]={**features[-1],"attributes":{**features[-1]["attributes"],"OPPORTUNITYID":"OFF-1"}}
    client=FakePagedFurasClient(features);completed={}
    async def commit(records,candidate):pass
    async def finish(checkpoint):completed.update(checkpoint)
    records,_=asyncio.run(FurasAdapter().fetch(client,on_batch=commit,on_complete=finish))
    assert len(records)==100
    assert completed["enumeration_complete"] is False
    assert completed["removal_reconciliation_allowed"] is False
    assert completed["duplicate_source_ids"]==1


def test_disappeared_snapshot_member_is_accounted_without_removal(monkeypatch):
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    client=FakePagedFurasClient([fake_feature(i,"OTHER") for i in range(1,202)],empty_object_ids=["101"])
    saved=[];completed={}
    async def commit(records,candidate):saved.append(candidate)
    async def finish(checkpoint):completed.update(checkpoint)
    _,_=asyncio.run(FurasAdapter().fetch(client,on_batch=commit,on_complete=finish))
    assert len(saved)==3 and saved[0]["last_committed_offset"]==100
    assert completed["enumeration_complete"] is True
    assert completed["removal_reconciliation_allowed"] is False
    assert completed["missing_object_ids"]==[101]
    assert completed["snapshot_membership_complete"] is True


@pytest.mark.skipif(not os.getenv("FURAS_CHECKPOINT_TEST_DATABASE_URL"),reason="requires isolated PostgreSQL advisory locks")
def test_postgres_prevents_concurrent_owners_of_same_resume_scope():
    engine=create_engine(os.environ["FURAS_CHECKPOINT_TEST_DATABASE_URL"])
    first=Session(engine);second=Session(engine)
    owner=acquire_resume_lock(first,FURAS_NATIONAL_SCOPE)
    assert owner is not None and owner is not False
    assert acquire_resume_lock(second,FURAS_NATIONAL_SCOPE) is False
    release_resume_lock(owner)
    replacement=acquire_resume_lock(second,FURAS_NATIONAL_SCOPE)
    assert replacement is not None and replacement is not False
    release_resume_lock(replacement);first.close();second.close();engine.dispose()




def test_furas_national_adapter_checks_scope_and_separates_source_records_from_local_eligibility(monkeypatch):
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    client=FakeFurasClient([fake_feature(1,"9"),fake_feature(2,"OTHER")])
    adapter=FurasAdapter();records,pages=asyncio.run(adapter.fetch(client))
    assert pages==4  # layer metadata, count, initial membership IDs, and one OBJECTID batch
    assert adapter.metrics["enumeration_scope"]==FURAS_NATIONAL_SCOPE
    assert adapter.metrics["pagination_complete"] is True
    assert len(adapter.raw_candidates)==2
    assert records[0].location_source_filtered is True
    assert records[1].location_source_filtered is False
    assert normalized_record(records[1])["relevant"] is False
    assert "CITY_ID IN" not in adapter.metrics["where"]
    assert adapter.metrics["city_filter_ids"]==[]
    assert adapter.metrics["verified_al_ahsa_city_ids"]==list(adapter.ahsa_city_ids)


def test_furas_count_mismatch_is_diagnostic_and_disappeared_id_is_not_a_removal(monkeypatch):
    monkeypatch.setenv("FURAS_NATIONAL_ENUMERATION_ENABLED","true")
    client=FakeFurasClient([fake_feature(1,"9")],reported_count=2)
    adapter=FurasAdapter()
    records,_=asyncio.run(adapter.fetch(client))
    assert len(records)==1
    assert adapter.metrics["pagination_complete"] is True
    assert adapter.metrics["membership_snapshot_count_mismatch"] is True
    client=FakePagedFurasClient([fake_feature(1,"9"),fake_feature(2,"OTHER")],empty_object_ids=["2"])
    adapter=FurasAdapter();records,_=asyncio.run(adapter.fetch(client))
    assert len(records)==1 and adapter.metrics["pagination_complete"] is True
    assert adapter.metrics["missing_object_ids"]==1
    assert adapter.metrics["checkpoint"]["removal_reconciliation_allowed"] is False


def test_reference_import_dry_run_validates_ids_parents_and_digest_without_license_gate_or_writes():
    engine=make_db()
    units=make_test_units();metadata=make_test_metadata(units)
    with Session(engine) as db:
        report=import_reference_dataset(db,metadata,units,dry_run=True,test_mode=True)
        assert report["valid"] is True and report["dry_run"] is True and report["imported"] is False
        assert db.scalar(select(GeographicReferenceDataset.id)) is None
        no_license=validate_reference_payload({**metadata,"license_verified":False},units,test_mode=True)
        assert no_license["valid"] is True
        not_public=validate_reference_payload({**metadata,"public_access_verified":False},units,test_mode=True)
        assert "PUBLIC_ACCESS_NOT_VERIFIED" in not_public["errors"]
        duplicate=validate_reference_payload(metadata,units+[dict(units[-1])],test_mode=True)
        assert any(error.startswith("DUPLICATE_ID:") for error in duplicate["errors"])
        unknown_parent=[*units[:-1],{**units[-1],"parent_external_id":"missing"}]
        invalid_parent=validate_reference_payload({**metadata,"content_sha256":canonical_dataset_digest(unknown_parent)},unknown_parent,test_mode=True)
        assert any(error.startswith("UNKNOWN_PARENT:") for error in invalid_parent["errors"])
        assert report["counts_by_level"]["city"]==0


def test_reference_import_rejects_missing_version_date_public_access_and_stable_ids_without_writes():
    engine=make_db()
    units=make_test_units();metadata=make_test_metadata(units)
    with Session(engine) as db:
        cases=[
            ({**metadata,"version":""},"MISSING_METADATA:version"),
            ({**metadata,"effective_date":""},"MISSING_METADATA:effective_date"),
            ({**metadata,"public_access_verified":False},"PUBLIC_ACCESS_NOT_VERIFIED"),
            ({**metadata,"stable_external_ids":False},"STABLE_EXTERNAL_IDS_NOT_ATTESTED"),
            ({**metadata,"effective_date":"not-a-date"},"INVALID_EFFECTIVE_DATE"),
            ({**metadata,"operator":""},"MISSING_METADATA:operator"),
        ]
        for candidate,expected in cases:
            report=import_reference_dataset(db,candidate,units,dry_run=True,test_mode=True)
            assert report["dry_run"] is True and report["imported"] is False
            assert expected in report["errors"]
        missing_id_units=[*units[:-1],{**units[-1],"external_id":""}]
        missing_id_metadata={**metadata,"content_sha256":canonical_dataset_digest(missing_id_units)}
        missing_id_report=import_reference_dataset(db,missing_id_metadata,missing_id_units,dry_run=True,test_mode=True)
        assert "MISSING_STABLE_ID:2" in missing_id_report["errors"]
        assert missing_id_report["imported"] is False
        assert db.scalar(select(GeographicReferenceDataset.id)) is None


def test_reference_alias_lookup_is_exact_and_parent_scoped():
    engine=make_db();units=make_test_units()
    units[1]={**units[1],"aliases":["منطقة الاختبار"]}
    metadata=make_test_metadata(units)
    with Session(engine) as db:
        imported=import_reference_dataset(db,metadata,units,dry_run=False,test_mode=True)
        region=resolve_reference_alias(db,imported["dataset_id"],"region","منطقة الاختبار")
        assert region is not None and region.external_id=="TEST_REGION_01"
        assert resolve_reference_alias(db,imported["dataset_id"],"region","منطقة الاختبار الزائدة") is None
        assert resolve_reference_alias(db,imported["dataset_id"],"governorate","محافظة اختبار اصطناعية",
                                       parent_external_id="UNKNOWN_REGION") is None


def test_reference_import_rejects_wrong_level_and_cyclic_parent_fixtures():
    units=make_test_units();metadata=make_test_metadata(units)
    wrong_level=[*units[:-1],{**units[-1],"parent_external_id":"TEST_COUNTRY_01"}]
    wrong_level_report=validate_reference_payload({**metadata,"content_sha256":canonical_dataset_digest(wrong_level)},wrong_level,test_mode=True)
    assert any(error.startswith("INVALID_PARENT_LEVEL:") for error in wrong_level_report["errors"])

    # The declared parent-level graph is acyclic by construction; any cycle
    # necessarily violates an allowed edge and is rejected as an invalid level.
    cycle=[units[0],{**units[1],"parent_external_id":"TEST_GOV_01"},units[2]]
    cycle_report=validate_reference_payload({**metadata,"content_sha256":canonical_dataset_digest(cycle)},cycle,test_mode=True)
    assert any(error.startswith("INVALID_PARENT_LEVEL:") for error in cycle_report["errors"])


def test_reference_import_is_versioned_transactional_and_rollback_preserves_history():
    engine=make_db()
    with Session(engine) as db:
        def import_version(version,parent=None):
            units=make_test_units(include_governorate=False);metadata=make_test_metadata(units)
            metadata={**metadata,"version":version}
            result=import_reference_dataset(db,metadata,units,dry_run=False,test_mode=True);db.flush();return result["dataset_id"]
        first=import_version("v1");db.commit()
        second=import_version("v2");db.flush()
        report=rollback_reference_import(db,second);db.commit()
        assert report=={"rolled_back_dataset_id":second,"restored_dataset_id":first}
        assert db.get(GeographicReferenceDataset,first).is_current is True
        assert db.get(GeographicReferenceDataset,second).import_status=="ROLLED_BACK"
        assert db.get(GeographicReferenceDataset,second).provenance_json["rollback_history"][-1]["restored_dataset_id"]==first
        assert db.scalar(select(GeographicReferenceUnit.id).where(GeographicReferenceUnit.dataset_id==first)) is not None


def test_national_api_scope_filter_is_backward_compatible_and_reference_selectors_fail_closed(monkeypatch):
    from app import main
    from sqlalchemy.orm import sessionmaker
    engine=make_db();factory=sessionmaker(engine,expire_on_commit=False)
    now=datetime.now(timezone.utc)
    with factory.begin() as db:
        db.add(Opportunity(canonical_id="NAT-1",title_ar="فرصة وطنية",normalized_title="فرصة وطنية",
            primary_publication_platform="Invest Saudi",city="",status="غير محددة",geographic_scope="NATIONWIDE",
            first_seen_at=now,last_seen_at=now,last_updated_at=now,created_at=now,updated_at=now))
    monkeypatch.setattr(main,"SessionLocal",factory)
    client=TestClient(main.app)
    catalog=client.get("/api/geography/catalog").json()
    assert catalog["enabled"] is False and catalog["complete"] is False
    assert catalog["national_map_enabled"] is False
    assert client.get("/api/source-geographic-coverage").json()["status"]=="NOT_ASSESSED"
    assert client.get("/api/opportunities",params={"geographic_scope":"NATIONWIDE"}).json()["total"]==1
    assert client.get("/api/opportunities",params={"geographic_scope":"UNSPECIFIED"}).json()["total"]==0
    assert client.get("/api/opportunities",params={"city_id":"UNVERIFIED-ID"}).status_code==422


def test_national_api_enables_only_levels_with_complete_reference_coverage(monkeypatch):
    from app import main
    from sqlalchemy.orm import sessionmaker
    engine=make_db();factory=sessionmaker(engine,expire_on_commit=False);now=datetime.now(timezone.utc)
    units=make_test_units();metadata=make_test_metadata(units)
    with factory.begin() as db:
        imported=import_reference_dataset(db,metadata,units,dry_run=False,test_mode=True)
        region=db.scalar(select(GeographicReferenceUnit).where(GeographicReferenceUnit.dataset_id==imported["dataset_id"],
            GeographicReferenceUnit.level=="region"))
        db.add(Opportunity(canonical_id="REGION-1",title_ar="فرصة على مستوى المنطقة",normalized_title="فرصة على مستوى المنطقة",
            primary_publication_platform="Invest Saudi",city="",status="غير محددة",geographic_scope="REGION_WIDE",
            geography_reference_unit_id=region.id,first_seen_at=now,last_seen_at=now,last_updated_at=now,created_at=now,updated_at=now))
    monkeypatch.setattr(main,"SessionLocal",factory)
    monkeypatch.setenv("NATIONAL_UI_ENABLED","true")
    monkeypatch.setattr(main,"_geographic_reference_readiness",lambda db:(
        db.scalar(select(GeographicReferenceDataset).where(GeographicReferenceDataset.is_current.is_(True))),
        {"ready":True,"reasons":[],"counts_by_level":{"region":1,"governorate":1,"city":0}}))
    client=TestClient(main.app)
    catalog=client.get("/api/geography/catalog").json()
    assert catalog["available_selector_levels"]==["region","governorate"]
    assert catalog["complete"] is True and catalog["national_map_enabled"] is False
    assert client.get("/api/opportunities",params={"region_id":"TEST_REGION_01"}).json()["total"]==1
    assert client.get("/api/opportunities",params={"city_id":"CITY-1"}).status_code==422


def test_geographic_filter_and_selectors_work_while_national_ui_flag_stays_off(monkeypatch):
    from app import main
    from sqlalchemy.orm import sessionmaker
    engine=make_db();factory=sessionmaker(engine,expire_on_commit=False);now=datetime.now(timezone.utc)
    units=make_test_units();governorate_unit=next(row for row in units if row["level"]=="governorate")
    governorate_unit["name_ar"]="الاحساء";governorate_unit["aliases"]=["الأحساء"]
    metadata=make_test_metadata(units)
    with factory.begin() as db:
        imported=import_reference_dataset(db,metadata,units,dry_run=False,test_mode=True)
        region=db.scalar(select(GeographicReferenceUnit).where(GeographicReferenceUnit.dataset_id==imported["dataset_id"],
            GeographicReferenceUnit.level=="region"))
        governorate=db.scalar(select(GeographicReferenceUnit).where(GeographicReferenceUnit.dataset_id==imported["dataset_id"],
            GeographicReferenceUnit.level=="governorate"))
        db.add(Opportunity(canonical_id="FILTER-READY-1",title_ar="فرصة جغرافية",normalized_title="فرصة جغرافية",
            primary_publication_platform="اختبار",city="",status="متاحة",geographic_scope="SPECIFIC_LOCATION",
            geography_reference_unit_id=governorate.id,first_seen_at=now,last_seen_at=now,last_updated_at=now,
            created_at=now,updated_at=now))
    monkeypatch.setattr(main,"SessionLocal",factory)
    monkeypatch.setattr(main,"_geographic_reference_readiness",lambda db:(
        db.scalar(select(GeographicReferenceDataset).where(GeographicReferenceDataset.is_current.is_(True))),
        {"ready":True,"reasons":[],"counts_by_level":{"region":1,"governorate":1,"city":0}}))
    monkeypatch.setenv("NATIONAL_UI_ENABLED","false")
    client=TestClient(main.app)
    catalog=client.get("/api/geography/catalog").json()
    assert catalog["national_ui_enabled"] is False and catalog["national_map_enabled"] is False
    assert client.get("/api/geography/options",params={"level":"region"}).status_code==200
    filter_options=client.get("/api/geography/filter-options")
    assert filter_options.status_code==200
    assert filter_options.json()["regions"]==[{"id":"TEST_REGION_01","name_ar":"منطقة اختبار اصطناعية",
        "display_name_ar":"منطقة اختبار اصطناعية",
        "unique_masters":1}]
    assert filter_options.json()["governorates"]==[{"id":"TEST_GOV_01","name_ar":"الاحساء",
        "display_name_ar":"الأحساء",
        "unique_masters":1,"parent_id":"TEST_REGION_01"}]
    result=client.get("/api/opportunities",params={"region_id":"TEST_REGION_01"})
    assert result.status_code==200 and result.json()["total"]==1
    governorate_result=client.get("/api/opportunities",params={"region_id":"TEST_REGION_01","governorate_id":"TEST_GOV_01"})
    assert governorate_result.status_code==200 and governorate_result.json()["total"]==1
    dashboard=client.get("/api/data-dashboard",params={"region_id":"TEST_REGION_01"})
    assert dashboard.status_code==200 and dashboard.json()["kpis"]["total"]==result.json()["total"]
    assert client.get("/api/export.csv",params={"region_id":"TEST_REGION_01"}).status_code==200
    assert client.get("/api/export.xlsx",params={"region_id":"TEST_REGION_01"}).status_code==200
    assert client.get("/api/opportunities",params={"region_id":"INVALID"}).status_code==422

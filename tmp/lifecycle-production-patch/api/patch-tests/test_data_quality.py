from datetime import datetime, timedelta, timezone
import json
import sys
import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (Base, AlertEvent, AuditEvent, DuplicateCandidate, LocationReview, MergeAudit, Opportunity,
    OpportunityConflict, QualificationReview, Source, SourceObservation, SourceOpportunity,
    SourceOpportunityDatasetMembership, SystemEvent, SyncJob)
from app.data_quality import evaluate_data_quality, _source_absence_classification


@pytest.fixture
def dq_db(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    from app import main
    monkeypatch.setattr(main,"SessionLocal",factory)
    db=factory()
    yield db
    db.close();engine.dispose()


def source(db,key="fixture",coverage="COMPLETE_PUBLIC_SOURCE"):
    row=Source(source_key=key,source_name_ar=key,organization_name=key,base_url=f"https://{key}.test",
        opportunities_url=f"https://{key}.test/opportunities",coverage_status=coverage,technical_health="HEALTHY",enabled=True,priority=1)
    db.add(row);db.flush();return row


def master(db,canonical="M-1",merged_into_id=None,reference=None):
    now=datetime.now(timezone.utc)
    row=Opportunity(canonical_id=canonical,title_ar=canonical,normalized_title=canonical,
        primary_publication_platform="fixture",city="الأحساء",status="متاحة",merged_into_id=merged_into_id,
        reference_number=reference,location_confidence_score=.9,location_detection_method="fixture",location_evidence="fixture",
        data_quality_score=.9,manual_review_required=False,first_seen_at=now,last_seen_at=now,last_updated_at=now,
        created_at=now,updated_at=now)
    db.add(row);db.flush();return row


def source_record(db,src,external="external-1",master_id=None,*,qualified=False,raw=None,standardized=None,official=None,canonical_status="متاحة",missing=0):
    now=datetime.now(timezone.utc)
    row=SourceOpportunity(source_id=src.id,master_opportunity_id=master_id,source_opportunity_id=external,
        official_source_id_original=official,official_source_id_normalized=official,source_reference_number=official,
        source_reference_number_normalized=official,source_title=external,normalized_source_title=external,
        source_url=f"https://{src.source_key}.test/opportunity/{external}",source_owner=None,raw_area=None,raw_value=None,
        raw_dates={},raw_status=None,canonical_status=canonical_status,raw_data_json={"qualified":qualified,**(raw or {})},
        standardized_data_json=standardized or {},standardization_version="21",first_seen_at=now,last_seen_at=now,
        missing_successful_checks=missing,
        content_hash=(external+str(src.id)).ljust(64,"x")[:64],parser_version="test")
    db.add(row);db.flush();return row


def failed_keys(result):
    return {row["gate_key"] for row in result["failed_gates"]}


def test_sync_job_state_consistency_passes_terminal_and_fails_intentionally_inconsistent(dq_db):
    src=source(dq_db,"lifecycle");now=datetime.now(timezone.utc)
    valid=SyncJob(source_id=src.id,started_at=now,finished_at=now,status="SUCCESS",job_state="COMPLETED")
    dq_db.add(valid);dq_db.flush()
    gate=lambda:next(row for row in evaluate_data_quality(dq_db,scope="fast",persist=False)["gates"]
        if row["gate_key"]=="SYNC_JOB_STATE_CONSISTENCY")
    assert gate()["status"]=="PASS"

    invalid=SyncJob(source_id=src.id,started_at=now,status="SUCCESS",job_state="RUNNING",finished_at=None)
    dq_db.add(invalid);dq_db.flush()
    broken=gate()
    assert broken["status"]=="FAIL" and invalid.id in broken["sample_ids"]
    assert broken["severity"]=="FAIL"


def test_autonomous_resolution_gates_reconcile_open_and_system_audited_cases(dq_db):
    src=source(dq_db); opportunity=master(dq_db); record=source_record(dq_db,src,master_id=opportunity.id)
    empty={g["gate_key"]:g for g in evaluate_data_quality(dq_db,scope="full",persist=False)["gates"]}
    assert empty["OPEN_REVIEW_BACKLOG"]["observed"]==0
    assert empty["OPEN_REVIEW_BACKLOG"]["status"]=="PASS"
    review=OpportunityConflict(opportunity_id=opportunity.id,field_name="activity",conflict_type="FIELD_VALUE_CONFLICT",
        selected_value="A",conflicting_value="B",source_id=src.id,source_record_id=record.id,
        detected_at=datetime.now(timezone.utc),status="OPEN")
    dq_db.add(review);dq_db.commit()
    before={g["gate_key"]:g for g in evaluate_data_quality(dq_db,scope="full",persist=False)["gates"]}
    assert before["OPEN_REVIEW_BACKLOG"]["observed"]==1
    assert before["OPEN_REVIEW_BACKLOG"]["status"]=="WARNING"
    assert before["OPEN_ACTIONABLE_REVIEW_BACKLOG"]["observed"]==1
    assert before["AUTONOMOUS_REVIEW_LEFT_UNRESOLVED"]["observed"]==1
    assert before["SOURCE_RECHECK_LEFT_OPEN"]["observed"]==0

    review.status="RESOLVED_KEEP"
    dq_db.add(AuditEvent(user_id=None,event_type="REVIEW_FIELD_KEEP",entity_type="opportunity_conflict",
        entity_id=str(review.id),before_json={"status":"OPEN"},after_json={"status":"RESOLVED_KEEP",
            "decision":"FIELD_KEEP","reason":"INSUFFICIENT_EVIDENCE_NO_CHANGE","resolution_class":"B_KEEP_CURRENT_CANONICAL",
            "confidence":"CONSERVATIVE","business_change":"NO_BUSINESS_CHANGE","evidence":{}},
        request_metadata={"actor":"SYSTEM","actor_role":"system","decision_kind":"AUTONOMOUS",
            "rule_version":"AUTONOMOUS_REVIEW_RESOLUTION_V1"},created_at=datetime.now(timezone.utc)))
    dq_db.commit()
    after={g["gate_key"]:g for g in evaluate_data_quality(dq_db,scope="full",persist=False)["gates"]}
    for key in ("OPEN_ACTIONABLE_REVIEW_BACKLOG","AUTONOMOUS_RESOLUTION_WITHOUT_AUDIT",
                "AUTONOMOUS_MERGE_WITHOUT_DETERMINISTIC_IDENTITY",
                "AUTONOMOUS_CANONICAL_CHANGE_WITHOUT_STRONGER_EVIDENCE",
                "AUTONOMOUS_LOW_CONFIDENCE_MUTATION","AUTONOMOUS_RESOLUTION_INVALID_ACTION",
                "AUTONOMOUS_REVIEW_LEFT_UNRESOLVED","SOURCE_RECHECK_LEFT_OPEN"):
        assert after[key]["status"]=="PASS", (key,after[key])


def test_source_recheck_gate_detects_location_scope_without_project_site(dq_db):
    src=source(dq_db,key="ahda"); opportunity=master(dq_db)
    record=source_record(dq_db,src,master_id=opportunity.id,raw={"source_scope":"SOURCE_SCOPE_AL_AHSA"})
    dq_db.add(LocationReview(source_id=src.id,external_id="no-site",source_record_id=record.id,title="No site",
        sector="Tourism",source_location=None,description="",latitude=None,longitude=None,evidence="scope only",
        confidence_score=0,reason="SOURCE_RECHECK_REQUIRED",status="PENDING",created_at=datetime.now(timezone.utc)))
    dq_db.commit()
    gates={g["gate_key"]:g for g in evaluate_data_quality(dq_db,scope="full",persist=False)["gates"]}
    assert gates["SOURCE_RECHECK_LEFT_OPEN"]["observed"]==1


def test_qualified_source_without_master_fails(dq_db):
    src=source(dq_db);record=source_record(dq_db,src,qualified=True)
    assert "QUALIFIED_SOURCE_WITHOUT_CURRENT_MASTER" in failed_keys(evaluate_data_quality(dq_db,scope="fast"))


def test_same_verified_official_reference_split_across_current_masters_fails(dq_db):
    src=source(dq_db);a=master(dq_db,"A");b=master(dq_db,"B")
    source_record(dq_db,src,"external-a",a.id,qualified=True,official="OFFICIAL-777")
    source_record(dq_db,src,"external-b",b.id,qualified=True,official="OFFICIAL-777")
    assert "VERIFIED_OFFICIAL_REFERENCE_SPLIT" in failed_keys(evaluate_data_quality(dq_db,scope="full"))


def test_current_master_without_source_fails(dq_db):
    master(dq_db)
    assert "MASTER_CURRENT_WITHOUT_SOURCE" in failed_keys(evaluate_data_quality(dq_db,scope="fast"))


def test_furas_unverified_dates_promoted_in_projection_fail(dq_db):
    src=source(dq_db,"furas");m=master(dq_db);source_record(dq_db,src,"f1",m.id,qualified=True,
        raw={"attributes":{"STARTDATE":"2026-01-01","ENDDATE":"2026-12-01"}},
        standardized={"fields":{"publication_date":{"mapping_status":"VALID"},"submission_deadline":{"mapping_status":"VALID"}}})
    keys=failed_keys(evaluate_data_quality(dq_db,scope="fast"))
    assert {"FURAS_UNVERIFIED_PUBLICATION_PROMOTION","FURAS_UNVERIFIED_DEADLINE_PROMOTION"} <= keys


def test_stale_worker_standardization_heartbeat_fails(dq_db,monkeypatch):
    src=source(dq_db);m=master(dq_db);source_record(dq_db,src,master_id=m.id,qualified=True)
    fake=types.SimpleNamespace(Redis=types.SimpleNamespace(from_url=lambda *a,**k: types.SimpleNamespace(
        scan_iter=lambda **k:["worker:test"],get=lambda key:json.dumps({"standardization_version":"20"}))))
    monkeypatch.setitem(sys.modules,"redis",fake);monkeypatch.setenv("REDIS_URL","redis://fixture")
    assert "API_WORKER_STANDARDIZATION_PARITY" in failed_keys(evaluate_data_quality(dq_db,scope="fast"))


def test_incomplete_scan_with_removals_fails_and_preserves_safe_rule(dq_db):
    src=source(dq_db);now=datetime.now(timezone.utc)
    dbjob=SyncJob(source_id=src.id,started_at=now,status="WARNING",job_state="COMPLETED_WITH_WARNINGS",
        pagination_complete=False,removed_records_count=1,trigger_type="scheduled")
    dq_db.add(dbjob);dq_db.flush()
    assert "PARTIAL_SCAN_REMOVAL_SAFETY" in failed_keys(evaluate_data_quality(dq_db,scope="fast"))


def test_incomplete_page_missing_does_not_count_as_completed_furas_gap(dq_db):
    src=source(dq_db,"furas");now=datetime.now(timezone.utc)
    dq_db.add(SyncJob(source_id=src.id,started_at=now,status="WARNING",job_state="COMPLETED_WITH_WARNINGS",
        pagination_complete=False,removed_records_count=0,trigger_type="scheduled"));dq_db.flush()
    keys=failed_keys(evaluate_data_quality(dq_db,scope="fast"))
    assert "FURAS_LAST_SUCCESSFUL_SCAN_PAGINATION" in keys
    assert "PARTIAL_SCAN_REMOVAL_SAFETY" not in keys


def test_source_freshness_gate_is_source_aware_read_only_and_returns_evidence(dq_db):
    src=source(dq_db,"ncp");now=datetime.now(timezone.utc)
    dq_db.add(SyncJob(source_id=src.id,started_at=now-timedelta(hours=30),finished_at=now-timedelta(hours=30)+timedelta(seconds=3),
        status="SUCCESS",job_state="COMPLETED",pagination_complete=True,trigger_type="scheduled",metrics_json={}))
    dq_db.flush()
    before=(dq_db.query(Opportunity).count(),dq_db.query(SourceOpportunity).count(),
            dq_db.query(SourceObservation).count(),dq_db.query(SystemEvent).count())
    result=evaluate_data_quality(dq_db,scope="full",persist=False)
    after=(dq_db.query(Opportunity).count(),dq_db.query(SourceOpportunity).count(),
           dq_db.query(SourceObservation).count(),dq_db.query(SystemEvent).count())
    gate=next(item for item in result["gates"] if item["gate_key"]=="SOURCE_LAST_SUCCESS_TOO_OLD")
    assert gate["status"]=="WARNING"
    assert gate["evidence"][0]["source"]=="ncp"
    assert gate["evidence"][0]["warning_threshold_minutes"]==1440
    assert gate["evidence"][0]["last_complete_scan"]
    assert before==after


def test_duplicate_logical_review_creation_fails(dq_db):
    src=source(dq_db);left=master(dq_db,"LEFT");right=master(dq_db,"RIGHT");now=datetime.now(timezone.utc)
    dq_db.add_all([DuplicateCandidate(left_opportunity_id=left.id,right_opportunity_id=right.id,confidence_score=.99,status="PENDING",created_at=now),
        DuplicateCandidate(left_opportunity_id=right.id,right_opportunity_id=left.id,confidence_score=.99,status="PENDING",created_at=now)])
    dq_db.flush()
    assert "LOGICAL_DUPLICATE_OPEN_REVIEW" in failed_keys(evaluate_data_quality(dq_db,scope="fast"))


def test_api_dashboard_export_count_mismatch_fails(dq_db,monkeypatch):
    src=source(dq_db);m=master(dq_db);source_record(dq_db,src,master_id=m.id,qualified=True)
    from app import main
    monkeypatch.setattr(main,"dashboard",lambda:{"total":987})
    gate=next(g for g in evaluate_data_quality(dq_db,scope="full")["gates"] if g["gate_key"]=="API_DASHBOARD_EXPORT_RECONCILIATION")
    assert gate["status"]=="FAIL"


def test_broken_furas_active_route_fails(dq_db,monkeypatch):
    src=source(dq_db,"furas");m=master(dq_db);source_record(dq_db,src,"f2",m.id,qualified=True,
        raw={"attributes":{"OPPORTUNITYID":"REF-2","OPPORTUNITYTYPE":"TemporaryRental"}})
    from app import source_links
    monkeypatch.setattr(source_links,"furas_detail_url",lambda reference,kind:f"https://furas.momah.gov.sa/index.php/ar/opportunity/{reference}?type=TemporaryRental")
    assert "FURAS_TEMPORARY_RENTAL_ROUTE_REGRESSION" in failed_keys(evaluate_data_quality(dq_db,scope="fast"))


def test_technical_source_id_as_official_reference_fails(dq_db):
    src=source(dq_db);m=master(dq_db,reference="furas:889922");source_record(dq_db,src,master_id=m.id,qualified=True)
    assert "TECHNICAL_SOURCE_ID_AS_MASTER_REFERENCE" in failed_keys(evaluate_data_quality(dq_db,scope="fast"))


def test_open_review_on_merged_master_fails(dq_db):
    src=source(dq_db);winner=master(dq_db,"WINNER");merged=master(dq_db,"MERGED",merged_into_id=winner.id);now=datetime.now(timezone.utc)
    dq_db.add(DuplicateCandidate(left_opportunity_id=winner.id,right_opportunity_id=merged.id,confidence_score=.9,status="PENDING",created_at=now));dq_db.flush()
    assert "OPEN_REVIEW_ON_MERGED_MASTER" in failed_keys(evaluate_data_quality(dq_db,scope="fast"))


def test_positive_states_do_not_create_false_identity_or_coverage_failures(dq_db):
    limited=source(dq_db,"limited",coverage="PUBLIC_COVERAGE_LIMITED")
    normal=source(dq_db,"fixture-b");current=master(dq_db,"CURRENT");merged=master(dq_db,"HISTORY",merged_into_id=current.id)
    source_record(dq_db,normal,"multi-a",current.id,qualified=True,official="SHARED-1")
    source_record(dq_db,limited,"multi-b",current.id,qualified=True,official="SHARED-1")
    source_record(dq_db,normal,"national-unqualified",None,qualified=False)
    source_record(dq_db,normal,"removed-history",merged.id,qualified=False,canonical_status="أزيلت من المصدر")
    now=datetime.now(timezone.utc)
    dq_db.add(LocationReview(source_id=normal.id,external_id="needs-location",source_record_id=None,title="مراجعة",evidence="دليل",confidence_score=.2,reason="pending",status="PENDING",created_at=now))
    dq_db.add(SourceObservation(source_opportunity_id=1,dataset_name="fixture",endpoint="test",official_source_id_original="id",official_source_id_normalized="id",raw_data_json={},content_hash="history",first_seen_at=now,last_seen_at=now))
    dq_db.flush()
    result=evaluate_data_quality(dq_db,scope="fast")
    assert not {"MASTER_CURRENT_WITHOUT_SOURCE","SOURCE_LINKED_TO_MULTIPLE_CURRENT_MASTERS","QUALIFIED_SOURCE_WITHOUT_CURRENT_MASTER","FURAS_LAST_SUCCESSFUL_SCAN_PAGINATION"} & failed_keys(result)


def test_read_only_is_default_and_only_audit_event_can_be_opted_in(dq_db):
    from app.models import SystemEvent
    before=dq_db.query(SystemEvent).count()
    evaluate_data_quality(dq_db,scope="fast",persist=False)
    assert dq_db.query(SystemEvent).count()==before


def test_nonqualified_national_invest_saudi_row_is_not_source_absence(dq_db):
    src=source(dq_db,"invest-saudi");row=source_record(dq_db,src,qualified=False,raw={"qualified_location":False},missing=2)
    now=datetime.now(timezone.utc)
    dq_db.add(SourceOpportunityDatasetMembership(source_opportunity_id=row.id,dataset_name="Opportunities",
        endpoint="https://investsaudi.test/opportunities",first_seen_at=now,last_seen_at=now,
        missing_successful_checks=0,is_current=True,dataset_specific_metadata={}))
    dq_db.flush()
    result=_source_absence_classification(dq_db,[row],{src.id:src})
    assert result["categories"]["true_absence_pending_confirmation"]==[]
    assert result["categories"]["confirmed_current_and_present"]==[row.id]


def test_unlinked_source_opportunity_is_not_automatically_source_absence(dq_db):
    src=source(dq_db);row=source_record(dq_db,src,master_id=None,qualified=False,missing=1)
    result=_source_absence_classification(dq_db,[row],{src.id:src})
    assert result["categories"]["true_absence_pending_confirmation"]==[]
    assert result["categories"]["other_valid_non_absence"]==[row.id]


def test_outside_al_ahsa_scope_is_not_source_absence(dq_db):
    src=source(dq_db);row=source_record(dq_db,src,qualified=False,
        raw={"qualified":False,"qualified_location":False,"location":"Riyadh"},missing=1)
    result=_source_absence_classification(dq_db,[row],{src.id:src})
    assert result["categories"]["true_absence_pending_confirmation"]==[]


def test_historical_removed_source_record_is_not_pending_absence(dq_db):
    src=source(dq_db);row=source_record(dq_db,src,qualified=True,
        canonical_status="أزيلت من المصدر",missing=3)
    result=_source_absence_classification(dq_db,[row],{src.id:src})
    assert result["categories"]["true_absence_pending_confirmation"]==[]
    assert result["legacy_population"]==0


def test_incomplete_or_noncomparable_enumeration_is_not_confirmed_absence(dq_db):
    src=source(dq_db);row=source_record(dq_db,src,qualified=True,raw={"qualified":True},missing=1)
    now=datetime.now(timezone.utc)
    dq_db.add(SyncJob(source_id=src.id,started_at=now,status="WARNING",job_state="COMPLETED_WITH_WARNINGS",
        pagination_complete=False,trigger_type="scheduled"));dq_db.flush()
    result=_source_absence_classification(dq_db,[row],{src.id:src})
    assert result["categories"]["true_absence_pending_confirmation"]==[]
    assert result["categories"]["limited_or_non_comparable_enumeration"]==[row.id]


def test_true_comparable_missing_source_record_enters_pending_confirmation(dq_db):
    src=source(dq_db);row=source_record(dq_db,src,qualified=True,raw={"qualified":True},missing=1)
    scan_at=datetime.now(timezone.utc)
    dq_db.add(SyncJob(source_id=src.id,started_at=scan_at,finished_at=scan_at,status="SUCCESS",job_state="COMPLETED",
        pagination_complete=True,trigger_type="scheduled"));dq_db.flush()
    row.last_seen_at=scan_at.replace(year=scan_at.year-1)
    result=_source_absence_classification(dq_db,[row],{src.id:src})
    assert result["categories"]["true_absence_pending_confirmation"]==[row.id]


def test_dq_run_does_not_create_review_cases_or_change_reconciliation_count(dq_db):
    src=source(dq_db);left=master(dq_db,"REVIEW-A");right=master(dq_db,"REVIEW-B")
    now=datetime.now(timezone.utc)
    dq_db.add(DuplicateCandidate(left_opportunity_id=left.id,right_opportunity_id=right.id,
        confidence_score=.9,status="PENDING",created_at=now))
    dq_db.add(OpportunityConflict(opportunity_id=left.id,field_name="sector",conflict_type="FIELD_VALUE_CONFLICT",
        selected_value="أ",conflicting_value="ب",source_id=src.id,
        source_record_id=source_record(dq_db,src,master_id=left.id,qualified=True).id,
        detected_at=now,status="OPEN"))
    dq_db.flush()
    before=(dq_db.query(DuplicateCandidate).count()+dq_db.query(LocationReview).count()
            +dq_db.query(QualificationReview).count()+dq_db.query(OpportunityConflict).count())
    result=evaluate_data_quality(dq_db,scope="fast",persist=False)
    after=(dq_db.query(DuplicateCandidate).count()+dq_db.query(LocationReview).count()
           +dq_db.query(QualificationReview).count()+dq_db.query(OpportunityConflict).count())
    assert result["read_only_business_data"] is True
    assert before==after
    assert dq_db.query(SystemEvent).filter_by(event_type="DATA_QUALITY_RUN_COMPLETED").count()==0


def test_status_sector_dq_gates_detect_legacy_published_value(dq_db):
    item=master(dq_db,"LEGACY-PUBLISHED");item.status="منشورة"
    result=evaluate_data_quality(dq_db,scope="fast",persist=False)
    gates={row["gate_key"]:row for row in result["gates"]}
    assert gates["CANONICAL_CURRENT_PUBLISHED_RECORDS"]["status"]=="FAIL"
    assert gates["USER_FACING_PUBLISHED_STATUS_BUCKET"]["status"]=="PASS"
    assert gates["TOURISM_AND_AGRICULTURE_CANONICAL_SECTORS"]["status"]=="PASS"


def test_sector_provenance_dq_gates_require_high_confidence_trace(dq_db):
    src=source(dq_db);item=master(dq_db,"INFERRED-SECTOR");item.sector="التعليم"
    source_row=source_record(dq_db,src,master_id=item.id,qualified=True)
    event=SystemEvent(event_type="SECTOR_INFERENCE_STATUS_CONSOLIDATION_APPLIED",created_at=datetime.now(timezone.utc),payload={
        "classifications":[{"master_id":item.id,"sector":"التعليم","classification_origin":"INFERRED_RULE",
            "rule_key":"TEST_RULE","evidence_fields":[{"field":"activity","signal":"الأنشطة التعليمية"}],
            "confidence":.95,"engine_version":"test","inference_timestamp":"2026-10-21T00:00:00Z"}]
    })
    dq_db.add(event);dq_db.flush()
    gates={row["gate_key"]:row for row in evaluate_data_quality(dq_db,scope="fast",persist=False)["gates"]}
    assert gates["SOURCE_EXPLICIT_SECTOR_OVERRIDDEN_BY_INFERENCE"]["status"]=="PASS"
    assert gates["FORCED_LOW_CONFIDENCE_SECTOR_CLASSIFICATIONS"]["status"]=="PASS"
    assert gates["INFERRED_SECTOR_WITHOUT_TRACEABLE_EVIDENCE"]["status"]=="PASS"
    source_row.source_sector="Tourism"
    dq_db.flush()
    gates={row["gate_key"]:row for row in evaluate_data_quality(dq_db,scope="fast",persist=False)["gates"]}
    assert gates["SOURCE_EXPLICIT_SECTOR_OVERRIDDEN_BY_INFERENCE"]["status"]=="FAIL"


def test_sector_provenance_gate_fails_when_trace_is_absent(dq_db):
    from app.models import SystemEvent
    item=master(dq_db,"INFERRED-UNTRACED");item.sector="التعليم"
    dq_db.add(SystemEvent(event_type="SECTOR_INFERENCE_STATUS_CONSOLIDATION_APPLIED",
        created_at=datetime.now(timezone.utc),payload={"classifications":[{
            "master_id":item.id,"sector":"التعليم","classification_origin":"INFERRED_RULE",
            "rule_key":"MISSING_EVIDENCE","evidence_fields":[],"confidence":.60,
            "engine_version":"test","inference_timestamp":"2026-10-21T00:00:00Z"}]}))
    dq_db.flush()
    gates={row["gate_key"]:row for row in evaluate_data_quality(dq_db,scope="fast",persist=False)["gates"]}
    assert gates["FORCED_LOW_CONFIDENCE_SECTOR_CLASSIFICATIONS"]["status"]=="FAIL"
    assert gates["INFERRED_SECTOR_WITHOUT_TRACEABLE_EVIDENCE"]["status"]=="FAIL"


def test_standardization_reviews_are_in_field_conflict_top_level_domain(dq_db):
    src=source(dq_db);current=master(dq_db,"STANDARDIZATION")
    record=source_record(dq_db,src,master_id=current.id,qualified=True)
    now=datetime.now(timezone.utc)
    dq_db.add(OpportunityConflict(opportunity_id=current.id,field_name="contract_duration_years",
        conflict_type="STANDARDIZATION_REVIEW",selected_value="5",conflicting_value="unknown",
        source_id=src.id,source_record_id=record.id,detected_at=now,status="OPEN"))
    dq_db.flush()
    result=evaluate_data_quality(dq_db,scope="full",persist=False)
    top_level=next(g for g in result["gates"] if g["gate_key"]=="TOP_LEVEL_REVIEW_RECONCILIATION")
    field_sum=next(g for g in result["gates"] if g["gate_key"]=="FIELD_CONFLICT_SUBCATEGORY_RECONCILIATION")
    assert top_level["status"]=="PASS"
    assert top_level["observed"]==top_level["expected"]["total"]==1
    assert field_sum["observed"]==field_sum["expected"]==1


def test_retention_is_bounded_to_dq_events_and_preserves_other_audit_history(dq_db):
    from app.models import SystemEvent
    from datetime import timedelta
    old=datetime.now(timezone.utc)-timedelta(days=400)
    dq_db.add_all([SystemEvent(event_type="DATA_QUALITY_RUN_COMPLETED",payload={"old":True},created_at=old),
                   SystemEvent(event_type="BUSINESS_AUDIT_EVENT",payload={"keep":True},created_at=old)])
    dq_db.flush()
    result=evaluate_data_quality(dq_db,scope="fast",persist=True)
    assert dq_db.query(SystemEvent).filter_by(event_type="DATA_QUALITY_RUN_COMPLETED").count()==1
    assert dq_db.query(SystemEvent).filter_by(event_type="BUSINESS_AUDIT_EVENT").count()==1
    assert result["retention"]["days"]==365


def test_review_dq_separates_legacy_metadata_and_system_supersession_from_human_decisions(dq_db):
    src=source(dq_db);left=master(dq_db,"AUDIT-LEFT");right=master(dq_db,"AUDIT-RIGHT");now=datetime.now(timezone.utc)
    record=source_record(dq_db,src,master_id=left.id,qualified=True)
    conflict=OpportunityConflict(opportunity_id=left.id,field_name="sector",conflict_type="TAXONOMY_CONFLICT",
        selected_value="تجاري",conflicting_value="صناعي",source_id=src.id,source_record_id=record.id,
        detected_at=now-timedelta(days=60),status="RESOLVED_KEEP")
    candidate=DuplicateCandidate(left_opportunity_id=left.id,right_opportunity_id=right.id,
        confidence_score=.9,status="MERGED",created_at=now-timedelta(days=100))
    dq_db.add_all([conflict,candidate]);dq_db.flush()
    dq_db.add(MergeAudit(merged_opportunity_id=right.id,target_opportunity_id=left.id,source_record_ids=[record.id],
        created_at=now-timedelta(days=100),merged_at=now-timedelta(days=100),undone_at=None,
        performed_by="admin",merge_reason="verified fixture merge",merge_evidence={"basis":"identity"}))
    dq_db.add(AuditEvent(user_id=None,event_type="REVIEW_LOGICAL_DUPLICATE_SUPERSEDED",
        entity_type="opportunity_conflict",entity_id="999",before_json={"status":"OPEN"},
        after_json={"status":"SUPERSEDED","decision":"LOGICAL_DUPLICATE_SUPERSEDED"},
        request_metadata={"actor":"field-conflict-reconciliation"},created_at=now))
    dq_db.add(AuditEvent(user_id=None,event_type="REVIEW_STALE_CONDITION_RESOLVED",
        entity_type="opportunity_conflict",entity_id="998",before_json={"status":"OPEN"},
        after_json={"status":"RESOLVED_CANONICAL","decision":"STALE_CONDITION_RESOLVED"},
        request_metadata={"actor":"SYSTEM"},created_at=now))
    dq_db.flush()
    result=evaluate_data_quality(dq_db,scope="full",persist=False)
    gates={row["gate_key"]:row for row in result["gates"]}
    assert gates["HUMAN_DECISION_WITHOUT_AUDIT"]["observed"]==0
    assert gates["HISTORICAL_REVIEW_AUDIT_INCOMPLETE"]["observed"]==1
    assert gates["REVIEW_DECISION_WITH_INVALID_ACTION"]["observed"]==0
    assert gates["HUMAN_DECISION_WITHOUT_AUDIT"]["status"]=="PASS"

    dq_db.add(AuditEvent(user_id=None,event_type="REVIEW_UNSUPPORTED_HUMAN_ACTION",
        entity_type="opportunity_conflict",entity_id="999",before_json={"status":"OPEN"},
        after_json={"status":"RESOLVED","decision":"UNSUPPORTED_FORCE_ACTION"},
        request_metadata={"actor":"Analyst","actor_role":"analyst","decision_kind":"HUMAN","review_audit_version":"2"},
        created_at=now+timedelta(seconds=1)))
    dq_db.flush()
    gates={row["gate_key"]:row for row in evaluate_data_quality(dq_db,scope="full",persist=False)["gates"]}
    assert gates["REVIEW_DECISION_WITH_INVALID_ACTION"]["observed"]==1
    assert gates["REVIEW_DECISION_WITH_INVALID_ACTION"]["status"]=="FAIL"


def test_unverified_legacy_and_arbitrary_human_actions_are_not_accepted_as_aliases(dq_db):
    now=datetime.now(timezone.utc)
    metadata={"actor":"Analyst","actor_role":"analyst","decision_kind":"HUMAN","review_audit_version":"2"}
    dq_db.add_all([
        AuditEvent(user_id=None,event_type="REVIEW_FIELD_KEEP",entity_type="opportunity_conflict",entity_id="boundary",
            before_json={"status":"OPEN"},after_json={"status":"RESOLVED_KEEP","decision":"FIELD_KEEP"},
            request_metadata=metadata,created_at=now),
        AuditEvent(user_id=None,event_type="REVIEW_LEGACY_ACTION",entity_type="opportunity_conflict",entity_id="1000",
            before_json={"status":"OPEN"},after_json={"status":"RESOLVED_KEEP","decision":"KEEP_CURRENT_VALUE"},
            request_metadata=metadata,created_at=now+timedelta(seconds=1)),
        AuditEvent(user_id=None,event_type="REVIEW_ARBITRARY_ACTION",entity_type="opportunity_conflict",entity_id="1001",
            before_json={"status":"OPEN"},after_json={"status":"RESOLVED_KEEP","decision":"UNTRUSTED_ACTION"},
            request_metadata=metadata,created_at=now+timedelta(seconds=2)),
    ])
    dq_db.flush()
    gates={row["gate_key"]:row for row in evaluate_data_quality(dq_db,scope="full",persist=False)["gates"]}
    assert gates["REVIEW_DECISION_WITH_INVALID_ACTION"]["observed"]==2
    assert gates["REVIEW_DECISION_WITH_INVALID_ACTION"]["status"]=="FAIL"


def test_closed_review_created_after_audit_governance_boundary_fails_without_audit(dq_db):
    src=source(dq_db);left=master(dq_db,"CURRENT-AUDIT-LEFT");record=source_record(dq_db,src,master_id=left.id)
    now=datetime.now(timezone.utc)
    dq_db.add(AuditEvent(user_id=None,event_type="REVIEW_FIELD_KEEP",entity_type="opportunity_conflict",
        entity_id="governance-boundary",before_json={"status":"OPEN"},
        after_json={"status":"RESOLVED_KEEP","decision":"FIELD_KEEP"},
        request_metadata={"actor":"Analyst","actor_role":"analyst","decision_kind":"HUMAN","review_audit_version":"2"},
        created_at=now))
    dq_db.flush()
    current=OpportunityConflict(opportunity_id=left.id,field_name="sector",conflict_type="FIELD_VALUE_CONFLICT",
        selected_value="تجاري",conflicting_value="صناعي",source_id=src.id,source_record_id=record.id,
        detected_at=now+timedelta(seconds=1),status="RESOLVED_KEEP")
    dq_db.add(current);dq_db.flush()
    result=evaluate_data_quality(dq_db,scope="full",persist=False)
    gates={row["gate_key"]:row for row in result["gates"]}
    assert gates["HUMAN_DECISION_WITHOUT_AUDIT"]["observed"]==1
    assert gates["HUMAN_DECISION_WITHOUT_AUDIT"]["sample_ids"]==[f"opportunity_conflict:{current.id}"]
    assert gates["HISTORICAL_REVIEW_AUDIT_INCOMPLETE"]["observed"]==0


def test_recommendation_snapshot_explanation_and_evidence_gates(dq_db):
    now=datetime.now(timezone.utc)
    complete={"action":None,"confidence":"NONE","reason":"لا توجد توصية آلية موثوقة لهذه الحالة.",
        "supporting_evidence":[],"contradictory_evidence":[],"version":"a"*64}
    metadata={"actor":"Analyst","actor_role":"analyst","decision_kind":"HUMAN","review_audit_version":"2"}
    dq_db.add_all([
        AuditEvent(user_id=None,event_type="REVIEW_RECOMMENDATION_SHOWN",entity_type="opportunity_conflict",entity_id="good",
            before_json=None,after_json={**complete,"evidence_references":[{"review_id":1,"basis":"NO_SUPPORTED_RULE"}]},
            request_metadata=metadata,created_at=now),
        AuditEvent(user_id=None,event_type="REVIEW_FIELD_KEEP",entity_type="opportunity_conflict",entity_id="good",
            before_json={"status":"OPEN"},after_json={"status":"RESOLVED_KEEP","decision":"FIELD_KEEP","reason":"Kept current value.",
                "evidence":{"recommendation":complete}},request_metadata=metadata,created_at=now),
    ])
    dq_db.flush()
    gates={row["gate_key"]:row for row in evaluate_data_quality(dq_db,scope="full",persist=False)["gates"]}
    assert gates["RECOMMENDATION_WITHOUT_EVIDENCE"]["observed"]==0
    assert gates["RECOMMENDATION_WITHOUT_EXPLANATION"]["observed"]==0
    assert gates["RECOMMENDATION_SNAPSHOT_MISSING"]["observed"]==0

    dq_db.add_all([
        AuditEvent(user_id=None,event_type="REVIEW_RECOMMENDATION_SHOWN",entity_type="opportunity_conflict",entity_id="bad",
            before_json=None,after_json={"action":"use_source","confidence":"HIGH","reason":"","supporting_evidence":[]},
            request_metadata=metadata,created_at=now+timedelta(seconds=1)),
        AuditEvent(user_id=None,event_type="REVIEW_FIELD_KEEP",entity_type="opportunity_conflict",entity_id="bad",
            before_json={"status":"OPEN"},after_json={"status":"RESOLVED_KEEP","decision":"FIELD_KEEP","reason":"Kept value.",
                "evidence":{"recommendation":{"action":"use_source","confidence":"HIGH","reason":"",
                    "supporting_evidence":[],"contradictory_evidence":[],"version":None}}},
            request_metadata=metadata,created_at=now+timedelta(seconds=2)),
    ])
    dq_db.flush()
    gates={row["gate_key"]:row for row in evaluate_data_quality(dq_db,scope="full",persist=False)["gates"]}
    assert gates["RECOMMENDATION_WITHOUT_EVIDENCE"]["observed"]==2
    assert gates["RECOMMENDATION_WITHOUT_EXPLANATION"]["observed"]==2
    assert gates["RECOMMENDATION_SNAPSHOT_MISSING"]["observed"]==1

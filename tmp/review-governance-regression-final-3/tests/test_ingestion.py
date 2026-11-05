from datetime import datetime, timezone
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.models import Base, Source, Opportunity, SourceOpportunity, SourceObservation, ChangeHistory, DuplicateCandidate, AlertEvent
from app.adapters import RawOpportunity
from app.service import _safe_record, reconcile_missing_records
from app.normalization import normalize_reference

def setup_db():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db=Session(engine)
    sources=[]
    for key in ("furas","municipality"):
        source=Source(source_key=key,source_name_ar=key,organization_name=key,base_url="https://example.test",opportunities_url="https://example.test",priority=1,polling_frequency_minutes=60,enabled=True,extraction_method="test",notes="",sync_status="HEALTHY",last_record_count=0)
        db.add(source); sources.append(source)
    db.flush()
    return engine,db,sources

def raw(source_id,title,*,reference=None,location="الأحساء",area="5000 م²",deadline="2026-11-17",owner=None,status="متاحة",raw_payload=None,duration=None):
    return RawOpportunity(str(source_id),title,f"https://example.test/{source_id}",owner=owner,location=location,area_text=area,deadline=deadline,status=status,reference=reference,description=title,contract_text=duration,raw=raw_payload or {"fixture":True})

def collect(db,source,record):
    counts={"raw_count":0,"ahsa_count":0,"new_count":0,"duplicate_count":0,"update_count":0,"rejected_count":0}
    _safe_record(db,source,record,counts); db.commit(); return counts

def add_source(db,key):
    source=Source(source_key=key,source_name_ar=key,organization_name=key,base_url="https://example.test",opportunities_url="https://example.test",priority=3,polling_frequency_minutes=360,enabled=True,extraction_method="test",notes="",sync_status="NEVER_SYNCED",last_record_count=0)
    db.add(source);db.flush();return source

def test_unverified_reference_string_is_reviewed_not_auto_linked():
    engine,db,sources=setup_db()
    collect(db,sources[0],raw("1","مصنع تدوير النخيل بالأحساء",reference="06-26-189921-64005",owner="جهة حكومية"))
    collect(db,sources[1],raw("2","إنشاء منشأة تحويلية لمنتجات النخيل",reference="06-26-189921-64005",owner="أمانة الأحساء"))
    assert db.scalar(select(func.count(Opportunity.id)))==2
    assert db.scalar(select(func.count(SourceOpportunity.id)))==2
    assert db.scalar(select(func.count(DuplicateCandidate.id)).where(DuplicateCandidate.status=="PENDING"))==1
    db.close();engine.dispose()

def test_future_sync_canonicalizes_master_but_preserves_source_owner_status_and_payload():
    engine,db,sources=setup_db()
    source_raw=raw("canonical-future","فرصة تشغيل منشأة بالأحساء",owner="أمانة محافظة الأحساء",status="UNKNOWN",raw_payload={"source_owner":"أمانة محافظة الأحساء","source_marker":"unchanged"})
    source_raw.activity="اخرى"
    original_fingerprint=source_raw.content_hash
    collect(db,sources[0],source_raw)
    master=db.scalars(select(Opportunity)).one()
    source_record=db.scalars(select(SourceOpportunity)).one()
    assert master.opportunity_owner=="أمانة الأحساء"
    assert master.sector=="أخرى"
    assert master.activity=="أخرى"
    assert master.opportunity_type is None
    assert master.status=="حالة غير معروفة"
    assert source_record.source_owner=="أمانة محافظة الأحساء"
    assert source_record.raw_status=="UNKNOWN"
    assert source_record.source_activity=="اخرى"
    assert source_record.raw_data_json=={"source_owner":"أمانة محافظة الأحساء","source_marker":"unchanged"}
    assert source_raw.content_hash == original_fingerprint
    assert source_record.standardization_version == "21"
    assert source_record.standardized_data_json["fields"]["opportunity_owner"]["raw"] == "أمانة محافظة الأحساء"
    assert source_record.standardized_data_json["fields"]["opportunity_owner"]["canonical_id"] == "al_ahsa_municipality"
    db.close();engine.dispose()

def test_future_furas_ingestion_marks_unknown_date_semantics_and_preserves_all_raw_attributes():
    engine,db,sources=setup_db()
    attributes={"STARTDATE":1792540800000,"ENDDATE":1793059200000,"LASTRFPSELLDATE":1793059200000,
        "LASTBIDATE":"","ENVELOPESOPENDATE":1793145600000}
    payload={"attributes":attributes,"publication_date":None,"source_endpoint":"https://example.test/furas"}
    source_raw=raw("future-furas-date","فرصة استثمارية بالأحساء",reference="FURAS-FUTURE-1",status="Announced",
        deadline=None,raw_payload=payload)
    original_payload=dict(payload)
    collect(db,sources[0],source_raw)
    master=db.scalars(select(Opportunity)).one()
    source_record=db.scalars(select(SourceOpportunity)).one()
    date_fields=source_record.standardized_data_json["fields"]
    assert master.submission_deadline is None
    assert master.publication_date is None
    assert source_record.raw_dates=={"deadline":None}
    assert source_record.raw_data_json==original_payload
    assert source_record.standardization_version=="21"
    assert source_record.standardized_data_json["version"]=="21"
    assert date_fields["submission_deadline"]["mapping_status"]=="UNVERIFIED"
    assert date_fields["submission_deadline"]["rule"]=="furas_dates_raw_only_v1"
    assert date_fields["submission_deadline"]["raw"]=={key:attributes.get(key) for key in ("STARTDATE","ENDDATE","LASTRFPSELLDATE","LASTBIDATE")}
    assert date_fields["publication_date"]["mapping_status"]=="UNVERIFIED"
    assert date_fields["publication_date"]["raw"]==attributes["STARTDATE"]
    db.close();engine.dispose()

def test_exact_identifier_links_cross_language_titles_despite_taxonomy_difference():
    engine,db,sources=setup_db()
    invest=add_source(db,"invest-saudi")
    ref="06-26-189921-64005"
    collect(db,sources[0],raw("1","تطوير مستشفى في الأحساء",reference=ref,owner="جهة حكومية",raw_payload={"attributes":{"OPPORTUNITYID":ref},"sector":"Healthcare"}))
    collect(db,invest,raw("2","Al Ahsa Hospital Development",reference=ref,raw_payload={"source_record_family":"project","modalData":{"opportunityNumber":ref},"sector":"Real Estate"}))
    assert db.scalar(select(func.count(Opportunity.id)))==1
    assert db.scalar(select(func.count(SourceOpportunity.id)))==2
    db.close();engine.dispose()

def test_official_reference_with_conflicting_parcel_is_queued_not_merged():
    engine,db,sources=setup_db();invest=add_source(db,"invest-saudi")
    ref="06-26-189921-64005"
    title_a="إنشاء وتشغيل مستودع القطعة رقم 12 بالمخطط 14/16"
    title_b="إنشاء وتشغيل مستودع القطعة رقم 13 بالمخطط 14/16"
    collect(db,sources[0],raw("furas-12",title_a,reference=ref,owner="أمانة الأحساء",raw_payload={"attributes":{"OPPORTUNITYID":ref}}))
    collect(db,invest,raw("invest-13",title_b,reference=ref,owner="أمانة الأحساء",raw_payload={"source_record_family":"project","modalData":{"opportunityNumber":ref}}))
    assert db.scalar(select(func.count(Opportunity.id)))==2
    candidate=db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status=="PENDING")).one()
    assert candidate.explanation_json["auto_merge_safe"] is False
    assert "conflicting parcel/plot identifiers" in candidate.explanation_json["contradicting_evidence"]
    db.close();engine.dispose()

def test_same_site_with_different_official_references_is_reviewed_not_auto_merged():
    engine,db,sources=setup_db();invest=add_source(db,"invest-saudi")
    title="إنشاء وتشغيل القطعة رقم 12 لنشاط صناعي بالمخطط 14/16"
    ref_a="06-26-189921-64005";ref_b="06-26-189921-64006"
    collect(db,sources[0],raw("furas-12",title,reference=ref_a,owner="أمانة الأحساء",raw_payload={"attributes":{"OPPORTUNITYID":ref_a}}))
    collect(db,invest,raw("invest-12",title,reference=ref_b,owner="أمانة الأحساء",raw_payload={"source_record_family":"project","modalData":{"opportunityNumber":ref_b}}))
    assert db.scalar(select(func.count(Opportunity.id)))==2
    candidate=db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status=="PENDING")).one()
    assert candidate.explanation_json["auto_merge_safe"] is False
    db.close();engine.dispose()

def test_location_review_is_written_to_separate_queue(monkeypatch):
    import asyncio
    import app.service as service
    from app.models import LocationReview
    engine,db,sources=setup_db();source=sources[1]
    candidate=raw("low","Opportunity with Al Ahsa only in the narrative",location="Eastern Province",raw_payload={"location_confidence_score":.8,"location_detection_method":"DESCRIPTION_ONLY_EXPLICIT_AL_AHSA","location_evidence":"Description mentions Al Ahsa"})
    class Adapter:
        metrics={"source_total_reported":1,"pages_requested":1,"pages_successful":1,"unique_records":1,"pagination_complete":True}
        raw_candidates=[candidate]
        location_reviews=[{"external_id":"low","title":candidate.title,"sector":"Healthcare","location":"Eastern Province","description":candidate.description,"confidence_score":.8,"evidence":"Description mentions Al Ahsa","reason":"Verify project site"}]
        async def fetch(self,client):return [],1
    monkeypatch.setattr(service,"SessionLocal",lambda:db)
    monkeypatch.setitem(service.ADAPTERS,"municipality",lambda:Adapter())
    result=asyncio.run(service.sync_source("municipality"))
    review=db.scalars(select(LocationReview)).one()
    source_record=db.scalars(select(SourceOpportunity)).one()
    assert result["status"]=="SUCCESS"
    completed_job=db.scalars(select(__import__("app.models",fromlist=["SyncJob"]).SyncJob)).one()
    assert completed_job.job_state=="COMPLETED"
    assert review.status=="PENDING" and review.source_record_id==source_record.id
    assert source_record.master_opportunity_id is None
    assert result["location_review_count"]==1
    db.close();engine.dispose()

def test_investsaudi_exact_furas_link_supplies_locality_and_merges_across_taxonomy(monkeypatch):
    import asyncio
    import app.service as service
    engine,db,sources=setup_db()
    reference="FURAS-ALAHSA-99"
    collect(db,sources[0],raw("furas-id","Palm processing facility",reference=reference,owner="جهة حكومية",raw_payload={"attributes":{"OPPORTUNITYID":reference},"sector":"Agriculture"}))
    national=Source(source_key="invest-saudi",source_name_ar="استثمر في السعودية",organization_name="وزارة الاستثمار",base_url="https://investsaudi.sa",opportunities_url="https://investsaudi.sa/investment-opportunities",priority=3,polling_frequency_minutes=360,enabled=True,extraction_method="test",notes="",sync_status="NEVER_SYNCED",last_record_count=0)
    db.add(national);db.commit()
    candidate=RawOpportunity("project:10","Palm processing project","https://investsaudi.sa/investment-opportunities",owner=None,location="Eastern Province",activity="Industrial",reference="FURAS ALAHSA 99",raw={"location_confidence_score":.3,"location_detection_method":"EASTERN_PROVINCE_ONLY","source_record_family":"project","modalData":{"opportunityNumber":"FURAS ALAHSA 99"}})
    class Adapter:
        metrics={"source_total_reported":1,"pages_requested":2,"pages_successful":2,"unique_records":1,"pagination_complete":True,"accepted_records":0,"location_review_count":0,"rejected_records":1}
        raw_candidates=[candidate]
        location_reviews=[]
        async def fetch(self,client):return [],2
    monkeypatch.setattr(service,"SessionLocal",lambda:db)
    monkeypatch.setitem(service.ADAPTERS,"invest-saudi",lambda:Adapter())
    result=asyncio.run(service.sync_source("invest-saudi"))
    records=db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
    assert result["status"]=="SUCCESS" and result["ahsa_count"]==1 and result["duplicate_count"]==1
    assert db.scalar(select(func.count(Opportunity.id)))==1
    assert records[-1].master_opportunity_id==records[0].master_opportunity_id
    assert records[-1].raw_data_json["location_detection_method"]=="LINKED_FURAS_REFERENCE"
    db.close();engine.dispose()

def test_normalized_reference_matches_arabic_digits_and_punctuation():
    engine,db,sources=setup_db()
    invest=add_source(db,"invest-saudi")
    arabic="٠٦-٢٦-١٨٩٩٢١-٦٤٠٠٥";western="06/26/189921/64005"
    collect(db,sources[0],raw("1","مصنع تدوير النخيل بالأحساء",reference=arabic,owner="جهة حكومية",raw_payload={"attributes":{"OPPORTUNITYID":arabic}}))
    collect(db,invest,raw("2","منشأة تحويلية لمنتجات النخيل",reference=western,raw_payload={"source_record_family":"project","modalData":{"opportunityNumber":western}}))
    assert normalize_reference(arabic)==normalize_reference(western)
    master=db.scalars(select(Opportunity)).one()
    source_record=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==sources[0].id)).one()
    assert master.reference_number==arabic
    assert master.reference_number_normalized=="062618992164005"
    assert source_record.source_reference_number_normalized=="062618992164005"
    db.close();engine.dispose()

def test_same_title_different_district_is_separate():
    engine,db,sources=setup_db(); title="إنشاء وتشغيل وصيانة مجمع تجاري"
    collect(db,sources[0],raw("1",title,location="الأحساء حي السلمانية"))
    collect(db,sources[1],raw("2",title,location="الأحساء حي الفتح"))
    assert db.scalar(select(func.count(Opportunity.id)))==2
    db.close();engine.dispose()

def test_cross_language_title_without_shared_identity_does_not_auto_merge():
    engine,db,sources=setup_db()
    collect(db,sources[0],raw("1","إنشاء وتشغيل وصيانة مستودع ومكاتب إدارية",location="الأحساء الهفوف",area="5000 م²"))
    collect(db,sources[1],raw("2","Construction, operation and maintenance of a warehouse and administrative offices",location="Al-Ahsa Hofuf",area="5000 sqm"))
    # Same locality and area do not establish asset identity without shared parcel,
    # reference, owner, or comparable title evidence.
    assert db.scalar(select(func.count(Opportunity.id)))==2
    assert db.scalar(select(func.count(SourceOpportunity.id)))==2
    db.close();engine.dispose()

def test_materially_different_plot_is_separate():
    engine,db,sources=setup_db()
    collect(db,sources[0],raw("1","إنشاء وتشغيل مستودع قطعة رقم 12",location="الأحساء الهفوف"))
    collect(db,sources[1],raw("2","إنشاء وتشغيل مستودع قطعة رقم 13",location="الأحساء الهفوف"))
    assert db.scalar(select(func.count(Opportunity.id)))==2
    db.close();engine.dispose()

def test_low_score_strong_parcel_case_is_surfaced_for_review_not_auto_merged():
    engine,db,sources=setup_db()
    title_a="إنشاء وتشغيل وصيانة مواقف للمعدات والنقليات وورشة ومستودع ومكاتب إدارية وسكن للموظفين للقطع رقم 405/ت الى 409/ت بالمخطط رقم 14/154 الصناعية الشمالية بالعيون"
    title_b="انشاء و تشغيل و صيانة مواقف للمعدات والنقليات وورشة ومستودع ومكاتب إدارية وسكن للموظفين للقطع رقم 405 ت الى 409 ت بالمخطط رقم 14 154 الصناعية الشمالية بالاحساء - الأنشطة التجارية - ورشة"
    owner="أمانة محافظة الأحساء"
    furas_raw={"attributes":{"CITYNAME":"الاحساء","CITY_ID":"005020001","DURATION":300,"OPPORTUNITYID":"01-26-017001-36001","AMANA":owner,"ENTITIESNAME":"وزارة الشئون البلدية والقروية","STREET":"الاحساء 173"}}
    collect(db,sources[0],raw("01-26-017001-36001",title_b,reference="01-26-017001-36001",location="الاحساء الاحساء 173",area="145000",deadline="2026-10-21",owner=owner,status="Announced",raw_payload=furas_raw,duration="300"))
    collect(db,sources[1],raw("444",title_a,location="العيون",area="145000 م²",deadline="2026-10-21",owner="أمانة الأحساء",duration="25"))
    candidate=db.scalars(select(DuplicateCandidate)).one()
    assert candidate.confidence_score < .75
    assert candidate.status=="PENDING"
    assert db.scalar(select(func.count(Opportunity.id)))==2
    assert db.scalar(select(func.count(SourceOpportunity.id)))==2
    assert all(master.contract_duration_years is None for master in db.scalars(select(Opportunity)).all())
    furas_record=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_id==sources[0].id))
    duration_field=furas_record.standardized_data_json["fields"]["contract_duration_years"]
    assert duration_field["mapping_status"]=="REVIEW_REQUIRED"
    assert duration_field["rule"]=="furas_duration_unit_and_semantics_unverified_v1"
    assert duration_field["raw"]==300
    db.close();engine.dispose()

def test_similar_listings_from_same_source_are_not_fuzzy_merged():
    engine,db,sources=setup_db()
    collect(db,sources[0],raw("1","تأجير موقع شاطئي لمزاولة البيع للموقع رقم 2",location="الأحساء شاطئ العقير",area="5000 م²"))
    collect(db,sources[0],raw("2","تأجير موقع شاطئي لمزاولة البيع للموقع رقم 3",location="الأحساء شاطئ العقير",area="5000 م²"))
    assert db.scalar(select(func.count(Opportunity.id)))==2
    assert db.scalar(select(func.count(SourceOpportunity.id)))==2
    db.close();engine.dispose()

def test_deadline_change_creates_history():
    engine,db,sources=setup_db(); title="إنشاء مستودع في الأحساء"
    collect(db,sources[0],raw("1",title,deadline="2026-11-17"))
    result=collect(db,sources[0],raw("1",title,deadline="2026-11-30"))
    history=db.scalars(select(ChangeHistory)).all()
    assert len(history)==1
    assert history[0].changed_field=="submission_deadline"
    assert history[0].previous_value=="2026-11-17" and history[0].new_value=="2026-11-30"
    assert result["new_count"]==0
    db.close();engine.dispose()

def test_title_area_owner_status_and_document_updates_are_recorded():
    engine,db,sources=setup_db()
    collect(db,sources[0],raw("1","إنشاء مستودع بالأحساء",owner="الجهة المالكة",area="5000 م²",raw_payload={"documents":[{"id":"a","url":"https://example.test/a.pdf"}]}))
    collect(db,sources[0],raw("1","إنشاء وتشغيل مستودع بالأحساء",owner="الجهة المالكة المعدلة",area="5200 م²",status="ملغاة",raw_payload={"documents":[{"id":"b","url":"https://example.test/b.pdf"}]}))
    changed={x.changed_field for x in db.scalars(select(ChangeHistory)).all()}
    assert {"title_ar","land_area_sqm","opportunity_owner","status","documents"}.issubset(changed)
    assert db.scalars(select(Opportunity)).one().status=="ملغاة"
    db.close();engine.dispose()

def test_single_missing_successful_scan_does_not_remove_master_and_threshold_does():
    engine,db,sources=setup_db();collect(db,sources[0],raw("1","فرصة تشغيل مستودع بالأحساء"))
    master=db.scalars(select(Opportunity)).one(); source_record=db.scalars(select(SourceOpportunity)).one()
    source=sources[0]; source.missing_confirmation_threshold=3
    for check in range(1,3):
        reconcile_missing_records(db,source,set(),datetime.now(timezone.utc));db.flush()
        assert master.status=="متاحة"
        assert source_record.missing_successful_checks==check
    reconcile_missing_records(db,source,set(),datetime.now(timezone.utc));db.flush()
    assert master.status=="أزيلت من المصدر"
    db.close();engine.dispose()

def test_source_removal_does_not_remove_master_while_another_source_publishes_and_reappearance_is_audited():
    engine,db,sources=setup_db()
    invest=add_source(db,"invest-saudi")
    ref="06-26-189921-64005"
    first=raw("first","فرصة تشغيل مستودع بالأحساء",reference=ref,status="Announced",raw_payload={"attributes":{"OPPORTUNITYID":ref}})
    second=raw("second","فرصة تشغيل مستودع بالأحساء",reference=ref,status="متاحة",raw_payload={"source_record_family":"project","modalData":{"opportunityNumber":ref}})
    collect(db,sources[0],first);collect(db,invest,second)
    master=db.scalars(select(Opportunity)).one()
    second_record=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==invest.id)).one()
    assert master.status=="متاحة"
    assert second_record.raw_status=="متاحة"
    first_snapshot_count=db.scalar(select(func.count(SourceObservation.id)))
    invest.missing_confirmation_threshold=1
    reconcile_missing_records(db,invest,set(),datetime.now(timezone.utc));db.flush()
    assert second_record.canonical_status=="أزيلت من المصدر"
    assert master.status=="منشورة"
    assert second_record.raw_status=="متاحة"
    assert db.scalar(select(func.count(SourceObservation.id)))>first_snapshot_count
    # Reappearance restores this source row's canonical state without creating a new identity.
    collect(db,invest,second)
    assert db.scalar(select(func.count(Opportunity.id)))==1
    assert db.scalar(select(func.count(SourceOpportunity.id)))==2
    assert second_record.canonical_status=="متاحة"
    assert master.status=="متاحة"
    transitions=[row for row in db.scalars(select(ChangeHistory)).all() if row.changed_field=="source_status"]
    assert [row.new_value for row in transitions]==["أزيلت من المصدر","متاحة"]
    db.close();engine.dispose()

def test_complete_scans_remove_unlinked_source_rows_only_after_confirmation_threshold():
    engine,db,sources=setup_db();source=sources[0];source.missing_confirmation_threshold=3
    now=datetime.now(timezone.utc)
    row=SourceOpportunity(source_id=source.id,master_opportunity_id=None,source_opportunity_id="unlinked-legacy",
        source_title="سجل وطني خارج نطاق الأحساء",normalized_source_title="سجل وطني خارج نطاق الأحساء",
        source_url="https://example.test/unlinked-legacy",raw_status="UNKNOWN",canonical_status="حالة غير معروفة",
        raw_data_json={"payload":"preserved"},standardized_data_json={},raw_dates={},first_seen_at=now,
        last_seen_at=now,content_hash="unlinked-legacy-hash",parser_version="fixture")
    db.add(row);db.commit();row_id=row.id

    for expected in (1,2):
        removed=reconcile_missing_records(db,source,set(),datetime.now(timezone.utc));db.flush()
        assert removed==[]
        assert db.get(SourceOpportunity,row_id).missing_successful_checks==expected
        assert db.get(SourceOpportunity,row_id).canonical_status=="حالة غير معروفة"
        assert db.scalar(select(func.count(SourceObservation.id)))==0

    removed=reconcile_missing_records(db,source,set(),datetime.now(timezone.utc));db.flush()
    current=db.get(SourceOpportunity,row_id)
    assert current.missing_successful_checks==3
    assert current.canonical_status=="أزيلت من المصدر"
    assert current.raw_status=="UNKNOWN" and current.raw_data_json=={"payload":"preserved"}
    assert removed==[{"source_opportunity_id":"unlinked-legacy","master_opportunity_id":None,"missing_successful_checks":3}]
    assert db.scalar(select(func.count(Opportunity.id)))==0
    assert db.scalar(select(func.count(SourceObservation.id)))==1
    db.close();engine.dispose()

def test_scheduled_lifecycle_reconciliation_expires_missing_status_only_after_local_deadline_day():
    import app.service as service
    engine,db,sources=setup_db()
    collect(db,sources[0],raw("deadline-row","فرصة تقديم عرض بالأحساء",deadline="2026-10-21",status=None))
    master=db.scalars(select(Opportunity)).one();source_record=db.scalars(select(SourceOpportunity)).one()
    assert master.status=="غير محددة"
    before=db.scalar(select(func.count(SourceObservation.id)))
    result=service.reconcile_status_lifecycle(db,datetime(2026,10,21,20,tzinfo=timezone.utc))
    assert result["updated_source_statuses"]==0 and master.status=="غير محددة"
    result=service.reconcile_status_lifecycle(db,datetime(2026,10,21,21,tzinfo=timezone.utc))
    assert result["updated_source_statuses"]==1 and result["updated_master_statuses"]==1
    assert source_record.canonical_status=="منتهية" and master.status=="منتهية"
    assert db.scalar(select(func.count(SourceObservation.id)))==before+1
    db.close();engine.dispose()

def test_scheduled_lifecycle_reconciliation_covers_unlinked_source_rows_without_inventing_a_master():
    import app.service as service
    engine,db,sources=setup_db();now=datetime.now(timezone.utc)
    row=SourceOpportunity(source_id=sources[0].id,master_opportunity_id=None,source_opportunity_id="unlinked-deadline",
        source_title="سجل مصدر غير مؤهل",normalized_source_title="سجل مصدر غير مؤهل",source_url="https://example.test/unlinked",
        raw_dates={"deadline":"2020-01-01"},raw_status=None,raw_data_json={"original":True},standardized_data_json={},
        canonical_status="غير محددة",first_seen_at=now,last_seen_at=now,content_hash="unlinked-hash",parser_version="fixture")
    db.add(row);db.commit()
    result=service.reconcile_status_lifecycle(db,datetime(2026,10,19,12,tzinfo=timezone.utc))
    assert result["updated_source_statuses"]==1
    assert row.canonical_status=="منتهية"
    assert db.scalar(select(func.count(Opportunity.id)))==0
    assert db.scalar(select(func.count(SourceObservation.id)))==1
    db.close();engine.dispose()

def test_parser_failure_does_not_count_a_missing_scan_or_remove_existing_record(monkeypatch):
    import app.service as service
    engine,db,sources=setup_db(); source=sources[0]
    collect(db,source,raw("1","فرصة تشغيل مستودع بالأحساء"))
    master=db.scalars(select(Opportunity)).one(); source_record=db.scalars(select(SourceOpportunity)).one()
    master_id=master.id; source_record_id=source_record.id; source_id=source.id
    source.missing_confirmation_threshold=1
    db.commit()

    class BrokenAdapter:
        async def fetch(self,client):
            raise ValueError("fixture parser failure")

    monkeypatch.setattr(service,"SessionLocal",lambda:db)
    monkeypatch.setitem(service.ADAPTERS,source.source_key,BrokenAdapter)
    import asyncio
    result=asyncio.run(service.sync_source(source.source_key))

    assert result["status"]=="FAILED"
    assert db.get(Source,source_id).technical_health=="WARNING"
    assert db.get(SourceOpportunity,source_record_id).missing_successful_checks==0
    assert db.get(Opportunity,master_id).status=="متاحة"
    assert db.scalar(select(func.count(service.SourceError.id)))==1
    db.close();engine.dispose()

def test_incomplete_collection_warns_and_does_not_reconcile_missing_records(monkeypatch):
    import app.service as service
    engine,db,sources=setup_db(); source=sources[0]
    collect(db,source,raw("old","فرصة قديمة في الأحساء"))
    old_master=db.scalars(select(Opportunity)).one(); old_record=db.scalars(select(SourceOpportunity)).one()
    old_master_id=old_master.id; old_record_id=old_record.id; source.missing_confirmation_threshold=1;db.commit()

    class PartialAdapter:
        def __init__(self): self.metrics={}
        async def fetch(self,client):
            self.metrics={"source_total_reported":2,"pages_requested":2,"pages_successful":1,
              "records_received":1,"records_parsed":1,"unique_records":1,"pagination_complete":False}
            return [raw("new","فرصة جديدة في الأحساء")],1

    monkeypatch.setattr(service,"SessionLocal",lambda:db)
    monkeypatch.setitem(service.ADAPTERS,source.source_key,PartialAdapter)
    import asyncio
    result=asyncio.run(service.sync_source(source.source_key))

    assert result["status"]=="INCOMPLETE_COLLECTION_WARNING"
    assert result["collection_completeness_percent"]==50.0
    assert db.get(SourceOpportunity,old_record_id).missing_successful_checks==0
    assert db.get(Opportunity,old_master_id).status=="متاحة"
    db.close();engine.dispose()

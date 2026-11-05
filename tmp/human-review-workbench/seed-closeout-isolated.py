"""Add isolated review fixtures for the governed UI closeout flows."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.database import SessionLocal
from app.models import FieldProvenance, Opportunity, OpportunityConflict, Source, SourceOpportunity

now = datetime.now(timezone.utc)
with SessionLocal() as db:
    conflict_source = db.scalar(select(Source).order_by(Source.id))
    conflict_source.priority = 2
    authority = Source(source_key="wb-authority", source_name_ar="مصدر حاكم للاختبار",
        organization_name="جهة اختبار", base_url="https://authority.example.test",
        opportunities_url="https://authority.example.test/opportunities", priority=1,
        polling_frequency_minutes=360, enabled=True, extraction_method="fixture", notes="")
    db.add(authority); db.flush()

    # Make the two original conflicts produce a medium recommendation to keep.
    original_conflicts = db.scalars(select(OpportunityConflict).order_by(OpportunityConflict.id)).all()
    for conflict in original_conflicts:
        if conflict.field_name == "activity":
            record = db.get(SourceOpportunity, conflict.source_record_id)
            standardized = dict(record.standardized_data_json or {})
            fields = dict(standardized.get("fields") or {})
            fields["activity"] = {"value":"ضيافة","mapping_status":"MAPPED","rule":"WB_ACTIVITY_V1"}
            standardized["fields"] = fields
            record.standardized_data_json = standardized
    for master_id in sorted({conflict.opportunity_id for conflict in original_conflicts}):
        master = db.get(Opportunity, master_id)
        record = SourceOpportunity(source_id=authority.id, master_opportunity_id=master.id,
            source_opportunity_id=f"authority-{master.id}", source_title=master.title_ar,
            normalized_source_title=master.normalized_title, source_url=f"https://authority.example.test/{master.id}",
            source_owner=master.opportunity_owner, raw_location="الهفوف", raw_status="منشورة",
            canonical_status="منشورة", raw_data_json={"sector":"تجاري"},
            standardized_data_json={"fields":{
                "sector":{"value":"تجاري","mapping_status":"MAPPED","rule":"WB_AUTHORITY_FIXTURE_V1"},
                "activity":{"value":"تجزئة","mapping_status":"MAPPED","rule":"WB_AUTHORITY_FIXTURE_V1"}}},
            raw_dates={}, first_seen_at=now, last_seen_at=now, content_hash=(f"a{master.id}"*32)[:64],
            parser_version="fixture")
        db.add(record); db.flush()
        for field,value in (("sector","تجاري"),("activity","تجزئة")):
            db.add(FieldProvenance(opportunity_id=master.id, field_name=field, selected_value=value,
                source_id=authority.id, source_record_id=record.id, captured_at=now, confidence=.99))

    # Two matching conflicts are reserved for the deterministic batch flow.
    for index in (3, 4):
        master = Opportunity(canonical_id=f"WB-BATCH-{index}", title_ar=f"فرصة دفعة {index}",
            normalized_title=f"فرصة دفعة {index}", opportunity_owner="جهة اختبار",
            primary_publication_platform=conflict_source.source_name_ar, city="الأحساء", district="الهفوف",
            sector="تجاري", activity="تجزئة", status="منشورة", location_confidence_score=.9,
            location_detection_method="fixture", location_evidence="fixture", data_quality_score=.9,
            manual_review_required=False, first_seen_at=now, last_seen_at=now, last_updated_at=now,
            created_at=now, updated_at=now)
        db.add(master); db.flush()
        conflict_record = SourceOpportunity(source_id=conflict_source.id, master_opportunity_id=master.id,
            source_opportunity_id=f"wb-batch-{index}", source_title=master.title_ar,
            normalized_source_title=master.normalized_title, source_url=f"https://example.test/item/{index}",
            source_owner="جهة اختبار", raw_location="الهفوف", raw_status="منشورة", canonical_status="منشورة",
            raw_data_json={"sector":"صناعي"},
            standardized_data_json={"fields":{"sector":{"value":"صناعي","mapping_status":"MAPPED","rule":"WB_EXPLICIT_SECTOR_V1"}}},
            raw_dates={}, first_seen_at=now, last_seen_at=now, content_hash="b"*64, parser_version="fixture")
        db.add(conflict_record); db.flush()
        authority_record = SourceOpportunity(source_id=authority.id, master_opportunity_id=master.id,
            source_opportunity_id=f"batch-authority-{index}", source_title=master.title_ar,
            normalized_source_title=master.normalized_title, source_url=f"https://authority.example.test/batch/{index}",
            source_owner="جهة اختبار", raw_location="الهفوف", raw_status="منشورة", canonical_status="منشورة",
            raw_data_json={"sector":"تجاري"},
            standardized_data_json={"fields":{"sector":{"value":"تجاري","mapping_status":"MAPPED","rule":"WB_AUTHORITY_FIXTURE_V1"}}},
            raw_dates={}, first_seen_at=now, last_seen_at=now, content_hash=f"d{index}"*32, parser_version="fixture")
        db.add(authority_record); db.flush()
        db.add(FieldProvenance(opportunity_id=master.id, field_name="sector", selected_value="تجاري",
            source_id=authority.id, source_record_id=authority_record.id, captured_at=now, confidence=.99))
        db.add(OpportunityConflict(opportunity_id=master.id, field_name="sector", conflict_type="FIELD_VALUE_CONFLICT",
            selected_value="تجاري", conflicting_value="صناعي", source_id=conflict_source.id,
            source_record_id=conflict_record.id, detected_at=now, status="OPEN"))

    # A deliberately mixed activity conflict makes batch preview reject a mixed signature.
    master = Opportunity(canonical_id="WB-MIXED-5", title_ar="فرصة نشاط مختلط", normalized_title="فرصة نشاط مختلط",
        opportunity_owner="جهة اختبار", primary_publication_platform=conflict_source.source_name_ar,
        city="الأحساء", district="الهفوف", sector="تجاري", activity="تجزئة", status="منشورة",
        location_confidence_score=.9, location_detection_method="fixture", location_evidence="fixture",
        data_quality_score=.9, manual_review_required=False, first_seen_at=now, last_seen_at=now,
        last_updated_at=now, created_at=now, updated_at=now)
    db.add(master); db.flush()
    conflict_record = SourceOpportunity(source_id=conflict_source.id, master_opportunity_id=master.id,
        source_opportunity_id="wb-mixed-5", source_title=master.title_ar, normalized_source_title=master.normalized_title,
        source_url="https://example.test/item/mixed", source_owner="جهة اختبار", raw_location="الهفوف",
        raw_status="منشورة", canonical_status="منشورة", raw_data_json={"activity":"تصنيع"},
        standardized_data_json={"fields":{"activity":{"value":"تصنيع","mapping_status":"MAPPED","rule":"WB_ACTIVITY_V1"}}},
        raw_dates={}, first_seen_at=now, last_seen_at=now, content_hash="c"*64, parser_version="fixture")
    db.add(conflict_record); db.flush()
    authority_record = SourceOpportunity(source_id=authority.id, master_opportunity_id=master.id,
        source_opportunity_id="mixed-authority-5", source_title=master.title_ar,
        normalized_source_title=master.normalized_title, source_url="https://authority.example.test/mixed",
        source_owner="جهة اختبار", raw_location="الهفوف", raw_status="منشورة", canonical_status="منشورة",
        raw_data_json={"activity":"تجزئة"},
        standardized_data_json={"fields":{"activity":{"value":"تجزئة","mapping_status":"MAPPED","rule":"WB_AUTHORITY_FIXTURE_V1"}}},
        raw_dates={}, first_seen_at=now, last_seen_at=now, content_hash="e"*64, parser_version="fixture")
    db.add(authority_record); db.flush()
    db.add(FieldProvenance(opportunity_id=master.id, field_name="activity", selected_value="تجزئة",
        source_id=authority.id, source_record_id=authority_record.id, captured_at=now, confidence=.99))
    db.add(OpportunityConflict(opportunity_id=master.id, field_name="activity", conflict_type="FIELD_VALUE_CONFLICT",
        selected_value="تجزئة", conflicting_value="تصنيع", source_id=conflict_source.id,
        source_record_id=conflict_record.id, detected_at=now, status="OPEN"))
    db.commit()
    print({"added_deterministic_batch_reviews": 2, "added_mixed_signature_review": 1,
           "authority_source_id": authority.id})

"""Seed the remaining isolated UI closeout cases."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.database import SessionLocal
from app.models import FieldProvenance, Opportunity, OpportunityConflict, Source, SourceOpportunity

now = datetime.now(timezone.utc)
with SessionLocal() as db:
    conflict_source = db.scalar(select(Source).where(Source.source_key == "furas"))
    authority = db.scalar(select(Source).where(Source.source_key == "wb-authority"))
    for index in (6, 7):
        field = "sector" if index == 6 else "sector"
        current, competing = ("تجاري", "صناعي")
        master = Opportunity(canonical_id=f"WB-BATCH-{index}", title_ar=f"فرصة دفعة {index}",
            normalized_title=f"فرصة دفعة {index}", opportunity_owner="جهة اختبار",
            primary_publication_platform=conflict_source.source_name_ar, city="الأحساء", district="الهفوف",
            sector=current, activity="تجزئة", status="منشورة", location_confidence_score=.9,
            location_detection_method="fixture", location_evidence="fixture", data_quality_score=.9,
            manual_review_required=False, first_seen_at=now, last_seen_at=now, last_updated_at=now,
            created_at=now, updated_at=now)
        db.add(master); db.flush()
        source_record = SourceOpportunity(source_id=conflict_source.id, master_opportunity_id=master.id,
            source_opportunity_id=f"wb-batch-{index}", source_title=master.title_ar,
            normalized_source_title=master.normalized_title, source_url=f"https://example.test/item/{index}",
            source_owner="جهة اختبار", raw_location="الهفوف", raw_status="منشورة", canonical_status="منشورة",
            raw_data_json={field:competing}, standardized_data_json={"fields":{field:{"value":competing,
                "mapping_status":"MAPPED","rule":"WB_EXPLICIT_SECTOR_V1"}}}, raw_dates={},
            first_seen_at=now, last_seen_at=now, content_hash="b"*64, parser_version="fixture")
        db.add(source_record); db.flush()
        authority_record = SourceOpportunity(source_id=authority.id, master_opportunity_id=master.id,
            source_opportunity_id=f"batch-authority-{index}", source_title=master.title_ar,
            normalized_source_title=master.normalized_title, source_url=f"https://authority.example.test/batch/{index}",
            source_owner="جهة اختبار", raw_location="الهفوف", raw_status="منشورة", canonical_status="منشورة",
            raw_data_json={field:current}, standardized_data_json={"fields":{field:{"value":current,
                "mapping_status":"MAPPED","rule":"WB_AUTHORITY_FIXTURE_V1"}}}, raw_dates={},
            first_seen_at=now, last_seen_at=now, content_hash=f"d{index}"*32, parser_version="fixture")
        db.add(authority_record); db.flush()
        db.add(FieldProvenance(opportunity_id=master.id, field_name=field, selected_value=current,
            source_id=authority.id, source_record_id=authority_record.id, captured_at=now, confidence=.99))
        db.add(OpportunityConflict(opportunity_id=master.id, field_name=field, conflict_type="FIELD_VALUE_CONFLICT",
            selected_value=current, conflicting_value=competing, source_id=conflict_source.id,
            source_record_id=source_record.id, detected_at=now, status="OPEN"))

    # Independent activity review is retained for mixed-signature rejection.
    master = Opportunity(canonical_id="WB-MIXED-8", title_ar="فرصة نشاط مختلط", normalized_title="فرصة نشاط مختلط",
        opportunity_owner="جهة اختبار", primary_publication_platform=conflict_source.source_name_ar,
        city="الأحساء", district="الهفوف", sector="تجاري", activity="تجزئة", status="منشورة",
        location_confidence_score=.9, location_detection_method="fixture", location_evidence="fixture",
        data_quality_score=.9, manual_review_required=False, first_seen_at=now, last_seen_at=now,
        last_updated_at=now, created_at=now, updated_at=now)
    db.add(master); db.flush()
    source_record = SourceOpportunity(source_id=conflict_source.id, master_opportunity_id=master.id,
        source_opportunity_id="wb-mixed-8", source_title=master.title_ar, normalized_source_title=master.normalized_title,
        source_url="https://example.test/item/mixed-8", source_owner="جهة اختبار", raw_location="الهفوف",
        raw_status="منشورة", canonical_status="منشورة", raw_data_json={"activity":"تصنيع"},
        standardized_data_json={"fields":{"activity":{"value":"تصنيع","mapping_status":"MAPPED","rule":"WB_ACTIVITY_V1"}}},
        raw_dates={}, first_seen_at=now, last_seen_at=now, content_hash="f"*64, parser_version="fixture")
    db.add(source_record); db.flush()
    authority_record = SourceOpportunity(source_id=authority.id, master_opportunity_id=master.id,
        source_opportunity_id="mixed-authority-8", source_title=master.title_ar, normalized_source_title=master.normalized_title,
        source_url="https://authority.example.test/mixed-8", source_owner="جهة اختبار", raw_location="الهفوف",
        raw_status="منشورة", canonical_status="منشورة", raw_data_json={"activity":"تجزئة"},
        standardized_data_json={"fields":{"activity":{"value":"تجزئة","mapping_status":"MAPPED","rule":"WB_AUTHORITY_FIXTURE_V1"}}},
        raw_dates={}, first_seen_at=now, last_seen_at=now, content_hash="g"*64, parser_version="fixture")
    db.add(authority_record); db.flush()
    db.add(FieldProvenance(opportunity_id=master.id, field_name="activity", selected_value="تجزئة",
        source_id=authority.id, source_record_id=authority_record.id, captured_at=now, confidence=.99))
    db.add(OpportunityConflict(opportunity_id=master.id, field_name="activity", conflict_type="FIELD_VALUE_CONFLICT",
        selected_value="تجزئة", conflicting_value="تصنيع", source_id=conflict_source.id,
        source_record_id=source_record.id, detected_at=now, status="OPEN"))
    db.commit()
    print({"added_batch_signatures":2,"added_mixed_activity_case":1})

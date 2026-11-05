"""Seed synthetic human-review cases in the isolated Playwright SQLite database."""
from datetime import datetime, timezone

from app.database import SessionLocal, init_db
from app.models import FieldProvenance, Opportunity, OpportunityConflict, Source, SourceOpportunity

init_db()
now = datetime.now(timezone.utc)

with SessionLocal() as db:
    conflict_source = db.query(Source).filter_by(source_key="wb-playwright-conflict").one_or_none()
    if conflict_source is None:
        conflict_source = Source(source_key="wb-playwright-conflict", source_name_ar="مصدر تعارض اختباري",
            organization_name="جهة اختبار", base_url="https://conflict.example.test",
            opportunities_url="https://conflict.example.test/opportunities", priority=2,
            polling_frequency_minutes=360, enabled=True, extraction_method="fixture", notes="Synthetic test source")
        db.add(conflict_source)
    authority = db.query(Source).filter_by(source_key="wb-playwright-authority").one_or_none()
    if authority is None:
        authority = Source(source_key="wb-playwright-authority", source_name_ar="مصدر حاكم اختباري",
            organization_name="جهة اختبار", base_url="https://authority.example.test",
            opportunities_url="https://authority.example.test/opportunities", priority=1,
            polling_frequency_minutes=360, enabled=True, extraction_method="fixture", notes="Synthetic test source")
        db.add(authority)
    db.flush()

    def add_case(key: str, title: str, field: str, canonical: str, competing: str, conflict_type: str):
        master = Opportunity(canonical_id=key, title_ar=title, normalized_title=title,
            opportunity_owner="جهة اختبار", primary_publication_platform=conflict_source.source_name_ar,
            city="الأحساء", district="الهفوف", sector=canonical if field == "sector" else "تجاري",
            activity=canonical if field == "activity" else "تجزئة", status="منشورة",
            location_confidence_score=.95, location_detection_method="fixture", location_evidence="synthetic",
            data_quality_score=.95, manual_review_required=False, first_seen_at=now, last_seen_at=now,
            last_updated_at=now, created_at=now, updated_at=now)
        db.add(master); db.flush()
        source_record = SourceOpportunity(source_id=conflict_source.id, master_opportunity_id=master.id,
            source_opportunity_id=f"{key}-conflict", source_title=title, normalized_source_title=title,
            source_url=f"https://conflict.example.test/item/{key}", source_owner="جهة اختبار",
            raw_location="الهفوف", raw_status="منشورة", canonical_status="منشورة",
            raw_data_json={field: competing, "description": "Synthetic review evidence."},
            standardized_data_json={"fields": {field: {"value": competing, "mapping_status": "MAPPED",
                "rule": "PLAYWRIGHT_EXPLICIT_FIXTURE_V1"}}}, raw_dates={}, first_seen_at=now,
            last_seen_at=now, content_hash=(key.encode().hex()*32)[:64], parser_version="fixture")
        db.add(source_record); db.flush()
        authority_record = SourceOpportunity(source_id=authority.id, master_opportunity_id=master.id,
            source_opportunity_id=f"{key}-authority", source_title=title, normalized_source_title=title,
            source_url=f"https://authority.example.test/item/{key}", source_owner="جهة اختبار",
            raw_location="الهفوف", raw_status="منشورة", canonical_status="منشورة",
            raw_data_json={field: canonical}, standardized_data_json={"fields": {field: {"value": canonical,
                "mapping_status": "MAPPED", "rule": "PLAYWRIGHT_AUTHORITY_FIXTURE_V1"}}}, raw_dates={},
            first_seen_at=now, last_seen_at=now, content_hash=("a"+key.encode().hex()*32)[:64], parser_version="fixture")
        db.add(authority_record); db.flush()
        db.add(FieldProvenance(opportunity_id=master.id, field_name=field, selected_value=canonical,
            source_id=authority.id, source_record_id=authority_record.id, captured_at=now, confidence=.99))
        conflict = OpportunityConflict(opportunity_id=master.id, field_name=field, conflict_type=conflict_type,
            selected_value=canonical, conflicting_value=competing, source_id=conflict_source.id,
            source_record_id=source_record.id, detected_at=now, status="OPEN")
        db.add(conflict)

    existing = {row.canonical_id for row in db.query(Opportunity).filter(Opportunity.canonical_id.like("WB-PLAYWRIGHT-%")).all()}
    cases = [
        ("WB-PLAYWRIGHT-SECTOR", "فرصة اختبار توصية القطاع", "sector", "تجاري", "صناعي", "TAXONOMY_CONFLICT"),
        ("WB-PLAYWRIGHT-ACTIVITY", "فرصة اختبار تجاوز التوصية", "activity", "تجزئة", "ضيافة", "FIELD_VALUE_CONFLICT"),
        ("WB-PLAYWRIGHT-BATCH-1", "فرصة دفعة اختبار 1", "sector", "تجاري", "صناعي", "FIELD_VALUE_CONFLICT"),
        ("WB-PLAYWRIGHT-BATCH-2", "فرصة دفعة اختبار 2", "sector", "تجاري", "صناعي", "FIELD_VALUE_CONFLICT"),
        ("WB-PLAYWRIGHT-MIXED", "فرصة اختبار توقيع مختلط", "activity", "تجزئة", "تصنيع", "FIELD_VALUE_CONFLICT"),
        ("WB-PLAYWRIGHT-OTHER-SECTOR", "فرصة اختبار قطاع إضافية", "sector", "تجاري", "زراعي", "FIELD_VALUE_CONFLICT"),
        ("WB-PLAYWRIGHT-MIXED-FLOW", "فرصة نشاط مختلط", "activity", "تجزئة", "تصنيع", "FIELD_VALUE_CONFLICT"),
    ]
    for case in cases:
        if case[0] not in existing:
            add_case(*case)
    db.commit()

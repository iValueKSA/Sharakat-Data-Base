from datetime import datetime, timezone
from sqlalchemy import select
from app.database import Base, engine, SessionLocal
from app.models import Source, Opportunity, SourceOpportunity, OpportunityConflict, User
from app.security import hash_password
from app.service import seed_sources

Base.metadata.create_all(engine)
now = datetime.now(timezone.utc)
with SessionLocal() as db:
    seed_sources(db)
    source = db.scalar(select(Source).order_by(Source.id))
    db.add(User(email="workbench.test@example.invalid", display_name="محلل اختباري", role="admin",
        password_hash=hash_password("Isolated-Workbench-Test-2026!"), is_active=True, created_at=now))
    master = Opportunity(canonical_id="WB-ISOLATED-1", title_ar="فرصة اختبار معزولة", normalized_title="فرصة اختبار معزولة",
        opportunity_owner="جهة اختبار", primary_publication_platform=source.source_name_ar, city="الأحساء", district="الهفوف",
        sector="تجاري", activity="تجزئة", status="منشورة", location_confidence_score=.9, location_detection_method="fixture",
        location_evidence="fixture", data_quality_score=.9, manual_review_required=False, first_seen_at=now,
        last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
    db.add(master); db.flush()
    record = SourceOpportunity(source_id=source.id, master_opportunity_id=master.id, source_opportunity_id="wb-isolated-1",
        source_title="فرصة اختبار معزولة", normalized_source_title="فرصة اختبار معزولة", source_url="https://example.test/item/1",
        source_owner="جهة اختبار", raw_location="الهفوف", raw_status="منشورة", canonical_status="منشورة",
        raw_data_json={"sector":"صناعي","activity":"تجزئة","description":"دليل اختبار"},
        standardized_data_json={"fields":{"sector":{"value":"صناعي","rule":"ISOLATED_FIXTURE"}}}, raw_dates={},
        first_seen_at=now, last_seen_at=now, content_hash="d"*64, parser_version="fixture")
    db.add(record); db.flush()
    ids=[]
    for field, current, competing in (("sector","تجاري","صناعي"),("activity","تجزئة","ضيافة")):
        row=OpportunityConflict(opportunity_id=master.id, field_name=field, conflict_type="TAXONOMY_CONFLICT",
            selected_value=current, conflicting_value=competing, source_id=source.id, source_record_id=record.id,
            detected_at=now, status="OPEN")
        db.add(row); db.flush(); ids.append(row.id)
    db.commit()
print({"seeded_reviews":len(ids),"review_ids":ids})

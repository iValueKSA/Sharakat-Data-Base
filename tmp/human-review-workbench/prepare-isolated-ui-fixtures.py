"""Align only temporary isolated fixtures for the closeout browser flows."""
from sqlalchemy import select
from app.database import SessionLocal
from app.models import FieldProvenance, OpportunityConflict, SourceOpportunity

with SessionLocal() as db:
    activity = db.scalar(select(OpportunityConflict).where(OpportunityConflict.field_name == "activity").order_by(OpportunityConflict.id).limit(1))
    if activity:
        record = db.get(SourceOpportunity, activity.source_record_id)
        data = dict(record.standardized_data_json or {})
        fields = dict(data.get("fields") or {})
        fields["activity"] = {"value":"ضيافة","mapping_status":"MAPPED","rule":"WB_ACTIVITY_V1"}
        data["fields"] = fields
        record.standardized_data_json = data
    batch_records = db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_opportunity_id.in_(("wb-batch-3", "wb-batch-4")))).all()
    ids = [row.id for row in batch_records]
    for conflict in db.scalars(select(OpportunityConflict).where(OpportunityConflict.source_record_id.in_(ids))).all():
        db.query(FieldProvenance).filter_by(opportunity_id=conflict.opportunity_id,
            field_name=conflict.field_name, source_id=conflict.source_id,
            source_record_id=conflict.source_record_id).delete(synchronize_session=False)
    for conflict in db.scalars(select(OpportunityConflict).where(OpportunityConflict.source_record_id.in_(ids))).all():
        conflict.conflict_type = "FIELD_VALUE_CONFLICT"
    db.commit()
    print({"activity_recommendation_fixture": bool(activity), "batch_review_count": len(ids), "batch_domains":"field_conflict"})

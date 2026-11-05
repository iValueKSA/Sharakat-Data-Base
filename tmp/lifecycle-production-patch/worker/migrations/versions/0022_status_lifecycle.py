"""Add canonical source status and reconcile Master lifecycle projection."""
from datetime import datetime
import hashlib
import json
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

revision = "0022_status_lifecycle"
down_revision = "0021_asset_facility_type"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("source_opportunities", sa.Column("canonical_status", sa.String(80), nullable=False,
        server_default="غير محددة"))
    op.create_index("ix_source_opportunities_canonical_status", "source_opportunities", ["canonical_status"])
    from app.models import ChangeHistory, Opportunity, Source, SourceOpportunity, SourceObservation
    from app.status_lifecycle import canonical_source_status, aggregate_master_status

    now = datetime.now().astimezone()
    session = Session(bind=op.get_bind())
    try:
        rows = session.query(SourceOpportunity).join(Source, Source.id == SourceOpportunity.source_id).all()
        for row in rows:
            raw_dates = row.raw_dates if isinstance(row.raw_dates, dict) else {}
            deadline = raw_dates.get("deadline")
            if row.missing_successful_checks >= max(1, int(row.source.missing_confirmation_threshold or 3)):
                row.canonical_status = "أزيلت من المصدر"
            else:
                row.canonical_status, _ = canonical_source_status(row.source.source_key, row.raw_status, deadline, now=now)
            payload={"raw_payload":row.raw_data_json or {},"raw_status":row.raw_status,"raw_deadline":deadline,
                "canonical_status":row.canonical_status}
            content_hash=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
            exists=session.query(SourceObservation.id).filter(SourceObservation.source_opportunity_id==row.id,
                SourceObservation.dataset_name=="source-record-status-snapshot",SourceObservation.content_hash==content_hash).first()
            if not exists:
                official_id=str(row.official_source_id_original or row.source_opportunity_id)[:200]
                normalized_id=str(row.official_source_id_normalized or official_id)[:200]
                session.add(SourceObservation(source_opportunity_id=row.id,dataset_name="source-record-status-snapshot",
                    endpoint=row.source_url,official_source_id_original=official_id,official_source_id_normalized=normalized_id,
                    raw_data_json=payload,source_updated_at=None,content_hash=content_hash,first_seen_at=now,last_seen_at=now))
        session.flush()
        masters = session.query(Opportunity).filter(Opportunity.merged_into_id.is_(None)).all()
        for master in masters:
            statuses = [record.canonical_status for record in master.source_records]
            projected, _ = aggregate_master_status(statuses)
            previous = master.status
            if previous != projected:
                master.status = projected
                master.last_updated_at = now
                master.updated_at = now
                source_id = master.source_records[0].source_id if master.source_records else None
                session.add(ChangeHistory(opportunity_id=master.id, changed_field="status", previous_value=previous,
                    new_value=projected, source_id=source_id, detected_at=now))
        session.flush()
    finally:
        session.close()


def downgrade():
    op.drop_index("ix_source_opportunities_canonical_status", table_name="source_opportunities")
    op.drop_column("source_opportunities", "canonical_status")

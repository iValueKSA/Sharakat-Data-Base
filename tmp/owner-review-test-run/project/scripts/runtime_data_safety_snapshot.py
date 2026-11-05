"""Read-only, deterministic business-data fingerprint for runtime refresh checks."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import (
    ChangeHistory,
    Opportunity,
    OpportunityConflict,
    QualificationReview,
    SourceObservation,
    SourceOpportunity,
)
from app.standardization import STANDARDIZATION_VERSION

ACTIVE_STATUSES = {"متاحة", "منشورة"}
HISTORICAL_STATUSES = {"منتهية", "ملغاة", "تمت الترسية", "أزيلت من المصدر"}


def stable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def digest_rows(rows):
    digest = hashlib.sha256()
    count = 0
    for row in rows:
        encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=stable).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def payload_digest(row_id, payload):
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=stable).encode("utf-8")
    return {"id": row_id, "sha256": hashlib.sha256(encoded).hexdigest()}


def main():
    with SessionLocal() as db:
        masters = db.scalars(select(Opportunity).order_by(Opportunity.id)).all()
        sources = db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
        observations = db.scalars(select(SourceObservation).order_by(SourceObservation.id)).all()
        changes = db.scalars(select(ChangeHistory).order_by(ChangeHistory.id)).all()
        conflicts = db.scalars(select(OpportunityConflict).where(OpportunityConflict.status == "OPEN").order_by(OpportunityConflict.id)).all()
        qualification = db.scalars(select(QualificationReview).where(QualificationReview.status.in_(["OPEN", "PENDING"])).order_by(QualificationReview.id)).all()

        master_identities = digest_rows({"id": row.id, "canonical_id": row.canonical_id, "merged_into_id": row.merged_into_id} for row in masters)
        source_links = digest_rows({"id": row.id, "source_id": row.source_id, "external_id": row.source_opportunity_id, "master_id": row.master_opportunity_id} for row in sources)
        source_payloads = digest_rows(payload_digest(row.id, row.raw_data_json) for row in sources)
        observation_identities = digest_rows({"id": row.id, "source_opportunity_id": row.source_opportunity_id, "endpoint": row.endpoint, "content_hash": row.content_hash} for row in observations)
        observation_payloads = digest_rows(payload_digest(row.id, row.raw_data_json) for row in observations)
        change_fingerprint = digest_rows({"id": row.id, "master_id": row.opportunity_id, "field": row.changed_field, "before": row.previous_value, "after": row.new_value, "source_id": row.source_id, "detected_at": row.detected_at} for row in changes)
        conflict_fingerprint = digest_rows({"id": row.id, "master_id": row.opportunity_id, "field": row.field_name, "kind": row.conflict_type, "selected": row.selected_value, "conflicting": row.conflicting_value, "source_id": row.source_id, "source_record_id": row.source_record_id, "status": row.status} for row in conflicts)
        qualification_fingerprint = digest_rows({"id": row.id, "source_id": row.source_id, "source_record_id": row.source_record_id, "external_id": row.external_id, "status": row.status, "proposed_type": row.proposed_type} for row in qualification)

        eligible = [row for row in masters if row.merged_into_id is None]
        active = [row for row in eligible if row.status in ACTIVE_STATUSES]
        historical = [row for row in eligible if row.status in HISTORICAL_STATUSES]
        reviews_by_dimension = {}
        for row in conflicts:
            reviews_by_dimension[row.field_name] = reviews_by_dimension.get(row.field_name, 0) + 1
        result = {
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "standardization_engine_version": STANDARDIZATION_VERSION,
            "total_masters": len(masters),
            "eligible_masters": len(eligible),
            "active_masters": len(active),
            "historical_masters": len(historical),
            "source_opportunity_count": len(sources),
            "observation_count": len(observations),
            "change_history_count": len(changes),
            "open_review_counts_by_dimension": reviews_by_dimension,
            "open_qualification_reviews": len(qualification),
            "fingerprints": {
                "master_identities": master_identities,
                "source_opportunity_links": source_links,
                "source_raw_payloads": source_payloads,
                "source_observation_identities": observation_identities,
                "source_observation_raw_payloads": observation_payloads,
                "change_history": change_fingerprint,
                "open_taxonomy_conflicts": conflict_fingerprint,
                "open_qualification_reviews": qualification_fingerprint,
            },
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

from sqlalchemy import select, func, text
from app.database import engine
from app.models import DuplicateCandidate, LocationReview, QualificationReview, OpportunityConflict, SyncJob
with engine.connect() as connection:
    connection.execute(text("SET TRANSACTION READ ONLY"))
    def count(model, status_column, values):
        return connection.execute(select(func.count(model.id)).where(status_column.in_(values))).scalar_one()
    snapshot = {
        "duplicate_open": count(DuplicateCandidate, DuplicateCandidate.status, ["PENDING", "OPEN"]),
        "location_open": count(LocationReview, LocationReview.status, ["PENDING", "OPEN"]),
        "qualification_open": count(QualificationReview, QualificationReview.status, ["PENDING", "OPEN"]),
        "conflict_open": count(OpportunityConflict, OpportunityConflict.status, ["PENDING", "OPEN"]),
        "sync_jobs_total": connection.execute(select(func.count(SyncJob.id))).scalar_one(),
        "sync_jobs_max_id": connection.execute(select(func.max(SyncJob.id))).scalar_one(),
    }
    snapshot["open_reviews_total"] = sum(snapshot[key] for key in ("duplicate_open", "location_open", "qualification_open", "conflict_open"))
    print(snapshot)

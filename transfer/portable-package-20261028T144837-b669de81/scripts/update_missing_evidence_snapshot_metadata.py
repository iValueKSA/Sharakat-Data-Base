"""Add live backlog/current-Master rollups to the captured blocked snapshot."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select, text

from app.database import SessionLocal
from app.models import DuplicateCandidate, LocationReview, OpportunityConflict, QualificationReview


PATH = Path("docs/validation/data/missing-evidence-recovery/blocked-review-snapshot.json")


def main() -> None:
    snapshot = json.loads(PATH.read_text(encoding="utf-8"))
    master_states = Counter()
    for case in snapshot.get("cases", []):
        master = case.get("master")
        if not master:
            key = "MISSING_MASTER"
        elif master.get("merged_into_id"):
            key = f"MERGED:{master.get('status') or 'UNSPECIFIED'}"
        else:
            key = f"CURRENT:{master.get('status') or 'UNSPECIFIED'}"
        master_states[key] += 1
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        count = 0
        for model, status_filter in (
            (DuplicateCandidate, DuplicateCandidate.status == "PENDING"),
            (LocationReview, LocationReview.status == "PENDING"),
            (QualificationReview, QualificationReview.status == "PENDING"),
            (OpportunityConflict, OpportunityConflict.status.in_(("OPEN", "PENDING"))),
        ):
            count += db.scalar(select(text("count(*)")).select_from(model).where(status_filter)) or 0
    snapshot["open_reviews_total"] = count
    snapshot["human_review_required"] = count - int(snapshot.get("blocked_review_count", 0))
    snapshot["blocked_by_master_current_state"] = dict(master_states)
    snapshot["snapshot_metadata_refreshed_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat()
    PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"snapshot_at": snapshot.get("snapshot_at"),
        "open_reviews_total": snapshot["open_reviews_total"],
        "human_review_required": snapshot["human_review_required"],
        "blocked_review_count": snapshot["blocked_review_count"],
        "blocked_by_master_current_state": snapshot["blocked_by_master_current_state"]},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

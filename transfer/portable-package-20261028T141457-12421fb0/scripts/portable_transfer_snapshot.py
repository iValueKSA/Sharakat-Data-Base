"""Read-only, privacy-preserving database snapshot used by portable transfer."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter

from sqlalchemy import create_engine, text


def _digest(rows: list[dict]) -> str:
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot() -> dict:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("Portable snapshot requires PostgreSQL")
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 8})
    try:
        with engine.connect() as connection:
            count = lambda sql: int(connection.scalar(text(sql)) or 0)
            source_rows = [dict(row) for row in connection.execute(text("""
                SELECT source_key, source_name_ar, organization_name, base_url,
                       opportunities_url, source_type, priority,
                       polling_frequency_minutes, enabled, extraction_method,
                       missing_confirmation_threshold
                FROM sources ORDER BY source_key
            """ )).mappings().all()]
            role_counts = {
                str(row[0]): int(row[1])
                for row in connection.execute(text(
                    "SELECT role, count(*) FROM users GROUP BY role ORDER BY role"
                )).all()
            }
            revision_rows = [str(row[0]) for row in connection.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num")
            ).all()]
            return {
                "total_masters": count("SELECT count(*) FROM opportunities"),
                "current_masters": count("SELECT count(*) FROM opportunities WHERE merged_into_id IS NULL"),
                "merged_masters": count("SELECT count(*) FROM opportunities WHERE merged_into_id IS NOT NULL"),
                "source_opportunities": count("SELECT count(*) FROM source_opportunities"),
                "observations": count("SELECT count(*) FROM source_observations"),
                "qualification_reviews": count("SELECT count(*) FROM qualification_reviews"),
                "location_reviews": count("SELECT count(*) FROM location_reviews"),
                "duplicate_reviews": count("SELECT count(*) FROM duplicate_candidates"),
                "conflict_reviews": count("SELECT count(*) FROM opportunity_data_conflicts"),
                "review_history_records": count(
                    "SELECT (SELECT count(*) FROM qualification_reviews) + "
                    "(SELECT count(*) FROM location_reviews) + "
                    "(SELECT count(*) FROM duplicate_candidates) + "
                    "(SELECT count(*) FROM opportunity_data_conflicts)"
                ),
                "open_review_records": count(
                    "SELECT (SELECT count(*) FROM qualification_reviews WHERE upper(status) IN ('OPEN','PENDING','IN_REVIEW')) + "
                    "(SELECT count(*) FROM location_reviews WHERE upper(status) IN ('OPEN','PENDING','IN_REVIEW')) + "
                    "(SELECT count(*) FROM duplicate_candidates WHERE upper(status) IN ('OPEN','PENDING','IN_REVIEW')) + "
                    "(SELECT count(*) FROM opportunity_data_conflicts WHERE upper(status) IN ('OPEN','PENDING','IN_REVIEW'))"
                ),
                "audit_events": count("SELECT count(*) FROM audit_events"),
                "system_events": count("SELECT count(*) FROM system_events"),
                "opportunity_change_history": count("SELECT count(*) FROM opportunity_change_history"),
                "merge_lineage_records": count("SELECT count(*) FROM opportunity_merge_audit"),
                "sync_jobs": count("SELECT count(*) FROM source_sync_jobs"),
                "active_sync_jobs": count(
                    "SELECT count(*) FROM source_sync_jobs WHERE job_state IN ('QUEUED','RUNNING','RETRYING')"
                ),
                "configured_sources": len(source_rows),
                "enabled_sources": sum(bool(row["enabled"]) for row in source_rows),
                "source_configuration_sha256": _digest(source_rows),
                "users": count("SELECT count(*) FROM users"),
                "active_admin_users": count(
                    "SELECT count(*) FROM users WHERE lower(role)='admin' AND is_active"
                ),
                "rbac_role_counts": role_counts,
                "rbac_fingerprint_sha256": _digest([
                    {"email": row[0], "role": row[1], "is_active": bool(row[2])}
                    for row in connection.execute(text(
                        "SELECT lower(email), lower(role), is_active FROM users ORDER BY lower(email)"
                    )).all()
                ]),
                "user_sessions": count("SELECT count(*) FROM user_sessions"),
                "alembic_heads": revision_rows,
            }
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(json.dumps(snapshot(), sort_keys=True, separators=(",", ":")))

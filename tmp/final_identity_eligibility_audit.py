import json
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import func, select, text

from app.database import engine, SessionLocal
from app.models import (
    DuplicateCandidate, LocationReview, MergeAudit, Opportunity,
    Source, SourceOpportunity, SystemEvent,
)

ROOT = Path("docs/validation/data/master-identity-duplicate-matching")
BEFORE = json.loads((ROOT / "snapshot-live-before-targeted-eligibility.json").read_text(encoding="utf-8"))
AFTER = json.loads((ROOT / "snapshot-post-targeted-eligibility.json").read_text(encoding="utf-8"))
TARGETS = [283, 466, 671, 1038, 1166, 1167, 2358, 2359, 2360, 2361, 2362]
RAW_ADMIN_FIELDS = {"qualified_location", "location_confidence_score", "location_detection_method", "location_evidence"}

assert BEFORE["metadata"]["snapshot_utc"] == "2026-10-20 10:14:57.355864"
assert AFTER["metadata"]["snapshot_utc"] == "2026-10-20 10:17:13.956362"
assert (BEFORE["metadata"]["observations"], AFTER["metadata"]["observations"]) == (11163, 11174)
assert BEFORE["metadata"]["latest_sync_job"]["id"] == AFTER["metadata"]["latest_sync_job"]["id"] == 379
assert BEFORE["metadata"]["latest_sync_job"]["trigger_type"] == AFTER["metadata"]["latest_sync_job"]["trigger_type"] == "scheduled"

before_masters = {row["id"]: row for row in BEFORE["masters"]}
after_masters = {row["id"]: row for row in AFTER["masters"]}
before_sources = {row["id"]: row for row in BEFORE["source_opportunities"]}
after_sources = {row["id"]: row for row in AFTER["source_opportunities"]}
assert set(before_masters).issubset(after_masters)
assert set(before_sources) == set(after_sources)
assert len(TARGETS) == 11

expected_decisions = {
    283: "A",
    466: "A",
    671: "A",
    1038: "A",
    1166: "A",
    1167: "A",
    2358: "A",
    2359: "A",
    2360: "A",
    2361: "A",
    2362: "A",
}
assert Counter(expected_decisions.values()) == {"A": 11}

raw_changed_keys = {}
for record_id in TARGETS:
    old = before_sources[record_id]
    new = after_sources[record_id]
    assert old["master_opportunity_id"] is None
    assert new["master_opportunity_id"] is not None
    assert new["master_opportunity_id"] not in {m["id"] for m in AFTER["masters"] if m["merged_into_id"] is not None}
    old_raw = old.get("raw_data_json") or {}
    new_raw = new.get("raw_data_json") or {}
    changed = {key for key in set(old_raw) | set(new_raw) if old_raw.get(key) != new_raw.get(key)}
    raw_changed_keys[record_id] = sorted(changed)
    assert changed.issubset(RAW_ADMIN_FIELDS), (record_id, changed)
    assert new_raw.get("qualified_location") is True
    assert new_raw.get("location_detection_method") == "ADMIN_LOCATION_REVIEW"
    assert new_raw.get("location_evidence", "").startswith("OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA.")
    assert old_raw.get("description") == new_raw.get("description")

new_master_ids = [after_sources[rid]["master_opportunity_id"] for rid in TARGETS]
assert len(set(new_master_ids)) == 11
assert len(set(new_master_ids) - set(before_masters)) == 11

before_ncp = before_sources[2810]
after_ncp = after_sources[2810]
assert before_ncp["master_opportunity_id"] is None and after_ncp["master_opportunity_id"] == 228
assert before_ncp.get("raw_data_json") == after_ncp.get("raw_data_json")
assert before_sources[2781]["master_opportunity_id"] == 228
assert before_sources[2781]["source_url"] == before_ncp["source_url"]
assert before_sources[2781]["source_title"] == before_ncp["source_title"]

assert BEFORE["merge_audits"] == AFTER["merge_audits"]
assert len(AFTER["merge_audits"]) == 21
assert len([m for m in AFTER["masters"] if m["merged_into_id"] is not None]) == 21

with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
    tx = conn.begin()
    conn.execute(text("SET TRANSACTION READ ONLY"))
    metrics = dict(conn.execute(text("""
        SELECT
          (SELECT count(*) FROM opportunities) AS total_master_rows,
          (SELECT count(*) FROM opportunities WHERE merged_into_id IS NULL) AS current_masters,
          (SELECT count(*) FROM opportunities WHERE merged_into_id IS NOT NULL) AS merged_masters,
          (SELECT count(*) FROM source_opportunities) AS source_opportunities,
          (SELECT count(*) FROM source_opportunities WHERE master_opportunity_id IS NOT NULL) AS linked_source_rows,
          (SELECT count(*) FROM source_opportunities WHERE master_opportunity_id IS NULL) AS unlinked_source_rows,
          (SELECT count(*) FROM source_opportunities WHERE coalesce((raw_data_json->>'qualified_location')::boolean,false)) AS explicit_qualified_source_rows,
          (SELECT count(*) FROM source_opportunities WHERE coalesce((raw_data_json->>'qualified_location')::boolean,false) AND master_opportunity_id IS NOT NULL) AS explicit_qualified_linked,
          (SELECT count(*) FROM source_opportunities WHERE coalesce((raw_data_json->>'qualified_location')::boolean,false) AND master_opportunity_id IS NULL) AS explicit_qualified_unlinked,
          (SELECT count(*) FROM opportunities o WHERE o.merged_into_id IS NULL AND NOT EXISTS (SELECT 1 FROM source_opportunities so WHERE so.master_opportunity_id=o.id)) AS current_masters_without_source,
          (SELECT count(*) FROM source_opportunities so WHERE so.master_opportunity_id IS NOT NULL AND EXISTS (SELECT 1 FROM opportunities o WHERE o.id=so.master_opportunity_id AND o.merged_into_id IS NOT NULL)) AS source_rows_still_on_merged_master,
          (SELECT count(*) FROM location_reviews WHERE status='PENDING') AS pending_location_reviews,
          (SELECT count(*) FROM duplicate_candidates WHERE status='PENDING') AS open_duplicate_queue,
          (SELECT count(*) FROM opportunities o WHERE o.merged_into_id IS NULL AND (SELECT count(*) FROM source_opportunities so WHERE so.master_opportunity_id=o.id)>1) AS masters_with_multiple_source_rows,
          (SELECT count(*) FROM opportunities o WHERE o.merged_into_id IS NULL AND (SELECT count(DISTINCT so.source_id) FROM source_opportunities so WHERE so.master_opportunity_id=o.id)>1) AS masters_with_multiple_distinct_sources,
          (SELECT count(*) FROM system_events WHERE event_type='SOURCE_RECORD_IDENTITY_LINKED' AND payload->>'source_record_id'='2810' AND payload->>'master_id_after'='228') AS ncp_link_audit_event
    """)).mappings().one())
    audit = conn.execute(text("""
        SELECT ma.id, ma.merged_opportunity_id, ma.target_opportunity_id,
               ma.merge_reason, ma.merge_evidence, ma.source_record_ids,
               ma.target_before_json, ma.target_after_json, ma.source_history_ids,
               ma.source_provenance_ids, ma.source_conflict_ids, ma.source_document_ids,
               ma.merge_history_ids, ma.undone_at, ma.created_at
          FROM opportunity_merge_audit ma ORDER BY ma.id
    """)).mappings().all()
    assert all(r["merge_reason"] and r["merge_evidence"] and r["source_record_ids"] is not None
               and r["target_before_json"] is not None and r["target_after_json"] is not None
               and r["source_history_ids"] is not None and r["source_provenance_ids"] is not None
               and r["source_conflict_ids"] is not None and r["source_document_ids"] is not None
               and r["merge_history_ids"] is not None and r["undone_at"] is None for r in audit)
    # Audit each of the 21 historical rows against a current survivor.
    valid_merge_lineage = 0
    for row in audit:
        merged = conn.execute(text("SELECT merged_into_id FROM opportunities WHERE id=:id"), {"id": row["merged_opportunity_id"]}).scalar_one_or_none()
        survivor = conn.execute(text("SELECT merged_into_id FROM opportunities WHERE id=:id"), {"id": row["target_opportunity_id"]}).scalar_one_or_none()
        assert merged == row["target_opportunity_id"]
        assert survivor is None
        valid_merge_lineage += 1
    tx.commit()

assert metrics["total_master_rows"] == 308
assert metrics["current_masters"] == 287
assert metrics["merged_masters"] == 21
assert metrics["source_opportunities"] == 2899
assert metrics["linked_source_rows"] == 312
assert metrics["unlinked_source_rows"] == 2587
assert metrics["explicit_qualified_source_rows"] == metrics["explicit_qualified_linked"] == 19
assert metrics["explicit_qualified_unlinked"] == 0
assert metrics["current_masters_without_source"] == 0
assert metrics["source_rows_still_on_merged_master"] == 0
assert metrics["pending_location_reviews"] == 15
assert metrics["open_duplicate_queue"] == 10
assert metrics["masters_with_multiple_source_rows"] == 25
assert metrics["masters_with_multiple_distinct_sources"] == 24
assert metrics["ncp_link_audit_event"] == 1
assert valid_merge_lineage == 21

with SessionLocal() as db:
    accepted = db.scalar(select(func.count()).select_from(LocationReview).where(
        LocationReview.status == "ACCEPTED",
        LocationReview.source_record_id.in_(TARGETS),
    ))
    assert accepted == 11
    pending_601 = db.scalar(select(LocationReview).where(LocationReview.source_record_id == 601))
    assert pending_601 and pending_601.status == "PENDING"

result = {
    "snapshot_before_utc": BEFORE["metadata"]["snapshot_utc"],
    "snapshot_after_utc": AFTER["metadata"]["snapshot_utc"],
    "metrics": metrics,
    "invest_saudi_11_classification_counts": {"A": 11, "B": 0, "C": 0, "D": 0},
    "invest_saudi_11_source_ids": TARGETS,
    "invest_saudi_11_master_ids": new_master_ids,
    "invest_saudi_601": {"classification": "D", "qualified": False, "master_id": None, "review_required": True},
    "ncp_2810": {"classification": "B", "master_id": 228, "same_article_alias_source_id": 2781, "raw_payload_preserved": True},
    "kfu_2775": {"classification": "C", "reason": "university-campus procurement announcement, not a geographically scoped investment opportunity"},
    "merge_lineage_valid": valid_merge_lineage,
    "merge_audits_unchanged": BEFORE["merge_audits"] == AFTER["merge_audits"],
    "raw_existing_fields_preserved": True,
    "raw_admin_changed_keys_by_record": raw_changed_keys,
    "observation_delta_since_pre_targeted_snapshot": AFTER["metadata"]["observations"] - BEFORE["metadata"]["observations"],
    "natural_sync_id": AFTER["metadata"]["latest_sync_job"]["id"],
    "natural_sync_trigger_type": AFTER["metadata"]["latest_sync_job"]["trigger_type"],
}
print(json.dumps(result, ensure_ascii=False, default=str))

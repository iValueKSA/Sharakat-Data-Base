import csv
import json
from pathlib import Path

candidate_root = Path("docs/validation/data/master-identity-duplicate-matching")
root = candidate_root if candidate_root.exists() else Path.cwd()
final = json.loads((root / "final-identity-eligibility-reconciliation.json").read_text(encoding="utf-8"))
adjudication = json.loads((root / "invest-saudi-11-adjudication.json").read_text(encoding="utf-8"))
blocker = json.loads((root / "acceptance-blocker.json").read_text(encoding="utf-8"))
summary = json.loads((root / "reconciliation-summary.json").read_text(encoding="utf-8"))
api = json.loads((root / "current-api-export-reconciliation.json").read_text(encoding="utf-8"))
test_log = (root / "full-regression-targeted-eligibility-final.txt").read_text(encoding="utf-8")
report = (root / "FINAL-REVIEW.md").read_text(encoding="utf-8")
locality = list(csv.DictReader((root / "locality-14-adjudication.csv").open(encoding="utf-8-sig")))
post = json.loads((root / "snapshot-post-targeted-eligibility.json").read_text(encoding="utf-8"))

assert final["status"] == "COMPLETE"
assert final["total_master_rows"] == 308
assert final["non_merged_masters"] == 287 and final["merged_masters"] == 21
assert final["source_opportunities"] == 2899
assert final["source_records_with_current_master"] == 312
assert final["source_records_without_current_master"] == 2587
assert final["eligible_source_records"] == final["eligible_source_records_with_current_master"] == 312
assert final["eligible_source_records_without_current_master"] == 0
assert final["unlinked_source_records_pending_location_eligibility_review"] == 6
assert final["literal_qualified_location_true"] == final["literal_qualified_location_true_linked"] == 19
assert final["literal_qualified_location_true_unlinked"] == 0
assert final["current_masters_with_zero_sources"] == 0
assert final["source_records_linked_to_multiple_current_masters"] == 0
assert final["new_merges_audited"] == final["new_merges_confirmed_valid"] == 16
assert final["new_merges_review_required"] == final["new_merges_confirmed_incorrect"] == 0
assert final["total_merged_masters_audited"] == 21 and final["merge_lineage_complete"] and final["merges_reversible"]
assert final["invest_saudi_11_reviewed"] == final["invest_saudi_confirmed_location_al_ahsa"] == 11
assert final["invest_saudi_review_required_within_11"] == 0
assert final["additional_invest_saudi_601_review_required"] == 1
assert final["ncp_2810_master_id"] == 228 and final["kfu_2775_classification"] == "C_MENTION_ONLY_NOT_PROJECT_LOCATION"
assert final["duplicate_review_queue_open"] == 10
assert final["strict_all_sourceopportunities_current_master_gate_removed"]
assert final["master_identities_preserved_or_auditably_merged"] and final["source_rows_preserved"]
assert final["raw_provenance_preserved_original_facts_unchanged"] and final["merge_audit_preserved"]
assert final["unexplained_business_data_changes"] == 0 and not final["manual_source_sync_started"]
assert final["full_regression"] == "185 passed / 0 failed" and final["full_regression_after_targeted_corrections"]

assert len(adjudication["records"]) == 11
assert adjudication["classification_counts"] == {
    "A_OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA": 11,
    "B_MULTI_LOCATION_INCLUDES_AL_AHSA": 0,
    "C_MENTION_ONLY_NOT_PROJECT_LOCATION": 0,
    "D_INSUFFICIENT_EVIDENCE_REVIEW": 0,
}
assert {row["source_opportunity_row_id"] for row in adjudication["records"]} == {283,466,671,1038,1166,1167,2358,2359,2360,2361,2362}
assert {row["master_id"] for row in adjudication["records"]} == set(range(328,339))
assert adjudication["additional_invest_saudi_text_match_601"]["status"] == "PENDING"

assert blocker["review_status"] == "COMPLETE"
assert blocker["eligible_source_records_without_current_master"] == 0
assert blocker["unlinked_source_records_pending_location_eligibility_review"] == 6
assert blocker["strict_all_sourceopportunities_current_master_gate"] == "REMOVED_SEMANTICALLY_INCORRECT"
assert summary["review_status"].endswith("= COMPLETE")
assert summary["qualified_source_linkage_gate"] == "PASSED"
assert summary["source_records_without_master"] == 2587
assert len(locality) == 14
assert sum(row["final_classification"] == "A_CONFIRMED_AL_AHSA_NEW_MASTER" for row in locality) == 11
assert sum(row["final_classification"] == "D_REVIEW_UNQUALIFIED" for row in locality) == 1
assert sum(row["final_classification"] == "C_MENTION_ONLY_NOT_OPPORTUNITY" for row in locality) == 1
assert sum(row["final_classification"] == "B_MULTILOCATION_LINKED_EXISTING_MASTER" for row in locality) == 1

assert api["api_total"] == api["api_returned"] == api["api_unique_master_ids"] == 287
assert api["dashboard_global_total"] == api["csv_data_rows"] == api["xlsx_data_rows"] == 287
assert api["master_228_detail_contains_ncp_alias"] and api["master_228_detail_source_records"] == 2
assert "185 passed, 1 warning in 7.52s" in test_log
assert "ELIGIBILITY_REVIEW_REQUIRED_SOURCE_RECORDS_WITHOUT_MASTER = 6" in report
assert "MASTER_IDENTITY_DUPLICATE_CROSS_SOURCE_DEEP_REVIEW = COMPLETE" in report
assert "STRICT_ALL_SOURCEOPPORTUNITIES_CURRENT_MASTER_GATE_REMOVED = TRUE" in report
assert "NOT_COMPLETE" not in report and "NOT_PASSED" not in report
assert post["metadata"]["total_master_rows"] == 308
assert post["metadata"]["observations"] == 11174

print(json.dumps({
    "validation": "PASSED",
    "master_rows": 308,
    "current_masters": 287,
    "merged_masters": 21,
    "linked_sources": 312,
    "unlinked_sources": 2587,
    "unlinked_location_review_cases": 6,
    "unlinked_outside_eligible_and_review_sets": 2581,
    "invest_saudi_targets": 11,
    "locality_screen_rows": 14,
    "merge_audits": 21,
    "api_csv_xlsx_dashboard_rows": 287,
    "full_regression": "185 passed / 0 failed",
}, ensure_ascii=False))

"""Promotion guard for RCU lifecycle values that still need source review."""
from __future__ import annotations

from .status_lifecycle import parse_deadline


def rcu_source_value_is_promotable(source_key: str | None, field_name: str,
                                   proposed_value: object, field_data: object) -> bool:
    """Reject RCU status/deadline evidence unless standardization resolved it."""
    if source_key != "rcu-investment-opportunities" or field_name not in {"status", "submission_deadline"}:
        return True
    if not isinstance(field_data, dict):
        return False
    if field_data.get("mapping_status") != "MAPPED" or field_data.get("review_flags"):
        return False
    standardized_value = field_data.get("value")
    if standardized_value in (None, "") or str(standardized_value).strip() != str(proposed_value).strip():
        return False
    if field_name == "status":
        return bool(field_data.get("canonical_id") or field_data.get("canonical_label"))
    return parse_deadline(proposed_value) is not None


def rcu_conflict_source_value_is_promotable(source, source_record, field_name: str,
                                            proposed_value: object) -> bool:
    if not source or not source_record:
        return False
    standardized = source_record.standardized_data_json if isinstance(source_record.standardized_data_json, dict) else {}
    fields = standardized.get("fields") or {}
    field_data = fields.get(field_name) or {}
    return rcu_source_value_is_promotable(source.source_key, field_name, proposed_value, field_data)

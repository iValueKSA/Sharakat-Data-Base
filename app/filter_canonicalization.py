"""Backward-compatible import path for the centralized standardization engine."""
from .standardization import (
    MISSING_LABEL,
    ACTIVITY_UNSPECIFIED_LABEL,
    SECTOR_UNSPECIFIED_LABEL,
    canonical_groups,
    canonical_id,
    canonical_identity,
    canonical_value,
    comparison_key,
    group_counts,
    matching_values,
    option_labels,
    standardize_field,
    standardize_opportunity,
    standardize_text,
    validate_url,
)

__all__ = [
    "MISSING_LABEL", "ACTIVITY_UNSPECIFIED_LABEL", "SECTOR_UNSPECIFIED_LABEL", "canonical_groups", "canonical_id", "canonical_identity", "canonical_value",
    "comparison_key", "group_counts", "matching_values", "option_labels",
    "standardize_field", "standardize_opportunity", "standardize_text", "validate_url",
]

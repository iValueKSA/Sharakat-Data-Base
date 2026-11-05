"""Classify live-source validation outcomes without requiring frozen data."""


REGRESSION_STATES = {
    "DATA_STABLE",
    "VALID_LIVE_CHANGE",
    "UNEXPECTED_DATA_CHANGE",
    "PARSER_REGRESSION",
}


def classify_live_regression(*, parser_failures=0, structural_failures=0,
                             pagination_complete=True, ids_stable=True,
                             provenance_preserved=True, source_health_valid=True,
                             unexpected_changes=0, legitimate_changes=0):
    """Return a regression state based on structure and provenance, not zero deltas."""
    if (parser_failures or structural_failures or not pagination_complete
            or not ids_stable or not provenance_preserved or not source_health_valid):
        return "PARSER_REGRESSION"
    if unexpected_changes:
        return "UNEXPECTED_DATA_CHANGE"
    if legitimate_changes:
        return "VALID_LIVE_CHANGE"
    return "DATA_STABLE"

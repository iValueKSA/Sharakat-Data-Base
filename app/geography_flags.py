"""Fail-closed feature gates for nationwide geography functionality."""
from __future__ import annotations

import os


def flag_enabled(name: str, environ: dict[str, str] | None = None) -> bool:
    values = os.environ if environ is None else environ
    return str(values.get(name, "false")).strip().casefold() in {"1", "true", "yes", "on"}


def geographic_feature_state(reference_ready: bool, environ: dict[str, str] | None = None) -> dict:
    """Feature flags never bypass the validated reference readiness gate."""
    ui_flag = flag_enabled("NATIONAL_UI_ENABLED", environ)
    map_flag = flag_enabled("NATIONAL_MAP_ENABLED", environ)
    dashboard_flag = flag_enabled("NATIONAL_DASHBOARD_ENABLED", environ)
    return {
        "national_ui_flag": ui_flag,
        "national_map_flag": map_flag,
        "national_dashboard_flag": dashboard_flag,
        "national_ui_enabled": bool(reference_ready and ui_flag),
        "national_map_enabled": bool(reference_ready and map_flag),
        "national_dashboard_enabled": bool(reference_ready and ui_flag and dashboard_flag),
    }

"""Validate a geographic reference JSON file without writing to a database."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.geographic_references import validate_reference_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="JSON file with metadata and units")
    parser.add_argument("--test-mode", action="store_true", help="Allow explicit TEST_ONLY fixtures for validation only")
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        report = validate_reference_payload(payload.get("metadata") or {}, payload.get("units") or [],
                                            test_mode=args.test_mode)
        report.update({"input": str(args.input.resolve()), "writes_performed": 0,
                       "mode": "TEST_ONLY_DRY_RUN" if args.test_mode else "DRY_RUN"})
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["valid"] else 2
    except (OSError, json.JSONDecodeError, TypeError) as error:
        print(json.dumps({"valid": False, "error": str(error), "writes_performed": 0}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())

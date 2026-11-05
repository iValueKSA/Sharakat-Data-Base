"""Controlled, versioned production import. Default mode is read-only dry-run."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from hashlib import sha256
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.database import SessionLocal
from app.geographic_references import import_reference_dataset


def verify_backup(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verification = manifest.get("restore_verification") or {}
    if verification.get("status") != "PASSED":
        raise ValueError("Backup restore_verification.status must be PASSED")
    declared_path = str(manifest.get("path") or "")
    backup_path = Path(declared_path)
    if not backup_path.is_file():
        # A Windows-authored manifest may be consumed inside the Linux app
        # container; resolve its basename beside the manifest in that case.
        backup_path = manifest_path.parent / declared_path.replace("\\", "/").split("/")[-1]
    if not backup_path.is_absolute():
        backup_path = (manifest_path.parent / backup_path).resolve()
    if not backup_path.is_file():
        raise ValueError("Verified backup file is missing")
    digest_state = sha256()
    with backup_path.open("rb") as backup_stream:
        for chunk in iter(lambda: backup_stream.read(1024 * 1024), b""):
            digest_state.update(chunk)
    digest = digest_state.hexdigest()
    if digest != str(manifest.get("sha256") or "").lower():
        raise ValueError("Backup SHA-256 does not match its manifest")
    return {"backup_id": manifest.get("backup_id"), "sha256": digest, "verification": "PASSED"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--backup-manifest", type=Path)
    parser.add_argument("--test-mode", action="store_true",
                        help="Permit TEST_ONLY fixture validation in dry-run mode only")
    parser.add_argument("--confirm-production-import", action="store_true",
                        help="Required to commit a production import; otherwise this command is a dry-run")
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        metadata, units = payload.get("metadata") or {}, payload.get("units") or []
        synthetic = metadata.get("test_only") is True or any(str(row.get("external_id", "")).startswith("TEST_") for row in units)
        if synthetic and (not args.test_mode or args.confirm_production_import):
            raise ValueError("TEST_ONLY geographic fixtures are permanently refused by this import command")
        if args.test_mode and args.confirm_production_import:
            raise ValueError("--test-mode cannot be combined with a production import")
        if not args.confirm_production_import:
            result = import_reference_dataset(None, metadata, units, dry_run=True, test_mode=args.test_mode)
            result.update({"mode": "TEST_ONLY_DRY_RUN" if args.test_mode else "DRY_RUN", "writes_performed": 0,
                           "backup_verification": "NOT_REQUIRED_FOR_DRY_RUN"})
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["valid"] else 2
        if not args.backup_manifest:
            raise ValueError("--backup-manifest is required for a production import")
        backup = verify_backup(args.backup_manifest)
        if os.getenv("GEOGRAPHIC_IMPORT_CONFIRMATION") != "CONFIRM_PRODUCTION_GEOGRAPHIC_IMPORT":
            raise ValueError("Set GEOGRAPHIC_IMPORT_CONFIRMATION to the exact confirmation string to commit")
        with SessionLocal.begin() as db:
            # A controlled import requires migration 0024 and immutable version storage.
            head = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if head not in {"0024_national_geography", "0025_source_geographic_coverage"}:
                raise ValueError(f"Expected migration 0024+; found {head}")
            result = import_reference_dataset(db, metadata, units, dry_run=False, test_mode=False)
        result.update({"mode": "PRODUCTION_IMPORT", "writes_performed": 1,
                       "backup_verification": backup})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(json.dumps({"imported": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())

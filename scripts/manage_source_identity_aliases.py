"""Explicit, artifact-pinned alias application/rollback command. Never runs ingestion."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVED = ROOT / "docs/validation/deployment/nationwide-source-expansion/furas-identity-reconciliation-20261110/FURAS-75-APPROVED-ALIASES-20261110.csv"


def _require_explicit_gate() -> None:
    if os.getenv("SOURCE_IDENTITY_ALIAS_APPLICATION_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        raise SystemExit("Blocked: set SOURCE_IDENTITY_ALIAS_APPLICATION_ENABLED=true only for an explicitly authorized application window")


def _apply(args) -> dict:
    _require_explicit_gate()
    file_path = Path(args.approved_csv).resolve()
    payload = file_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != args.expected_sha256.lower():
        raise SystemExit("Blocked: approved artifact SHA-256 does not match --expected-sha256")
    with file_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != args.expected_count:
        raise SystemExit(f"Blocked: expected {args.expected_count} approved rows, found {len(rows)}")
    for row in rows:
        row["evidence_references"] = json.loads(row["evidence_references"])

    from app.database import SessionLocal
    from app.source_identity_aliases import apply_approved_alias_batch

    with SessionLocal() as db:
        result = apply_approved_alias_batch(
            db, args.source_key, rows, expected_count=args.expected_count,
            application_batch_id=args.batch_id,
            approved_artifact_reference=str(file_path), approved_artifact_sha256=digest,
            actor=args.actor)
    return result


def _rollback(args) -> dict:
    _require_explicit_gate()
    from app.database import SessionLocal
    from app.source_identity_aliases import rollback_alias_batch

    with SessionLocal() as db:
        return rollback_alias_batch(
            db, args.source_key, args.application_batch_id,
            expected_count=args.expected_count,
            rollback_batch_id=args.rollback_batch_id or str(uuid.uuid4()),
            reason=args.reason, actor=args.actor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    apply = subparsers.add_parser("apply", help="Apply an exact approved CSV as one atomic batch")
    apply.add_argument("--approved-csv", default=str(DEFAULT_APPROVED))
    apply.add_argument("--expected-sha256", required=True)
    apply.add_argument("--expected-count", type=int, default=75)
    apply.add_argument("--source-key", default="furas")
    apply.add_argument("--batch-id", required=True, help="Unique application batch identifier")
    apply.add_argument("--actor", required=True, help="Authorized operator/process identity for the audit record")
    apply.set_defaults(run=_apply)

    rollback = subparsers.add_parser("rollback", help="Deactivate one complete prior alias batch; retain audit history")
    rollback.add_argument("--source-key", default="furas")
    rollback.add_argument("--application-batch-id", required=True)
    rollback.add_argument("--rollback-batch-id")
    rollback.add_argument("--expected-count", type=int, default=75)
    rollback.add_argument("--reason", required=True)
    rollback.add_argument("--actor", required=True)
    rollback.set_defaults(run=_rollback)

    args = parser.parse_args()
    print(json.dumps(args.run(args), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

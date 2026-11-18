"""Run one explicit, production-independent document-collection pilot.

Requires the dedicated isolated PostgreSQL container documented in
docs/validation/development/document-collection-engine-phase1-20261118/README.md.
This script never writes into the public opportunity_documents table.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from sqlalchemy.engine import make_url


PILOT_DATABASE_HOST = "doccollection-pilot-pg16-20261118"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("allowlist", type=Path)
    parser.add_argument("--resume-run-id", type=int)
    args = parser.parse_args()
    url_value = os.environ.get("DATABASE_URL", "")
    if os.environ.get("DOCUMENT_COLLECTION_ISOLATED") != "1":
        parser.error("DOCUMENT_COLLECTION_ISOLATED=1 is required")
    url = make_url(url_value)
    if url.host != PILOT_DATABASE_HOST:
        parser.error("Refusing to run outside the dedicated isolated pilot PostgreSQL host")
    payload = json.loads(args.allowlist.read_text(encoding="utf-8-sig"))
    if payload.get("source_key") != "furas" or payload.get("mode") != "EXPLICIT_EXISTING_SOURCE_OPPORTUNITY_ALLOWLIST":
        parser.error("Allowlist must be the explicit Furas SourceOpportunity pilot format")
    records = payload.get("records")
    if not isinstance(records, list) or not records or len(records) > 25:
        parser.error("Allowlist must contain between 1 and 25 existing SourceOpportunity records")
    ids = [record.get("source_opportunity_id") for record in records]
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in ids):
        parser.error("Allowlist contains an invalid SourceOpportunity integer ID")
    if len(set(ids)) != len(ids):
        parser.error("Allowlist contains duplicate SourceOpportunity IDs")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.database import SessionLocal
    from app.document_collection.engine import collect_allowlisted

    result = collect_allowlisted(ids, session_factory=SessionLocal, resume_run_id=args.resume_run_id)
    print(json.dumps({"pilot": payload.get("pilot_id"), "source_key": "furas",
                      "allowlist_count": len(ids), "result": result}, ensure_ascii=False, default=str))
    return 0 if result.get("status") in {"COMPLETED", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

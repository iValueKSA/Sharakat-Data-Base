"""Export the isolated pilot run and staged review register without DB writes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url


PILOT_DATABASE_HOST = "doccollection-pilot-pg16-20261118"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", type=int)
    parser.add_argument("allowlist", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    if os.environ.get("DOCUMENT_COLLECTION_ISOLATED") != "1":
        parser.error("DOCUMENT_COLLECTION_ISOLATED=1 is required")
    if make_url(os.environ.get("DATABASE_URL", "")).host != PILOT_DATABASE_HOST:
        parser.error("Refusing to export from outside the isolated pilot PostgreSQL host")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.database import SessionLocal
    from app.document_collection.registry import capability_matrix
    from app.models import (DocumentCandidate, DocumentCollectionRun, Opportunity,
                            OpportunityDocument, Source, SourceOpportunity)

    allowlist = json.loads(args.allowlist.read_text(encoding="utf-8-sig"))
    input_records = {int(row["source_opportunity_id"]): row for row in allowlist["records"]}
    with SessionLocal() as db:
        run = db.get(DocumentCollectionRun, args.run_id)
        if run is None:
            parser.error(f"Collection run {args.run_id} does not exist")
        if run.source_key != "furas" or run.scope != "EXPLICIT_ALLOWLIST":
            parser.error("Run is not an explicit Furas allowlist run")
        process_records = list((run.summary_json or {}).get("processed_records", []))
        process_by_id = {int(row["source_opportunity_id"]): row for row in process_records}
        record_rows = []
        for source_id, selected in input_records.items():
            result = process_by_id.get(source_id, {})
            record_rows.append({
                "source_opportunity_id": source_id,
                "provider_opportunity_id": selected["provider_opportunity_id"],
                "master_opportunity_id": selected["master_opportunity_id"],
                "master_city": selected["master_city"],
                "source_opportunity_url": selected["source_opportunity_url"],
                "status": result.get("status", "NOT_PROCESSED"),
                "documents_discovered": result.get("discovered", 0),
                "candidate_ids": result.get("candidate_ids", []),
                "error_code": result.get("error_code"),
            })
        candidates = db.scalars(select(DocumentCandidate).where(
            DocumentCandidate.run_id == args.run_id).order_by(
                DocumentCandidate.source_opportunity_id, DocumentCandidate.id)).all()
        candidate_rows = []
        for candidate in candidates:
            source_record = db.get(SourceOpportunity, candidate.source_opportunity_id)
            source = db.get(Source, candidate.source_id)
            master = db.get(Opportunity, candidate.opportunity_id) if candidate.opportunity_id else None
            evidence = candidate.evidence_json or {}
            direct = evidence.get("direct_link") or {}
            price = evidence.get("price") or {}
            provenance = candidate.provenance_json or {}
            candidate_rows.append({
                "candidate_id": candidate.id,
                "source_key": source.source_key if source else None,
                "source_opportunity_id": candidate.source_opportunity_id,
                "provider_opportunity_id": candidate.provider_opportunity_id,
                "master_opportunity_id": candidate.opportunity_id,
                "master_city": master.city if master else None,
                "source_document_id": candidate.source_document_id,
                "title": candidate.original_title,
                "document_type": candidate.document_type,
                "document_category": candidate.document_category,
                "document_scope": candidate.document_scope,
                "official_document_url": provenance.get("source_document_href"),
                "display_fallback_url": candidate.url,
                "source_opportunity_url": candidate.source_opportunity_url,
                "direct_verification_outcome": direct.get("outcome"),
                "access_status": candidate.access_status,
                "rights_status": candidate.rights_status,
                "link_verification_status": candidate.link_verification_status,
                "verification_status": candidate.verification_status,
                "review_status": candidate.review_status,
                "participation_requirement": candidate.participation_requirement,
                "authentication_required": candidate.authentication_required,
                "payment_required_for_document": candidate.payment_required_for_document,
                "raw_amount": str(candidate.raw_amount) if candidate.raw_amount is not None else None,
                "raw_currency": candidate.raw_currency,
                "raw_price_evidence": price.get("raw_value"),
                "raw_price_field": price.get("raw_field"),
                "verified_amount": str(candidate.verified_amount) if candidate.verified_amount is not None else None,
                "verified_currency": candidate.verified_currency,
                "price_verification": price.get("verification"),
                "currency_evidence": price.get("currency_evidence"),
                "publicly_displayable_price": candidate.publicly_displayable_price,
                "purchase_url": candidate.official_purchase_url,
                "purchase_url_verified": candidate.purchase_url_verified,
                "missing_evidence": candidate.missing_evidence_json,
                "last_verified_at": candidate.last_verified_at.isoformat() if candidate.last_verified_at else None,
                "source_payload_sha256": candidate.source_payload_sha256,
            })
        all_sources = db.scalars(select(Source.source_key).order_by(Source.source_key)).all()
        documents = db.scalars(select(OpportunityDocument).order_by(OpportunityDocument.id)).all()
        published_doc = db.get(OpportunityDocument, 1)
        document_hash = None
        if published_doc:
            payload = {column.name: getattr(published_doc, column.name)
                       for column in OpportunityDocument.__table__.columns}
            document_hash = hashlib.sha256(json.dumps(
                payload, ensure_ascii=False, sort_keys=True, default=str,
                separators=(",", ":")).encode("utf-8")).hexdigest()

    categories = dict(Counter(row["document_category"] for row in candidate_rows))
    direct_outcomes = dict(Counter(row["direct_verification_outcome"] or "NO_DIRECT_URL"
                                   for row in candidate_rows))
    summary = {
        "pilot_id": allowlist.get("pilot_id"),
        "run_id": run.id,
        "run_status": run.status,
        "source_key": run.source_key,
        "requested_opportunities": run.requested_count,
        "processed_opportunities": run.processed_count,
        "documents_discovered": run.discovered_count,
        "candidates_staged": len(candidate_rows),
        "verified_candidates": run.verified_count,
        "ready_for_approval": run.ready_count,
        "review_required": run.review_count,
        "duplicates_prevented": run.duplicate_count,
        "temporary_failures": run.temporary_failure_count,
        "failed_records": (run.summary_json or {}).get("failures", []),
        "document_categories": categories,
        "direct_link_outcomes": direct_outcomes,
        "verified_amount_count": sum(row["verified_amount"] is not None for row in candidate_rows),
        "raw_price_evidence_count": sum(row["raw_price_evidence"] is not None for row in candidate_rows),
        "verified_currency_count": sum(row["verified_currency"] is not None for row in candidate_rows),
        "public_price_count": sum(bool(row["publicly_displayable_price"]) for row in candidate_rows),
        "candidate_source_ids": sorted({row["source_opportunity_id"] for row in candidate_rows}),
        "candidate_master_ids": sorted({row["master_opportunity_id"] for row in candidate_rows
                                         if row["master_opportunity_id"] is not None}),
        "opportunity_document_row_count": len(documents),
        "published_document_1_present": published_doc is not None,
        "published_document_1_sha256": document_hash,
        "source_capabilities": capability_matrix(all_sources),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "real-furas-pilot-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "real-furas-pilot-candidates.json").write_text(
        json.dumps(candidate_rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with (args.output_dir / "candidate-review-register.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(candidate_rows[0]) if candidate_rows else ["candidate_id"])
        writer.writeheader()
        for row in candidate_rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})
    with (args.output_dir / "source-opportunity-outcomes.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(record_rows[0]) if record_rows else ["source_opportunity_id"])
        writer.writeheader()
        for row in record_rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})
    print(json.dumps(summary, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

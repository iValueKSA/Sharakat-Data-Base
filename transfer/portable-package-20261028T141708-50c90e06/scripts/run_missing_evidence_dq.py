"""Run the full DQ suite against the live DB in a read-only transaction."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from app.data_quality import evaluate_data_quality
from app.database import SessionLocal


def main() -> None:
    output = Path("docs/validation/data/missing-evidence-recovery/evidence-recovery-dq-results.json")
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        result = evaluate_data_quality(db, scope="full", trigger="missing_evidence_recovery_read_only", persist=False)
        gates = result.get("gates", [])
        result["review_evidence_gate_assertions"] = {
            key: next((gate for gate in gates if gate.get("gate_key") == key), None)
            for key in ("RECOVERED_EVIDENCE_WITHOUT_PROVENANCE",
                        "DUPLICATE_REVIEW_EVIDENCE_ATTACHMENT",
                        "AUTO_RESOLUTION_WITHOUT_RECOVERED_EVIDENCE",
                        "BLOCKED_REVIEW_WITH_EXISTING_SUFFICIENT_EVIDENCE",
                        "REVIEW_EVIDENCE_PROVENANCE_BROKEN",
                        "EVIDENCE_ENRICHMENT_IDEMPOTENCY")
        }
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"scope": result["scope"], "gates": result["gates_evaluated"],
        "counts": result["counts"], "failed": [g.get("gate_key") for g in result["failed_gates"]],
        "warnings": [g.get("gate_key") for g in result["warning_gates"]],
        "review_evidence_gates": {k: (v or {}).get("status") for k, v in result["review_evidence_gate_assertions"].items()}},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

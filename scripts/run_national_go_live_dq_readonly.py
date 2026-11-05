"""Run and capture the full national go-live DQ suite read-only."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from app.data_quality import evaluate_data_quality
from app.database import SessionLocal


def main() -> None:
    output = Path("/tmp/national-go-live-dq-20261104.json")
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        result = evaluate_data_quality(db, scope="full", trigger="national_go_live_final_read_only", persist=False)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summary = {"run_id": result.get("run_id"), "scope": result.get("scope"),
        "gates": result.get("gates_evaluated"), "counts": result.get("counts"),
        "failed_gate_keys": [item.get("gate_key") for item in result.get("failed_gates", [])],
        "warning_gate_keys": [item.get("gate_key") for item in result.get("warning_gates", [])],
        "snapshot": result.get("snapshot")}
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

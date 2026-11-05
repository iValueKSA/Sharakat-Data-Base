import json
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import engine
from app.data_quality import evaluate_data_quality
output=Path("docs/validation/ui/human-review-workbench/review-workbench-dq-results.json")
with engine.connect() as connection:
    connection.execute(text("SET TRANSACTION READ ONLY"))
    with Session(bind=connection) as db:
        result=evaluate_data_quality(db,scope="full",trigger="workbench_readonly_acceptance",persist=False)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
summary={"counts":result["counts"],"gates_evaluated":result["gates_evaluated"],
    "review_gates":[{"gate_key":g["gate_key"],"status":g["status"],"observed":g.get("observed")}
        for g in result["gates"] if g["gate_key"] in {"HUMAN_DECISION_WITHOUT_AUDIT","HISTORICAL_REVIEW_AUDIT_INCOMPLETE","REVIEW_DECISION_WITH_INVALID_ACTION","REVIEW_DECISION_STALE_VERSION","RECOMMENDATION_WITHOUT_EVIDENCE","BATCH_DECISION_NONDETERMINISTIC","RECOMMENDATION_OVERRIDE_WITHOUT_REASON","REOPEN_WITHOUT_AUDIT","BATCH_DECISION_WITHOUT_INDIVIDUAL_AUDIT","RECOMMENDATION_OVERRIDE_WITHOUT_AUDIT","REVIEW_ACTION_RBAC_VIOLATION","BUSINESS_CHANGE_WITHOUT_REVIEW_DECISION"}],
    "failed_gates":[g["gate_key"] for g in result["failed_gates"]],
    "warning_gates":[{"gate_key":g["gate_key"],"observed":g.get("observed")} for g in result["warning_gates"]],
    "persisted":False,"artifact":str(output)}
print(json.dumps(summary,ensure_ascii=False))

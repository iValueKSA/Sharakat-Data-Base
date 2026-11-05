import json
from app.database import SessionLocal
from app.data_quality import evaluate_data_quality

with SessionLocal() as db:
    result = evaluate_data_quality(
        db,
        scope="full",
        trigger="final_platform_readiness_read_only_post_restart",
        persist=False,
    )
    result["read_only_business_data"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

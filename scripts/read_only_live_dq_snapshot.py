"""Run the current live DQ suite without persisting a DQ event or business change."""
import json
from sqlalchemy import text
from app.database import SessionLocal
from app.data_quality import evaluate_data_quality


with SessionLocal() as db:
    db.execute(text("SET TRANSACTION READ ONLY"))
    result=evaluate_data_quality(db,scope="full",trigger="nationwide_expansion_preflight",persist=False)
    db.rollback()
print(json.dumps(result,ensure_ascii=False,indent=2,default=str))

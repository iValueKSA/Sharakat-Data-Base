import json
from sqlalchemy.orm import Session
from app.database import engine
from app.data_quality import evaluate_data_quality
with engine.connect() as conn:
 conn.exec_driver_sql('SET TRANSACTION READ ONLY')
 with Session(bind=conn,autoflush=False,expire_on_commit=False) as db:
  result=evaluate_data_quality(db,scope='full',trigger='job439_integrity_read_only',persist=False)
  print(json.dumps(result,ensure_ascii=False,default=str))

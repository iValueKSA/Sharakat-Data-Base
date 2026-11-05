from sqlalchemy import text
from app.database import engine
import json
c=engine.connect()
for q in ["SELECT s.source_key, count(*) total, count(so.master_opportunity_id) linked, count(*)-count(so.master_opportunity_id) unlinked FROM source_opportunities so JOIN sources s ON s.id=so.source_id GROUP BY s.source_key ORDER BY s.source_key", "SELECT o.id, o.title_ar, count(so.id) source_count, count(distinct so.source_id) source_keys, string_agg(distinct s.source_key, ', ' ORDER BY s.source_key) sources FROM opportunities o LEFT JOIN source_opportunities so ON so.master_opportunity_id=o.id LEFT JOIN sources s ON s.id=so.source_id WHERE o.merged_into_id IS NULL GROUP BY o.id ORDER BY source_count DESC,o.id"]:
 print(json.dumps([dict(x) for x in c.execute(text(q)).mappings()],ensure_ascii=False,default=str))
c.close()

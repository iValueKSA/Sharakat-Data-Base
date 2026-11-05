import json
from sqlalchemy import text
from app.database import engine
c=engine.connect()
queries={
"multi": """SELECT o.id,o.title_ar,count(so.id) AS source_count,count(DISTINCT so.source_id) AS source_count_unique,string_agg(DISTINCT s.source_key, ', ' ORDER BY s.source_key) AS sources FROM opportunities o LEFT JOIN source_opportunities so ON so.master_opportunity_id=o.id LEFT JOIN sources s ON s.id=so.source_id WHERE o.merged_into_id IS NULL GROUP BY o.id HAVING count(so.id)>1 ORDER BY o.id""",
"merges": """SELECT ma.id AS audit_id,ma.merged_opportunity_id,ma.target_opportunity_id,ma.source_record_ids,ma.created_at,ma.merged_at,ma.undone_at,ma.merge_reason,ma.merge_evidence,ma.performed_by,ma.target_before_json,ma.target_after_json,merged.canonical_id AS merged_canonical_id,merged.title_ar AS merged_title,merged.merged_into_id AS current_merged_into,surv.canonical_id AS survivor_canonical_id,surv.title_ar AS survivor_title FROM opportunity_merge_audit ma LEFT JOIN opportunities merged ON merged.id=ma.merged_opportunity_id LEFT JOIN opportunities surv ON surv.id=ma.target_opportunity_id ORDER BY ma.id""",
"queue": """SELECT id,left_opportunity_id,right_opportunity_id,confidence_score,status,created_at,explanation_json FROM duplicate_candidates ORDER BY id""",
"refs": """SELECT reference_number_normalized, count(*) AS masters, array_agg(id ORDER BY id) AS ids FROM opportunities WHERE merged_into_id IS NULL AND coalesce(reference_number_normalized,'')<>'' GROUP BY reference_number_normalized HAVING count(*)>1 ORDER BY reference_number_normalized""",
"source_refs": """SELECT so.source_reference_number_normalized, count(DISTINCT o.id) AS masters, array_agg(DISTINCT o.id ORDER BY o.id) AS ids, string_agg(DISTINCT s.source_key, ', ' ORDER BY s.source_key) AS sources FROM source_opportunities so JOIN opportunities o ON o.id=so.master_opportunity_id LEFT JOIN sources s ON s.id=so.source_id WHERE o.merged_into_id IS NULL AND coalesce(so.source_reference_number_normalized,'')<>'' GROUP BY so.source_reference_number_normalized HAVING count(DISTINCT o.id)>1 ORDER BY so.source_reference_number_normalized"""
}
out={}
for k,q in queries.items(): out[k]=[dict(r) for r in c.execute(text(q)).mappings()]
open('/tmp/identity_quick.json','w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,default=str))
print(json.dumps({k:len(v) for k,v in out.items()}))
c.close()

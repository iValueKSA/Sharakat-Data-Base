import json, hashlib
from datetime import datetime, timezone
from sqlalchemy import text
from app.database import engine

def canon(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def rows(conn, table, order=""):
    q=f"SELECT * FROM {table} {order}"
    return [dict(x._mapping) for x in conn.execute(text(q)).fetchall()]
def digest(obj): return hashlib.sha256(canon(obj).encode("utf-8")).hexdigest()
conn=engine.connect().execution_options(isolation_level="REPEATABLE READ")
trans=conn.begin()
conn.execute(text("SET TRANSACTION READ ONLY"))
meta=dict(conn.execute(text("SELECT now() AT TIME ZONE 'utc' AS snapshot_utc, current_database() AS database_name" )).mappings().one())
masters=rows(conn,"opportunities","ORDER BY id")
sources=rows(conn,"source_opportunities","ORDER BY id")
source_names=rows(conn,"sources","ORDER BY id")
obs=rows(conn,"source_observations","ORDER BY id")
merges=rows(conn,"opportunity_merge_audit","ORDER BY id")
candidates=rows(conn,"duplicate_candidates","ORDER BY id")
links=[{"source_record_id":r["id"],"master_id":r["master_opportunity_id"],"source_id":r["source_id"],"external_id":r["source_opportunity_id"]} for r in sources]
source_rows_by_id={r["id"]:r for r in sources}
master_rows_by_id={r["id"]:r for r in masters}
metadata={
 "snapshot_utc":str(meta["snapshot_utc"]),"database_name":meta["database_name"],
 "total_master_rows":len(masters),"non_merged_masters":sum(1 for r in masters if r["merged_into_id"] is None),
 "merged_masters":sum(1 for r in masters if r["merged_into_id"] is not None),
 "source_opportunities":len(sources),"observations":len(obs),"merge_audits":len(merges),
 "duplicate_candidates":len(candidates),"duplicate_candidates_open":sum(1 for r in candidates if r["status"]=="PENDING"),
 "masters_sha256":digest(masters),"sources_sha256":digest(source_rows_by_id),"source_links_sha256":digest(links),
 "raw_source_payloads_sha256":digest([(r["id"],digest(r.get("raw_data_json") or {})) for r in sources]),
 "observations_sha256":digest(obs),"merge_relationships_sha256":digest([(r["id"],r.get("merged_into_id")) for r in masters]),
 "canonical_fields_sha256":digest([(r["id"], {k:r.get(k) for k in ["title_ar","title_en","normalized_title","reference_number","reference_number_normalized","opportunity_owner","sector","activity","sub_activity","opportunity_type","investment_model","city","district","latitude","longitude","land_area_sqm","plot_number","investment_value","currency","contract_duration_years","publication_date","submission_deadline","status"]}) for r in masters])
}
# report latest sync row from same snapshot
latest=conn.execute(text("SELECT id,source_id,started_at,finished_at,status,trigger_type,new_count,duplicate_count,merged_records_count,records_received FROM source_sync_jobs ORDER BY started_at DESC,id DESC LIMIT 1")).mappings().first()
metadata["latest_sync_job"]=dict(latest) if latest else None
bundle={"metadata":metadata,"masters":masters,"sources":source_names,"source_opportunities":sources,"merge_audits":merges,"duplicate_candidates":candidates}
with open("/tmp/master_identity_snapshot_pre.json","w",encoding="utf-8") as f: json.dump(bundle,f,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)
trans.commit();conn.close()
print(json.dumps(metadata,ensure_ascii=False,default=str))


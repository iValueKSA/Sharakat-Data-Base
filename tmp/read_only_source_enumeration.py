import asyncio, json, ssl, sys
sys.path.insert(0, "/app")
import httpx
from app.adapters import ADAPTERS

SAFE_KEYS = {
 'source_total_reported','pages_requested','pages_successful','records_received','records_parsed','unique_records',
 'pagination_complete','active_count','expired_count','duplicate_items_between_pages','page_size',
 'source_collection_complete','reconciliation_safe','coverage_status','coverage_contract','coverage_notes',
 'dataset_count','datasets_complete','endpoint_rows_received','unique_official_ids','duplicate_endpoint_memberships',
 'accepted_records','location_review_count','rejected_records','rejected_content','error_pages','page_errors',
 'source_limitations','public_scope_complete','collection_incomplete','route_inventory','pagination_routes',
 'pages_scanned','pages_expected','load_more_controls','records_missing_stable_id','official_item_count',
 'sitemap_complete','archive_pages','qualified_opportunities','investment_pages','attachments'
}
async def main():
 out={}
 timeout=httpx.Timeout(50,connect=18)
 async with httpx.AsyncClient(timeout=timeout, verify=ssl.create_default_context(), follow_redirects=True,
         limits=httpx.Limits(max_connections=4)) as client:
  for key, cls in ADAPTERS.items():
   adapter=cls()
   try:
    records,pages=await adapter.fetch(client)
    metrics=getattr(adapter,'metrics',{}) or {}
    out[key]={"ok":True,"records_returned":len(records),"fetch_pages_returned":pages,
      "external_ids":[str(r.external_id) for r in records],
      "metrics":{k:v for k,v in metrics.items() if k in SAFE_KEYS}}
   except Exception as exc:
    out[key]={"ok":False,"error_type":type(exc).__name__,"error":str(exc)[:500],
      "metrics":{k:v for k,v in (getattr(adapter,'metrics',{}) or {}).items() if k in SAFE_KEYS}}
 print(json.dumps(out,ensure_ascii=False,separators=(',',':')))
asyncio.run(main())



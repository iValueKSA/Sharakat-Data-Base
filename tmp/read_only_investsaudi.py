import asyncio,json,ssl,sys
sys.path.insert(0,'/app')
import httpx
from app.adapters import InvestSaudiAdapter
async def main():
 a=InvestSaudiAdapter()
 try:
  async with httpx.AsyncClient(timeout=httpx.Timeout(45,connect=15),verify=ssl.create_default_context(),follow_redirects=True) as c:
   records,pages=await a.fetch(c)
  print(json.dumps({'ok':True,'pages':pages,'metrics':a.metrics,'accepted_ids':[x.external_id for x in records],'all_candidates':[{'id':x.external_id,'family':(x.raw or {}).get('source_record_family'),'dataset':(x.raw or {}).get('dataset_name'),'location_method':(x.raw or {}).get('location_detection_method'),'score':(x.raw or {}).get('location_confidence_score')} for x in a.raw_candidates],'reviews':[{'id':x['external_id'],'location':x.get('location'),'method':x.get('reason'),'confidence':x.get('confidence_score')} for x in a.location_reviews]},ensure_ascii=False,separators=(',',':')))
 except Exception as e:
  print(json.dumps({'ok':False,'error_type':type(e).__name__,'error':str(e)[:300],'metrics':a.metrics},ensure_ascii=False))
asyncio.run(main())

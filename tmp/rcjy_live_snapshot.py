import asyncio, json
import httpx
from app.adapters import RcjyAdapter, normalized_record
async def main():
    adapter=RcjyAdapter()
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        records,pages=await adapter.fetch(client)
    result={"metrics":adapter.metrics,"pages_returned":pages,"records":[]}
    for item in records:
        normalized=normalized_record(item)
        result["records"].append({"external_id":item.external_id,"title":item.title,"title_en":item.raw.get("title_en"),"location":item.location,"activity":item.activity,"sub_activity":item.sub_activity,"status":item.status,"reference":item.reference,"area_text":item.area_text,"latitude":item.latitude,"longitude":item.longitude,"owner":item.owner,"raw":item.raw,"normalized_location":{k:normalized.get(k) for k in ("relevant","location_confidence_score","city","location_detection_method","location_evidence")}})
    print(json.dumps(result,ensure_ascii=False))
asyncio.run(main())

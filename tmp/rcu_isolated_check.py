import asyncio, json, httpx
from app.adapters import RcuAdapter
async def main():
    snapshots=[]
    for _ in range(2):
        adapter=RcuAdapter()
        async with httpx.AsyncClient(timeout=35, follow_redirects=True) as client:
            rows,pages=await adapter.fetch(client)
        snapshots.append((adapter,rows,pages))
    first,second=snapshots
    print(json.dumps({"method":first[0].metrics["extraction_method"],"count":len(first[1]),"reported":first[0].metrics["source_total_reported"],"pages":first[2],"ids":[r.external_id for r in first[1]],"unique":len({r.external_id for r in first[1]})==len(first[1]),"deterministic":[(r.external_id,r.content_hash) for r in first[1]]==[(r.external_id,r.content_hash) for r in second[1]],"coordinates":[[r.latitude,r.longitude] for r in first[1]]},ensure_ascii=False))
asyncio.run(main())

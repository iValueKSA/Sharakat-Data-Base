import asyncio, json
from pathlib import Path
import httpx
from app.adapters import NcpAdapter

async def main():
    adapter = NcpAdapter()
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        records, metrics = await adapter.fetch_investor_portal(client)
    payload = {
        "metrics": metrics,
        "records": [
            {"external_id": r.external_id, "title": r.title, "url": r.url, "owner": r.owner,
             "location": r.location, "area_text": r.area_text, "activity": r.activity,
             "deadline": r.deadline, "status": r.status, "reference": r.reference,
             "description": r.description, "latitude": r.latitude, "longitude": r.longitude,
             "raw": r.raw}
            for r in records
        ],
    }
    Path('/tmp/ncp_portal_current.json').write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding='utf-8')
    print(json.dumps({k: metrics.get(k) for k in ("public_project_count", "pages", "pagination_complete", "provider_id_field", "provider_ids_unique", "details_refreshed", "is_closed_false", "available_to_submit", "documents", "coordinate_records", "endpoint", "api_base")}, ensure_ascii=False))

asyncio.run(main())

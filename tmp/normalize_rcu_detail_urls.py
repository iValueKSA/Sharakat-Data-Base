import asyncio, json
from datetime import datetime, timezone
import httpx
from sqlalchemy import select
from app.adapters import RcuAdapter
from app.database import SessionLocal
from app.models import AuditEvent, Source, SourceOpportunity
from app.service import store_status_observation

async def main():
    adapter=RcuAdapter()
    async with httpx.AsyncClient(timeout=35,follow_redirects=True) as client:
        records,_=await adapter.fetch(client)
    by_id={r.external_id:r for r in records}
    if len(by_id)!=6: raise RuntimeError('RCU detail-route normalization expected six current records')
    normalized=[]
    with SessionLocal.begin() as db:
        source=db.scalar(select(Source).where(Source.source_key==RcuAdapter.key))
        rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id)).all()
        if {r.source_opportunity_id for r in rows}!=set(by_id):
            raise RuntimeError('RCU source rows no longer reconcile to the current public identity set')
        for row in rows:
            raw=by_id[row.source_opportunity_id]
            before_url=row.source_url
            before_detail=(row.raw_data_json or {}).get('detail_url')
            if before_url==raw.url and before_detail==raw.url:
                continue
            row.source_url=raw.url
            row.raw_data_json=raw.raw or {}
            row.content_hash=raw.content_hash
            row.parser_version=adapter.parser_version
            store_status_observation(db,source,row,raw,datetime.now(timezone.utc))
            db.add(AuditEvent(event_type='RCU_SOURCE_DETAIL_URL_NORMALIZED',entity_type='source_opportunity',
                entity_id=str(row.id),before_json={'source_url':before_url,'detail_url':before_detail},
                after_json={'source_url':raw.url,'detail_url':(raw.raw or {}).get('detail_url'),
                    'provider_id':row.source_opportunity_id,'content_hash':row.content_hash},
                request_metadata={'actor':'controlled_rcu_integration','reason':'official RCU route manifest declares opportunities/detail/:id'},
                created_at=datetime.now(timezone.utc)))
            normalized.append({'provider_id':row.source_opportunity_id,'source_opportunity_id':row.id,'url':raw.url})
    print(json.dumps({'metadata_rows_normalized':len(normalized),'records':normalized},ensure_ascii=False))
asyncio.run(main())

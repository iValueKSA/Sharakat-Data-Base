import asyncio, json, re, difflib
import httpx
from sqlalchemy import select
from app.database import SessionLocal
from app.models import SourceOpportunity, Source, Opportunity, GeographicReferenceDataset, GeographicReferenceUnit
from app.adapters import RcuAdapter
from app.normalization import normalize_arabic

def en_norm(s): return re.sub(r'[^a-z0-9]+',' ',str(s or '').casefold()).strip()
def ratio(a,b): return difflib.SequenceMatcher(None,a,b).ratio() if a and b else 0.0
async def main():
    adapter=RcuAdapter()
    async with httpx.AsyncClient(timeout=35,follow_redirects=True) as client: records,pages=await adapter.fetch(client)
    with SessionLocal() as db:
        sources={s.id:s for s in db.scalars(select(Source)).all()}
        existing=db.scalars(select(SourceOpportunity).options()).all()
        masters={m.id:m for m in db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()}
        ds=db.scalar(select(GeographicReferenceDataset).where(GeographicReferenceDataset.dataset_key=='saudi_administrative_units',GeographicReferenceDataset.version=='taadeen-public-gis-20261102-v3'))
        units=db.scalars(select(GeographicReferenceUnit).where(GeographicReferenceUnit.dataset_id==ds.id)).all() if ds else []
        by_id={u.id:u for u in units}
        alula=[u for u in units if u.level=='governorate' and u.external_id=='302']
        result=[]
        for r in records:
            raw=r.raw or {}; ar=normalize_arabic(r.title); en=en_norm(raw.get('titleEN'))
            candidates=[]
            for row in existing:
                master=masters.get(row.master_opportunity_id)
                src=sources.get(row.source_id)
                t_ar=normalize_arabic(row.source_title or (master.title_ar if master else ''))
                t_en=en_norm((row.raw_data_json or {}).get('titleEN') or (row.raw_data_json or {}).get('title_en') or (master.title_en if master else ''))
                ar_score=ratio(ar,t_ar); en_score=ratio(en,t_en)
                score=max(ar_score,en_score)
                if score>=.45:
                    candidates.append({'source_key':src.source_key if src else None,'source_record_id':row.id,'master_id':row.master_opportunity_id,'title':row.source_title,'title_ar_similarity':round(ar_score,3),'title_en_similarity':round(en_score,3),'reference':row.source_reference_number})
            candidates.sort(key=lambda x:max(x['title_ar_similarity'],x['title_en_similarity']),reverse=True)
            result.append({'provider_id':r.external_id,'display_id':r.reference,'title_ar':r.title,'title_en':raw.get('titleEN'),
                'description_ar':raw.get('descriptionAR'),'description_en':raw.get('descriptionEN'),'opportunity_type':raw.get('opportunityType'),
                'status_evidence':raw.get('lifecycle_evidence'),'latitude':r.latitude,'longitude':r.longitude,
                'location_text':r.location,'alula_named_in_title_or_description':any(x in (r.title+' '+str(raw.get('titleEN') or '')+' '+str(raw.get('descriptionAR') or '')+' '+str(raw.get('descriptionEN') or '')).casefold() for x in ['العلا','alula','al ula']),
                'top_candidates':candidates[:8]})
        parent=by_id[alula[0].parent_id] if alula else None
        print(json.dumps({'count':len(records),'pages':pages,'provider_id_field':adapter.metrics['provider_id_field'],'source_records_examined':len(existing),'masters_examined':len(masters),'geography_unit':{'id':alula[0].id,'level':alula[0].level,'external_id':alula[0].external_id,'name_ar':alula[0].name_ar,'name_en':alula[0].name_en,'region_id':parent.id if parent else None,'region_external_id':parent.external_id if parent else None,'region_ar':parent.name_ar if parent else None,'region_en':parent.name_en if parent else None} if alula else None,'records':result},ensure_ascii=False,default=str))
asyncio.run(main())

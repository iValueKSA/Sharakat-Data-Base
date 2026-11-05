import json
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import Source, SourceOpportunity, Opportunity, SourceObservation

db=SessionLocal()
sources={s.id:s.source_key for s in db.scalars(select(Source)).all()}
rows=[]
for r in db.scalars(select(SourceOpportunity)).all():
    raw=r.raw_data_json or {}
    rows.append({'id':r.id,'source_key':sources.get(r.source_id),'external_id':r.source_opportunity_id,
       'official_id':r.official_source_id_original,'normalized_id':r.official_source_id_normalized,
       'reference':r.source_reference_number,'reference_normalized':r.source_reference_number_normalized,
       'title':r.source_title,'url':r.source_url,'owner':r.source_owner,'sector':r.source_sector,
       'activity':r.source_activity,'location':r.raw_location,'status':r.raw_status,
       'stage':raw.get('project_stage'),'description':(raw.get('raw_text') or raw.get('description') or raw.get('extracted_description') or '')[:1200],
       'master_id':r.master_opportunity_id,'master_title_ar':r.master.title_ar if r.master else None,
       'master_title_en':r.master.title_en if r.master else None,'master_owner':r.master.opportunity_owner if r.master else None,
       'master_sector':r.master.sector if r.master else None,'master_location':r.master.location_description if r.master else None,
       'observations':db.scalar(select(func.count()).select_from(SourceObservation).where(SourceObservation.source_opportunity_id==r.id))})
linked_current=set()
for r in rows:
    if r['source_key']=='ncp' and r['master_id']:
        m=db.get(Opportunity,r['master_id'])
        if m and m.merged_into_id is None: linked_current.add(m.id)
result={'configured_sources':db.scalar(select(func.count()).select_from(Source)),
        'all_masters_unmerged':db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.merged_into_id.is_(None))),
        'ncp_linked_current_masters':len(linked_current),'ncp_source_rows':rows}
print(json.dumps(result,ensure_ascii=False,default=str))

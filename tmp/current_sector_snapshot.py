import json
from collections import Counter
from sqlalchemy import select, func, text
from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity, SourceObservation, OpportunityAssetFacilityType, ChangeHistory, SystemEvent, SyncJob
from app.standardization import _SECTOR_LABELS, SECTOR_UNSPECIFIED_LABEL, canonical_id

s=SessionLocal()
s.execute(text('SET TRANSACTION READ ONLY'))
masters=s.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
current=[m for m in masters if (m.status or '') not in {'ARCHIVED','MERGED'}]
unspec=[m for m in current if canonical_id('sector',m.sector)=='sector:unspecified']
scount=Counter(canonical_id('sector',m.sector) for m in current)
source_map={x.id:x for x in s.scalars(select(Source)).all()}
rows=[]
for m in unspec:
    srcs=s.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==m.id).order_by(SourceOpportunity.id)).all()
    source_items=[]
    for so in srcs:
        src=source_map.get(so.source_id)
        obs=s.scalars(select(SourceObservation).where(SourceObservation.source_opportunity_id==so.id).order_by(SourceObservation.last_seen_at.desc()).limit(3)).all()
        assets=s.execute(select(OpportunityAssetFacilityType.raw_value).where(OpportunityAssetFacilityType.source_record_id==so.id)).scalars().all()
        source_items.append({'source_key':src.source_key if src else None,'source_name':src.source_name_ar if src else None,'source_record_id':so.id,'source_opportunity_id':so.source_opportunity_id,'official_source_id_original':so.official_source_id_original,'source_title':so.source_title,'source_sector':so.source_sector,'source_activity':so.source_activity,'source_sub_activity':so.source_sub_activity,'source_subsector':so.source_subsector,'source_owner':so.source_owner,'raw_location':so.raw_location,'raw_area':so.raw_area,'raw_value':so.raw_value,'raw_dates':so.raw_dates,'raw_data_json':so.raw_data_json,'standardized_data_json':so.standardized_data_json,'assets':assets,'observations':[{'seen':str(o.last_seen_at),'raw':o.raw_data_json} for o in obs]})
    master_assets=s.execute(select(OpportunityAssetFacilityType.raw_value).where(OpportunityAssetFacilityType.opportunity_id==m.id)).scalars().all()
    rows.append({'id':m.id,'canonical_id':m.canonical_id,'title_ar':m.title_ar,'title_en':m.title_en,'normalized_title':m.normalized_title,'reference_number':m.reference_number,'opportunity_owner':m.opportunity_owner,'primary_publication_platform':m.primary_publication_platform,'sector':m.sector,'activity':m.activity,'sub_activity':m.sub_activity,'subsector':m.subsector,'opportunity_type':m.opportunity_type,'investment_model':m.investment_model,'city':m.city,'district':m.district,'location_description':m.location_description,'latitude':m.latitude,'longitude':m.longitude,'land_area_sqm':m.land_area_sqm,'plot_number':m.plot_number,'investment_value':m.investment_value,'contract_duration_years':m.contract_duration_years,'publication_date':m.publication_date,'submission_deadline':m.submission_deadline,'short_description':m.short_description,'full_description':m.full_description,'asset_facility_type':' | '.join(sorted(set(master_assets))),'sources':source_items})
job_count=s.scalar(select(func.count()).select_from(SyncJob)) or 0
max_job=s.scalar(select(func.max(SyncJob.id)))
active_jobs=s.scalar(select(func.count()).select_from(SyncJob).where(SyncJob.job_state.notin_(['COMPLETED','COMPLETED_WITH_WARNINGS','FAILED','CANCELLED']))) or 0
history_count=s.scalar(select(func.count()).select_from(ChangeHistory)) or 0
result={'snapshot_at':str(s.scalar(text('SELECT now()'))),'current_masters':len(current),'all_master_rows':len(masters),'specified':len(current)-len(unspec),'unspecified':len(unspec),'sector_counts':dict(scount),'canonical_taxonomy':{f'sector:{k}':v for k,v in _SECTOR_LABELS.items()},'unspecified_by_source':dict(Counter(src['source_key'] for row in rows for src in row['sources'] if src['source_key'])),'unspecified_by_owner':dict(Counter(row['opportunity_owner'] or '(null)' for row in rows)),'unspecified_by_opportunity_type':dict(Counter(row['opportunity_type'] or '(null)' for row in rows)),'unspecified_records':rows,'sync_jobs':{'count':job_count,'max_id':max_job,'active':active_jobs},'change_history_count':history_count}
with open('/tmp/current-sector-snapshot.json','w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False,indent=2,default=str)
print(json.dumps({k:v for k,v in result.items() if k not in ('unspecified_records',)},ensure_ascii=False,indent=2,default=str))
s.close()

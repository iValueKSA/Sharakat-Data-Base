import json
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import Source, SourceOpportunity, Opportunity, SourceObservation

db = SessionLocal()
src = db.scalar(select(Source).where(Source.source_key == 'ncp'))
ncp = db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id == src.id)).all()
masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
ncp_rows = []
for r in ncp:
    raw = r.raw_data_json or {}
    ncp_rows.append({
        'id': r.id, 'external_id': r.source_opportunity_id, 'title': r.source_title,
        'description': (raw.get('raw_text') or '')[:3500], 'url': r.source_url,
        'stage': raw.get('project_stage'), 'location': r.raw_location, 'status': r.raw_status,
        'master_id': r.master_opportunity_id,
        'master_title_ar': r.master.title_ar if r.master else None,
        'master_title_en': r.master.title_en if r.master else None,
        'observation_count': db.scalar(select(func.count()).select_from(SourceObservation).where(SourceObservation.source_opportunity_id == r.id)),
    })
master_rows = []
for m in masters:
    master_rows.append({
        'id': m.id, 'title_ar': m.title_ar, 'title_en': m.title_en,
        'reference': m.reference_number, 'owner': m.opportunity_owner,
        'platform': m.primary_publication_platform, 'sector': m.sector,
        'activity': m.activity, 'type': m.opportunity_type, 'model': m.investment_model,
        'city': m.city, 'location': m.location_description, 'status': m.status,
        'description': (m.short_description or '')[:1000],
    })
result = {
    'ncp_source': {'key': src.source_key, 'name': src.source_name_ar, 'enabled': src.enabled,
        'opportunities_url': src.opportunities_url, 'extraction_method': src.extraction_method,
        'last_success': str(src.last_successful_sync), 'record_count': len(ncp)},
    'ncp_rows': ncp_rows, 'all_current_unmerged_masters': master_rows,
    'configured_sources': db.scalar(select(func.count()).select_from(Source)),
}
print(json.dumps(result, ensure_ascii=False, default=str))

import json
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import SessionLocal
from app.models import Source, SourceOpportunity, Opportunity, GeographicReferenceUnit

wanted = {"ncp", "furas", "invest-saudi", "pif", "nhc", "modon", "mwan", "rcjy-investment-opportunities", "rcu-investment-opportunities"}
with SessionLocal() as db:
    sources = {s.id: s for s in db.scalars(select(Source))}
    rows = db.scalars(select(SourceOpportunity).options(selectinload(SourceOpportunity.opportunity_locations))).all()
    current_rows = [r for r in rows if sources[r.source_id].source_key in wanted]
    masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
    units = {u.id:u for u in db.scalars(select(GeographicReferenceUnit))}
    links = {}
    for r in current_rows:
        links.setdefault(r.master_opportunity_id, []).append({"source_key":sources[r.source_id].source_key,"source_row_id":r.id,"external_id":r.source_opportunity_id,"reference":r.source_reference_number,"title":r.source_title,"url":r.source_url})
    payload = {
      "exported_at_utc": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
      "configured_source_count": len(sources), "current_master_count": len(masters),
      "source_row_count_all_sources": len(rows), "source_rows_included": len(current_rows),
      "ncp_source": {"id":next((s.id for s in sources.values() if s.source_key=="ncp"),None),"key":"ncp","name":next((s.source_name_ar for s in sources.values() if s.source_key=="ncp"),None)},
      "source_rows": [{
        "source_key":sources[r.source_id].source_key,"source_row_id":r.id,"external_id":r.source_opportunity_id,
        "master_id":r.master_opportunity_id,"reference":r.source_reference_number,"title":r.source_title,
        "url":r.source_url,"owner":r.source_owner,"sector":r.source_sector,"activity":r.source_activity,
        "raw_location":r.raw_location,"raw_area":r.raw_area,"raw_status":r.raw_status,"canonical_status":r.canonical_status,
        "raw_dates":r.raw_dates,"raw":r.raw_data_json or {},
        "locations":[{"name":p.location_name,"scope":p.location_scope,"source_location_text":p.source_location_text,"geography_unit_id":p.geography_reference_unit_id,"reference_level":units[p.geography_reference_unit_id].level if p.geography_reference_unit_id in units else None,"reference_external_id":units[p.geography_reference_unit_id].external_id if p.geography_reference_unit_id in units else None,"reference_name_ar":units[p.geography_reference_unit_id].name_ar if p.geography_reference_unit_id in units else None} for p in r.opportunity_locations]
      } for r in current_rows],
      "current_masters": [{
        "id":m.id,"canonical_id":m.canonical_id,"title_ar":m.title_ar,"title_en":m.title_en,"reference":m.reference_number,
        "owner":m.opportunity_owner,"primary_publication_platform":m.primary_publication_platform,"sector":m.sector,
        "activity":m.activity,"opportunity_type":m.opportunity_type,"investment_model":m.investment_model,
        "city":m.city,"location":m.location_description,"latitude":m.latitude,"longitude":m.longitude,"area":m.land_area_sqm,
        "publication_date":m.publication_date,"deadline":m.submission_deadline,"status":m.status,
        "geographic_scope":m.geographic_scope,"geo_unit_id":m.geography_reference_unit_id,
        "geo_level":units[m.geography_reference_unit_id].level if m.geography_reference_unit_id in units else None,
        "geo_external_id":units[m.geography_reference_unit_id].external_id if m.geography_reference_unit_id in units else None,
        "geo_name_ar":units[m.geography_reference_unit_id].name_ar if m.geography_reference_unit_id in units else None,
        "sources":links.get(m.id,[])
      } for m in masters]
    }
Path('/tmp/ncp_live_comparison.json').write_text(json.dumps(payload,ensure_ascii=False,default=str),encoding='utf-8')
print(json.dumps({k:payload[k] for k in ('exported_at_utc','configured_source_count','current_master_count','source_row_count_all_sources','source_rows_included')},ensure_ascii=False))

import json
from collections import Counter, defaultdict
from pathlib import Path
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Opportunity, SourceOpportunity, Source, SourceOpportunityTaxonomy, OpportunityConflict
from app.standardization import canonical_id, canonical_value, standardize_text

out={"mode":"READ_ONLY_DRY_RUN","masters":{},"source_fields":{},"opportunity_type":{},"taxonomy_table":{},"investment_opportunity_records":[]}
with SessionLocal() as db:
    masters=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
    out["masters"]["total_nonmerged"]=len(masters)
    def count_field(seq):
        c=Counter("<NULL>" if v is None else "<BLANK>" if not standardize_text(v) else str(v) for v in seq)
        return [{"value":k,"count":v,"canonical_id":canonical_id("sector",None if k=="<NULL>" else "" if k=="<BLANK>" else k),"canonical_label":canonical_value("sector",None if k=="<NULL>" else "" if k=="<BLANK>" else k)} for k,v in sorted(c.items(),key=lambda x:(-x[1],x[0]))]
    out["masters"]["sector_values"]=count_field([m.sector for m in masters])
    out["masters"]["subsector_values"]=count_field([m.subsector for m in masters])
    out["masters"]["opportunity_type_values"]=count_field([m.opportunity_type for m in masters])
    src=db.execute(select(SourceOpportunity,Source.source_key,Source.source_name_ar).join(Source,Source.id==SourceOpportunity.source_id).order_by(SourceOpportunity.id)).all()
    out["source_rows_total"]=len(src)
    for field, getter in {
      "source_sector":lambda r,k,n:r.source_sector,
      "normalized_sector":lambda r,k,n:r.normalized_sector,
      "source_subsector":lambda r,k,n:r.source_subsector,
      "payload_source_taxonomy_sector":lambda r,k,n:(r.raw_data_json or {}).get("source_taxonomy",{}).get("sector"),
      "payload_normalized_taxonomy_sector":lambda r,k,n:(r.raw_data_json or {}).get("normalized_taxonomy",{}).get("sector"),
      "payload_activity":lambda r,k,n:(r.raw_data_json or {}).get("activity"),
      "payload_category":lambda r,k,n:(r.raw_data_json or {}).get("category"),
      "payload_opportunity_category":lambda r,k,n:(r.raw_data_json or {}).get("opportunity_category"),
      "payload_opportunity_type":lambda r,k,n:(r.raw_data_json or {}).get("opportunity_type"),
      "standardized_sector":lambda r,k,n:((r.standardized_data_json or {}).get("fields",{}).get("sector",{}).get("canonical_label")),
    }.items():
      out["source_fields"][field]=count_field([getter(r,k,n) for r,k,n in src if getter(r,k,n) is not None])
    taxonomy=db.execute(select(SourceOpportunityTaxonomy.source_taxonomy_value,SourceOpportunityTaxonomy.normalized_taxonomy_value,SourceOpportunityTaxonomy.dataset_name,Source.source_key).join(SourceOpportunity,SourceOpportunity.id==SourceOpportunityTaxonomy.source_opportunity_id).join(Source,Source.id==SourceOpportunity.source_id)).all()
    out["taxonomy_table"]["rows"]=len(taxonomy)
    out["taxonomy_table"]["source_taxonomy_values"]=count_field([row[0] for row in taxonomy])
    out["taxonomy_table"]["normalized_taxonomy_values"]=count_field([row[1] for row in taxonomy])
    candidates=[m for m in masters if standardize_text(m.sector)=="فرصة استثمارية"]
    for m in candidates:
      related=[(r,k,n) for r,k,n in src if r.master_opportunity_id==m.id]
      conflicts=db.scalars(select(OpportunityConflict).where(OpportunityConflict.opportunity_id==m.id,OpportunityConflict.status=="OPEN")).all()
      out["investment_opportunity_records"].append({
        "master_id":m.id,"canonical_id":m.canonical_id,"title":m.title_ar,"title_en":m.title_en,"owner":m.opportunity_owner,
        "current_sector":m.sector,"subsector":m.subsector,"opportunity_type":m.opportunity_type,"description":m.short_description or m.full_description,
        "source_evidence":[{"source_key":k,"source_name":n,"source_record_id":r.id,"source_opportunity_id":r.source_opportunity_id,"title":r.source_title,"source_sector":r.source_sector,"normalized_sector":r.normalized_sector,"source_subsector":r.source_subsector,"source_taxonomy":(r.raw_data_json or {}).get("source_taxonomy"),"normalized_taxonomy":(r.raw_data_json or {}).get("normalized_taxonomy"),"activity":(r.raw_data_json or {}).get("activity"),"category":(r.raw_data_json or {}).get("category"),"opportunity_category":(r.raw_data_json or {}).get("opportunity_category"),"opportunity_type":(r.raw_data_json or {}).get("opportunity_type"),"dataset_name":(r.raw_data_json or {}).get("dataset_name"),"description":(r.raw_data_json or {}).get("description") or (r.raw_data_json or {}).get("full_description")} for r,k,n in related],
        "open_conflicts":[{"field":c.field_name,"selected":c.selected_value,"conflicting":c.conflicting_value,"source_record_id":c.source_record_id} for c in conflicts]
      })
Path('/tmp/sector-deep-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({"mode":"READ_ONLY_DRY_RUN","masters":out["masters"]["total_nonmerged"],"source_rows":out["source_rows_total"],"masters_sector_distinct":len(out["masters"]["sector_values"]),"records_currently_opportunity_sector":len(out["investment_opportunity_records"]),"ids":[r["master_id"] for r in out["investment_opportunity_records"]],"source_taxonomy_records":out["taxonomy_table"]["rows"]},ensure_ascii=False))

"""Map RCU's explicit realEstateCategory into governed canonical sectors."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.models import Opportunity, Source, SourceOpportunity, SourceOpportunityTaxonomy
from app.security import audit
from app.service import apply_sector_phase2_after_ingestion
from app.standardization import canonical_id


RCU_CATEGORY_MAP={
    "Transport (e.g., Roads, Rail, Airports)":("الخدمات اللوجستية","sector:logistics"),
    "Water & Waste":("البيئة","sector:environment"),
}


def classify_rcu_sectors(db, *, apply=False):
    source=db.scalar(select(Source).where(Source.source_key=="rcu-investment-opportunities"))
    if source is None: raise RuntimeError("RCU source is not registered")
    rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id)
        .order_by(SourceOpportunity.source_opportunity_id)).all()
    if len(rows)!=6 or any(row.master_opportunity_id is None for row in rows):
        raise RuntimeError("RCU category mapping requires the exact six captured and linked RCU rows")
    actions=[]
    for row in rows:
        raw=row.raw_data_json or {}; category=raw.get("realEstateCategory") or {}
        category_name=category.get("name") if isinstance(category,dict) else None
        mapped=RCU_CATEGORY_MAP.get(category_name)
        if not mapped: raise RuntimeError(f"Unmapped RCU official category for provider {row.source_opportunity_id}")
        label,sector_id=mapped
        master=db.get(Opportunity,row.master_opportunity_id)
        if not master: raise RuntimeError(f"Missing linked Master for RCU provider {row.source_opportunity_id}")
        before={"master_sector":master.sector,"source_sector_projection":row.source_sector,
            "normalized_sector":row.normalized_sector}
        if not apply:
            actions.append({"provider_id":row.source_opportunity_id,"master_id":master.id,
                "source_category":category_name,"canonical_sector":label,"action":"WOULD_CLASSIFY"})
            continue
        if master.sector not in (None,"",label):
            raise RuntimeError(f"RCU Master {master.id} already has a different sector; review required")
        row.source_sector=label;row.normalized_sector=sector_id
        standardized=dict(row.standardized_data_json or {})
        fields=dict(standardized.get("fields") or {})
        fields["sector"]={"raw":category_name,"raw_display_ar":category.get("displayNameArabic"),
            "raw_display_en":category.get("displayNameEnglish"),"canonical_id":sector_id,
            "canonical_label":label,"mapping_status":"MAPPED",
            "rule":"rcu_realEstateCategory_to_canonical_sector_v1",
            "evidence_fields":["realEstateCategory.name","realEstateCategory.displayNameArabic",
                "realEstateCategory.displayNameEnglish"],"review_flags":[]}
        standardized["fields"]=fields;standardized["source_taxonomy_mapping"]={
            "source_field":"realEstateCategory.name","source_value":category_name,
            "canonical_sector_id":sector_id,"canonical_sector":label,
            "mapping_rule":"rcu_realEstateCategory_to_canonical_sector_v1","mapping_version":"1"}
        row.standardized_data_json=standardized
        taxonomy=db.scalar(select(SourceOpportunityTaxonomy).where(
            SourceOpportunityTaxonomy.source_opportunity_id==row.id,
            SourceOpportunityTaxonomy.dataset_name=="realEstateCategory",
            SourceOpportunityTaxonomy.source_taxonomy_value==category_name))
        if taxonomy is None:
            taxonomy=SourceOpportunityTaxonomy(source_opportunity_id=row.id,dataset_name="realEstateCategory",
                source_taxonomy_value=category_name,normalized_taxonomy_value=sector_id,
                mapping_rule="Official RCU realEstateCategory mapping v1",mapping_version="1")
            db.add(taxonomy)
        else:
            taxonomy.normalized_taxonomy_value=sector_id
            taxonomy.mapping_rule="Official RCU realEstateCategory mapping v1";taxonomy.mapping_version="1"
        apply_sector_phase2_after_ingestion(db,master,source=source,source_record=row,detected_at=datetime.now(timezone.utc))
        if canonical_id("sector",master.sector)!=sector_id:
            raise RuntimeError(f"Governed sector classifier did not accept the explicit RCU category for Master {master.id}")
        audit(db,"RCU_MASTER_SECTOR_STANDARDIZED",entity_type="opportunity",entity_id=str(master.id),before=before,
            after={"master_id":master.id,"source_opportunity_id":row.id,"provider_id":row.source_opportunity_id,
                "source_category":category_name,"canonical_sector":master.sector,
                "classification_method":"SOURCE_EXPLICIT","confidence":"HIGH",
                "mapping_rule":"rcu_realEstateCategory_to_canonical_sector_v1"},
            metadata={"actor":"controlled_rcu_integration","evidence_url":raw.get("source_url")})
        actions.append({"provider_id":row.source_opportunity_id,"master_id":master.id,
            "source_category":category_name,"canonical_sector":master.sector,"action":"CLASSIFIED_AND_AUDITED"})
    db.flush()
    return {"apply":apply,"records_reconciled":len(rows),"actions":actions}

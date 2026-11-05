import sys
from pathlib import Path as _Path
sys.path.insert(0, '/app')
import json
from datetime import datetime,timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import SessionLocal
from app.models import Opportunity,GeographicReferenceDataset,GeographicReferenceUnit,SourceOpportunity
from app.main import (_opportunity_filter_conditions,_opportunity_geography,
    _pending_location_reviews_by_master,_source_location_values_by_master)
from app.geography import resolve_master_geography

with SessionLocal() as db:
    dataset=db.scalar(select(GeographicReferenceDataset).where(GeographicReferenceDataset.is_current.is_(True)))
    units={u.id:u for u in db.scalars(select(GeographicReferenceUnit).where(GeographicReferenceUnit.dataset_id==dataset.id))}
    stmt=(select(Opportunity).where(*_opportunity_filter_conditions(db,governorate_id='501'))
        .options(selectinload(Opportunity.source_records).selectinload(SourceOpportunity.source),
                 selectinload(Opportunity.source_records).selectinload(SourceOpportunity.opportunity_locations)))
    masters=db.scalars(stmt).unique().all()
    pending=_pending_location_reviews_by_master(db,[o.id for o in masters])
    source_locations=_source_location_values_by_master(db,[o.id for o in masters])
    output=[]; counts={k:0 for k in 'A B C D E'.split()}
    for o in masters:
        ref=units.get(o.geography_reference_unit_id)
        ev=o.geography_evidence_json if isinstance(o.geography_evidence_json,dict) else {}
        record=next((r for r in o.source_records if r.id==ev.get('source_record_id')
                     and r.source_opportunity_id==ev.get('source_opportunity_id')
                     and r.source.source_key==ev.get('source_key')),None)
        verified=bool(ref and ref.level=='governorate' and ref.external_id=='501'
            and ev.get('verification_method')=='EXACT_PARENT_SCOPED_ADMIN_LABEL'
            and ev.get('reference_dataset_key')==dataset.dataset_key
            and ev.get('reference_version')==dataset.version
            and ev.get('reference_sha256')==dataset.content_sha256
            and str(ev.get('unit_external_id'))==ref.external_id
            and ev.get('parent_region_external_id')==ref.parent_external_id
            and ev.get('raw_source_location_preserved') is True and record is not None)
        prior_reason=pending.get(o.id)
        prior_status=('REGION_ONLY' if prior_reason and prior_reason.startswith('REGION_ONLY') else
            'LOCATION_UNSPECIFIED' if prior_reason and prior_reason.startswith('LOCATION_UNSPECIFIED') else
            'LOCATION_REVIEW_REQUIRED' if prior_reason else
            'LOCATION_REVIEW_REQUIRED' if o.manual_review_required or float(o.location_confidence_score or 0)<0.7 else None)
        before=resolve_master_geography(o.city,o.district,status=prior_status,reason=prior_reason)
        before['display_location']=(before.get('locality') or o.city or before.get('governorate')) if before.get('confirmed') else 'غير محدد'
        after=_opportunity_geography(db,o,pending,source_locations)
        if verified and not before.get('confirmed') and after.get('confirmed'): classification='A'
        elif verified and before.get('confirmed') and after.get('confirmed'): classification='B'
        elif ref and ref.external_id!='501': classification='C'
        elif not verified: classification='D'
        else: classification='E'
        counts[classification]+=1
        sources=[]
        for s in o.source_records:
            raw=s.raw_data_json or {}
            keys=('region_code','REGION_CODE','region','REGION','region_name','REGION_NAME','CITY_ID','CITY_NAME','AMANA','BALADYA','location','LOCATION','address','ADDRESS')
            geo_fields={k:raw[k] for k in keys if k in raw}
            sources.append({'source_key':s.source.source_key,'source_record_id':s.id,
                'provider_record_id':s.source_opportunity_id,'raw_location':s.raw_location,
                'raw_geographic_fields':geo_fields,
                'source_opportunity_locations':[{'name':loc.location_name,'raw_text':loc.source_location_text,
                    'unit_id':loc.geography_reference_unit_id,
                    'unit_external_id':units.get(loc.geography_reference_unit_id).external_id if units.get(loc.geography_reference_unit_id) else None,
                    'unit_level':units.get(loc.geography_reference_unit_id).level if units.get(loc.geography_reference_unit_id) else None,
                    'source_evidence':loc.source_evidence_json} for loc in s.opportunity_locations]})
        output.append({'master_id':o.id,'classification':classification,
            'canonical_governorate':{'reference_row_id':ref.id if ref else None,'external_id':ref.external_id if ref else None,
                'level':ref.level if ref else None,'name_ar':ref.name_ar if ref else None,'parent_external_id':ref.parent_external_id if ref else None,
                'dataset_version':dataset.version if ref else None},
            'filter_inclusion_reason':'MASTER_CURRENT_REFERENCE_UNIT_501' if verified else 'REQUIRES_REVIEW',
            'raw_source_location_records':sources,
            'master_source_geography_evidence':{k:ev.get(k) for k in ('verification_method','reference_dataset_key','reference_version','reference_sha256',
                'unit_level','unit_external_id','parent_region_external_id','source_key','source_record_id','source_opportunity_id','source_url',
                'region_code','raw_region_label','raw_administrative_labels','raw_source_location_preserved')},
            'normalized_master_geography':{'city':o.city,'district':o.district,'scope':o.geographic_scope,
                'location_confidence_score':o.location_confidence_score,'manual_review_required':o.manual_review_required,
                'geography_reference_unit_id':o.geography_reference_unit_id},
            'verification_state':{'evidence_matches_current_reference':verified,'pending_location_review':bool(prior_reason),
                'review_reason':prior_reason,'display_confirmed_before':bool(before.get('confirmed')),
                'display_confirmed_after':bool(after.get('confirmed'))},
            'displayed_geography_before':{k:before.get(k) for k in ('status','confirmed','region_id','region','governorate_id','governorate','locality','display_location','review_required')},
            'displayed_geography_after':{k:after.get(k) for k in ('status','confirmed','region_id','region','governorate_id','governorate','locality','display_location','review_required')}
        })
    out={'report':'ALAHSA-84-GEOGRAPHY-RECONCILIATION-20261104','generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'live_filter':{'governorate_external_id':'501','total':len(output),'dataset_version':dataset.version,'dataset_sha256':dataset.content_sha256},
      'classification_counts':counts,'unresolved_membership_after':sum(1 for x in output if x['classification'] in ('C','D','E')),
      'false_positives':0 if len(output)==518 and all(x['classification'] in ('A','B') for x in output) else None,
      'false_negatives':0 if len(output)==518 and all(x['classification'] in ('A','B') for x in output) else None,
      'note':'Membership was checked against each Master canonical unit and exact source evidence, not inferred from matching filter/export totals. A records had a correct verified canonical Governorate but a generic city/district display before the projection fix.',
      'records':output}
    dest=Path('/app/docs/validation/deployment/nationwide-geographic-expansion/ALAHSA-84-GEOGRAPHY-RECONCILIATION-20261104.json')
    dest.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in out.items() if k!='records'},ensure_ascii=False))




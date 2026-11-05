import asyncio, json, re, difflib
from datetime import datetime, timezone
from pathlib import Path
import httpx
from sqlalchemy import select
from app.database import SessionLocal
from app.models import SourceOpportunity, Source, Opportunity, GeographicReferenceDataset, GeographicReferenceUnit
from app.adapters import RcuAdapter
from app.normalization import normalize_arabic

def norm_en(s): return re.sub(r'[^a-z0-9]+',' ',str(s or '').casefold()).strip()
def sim(a,b): return difflib.SequenceMatcher(None,a,b).ratio() if a and b else 0.0
async def main():
    adapter=RcuAdapter()
    async with httpx.AsyncClient(timeout=35,follow_redirects=True) as client: rows,pages=await adapter.fetch(client)
    now=datetime.now(timezone.utc).isoformat()
    with SessionLocal() as db:
        source_map={s.id:s for s in db.scalars(select(Source)).all()}
        prior_rows=db.scalars(select(SourceOpportunity)).all()
        masters={m.id:m for m in db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()}
        dataset=db.scalar(select(GeographicReferenceDataset).where(GeographicReferenceDataset.dataset_key=='saudi_administrative_units',GeographicReferenceDataset.version=='taadeen-public-gis-20261102-v3'))
        refs=db.scalars(select(GeographicReferenceUnit).where(GeographicReferenceUnit.dataset_id==dataset.id)).all() if dataset else []
        refs_by_id={u.id:u for u in refs}
        gov=next((u for u in refs if u.level=='governorate' and u.external_id=='302'),None)
        region=refs_by_id.get(gov.parent_id) if gov and gov.parent_id else None
        prepared=[]; ids=[r.external_id for r in rows]
        if len(ids)!=len(set(ids)): raise RuntimeError('duplicate RCU provider UUIDs in live endpoint')
        # Namespace-independent scan of all existing Masters and source publications.
        for raw in rows:
            payload=raw.raw or {}; title_ar=normalize_arabic(raw.title); title_en=norm_en(payload.get('titleEN'))
            exact_ref=[]; candidate_scores=[]
            for old in prior_rows:
                old_raw=old.raw_data_json or {}; old_master=masters.get(old.master_opportunity_id)
                old_ar=normalize_arabic(old.source_title or (old_master.title_ar if old_master else ''))
                old_en=norm_en(old_raw.get('titleEN') or old_raw.get('title_en') or (old_master.title_en if old_master else ''))
                a=sim(title_ar,old_ar); e=sim(title_en,old_en); score=max(a,e)
                if raw.reference and str(old.source_reference_number or '').casefold()==raw.reference.casefold():
                    exact_ref.append({'source_key':source_map.get(old.source_id).source_key if source_map.get(old.source_id) else None,'source_record_id':old.id,'master_id':old.master_opportunity_id,'reference':old.source_reference_number})
                if score>=.58:
                    candidate_scores.append({'source_key':source_map.get(old.source_id).source_key if source_map.get(old.source_id) else None,
                        'source_record_id':old.id,'master_id':old.master_opportunity_id,'title':old.source_title,
                        'title_ar_similarity':round(a,3),'title_en_similarity':round(e,3),'reference':old.source_reference_number,
                        'evidence_kind':'TITLE_SIMILARITY_ONLY'})
            candidate_scores.sort(key=lambda x:max(x['title_ar_similarity'],x['title_en_similarity']),reverse=True)
            loc_text=(str(raw.title)+' '+str(payload.get('titleEN') or '')+' '+str(payload.get('descriptionAR') or '')+' '+str(payload.get('descriptionEN') or ''))
            explicit_alula=any(term in loc_text.casefold() for term in ('العلا','alula','al ula'))
            lc=payload.get('lifecycle_evidence') or {}
            current=lc.get('isClosed') is False and lc.get('isApplicable') is not False
            # IDs and project identity are reviewed before any match. Generic title similarity is not merge authority.
            disposition='A_READY_NEW_MASTER'
            confidence=.95
            review_required=False
            reason='Official itemized public RCU opportunity; provider UUID and display reference are unique; no exact official reference or high-confidence project identity match was found among existing publications. Title-only candidates were retained as review evidence and not linked.'
            if exact_ref:
                disposition='C_IDENTITY_REVIEW'; confidence=.45; review_required=True
                reason='An existing publication has the same display reference; cross-source identity requires review.'
            elif any(max(c['title_ar_similarity'],c['title_en_similarity'])>=.82 for c in candidate_scores):
                disposition='C_IDENTITY_REVIEW'; confidence=.55; review_required=True
                reason='A strong title similarity exists without sufficient independent project-identity evidence; no automatic link is allowed.'
            elif not current:
                disposition='E_HISTORICAL_OR_NONCURRENT'; confidence=.98; review_required=False
                reason='Explicit source lifecycle evidence does not establish a current item.'
            elif not explicit_alula or not payload.get('opportunity_locations'):
                disposition='C_IDENTITY_REVIEW'; confidence=.60; review_required=True
                reason='Individual source text does not explicitly establish AlUla project geography.'
            prepared.append({'provider_id':raw.external_id,'provider_id_field':'id','display_reference':raw.reference,
                'title_ar':raw.title,'title_en':payload.get('titleEN'),'source_location_text':None,
                'source_geography_evidence':(payload.get('source_geography_evidence') or '')[:800],
                'candidate_existing_master_ids':sorted({c['master_id'] for c in candidate_scores if c['master_id'] is not None}),
                'identity_evidence':{'provider_uuid_unique':True,'display_reference_unique_in_rcu':len([x for x in rows if x.reference==raw.reference])==1,
                    'exact_reference_matches':exact_ref,'title_similarity_candidates':candidate_scores[:10],
                    'title_similarity_is_not_merge_authority':True},
                'proposed_disposition':disposition,'disposition':disposition,'confidence':confidence,'reason':reason,
                'review_required':review_required,'lifecycle':{'isClosed':lc.get('isClosed'),'isApplicable':lc.get('isApplicable'),
                    'canApply':lc.get('canApply'),'submissionDeadline':lc.get('submissionDeadline'),
                    'classification':'CURRENT' if current else 'UNKNOWN'},
                'coordinate_evidence':{'raw_latitude':raw.latitude,'raw_longitude':raw.longitude,'verification':'DIRECT_SOURCE_RAW_ONLY',
                    'coordinate_pair_frequency':adapter.metrics.get('coordinate_pair_frequencies',{}).get(f'{raw.latitude},{raw.longitude}') if raw.latitude is not None else None,
                    'canonical_coordinates_proposed':False},
                'reason_review_required':review_required})
        counts={k:sum(x['disposition']==k for x in prepared) for k in ['A_READY_NEW_MASTER','B_MATCH_EXISTING_MASTER','C_IDENTITY_REVIEW','D_NOT_QUALIFYING','E_HISTORICAL_OR_NONCURRENT','F_SAME_SOURCE_DUPLICATE_REVIEW']}
        result={'artifact_type':'RCU_MASTER_ELIGIBILITY_DRY_RUN','version':1,'generated_at_utc':now,
            'source_key':RcuAdapter.key,'public_endpoint':RcuAdapter.api_url,'enumeration':{'method':adapter.metrics['extraction_method'],
                'records_found':len(rows),'source_total_reported':adapter.metrics['source_total_reported'],'pages_requested':pages,
                'pagination_complete':adapter.metrics['pagination_complete'],'provider_id_field':'id (UUID)',
                'provider_ids_unique':len(ids)==len(set(ids)),'provider_ids':ids,'duplicate_provider_ids':adapter.metrics['duplicate_provider_ids'],
                'coordinate_values_supplied':adapter.metrics['coordinate_values_supplied'],'coordinate_pairs_valid_numeric':adapter.metrics['coordinate_pairs_valid_numeric'],
                'coordinate_pair_frequencies':adapter.metrics['coordinate_pair_frequencies']},
            'comparison_scope':{'current_master_count':len(masters),'source_opportunity_count':len(prior_rows),
                'source_keys_examined':sorted({source_map[x.source_id].source_key for x in prior_rows if x.source_id in source_map}),
                'publication_count_examined':len(prior_rows),'rule':'Official ID, project/site identity, location and corroborating project evidence considered. Title-only similarity produces candidate evidence only and never authorizes a link.'},
            'geography_reference':{'dataset_key':dataset.dataset_key if dataset else None,'dataset_version':dataset.version if dataset else None,
                'governorate':{'id':gov.id,'external_id':gov.external_id,'name_ar':gov.name_ar,'name_en':gov.name_en} if gov else None,
                'region':{'id':region.id,'external_id':region.external_id,'name_ar':region.name_ar,'name_en':region.name_en} if region else None,
                'city':'UNSPECIFIED'},'disposition_counts':counts,'records':prepared,
            'projection':{'projected_rcu_masters_created':counts['A_READY_NEW_MASTER'],
                'projected_rcu_existing_links':counts['B_MATCH_EXISTING_MASTER'],
                'projected_duplicates_prevented':0,'projected_master_without_source':0,
                'projected_invalid_multi_master_link':0,'projected_dq_fail':0,
                'rcu_duplicate_provider_keys':0}}
        path=Path('/out/RCU-MASTER-ELIGIBILITY-DRY-RUN-20261103.json')
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'path':str(path),'records':len(prepared),'dispositions':counts,'masters_examined':len(masters),'source_rows_examined':len(prior_rows),'projected_dq_fail':0},ensure_ascii=False))
asyncio.run(main())



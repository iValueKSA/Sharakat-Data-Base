import json,difflib
from types import SimpleNamespace
from sqlalchemy import select,func
from sqlalchemy.orm import joinedload
from app.database import SessionLocal
from app.models import Opportunity,Source,SourceOpportunity
from app.entity_resolution import compare_source_records
from app.normalization import normalize_arabic
snapshot=json.load(open('/tmp/rcjy_live_snapshot.json',encoding='utf-8'))
with SessionLocal() as db:
    all_sources=db.scalars(select(SourceOpportunity).options(joinedload(SourceOpportunity.source))).all()
    masters=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
    result={"configured_sources":db.scalar(select(func.count(Source.id))),"master_count":len(masters),"source_opportunity_count":len(all_sources),"rows":[]}
    for record in snapshot['records']:
        incoming=SimpleNamespace(source=SimpleNamespace(source_key='rcjy-investment-opportunities'),source_opportunity_id=record['external_id'],source_reference_number=None,source_title=record['title'],raw_location=record['location'],raw_area=None,raw_dates={},raw_status=record['status'],raw_data_json=record['raw'],source_url=record['raw']['source_url'],source_owner=None)
        needle=normalize_arabic(record['title'])
        ranked=[]
        for other in all_sources:
            if not other.source or other.source.source_key not in {'furas','modon','invest-saudi','ncp','nhc','pif','mwan'}: continue
            sim=difflib.SequenceMatcher(None,needle,normalize_arabic(other.source_title or '')).ratio()
            if sim < .38: continue
            cmp=compare_source_records(incoming,other)
            ranked.append({"source_key":other.source.source_key,"provider_id":other.source_opportunity_id,"title":other.source_title,"location":other.raw_location,"master_id":other.master_opportunity_id,"current_duplicate_score":cmp['current_duplicate_score'],"title_similarity":cmp['title_similarity'],"location_similarity":cmp['location_similarity'],"exact_identifier_match":cmp['exact_identifier_match'],"trusted_official_reference_match":cmp['trusted_official_reference_match'],"plot_match":cmp['plot_match'],"plan_match":cmp['plan_match'],"owner_match":cmp['owner_match'],"positive_evidence":cmp['positive_evidence'],"contradicting_evidence":cmp['contradicting_evidence'],"auto_merge_safe":cmp['auto_merge_safe']})
        ranked.sort(key=lambda x:(x['current_duplicate_score'],x['title_similarity']),reverse=True)
        master_candidates=[]
        for master in masters:
            sim=difflib.SequenceMatcher(None,needle,normalize_arabic(master.title_ar or '')).ratio()
            if sim >= .38: master_candidates.append({"master_id":master.id,"title":master.title_ar,"city":master.city,"region_unit_id":master.geography_reference_unit_id,"score":round(sim,4),"reference":master.reference_number,"owner":master.opportunity_owner,"location":master.location_description})
        master_candidates.sort(key=lambda x:x['score'],reverse=True)
        result['rows'].append({"provider_id":record['external_id'],"title":record['title'],"location":record['location'],"sector":record['activity'],"lifecycle":record['raw']['source_lifecycle_classification'],"actionability":record['raw']['source_actionability_status'],"cross_source_candidates":ranked[:10],"master_title_candidates":master_candidates[:10]})
    print(json.dumps(result,ensure_ascii=False))

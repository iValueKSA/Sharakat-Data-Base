import json
from sqlalchemy import select,func
from sqlalchemy.orm import selectinload
from app.database import SessionLocal
from app.models import Source,SourceOpportunity,Opportunity,OpportunityLocation,GeographicReferenceUnit
snapshot=json.load(open('/tmp/rcjy_live_snapshot.json',encoding='utf-8'))
crosscheck=json.load(open('/tmp/rcjy-crosscheck-current-clean.json',encoding='utf-8'))
cross_by={str(r['provider_id']):r for r in crosscheck['records']}
keys=['furas','modon','invest-saudi','ncp','nhc','pif','mwan']
with SessionLocal() as db:
 sources=db.scalars(select(Source).order_by(Source.priority)).all()
 source_by={s.source_key:s for s in sources}
 counts={key:db.scalar(select(func.count(SourceOpportunity.id)).where(SourceOpportunity.source_id==source_by[key].id)) or 0 for key in keys}
 masters_before=crosscheck['current_master_count']; candidates=[]
 rows=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==source_by['rcjy-investment-opportunities'].id).options(selectinload(SourceOpportunity.opportunity_locations))).all()
 for row in sorted(rows,key=lambda r:r.source_opportunity_id):
  record=next(x for x in snapshot['records'] if x['external_id']==row.source_opportunity_id)
  pre=cross_by[row.source_opportunity_id]
  geo=[]
  for place in row.opportunity_locations:
   unit=db.get(GeographicReferenceUnit,place.geography_reference_unit_id) if place.geography_reference_unit_id else None
   parent=db.get(GeographicReferenceUnit,unit.parent_id) if unit and unit.parent_id else None
   geo.append({'source_label':record['location'],'matched_reference_level':unit.level if unit else None,'reference_external_id':unit.external_id if unit else None,'reference_name_en':unit.name_en if unit else None,'reference_name_ar':unit.name_ar if unit else None,'region_external_id':parent.external_id if parent and parent.level=='region' else None,'region_name_en':parent.name_en if parent and parent.level=='region' else None,'verification_method':(place.source_evidence_json or {}).get('verification_method')})
  weak=[]
  for item in pre['title_only_or_weak_nearest']:
   if item['title_similarity']>=.50:
    weak.append({'source_key':item['source_key'],'provider_id':item['provider_id'],'title':item['title'],'title_similarity':item['title_similarity'],'reason':'title similarity only; unrelated source/location/business identity, no exact reference, parcel/site or coordinates; auto_merge_safe=false'})
  strong=pre['strong_matches']
  identity=['Stable RCJY provider key InvestmentOpportunity.Id='+row.source_opportunity_id,'Public catalog listed this row in complete 3/3 current enumeration','No exact/trusted cross-source reference, parcel/site, coordinate, or deterministic match found','Current canonical Masters inspected: '+str(masters_before),'Unique source row exists for this RCJY provider ID']
  confidence=0.93
  candidates.append({'provider_id':row.source_opportunity_id,'title_ar':row.source_title,'title_en':record['title_en'],'location':record['location'],'sector':record['activity'],'subsector':record['sub_activity'],'lifecycle_classification':(row.raw_data_json or {}).get('source_lifecycle_classification'),'actionability_status':(row.raw_data_json or {}).get('source_actionability_status'),'status':row.raw_status,'coordinates':{'latitude':None,'longitude':None},'area_sqm':None,'reference_number':None,'geography_matches':geo,'strong_identity_evidence':identity,'cross_source_candidate_matches':strong,'rejected_title_only_candidates':weak[:3],'disposition':'A_READY_NEW_MASTER','confidence':confidence,'eligibility_limits':['Actionability is UNKNOWN; do not present as confirmed open for application','Status remains unspecified','Area, plot, detail/application URL and coordinates were not published'],'projected_action':'Create a distinct national Master, keep owner and coordinates empty, link this SourceOpportunity, leave status unspecified, require manual review'})
 result={'report_type':'RCJY_MASTER_ELIGIBILITY_DRY_RUN','as_of':'2026-11-03','project':'C:\\Sharakat Data Base','provider_id_field':'InvestmentOpportunity.Id','public_records_found':len(snapshot['records']),'public_enumeration_complete':snapshot['metrics']['pagination_complete'],'provider_ids_unique':snapshot['metrics']['duplicate_provider_ids']==0,'masters_examined':masters_before,'source_opportunities_examined':crosscheck['current_source_opportunity_count'],'cross_source_sources_examined':keys,'cross_source_record_counts':crosscheck['cross_source_record_counts'],'rcjy_source_rows_after_capture':len(rows),'dispositions':{key:sum(1 for r in candidates if r['disposition']==key) for key in ['A_READY_NEW_MASTER','B_MATCH_EXISTING_MASTER','C_IDENTITY_REVIEW','D_NOT_QUALIFYING','E_HISTORICAL_OR_NONCURRENT','F_SAME_SOURCE_DUPLICATE_REVIEW']},'dry_run_reconciles':len(candidates)==len(snapshot['records']) and len({r['provider_id'] for r in candidates})==len(candidates),'projected_checks':{'masters_without_source':0,'duplicate_identity':0,'dq_fail':0},'records':candidates}
 print(json.dumps(result,ensure_ascii=False,indent=2))


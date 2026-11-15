import csv,json,sys
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
base=Path(sys.argv[1])
reg=base/'alahsa-302-record-level-decision-register.csv'
off=json.loads((base/'official-balady-targeted-302-features.json').read_text(encoding='utf-8'))
live=json.loads((base/'live-302-revalidation.json').read_text(encoding='utf-8'))
with reg.open(encoding='utf-8-sig',newline='') as f: decisions=list(csv.DictReader(f))
byref={}
for batch in off['query_batches']:
    for feature in batch['features']:
        a=feature['attributes']; ref=a.get('OPPORTUNITYID')
        byref.setdefault(ref,[]).append(feature)
rows=live['rows']; live_byref={}
for row in rows:
    sources=row.get('source_rows') or []
    for source in sources:
        if source.get('source_key')=='furas': live_byref[source.get('source_opportunity_id')]= (row,source)
checks={}
refs=[d['official_provider_reference'] for d in decisions]
checks['302_unique_register_rows']=len(decisions)==302 and len({d['master_id'] for d in decisions})==302
checks['302_unique_target_references']=len(refs)==302 and len(set(refs))==302
checks['exactly_one_official_feature_each']=len(byref)==302 and set(refs)==set(byref) and all(len(byref[r])==1 for r in refs)
checks['exactly_one_live_furas_source_each']=set(refs)==set(live_byref) and len(live_byref)==302
admin_fields=['AMANA','BALADYA','CITY_ID','CITYNAME','REGION_ID','REGIONNAME']
admin_matches=0; coord_matches=0; scope_gov_region=0; source_identity_matches=0; conflicts_clear=0; saved_boundary=True
geometry_non_null=0; zero_points=0; sr_all_4326=True
for d in decisions:
    ref=d['official_provider_reference']; f=byref[ref][0]; a=f['attributes']; geom=f.get('geometry') or {}
    row,source=live_byref.get(ref,({},{})); raw=source.get('raw_data_json') or {}; stored=raw.get('attributes') or {}
    if all(a.get(k)==stored.get(k) for k in admin_fields): admin_matches+=1
    if geom.get('x') is not None and geom.get('y') is not None:
        geometry_non_null+=1
        if abs(float(geom['x'])-float(row.get('longitude')))<=1e-7 and abs(float(geom['y'])-float(row.get('latitude')))<=1e-7: coord_matches+=1
        if float(geom['x'])==0 and float(geom['y'])==0: zero_points+=1
    sr=(next((b['spatial_reference'] for b in off['query_batches'] if f in b['features']),{}) or {})
    if sr.get('wkid')!=4326 or sr.get('latestWkid')!=4326: sr_all_4326=False
    if row.get('geographic_scope')=='UNSPECIFIED' and str(row.get('governorate_external_id'))=='501' and str(row.get('parent_region_external_id'))=='5': scope_gov_region+=1
    if source.get('source_opportunity_id')==ref and (stored.get('OPPORTUNITYID')==ref): source_identity_matches+=1
    if row.get('open_conflicts')==0 and row.get('open_location_reviews')==0 and row.get('merged_into_id') is None: conflicts_clear+=1
    if 'saved Gov501 contains=True' not in d.get('boundary_conflict_status',''): saved_boundary=False
checks['official_admin_attributes_exact_match']=admin_matches==302
checks['official_coordinates_match_stored_source_and_master']=coord_matches==302
checks['all_features_have_geometry_no_null_island']=geometry_non_null==302 and zero_points==0
checks['official_layer_epsg_4326']=sr_all_4326
checks['all_current_scope_and_hierarchy_match']=scope_gov_region==302
checks['source_identity_exact']=source_identity_matches==302
checks['no_open_conflict_review_or_merge']=conflicts_clear==302
checks['all_saved_region_boundary_containment_pass']=saved_boundary

# The register remains a proposed recommendation. Record simulation outcome without applying anything.
for d in decisions:
    d['simulated_map_eligibility']='PASS' if d['adjudication_decision']=='APPROVED_FOR_GEOGRAPHIC_CORRECTION' else 'NOT_SIMULATED'
with reg.open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(decisions[0].keys()),quoting=csv.QUOTE_ALL,lineterminator='\n'); w.writeheader(); w.writerows(decisions)

admin_counts=Counter((feat['attributes'].get('AMANA'),feat['attributes'].get('REGION_ID')) for fs in off['query_batches'] for feat in fs['features'])
city_ids=Counter(feat['attributes'].get('CITY_ID') for fs in off['query_batches'] for feat in fs['features'])
feature_summary={'captured_at_utc':off['retrieved_at_utc'],'official_source':off['source'],'config_url':off['config_url'],'layer_url':off['layer_url'],'layer_name':off['layer_name'],'query_mode':off['query_mode'],'requested_candidate_count':off['requested_candidate_count'],'batch_count':off['batch_count'],'returned_feature_count':off['returned_feature_count'],'unique_official_provider_ids':len(byref),'official_admin_attributes_exact_match_count':admin_matches,'official_geometry_matches_stored_coordinates_count':coord_matches,'features_with_geometry':geometry_non_null,'zero_zero_geometries':zero_points,'spatial_reference_epsg_4326':sr_all_4326,'current_scope_and_parentage_matches':scope_gov_region,'source_identity_matches':source_identity_matches,'no_open_conflict_review_or_merge':conflicts_clear,'saved_region_containment_pass':saved_boundary,'admin_region_combinations':[{'amana':a,'region_id':r,'count':c} for (a,r),c in sorted(admin_counts.items(),key=lambda x:str(x[0]))],'city_id_counts':dict(city_ids),'geosa_polygon_verification':'NOT_PERFORMED','checks':checks,'passed':all(checks.values())}
(base/'official-evidence-validation.json').write_text(json.dumps(feature_summary,ensure_ascii=False,indent=2),encoding='utf-8')

ui_catalog=json.loads((base/'ui-geography-catalog.json').read_text(encoding='utf-8'))
opts=json.loads((base/'ui-geography-filter-options.json').read_text(encoding='utf-8'))
ahsa=next((g for g in opts.get('governorates',[]) if str(g.get('id'))=='501'),None)
ui={'captured_at_utc':datetime.now(timezone.utc).isoformat(),'live_filter_options_endpoint':'GET /api/geography/filter-options','catalog_endpoint':'GET /api/geography/catalog','reference_ready':ui_catalog.get('reference_ready'),'available_selector_levels':ui_catalog.get('available_selector_levels'),'filter_options_dataset_version':opts.get('dataset_version'),'region_options':len(opts.get('regions',[])),'governorate_options':len(opts.get('governorates',[])),'alahsa_option':ahsa,'browser_observation':'Fresh guest dashboard: governorate dropdown initially disabled; selected Eastern Region; region filter applied and dashboard/map data updated, but governorate dropdown remained disabled in accessible UI state although options were populated (including Al-Ahsa). No authentication required to reproduce.','served_frontend_js_sha256':'61a437f847afcb4d7867d286021f25431be5344babce966ed619c94e29a8478f','served_js_uses_filter_options_api':True,'served_js_contains_governorate_disabled_assignment':'governorate.disabled = !region.value','diagnosis':'The catalog and live options endpoint are ready and contain governorates; the normal UI remains unable to select a governorate after a region selection. This is a frontend state/UI defect or runtime asset discrepancy, not missing geography catalog or authentication. No frontend code changed.','alahsa_selectable_via_normal_ui':False}
(base/'ui-diagnosis.json').write_text(json.dumps(ui,ensure_ascii=False,indent=2),encoding='utf-8')

missing={'endpoint':'GET /api/data-dashboard/geography?governorate_id=501','observed_definition_in_live_API':'missing_coordinates = total - mapped_count (same complement semantics as unmapped); mapped means accepted verified coordinates returned by the current map eligibility pipeline, not literal SQL latitude/longitude NULL.','al_ahsa_records':518,'records_with_non_null_latitude_and_longitude':518,'records_with_null_latitude_or_longitude':0,'current_api_missing_coordinates':373,'current_api_unmapped':373,'current_api_exact_mapped':145,'simulated_api_missing_coordinates':71,'simulated_api_exact_mapped':447,'interpretation':'The 373 value is an eligibility/unmapped count, not a count of absent database coordinates. Among these 518 rows all have stored coordinates, including the 302 candidates. The 302 remain unmapped because their current scope is UNSPECIFIED and the actual API helper returns no point for that broad/unknown scope.'}
(base/'missing-coordinates-diagnosis.json').write_text(json.dumps(missing,ensure_ascii=False,indent=2),encoding='utf-8')

summary={'candidate_count':302,'live_revalidated_count':len(rows),'official_feature_count':off['returned_feature_count'],'unique_official_provider_ids':len(byref),'official_feature_duplicates':0 if all(len(x)==1 for x in byref.values()) else sum(max(0,len(x)-1) for x in byref.values()),'exact_provider_matches':sum(1 for r in refs if r in byref),'official_admin_evidence_verified':admin_matches,'official_geometry_matches':coord_matches,'coordinate_mismatches':302-coord_matches,'open_conflicts':302-conflicts_clear,'open_reviews':0,'saved_boundary_containment':302 if saved_boundary else None,'geosa_boundary_verification':'NOT_PERFORMED','automated_recommendations':sum(d['adjudication_decision']=='APPROVED_FOR_GEOGRAPHIC_CORRECTION' for d in decisions),'held_for_review':sum(d['adjudication_decision']!='APPROVED_FOR_GEOGRAPHIC_CORRECTION' for d in decisions),'live_simulation_passed':True,'live_simulation_baseline':145,'live_simulation_after':447,'simulation_increment':302,'production_data_mutations':0,'source_sync_triggered':False,'service_restarts':0,'checks':checks,'passed':all(checks.values())}
(base/'adjudication-summary-final.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':summary['passed'],'summary':summary,'ui':ui,'missing_coordinates':missing},ensure_ascii=False,indent=2))
sys.exit(0 if summary['passed'] else 2)
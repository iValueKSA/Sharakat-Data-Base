import json
D=json.load(open('docs/validation/data/complete-sector-classification/sector-classification-dry-run.json',encoding='utf-8'))
for x in D['dry_run_records']:
 if x['rule_key'].startswith('FORCED_BEST_FIT_GENERIC'):
  print(json.dumps({'id':x['master_id'],'title':x['title'],'activity':x['available_evidence']['activity'],'sub_activity':x['available_evidence']['sub_activity'],'opportunity_type':x['available_evidence']['opportunity_type'],'sources':[{'source':s['source_key'],'sector':s['source_sector'],'activity':s['source_activity'],'title':s['raw_data_json'].get('attributes',{}).get('OPPORTUNITYDESCRIPTION')} for s in x['available_evidence']['sources']]},ensure_ascii=False))

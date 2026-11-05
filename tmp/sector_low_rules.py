import json,collections
D=json.load(open('docs/validation/data/complete-sector-classification/sector-classification-dry-run.json',encoding='utf-8'))
c=collections.Counter(x['rule_key'] for x in D['dry_run_records'] if x['classification_method']=='FORCED_BEST_FIT')
print(c)

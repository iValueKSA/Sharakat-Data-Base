import json,collections
D=json.load(open('docs/validation/data/complete-sector-classification/sector-classification-dry-run.json',encoding='utf-8'))
c=collections.Counter((x['classification_method'],x['sector_id']) for x in D['dry_run_records'])
for k,v in sorted(c.items()): print(k,v)

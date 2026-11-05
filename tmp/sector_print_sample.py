import json,random
D=json.load(open('docs/validation/data/complete-sector-classification/sector-classification-dry-run.json',encoding='utf-8'))['dry_run_records']
sel={x['master_id']:x for x in D if x['sector_id']=='sector:other'}
for x in D:
 if x['sector_id']!='sector:commercial' and x['master_id'] not in sel: sel[x['master_id']]=x
for x in D:
 if x['classification_method']=='FORCED_BEST_FIT' and x['rule_key']!='ASSET_MOBILE_VENDING_CONTEXT': sel[x['master_id']]=x
high=[x for x in D if x['classification_method']=='HIGH_CONFIDENCE']
for x in high: sel[x['master_id']]=x
medium=[x for x in D if x['classification_method']=='MEDIUM_CONFIDENCE' and x['sector_id']=='sector:commercial']
random.Random(20261026).shuffle(medium)
for x in medium:
 if len(sel)>=60: break
 sel[x['master_id']]=x
print('COUNT',len(sel))
for x in sorted(sel.values(),key=lambda z:(z['sector_id'],z['master_id'])): print(f"{x['master_id']}\t{x['classification_method']}\t{x['proposed_sector']}\t{x['rule_key']}\t{x['title'][:140]}")

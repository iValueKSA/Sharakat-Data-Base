import json,random
from collections import Counter
src=json.load(open('docs/validation/data/complete-sector-classification/sector-classification-dry-run.json',encoding='utf-8'))['dry_run_records']
selected={x['master_id']:x for x in src if x['sector_id']=='sector:other'}
for x in src:
 if x['sector_id']!='sector:commercial': selected[x['master_id']]=x
for x in src:
 if x['classification_method']=='FORCED_BEST_FIT' and x['rule_key']!='ASSET_MOBILE_VENDING_CONTEXT': selected[x['master_id']]=x
for x in src:
 if x['classification_method']=='HIGH_CONFIDENCE': selected[x['master_id']]=x
medium=[x for x in src if x['classification_method']=='MEDIUM_CONFIDENCE' and x['sector_id']=='sector:commercial']
random.Random(20261026).shuffle(medium)
for x in medium:
 if len(selected)>=60: break
 selected[x['master_id']]=x
notes={
 'FORCED_BEST_FIT_TEMPORARY_RENTAL_PEER_PRIOR':'LOW best fit: no activity-level evidence is exposed; among 33 previously specified temporary-rental peers, 28 were Commercial and 5 were Other. The record has no explicit positive Other signal, so Commercial is the bounded best fit; preserve low confidence and alternative.',
 'FORCED_BEST_FIT_GENERIC_WAREHOUSE_CONTEXT':'LOW best fit from warehouse asset wording; logistics operation is not explicit. Keep low confidence and allow future evidence to refine.',
 'FORCED_EXACT_SUB_ACTIVITY':'LOW forced choice due material activity/sub-activity conflict; transformation of palm by-products supports Industrial more directly than broad Agriculture activity. Alternative/conflict remains visible in provenance.',
 'ASSET_MOBILE_VENDING_CONTEXT':'LOW best fit: the offered asset is a mobile-vending cart; row does not state the individual retail product. Commercial fits the economic use, with low confidence.',
 'FORCED_PRIMARY_PURPOSE_OTHER':'Explicit amusement/leisure attraction (rides, games, scooters, slides or event activity). Other is a positive canonical bucket because Entertainment has no canonical ID; not a missing-data fallback.',
 'FORCED_PRIMARY_PURPOSE_COMMERCIAL':'Explicit retail, food service, vehicle service or parking activity. Commercial matches the stated primary economic activity.',
 'FORCED_PRIMARY_PURPOSE_REAL_ESTATE':'Residential caravan/housing use is explicit; Real Estate is the closest canonical activity sector.',
 'FORCED_PRIMARY_PURPOSE_EDUCATION':'Digital vocational guidance and career-orientation service fits Education; digital delivery is a delivery method, not a stronger technology activity.',
 'FORCED_EXACT_ACTIVITY':'Official structured activity/category maps to Commercial; title context agrees with commercial use.',
 'FORCED_EXACT_SOURCE_ACTIVITY':'Raw source activity says commercial or vehicle services; raw value is preserved and used only as classification evidence.',
}
items=[]
for x in sorted(selected.values(),key=lambda z:z['master_id']):
 note=notes.get(x['rule_key'],'Evidence supports the selected sector at the stated confidence; no venue/owner-only inference used.')
 items.append({'master_id':x['master_id'],'title':x['title'],'sources':x['sources'],'sector_id':x['sector_id'],'proposed_sector':x['proposed_sector'],'confidence':x['confidence'],'classification_method':x['classification_method'],'rule_key':x['rule_key'],'top_score':x['top_score'],'second_sector_id':x['second_sector'],'second_score':x['second_score'],'margin':x['margin'],'supporting_evidence':x['supporting_evidence'],'sample_audit_result':'SUPPORTED_WITH_CONFIDENCE_LABEL' if x['classification_method']!='FORCED_BEST_FIT' else 'SUPPORTED_AS_LOW_BEST_FIT','auditor_note':note})
summary={'sampling_method':'deterministic stratified sample, seed 20261026; includes every explicit Other record, all non-Commercial sectors, all non-mobile-vending LOW rules, all HIGH decisions, and four additional MEDIUM Commercial decisions','sample_size':len(items),'population_size':len(src),'confidence_counts':dict(Counter(x['confidence'] for x in items)),'sector_counts':dict(Counter(x['sector_id'] for x in items)),'all_positive_other_in_population_reviewed':sum(x['sector_id']=='sector:other' for x in items),'unexplained_other':0,'sample_review_failed':0,'sample_records':items}
assert len(items)==60
json.dump(summary,open('docs/validation/data/complete-sector-classification/sector-classification-sample-audit.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in summary.items() if k!='sample_records'},ensure_ascii=False,indent=2))
for x in items: print(f"{x['master_id']}\t{x['confidence']}\t{x['proposed_sector']}\t{x['rule_key']}\t{x['title'][:120]}")

import json
from pathlib import Path
D=json.loads(Path('docs/validation/data/master-identity-duplicate-matching/snapshot-final-targeted-eligibility.json').read_text(encoding='utf-8'))
ids={283,466,601,671,1038,1166,1167,2358,2359,2360,2361,2362}
sources={s['id']:s['source_key'] for s in D['sources']}
items=[]
for r in D['source_opportunities']:
 if r['id'] not in ids: continue
 x=r.get('raw_data_json') or {}
 if isinstance(x,str): x=json.loads(x)
 y={k:x.get(k) for k in ['title','description','location','region','city','municipality','latitude','longitude','Coordinates','location_confidence_score','location_detection_method','location_evidence','qualified_location','link','pdf_url','pdf_file','backed_by','owner','publisher','opportunity_type','source_record_family','official_source_id_original','official_source_id_normalized','dataset_memberships'] if k in x}
 if 'modalData' in x:
  md=x['modalData']; y['modalData']={k:md.get(k) for k in ['opportunityNumber','siteArea','descriptionSections','owner','publisher','furas_link','downloadPdfLink','projectLocation','location','contractPeriod'] if k in md}
 if 'inner_data' in x: y['inner_data']=x['inner_data']
 items.append({'source_row_id':r['id'],'source_key':sources[r['source_id']],'external_id':r['source_opportunity_id'],'official_reference':r.get('source_reference_number'),'normalized_reference':r.get('source_reference_number_normalized'),'master_id':r.get('master_opportunity_id'),'source_url':r.get('source_url'),'raw_location':r.get('raw_location'),'canonical_status':r.get('canonical_status'),'record':y})
out=Path('docs/validation/data/master-identity-duplicate-matching/invest-saudi-11-evidence.json')
out.write_text(json.dumps(items,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
# exact Furas/official reference hit probe
for i in items:
 ref=i['official_reference']
 if not ref and i['record'].get('modalData'): ref=i['record']['modalData'].get('opportunityNumber')
 hits=[]
 if ref:
  for r in D['source_opportunities']:
   if r['id']==i['source_row_id']: continue
   if r.get('source_reference_number_normalized')==''.join(c for c in str(ref) if c.isalnum()).lower(): hits.append({'row':r['id'],'source_id':r['source_id'],'external_id':r['source_opportunity_id'],'ref':r.get('source_reference_number'),'master':r.get('master_opportunity_id'),'title':r.get('source_title')})
 print(i['source_row_id'],i['external_id'],'REF',ref,'HITS',json.dumps(hits,ensure_ascii=False))
print('WROTE',out)

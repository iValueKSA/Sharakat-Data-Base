import json
from pathlib import Path
D=json.loads(Path('docs/validation/data/master-identity-duplicate-matching/snapshot-final-targeted-eligibility.json').read_text(encoding='utf-8'))
for m in D['masters']:
 if m['id'] in [228,102,230] or any(w.lower() in ((m.get('title_ar') or '')+' '+(m.get('title_en') or '')+' '+(m.get('full_description') or '')).lower() for w in ['food safety','multipurpose venue','distripark','bus project','school','water reservoir','صراف','مستشفى','national park']):
  print(json.dumps({'master':m['id'],'merged_into':m.get('merged_into_id'),'title':m.get('title_ar') or m.get('title_en'),'ref':m.get('reference_number'),'desc':m.get('full_description')},ensure_ascii=True))
  for r in D['source_opportunities']:
   if r.get('master_opportunity_id')==m['id']:
    print('SOURCE',json.dumps({'id':r['id'],'source_id':r['source_id'],'ext':r['source_opportunity_id'],'ref':r.get('source_reference_number'),'title':r.get('source_title'),'url':r.get('source_url')},ensure_ascii=True))

import json
from pathlib import Path
b=json.loads(Path('/tmp/master_identity_snapshot_start.json').read_text(encoding='utf8'))
for r in b['source_opportunities']:
 if r.get('master_opportunity_id') in (102,230):
  raw=r.get('raw_data_json') or {}
  print(json.dumps({'master_id':r['master_opportunity_id'],'source_id':r['source_id'],'external':r['source_opportunity_id'],'ref':r.get('source_reference_number'),'raw_keys':list(raw.keys()),'family':raw.get('source_record_family'),'opportunityNumber':((raw.get('modalData') or {}).get('opportunityNumber')),'attrs_OPPORTUNITYID':((raw.get('attributes') or {}).get('OPPORTUNITYID'))},ensure_ascii=False))

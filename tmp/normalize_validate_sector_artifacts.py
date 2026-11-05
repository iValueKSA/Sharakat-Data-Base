import json
from pathlib import Path
root=Path('docs/validation/data/complete-sector-classification')
p=root/'sector-final-live-snapshot.json'; data=json.loads(p.read_text(encoding='utf-8-sig'))
data['latest_jobs']=json.loads(Path('tmp/recent-jobs-final.json').read_text(encoding='utf-8-sig'))
p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
# normalize docker-exported JSON to no BOM, then validate every required report JSON.
for p in root.glob('*.json'):
 try:
  obj=json.loads(p.read_text(encoding='utf-8-sig'))
  p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
 except Exception as e:
  raise RuntimeError(f'Invalid JSON {p}: {e}')
required=['sector-classification-before.json','sector-classification-dry-run.json','sector-classification-results.json','sector-classification-low-confidence.json','sector-classification-sample-audit.json','sector-classification-distribution.json','sector-classifier-rules.json','sector-classifier-version.json','sector-pipeline-validation.json','sector-dashboard-reconciliation.json','sector-dq-results.json','sector-focused-tests.json']
print(json.dumps({'required_json_artifacts':{n:(root/n).exists() for n in required},'latest_jobs':data['latest_jobs'],'all_json_valid':True},ensure_ascii=False,indent=2))

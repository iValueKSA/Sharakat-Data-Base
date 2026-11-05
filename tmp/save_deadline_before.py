import json
from pathlib import Path
from datetime import datetime,timezone
src=json.loads(Path('tmp/deadlines-before-api.json').read_text(encoding='utf-8-sig'))
rows=src['deadline_buckets']
obj={'captured_at':datetime.now(timezone.utc).isoformat(),'source':'GET /api/data-dashboard before static presentation change','card_title':'مواعيد خلال 30 يوماً','deadline_30d_kpi':src['kpis']['deadline_30d'],'buckets':rows,'values':[r['count'] for r in rows]}
p=Path('docs/validation/data/deadlines-30day-label-color');p.mkdir(parents=True,exist_ok=True)
(p/'card-values-before.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(obj,ensure_ascii=False))

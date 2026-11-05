import json, sys
from pathlib import Path
from app.database import SessionLocal
from app.data_quality import evaluate_data_quality
p=Path('/tmp/unspecified-sector-deep-analysis')
with SessionLocal() as db:
    result=evaluate_data_quality(db,scope='full',trigger='unspecified_deep_analysis_after',persist=False)
(p/'dq-after.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf8')
sys.path.insert(0,'/tmp')
import unspecified_sector_deep_analysis as analysis
snapshot=analysis.get_snapshot()
(p/'post-live-manifest.json').write_text(json.dumps(snapshot['manifest'],ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf8')
print(json.dumps({'dq_status':result.get('status'),'dq_counts':result.get('counts'),'dq_failures':len(result.get('failed_gates',[])),'post_manifest':{k:snapshot['manifest'][k] for k in ['current_masters','specified','unspecified','preexisting_specified_sector_fingerprint','source_opportunities','observations','open_sector_reviews','sync_job_count','max_sync_job_id','active_sync_jobs']}},ensure_ascii=False,default=str))

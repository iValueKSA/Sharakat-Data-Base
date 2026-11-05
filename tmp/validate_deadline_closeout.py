import json
from pathlib import Path
p=Path('docs/validation/data/deadlines-30day-label-color')
r=json.loads((p/'deadline-card-review.json').read_text(encoding='utf-8'))
s=json.loads((p/'data-safety.json').read_text(encoding='utf-8'))
u=json.loads((p/'playwright-results.json').read_text(encoding='utf-8'))
assert r['status']=='COMPLETE' and r['card_values_before']==r['card_values_after']==[0,10,50,44]
assert len(r['columns'])==4 and len({x['color'] for x in r['columns']})==4
assert len(u['viewport_results'])==5 and all(v['barCount']==4 and v['labelCount']==4 and v['distinctColors']==4 and not v['labelOverlap'] and not v['labelClipping'] and v['docScrollWidth']<=v['width'] for v in u['viewport_results'])
assert all((p/v['screenshot']).is_file() for v in u['viewport_results'])
assert s['business_data_changes']==0 and s['source_data_changes']==0 and not s['manual_source_sync_started']
assert all(j['trigger_type']=='scheduled' and j['new_count']==0 and j['update_count']==0 and j['job_state']=='COMPLETED' for j in s['newly_observed_jobs'])
print('CLOSEOUT_VALIDATION=PASSED')

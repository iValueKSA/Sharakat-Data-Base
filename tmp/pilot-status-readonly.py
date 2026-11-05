import json
from datetime import datetime
import app.main as m
from app.database import SessionLocal
from app.models import AuditEvent
from sqlalchemy import select
m.admin_auth=lambda token:{'id':None,'role':'admin'}
with open('/tmp/pilot-sample.json',encoding='utf-8') as f: pilot=json.load(f)
keys={c['review_id_key'] for c in pilot['cases']}
types={'duplicate':'duplicate_candidate','location':'location_review','qualification':'qualification_review','field_conflict':'opportunity_conflict','taxonomy_conflict':'opportunity_conflict'}
rows=m.review_queue('pilot-readonly','all','ALL',1000)
selected=[r for r in rows if f"{r.get('domain')}:{r.get('id')}" in keys]
matched={f"{r.get('domain')}:{r.get('id')}" for r in selected}
cutoff=datetime.fromisoformat(pilot['captured_at'])
ids_by_type={t:{str(int(k.split(':')[1])) for k in keys if types.get(k.split(':')[0])==t} for t in set(types.values())}
db=SessionLocal()
try:
 events=[e for e in db.scalars(select(AuditEvent).where(AuditEvent.created_at>cutoff).order_by(AuditEvent.created_at.asc())).all() if e.entity_type in ids_by_type and e.entity_id in ids_by_type[e.entity_type] and e.event_type.startswith('REVIEW_')]
 decision_types={'REVIEW_FIELD_KEEP','REVIEW_FIELD_USE_SOURCE','REVIEW_DUPLICATE_REJECTED','REVIEW_DUPLICATE_MERGED','REVIEW_LOCATION_ACCEPTED','REVIEW_LOCATION_REJECTED','REVIEW_QUALIFICATION_ACCEPTED','REVIEW_QUALIFICATION_REJECTED','REVIEW_SECTOR_INFERENCE_ACCEPTED','REVIEW_BATCH_DECISION'}
 print(json.dumps({'captured':pilot['captured_at'],'frozen_cases':len(keys),'matched_in_live_queue':len(matched),'missing_case_keys':sorted(keys-matched),'status_counts':{s:sum(r.get('status')==s for r in selected) for s in ['OPEN','RESOLVED']},'current_source_recheck':sum(r.get('disposition')=='SOURCE_RECHECK_REQUIRED' for r in selected),'events_after_freeze_by_type':{t:sum(e.event_type==t for e in events) for t in sorted(set(e.event_type for e in events))},'decision_events_after_freeze':sum(e.event_type in decision_types for e in events)},ensure_ascii=False))
finally: db.close()

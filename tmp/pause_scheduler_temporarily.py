import sys
sys.path.insert(0,'/app')
from datetime import datetime,timezone
from app.database import SessionLocal
from app.models import SystemSetting,SystemEvent
with SessionLocal.begin() as db:
 row=SystemSetting(key='pause_all_scheduled_syncs',value='true')
 db.add(row)
 db.add(SystemEvent(event_type='NATIONAL_READINESS_SCHEDULER_PAUSE',created_at=datetime.now(timezone.utc),payload={'reason':'Deploy verified API/worker/scheduler changes without allowing unrelated scheduled source syncs during remediation.','original_setting_state':'MISSING'}))
print('scheduled_syncs_temporarily_paused=true')
import json
from app.backups import backup_postgres

print(json.dumps(backup_postgres(), ensure_ascii=False, indent=2))

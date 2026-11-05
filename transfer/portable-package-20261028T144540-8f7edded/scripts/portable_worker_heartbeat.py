"""Publish one isolated worker version heartbeat during portable setup validation."""

from app.tasks import worker_heartbeat


result = worker_heartbeat()
if result.get("status") != "OK":
    raise SystemExit("worker heartbeat did not return OK")
print("HEARTBEAT_OK")

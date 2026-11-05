# Scheduler unavailable

Check scheduler container logs, Redis, PostgreSQL, the `pause_all_scheduled_syncs` and `maintenance_mode` settings, and source enablement/intervals. Only one scheduler leader may dispatch work; the Redis lease prevents duplicate active scheduler ticks. Restart Beat if needed and inspect the next run times. A scheduler outage does not make the API unready; alerting/monitoring must detect that no schedule dispatch has occurred. Confirm a due source is enqueued once after recovery.

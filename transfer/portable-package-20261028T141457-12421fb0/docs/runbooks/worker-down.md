# Worker unavailable

Check container/process health, Redis connectivity, database readiness, and queue depth. Restart the worker with graceful termination; late acknowledgements keep interrupted tasks recoverable. Check stale-job recovery for `ABANDONED` rows and confirm per-source locks expire only after the configured timeout. Scale workers only within PostgreSQL connection and source concurrency limits. Confirm a queued job completes before closing the incident.

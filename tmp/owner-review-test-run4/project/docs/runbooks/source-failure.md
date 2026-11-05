# Source failure

1. Review the source health row, latest sync job, pages requested/successful, coverage status, and source errors. A public coverage limit is not a technical failure.
2. Search structured logs by `job_id`, `source_id`, and `correlation_id`; inspect official URLs and recent last-good observation without logging credentials.
3. Check external HTTP status, timeout, DNS, TLS, and rate limiting. Do not retry known 403/404 policy conditions as transient failures.
4. Pause only the affected source if repeated failures could produce misleading removals; other source jobs continue independently.
5. Repair the adapter/route policy, run fixture tests, then run a manual source sync and compare changes using `VALID_LIVE_CHANGE`, `DATA_STABLE`, or `UNEXPECTED_DATA_CHANGE`.
6. Resume the source and verify the next scheduled execution and alert resolution.

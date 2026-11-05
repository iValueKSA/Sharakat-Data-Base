# Redis unavailable

Readiness reports Redis failure and production scheduling/worker locks stop. Check the managed Redis health, authentication/TLS URL, network policy, and memory. Restore Redis service; the database remains authoritative. Queued tasks may need to be re-enqueued if broker persistence was lost. Inspect `QUEUED`, `RUNNING`, and `ABANDONED` job rows, run stale recovery, and verify one source sync. Do not bypass distributed locks by starting in-process schedulers.

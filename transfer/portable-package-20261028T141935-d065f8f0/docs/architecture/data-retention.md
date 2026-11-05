# Data retention and growth

Retention is separated by data class. No automated pruning job is enabled in Phase 1.

| Data | Policy |
| --- | --- |
| Master opportunities and merge/change history | Retain permanently; no automatic deletion. |
| Source rows, normalized raw JSON, source observations, taxonomy and location provenance | Retain permanently. These records explain qualification and historical source changes. |
| Raw HTML and downloaded files | No attachment binaries are downloaded today. If a future adapter stores raw HTML or files, store outside the web root, hash content, and keep compressed raw HTML for at least 90 days; retain change-triggering evidence permanently. |
| Sync job metadata and source errors | Retain at least 24 months; export archived job metadata before any approved cleanup. |
| User audit events and security events | Retain at least 7 years; access is admin-only and events are not removed by the application. |
| Application/container logs | Retain 30 days locally and 90 days in the configured centralized logging platform; scrub auth headers and cookies. |
| PostgreSQL backups | 7 daily, 4 weekly, and 3 monthly by default, with off-host encrypted copies configured by operations. |

Admin system status reports PostgreSQL database size, source-observation/job counts, attachment directory bytes, queue depth, pool state, and latest backup manifest. Growth thresholds and paging are deployment monitoring configuration. Do not prune raw observations or audit history until a separate approved retention migration documents the selection rule, dry-run count, backup, and recovery path.

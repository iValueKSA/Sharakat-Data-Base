# ADR: PostgreSQL backup strategy

**Status:** Accepted; restore exercise pending

Run daily `pg_dump` custom-format backups from the maintenance queue. Write a manifest and SHA-256 digest next to each artifact. Retain 7 daily, 4 weekly, and 3 monthly restore points by default. Send backup failures as CRITICAL internal alerts and optional email. Mount backup storage outside the application image and replicate it to encrypted off-host/object storage in production. The initial targets are RPO ≤ 24 hours and RTO ≤ 4 hours. These targets are not proven until a staging restore is measured; the repository has not executed that restore.

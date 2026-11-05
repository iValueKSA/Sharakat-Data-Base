# Rollback

1. Stop rollout and capture API, worker, scheduler, database, and queue logs with correlation IDs.
2. For an application-only regression, redeploy the previous immutable image. Do not downgrade the database automatically.
3. Check whether the new migration is backward compatible with the old image. If not, keep the new image and use a forward fix, or follow the approved database recovery plan.
4. Restore a database backup only for confirmed data corruption and only into an isolated recovery database first. Compare records and obtain incident-owner approval before any production restore.
5. Verify health/readiness, login, source rows, recent observations, and exports. Document impact and follow-up actions.

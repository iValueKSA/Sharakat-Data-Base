# ADR: Production scheduler and worker boundary

**Status:** Accepted for Phase 1

## Context

The current scheduler runs inside FastAPI and its `asyncio.Lock` cannot coordinate multiple processes. A source outage must not block other sources, and duplicate runs must be suppressed across replicas.

## Decision

Use Celery with Redis as broker/backend and Celery Beat as the dispatcher. A Redis scheduler lease prevents concurrent dispatch ticks. A Redis reservation prevents duplicate queued jobs per source; a separate expiring execution lock prevents concurrent syncs for the same source. Workers use late acknowledgements, reject work on worker loss, one-message prefetch, bounded source timeouts, and capped exponential retry with jitter. SQL job rows remain the execution-history system of record. Intervals live on each source row and can be changed using the admin source settings API.

## Consequences

Redis is required in production and is not the source of truth. Job execution remains behind the existing source adapter and normalization code. Recovery depends on the periodic stale-job task and lock expiry. Deploy only one Beat process per environment; the lease is a second guard against accidental overlap.

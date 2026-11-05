# ADR: Internal alert events and delivery

**Status:** Accepted for Phase 1

Persist deduplicated alert events in PostgreSQL so alert state survives worker restarts. Alerts have severity, source, event payload, open/acknowledged/resolved state, acknowledgement identity, and timestamps. Ingestion emits opportunity-created and material deadline/status/location change events; worker tasks emit source, parser, collection, backup, stale-sync, and deadline reminders. Deadline warning days are configurable with `DEADLINE_ALERT_DAYS` (default `30,14,7,3,1`); expired or cancelled opportunities are excluded and fingerprints prevent repeat reminders for the same opportunity, deadline, and threshold. Email delivery is a separate notification queue task and optional SMTP adapter; the database event remains authoritative. Delivery is disabled when no recipients/SMTP configuration is present. Other channels can implement the same adapter boundary later.

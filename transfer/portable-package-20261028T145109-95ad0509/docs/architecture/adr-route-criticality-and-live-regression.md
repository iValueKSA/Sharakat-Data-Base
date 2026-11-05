# ADR: Route criticality and live-source regression

**Status:** Accepted  
**Date:** 2026-10-12

## Context

Public source adapters monitor routes with different jobs. A route can describe an opportunity population, provide supporting qualification or program context, be optional, or exist only for discovery. Treating every HTTP failure as a source failure causes a non-critical route interruption to invalidate a source even when its required public scope is still observable. Likewise, live sources can legitimately add or update records between syncs, so a successful regression check cannot require zero deltas.

## Route criticality

Each monitored route receives one of four values:

- **CRITICAL** — required to establish or monitor the source's defined public opportunity population. A failed critical route makes the defined public scope incomplete.
- **SUPPORTING** — provides useful context, qualification requirements, documentation, or secondary discovery. A failure may reduce coverage but does not by itself make the source unhealthy.
- **OPTIONAL** — helpful but unnecessary to the monitoring contract.
- **DISCOVERY_ONLY** — reconnaissance or detection of additional public surfaces; outside the production completeness contract.

Every route snapshot records its URL, name, type, criticality, last HTTP status, last success and failure timestamps, consecutive failures, content role, source-health and coverage effects, and route health. `ACCESS_RESTRICTED` represents HTTP 401/403/429. NHC stores these snapshots in `SyncJob.metrics_json`; a failed route does not erase its prior `SourceContentItem` or imply an empty opportunity population.

## Source health

Source health is evaluated against its defined monitoring contract. All CRITICAL routes must succeed and parse, and there must be no parser failure. A SUPPORTING, OPTIONAL, or DISCOVERY_ONLY route may be access-restricted while source health remains `HEALTHY` when the critical public scope is still defensible. Coverage remains `PUBLIC_COVERAGE_LIMITED` when the source does not expose a complete public itemized inventory or when a supporting public route is restricted.

For NHC, the Arabic investment-opportunities page is the required category surface. The English page is a supporting locale mirror because the Arabic page carries the same public categories. The English mirror's 403 therefore appears as `ACCESS_RESTRICTED`; it does not make NHC unhealthy or imply zero NHC assets.

## Live regression

The regression result is one of:

- `DATA_STABLE` — structure is valid and there are no material source-data changes.
- `VALID_LIVE_CHANGE` — structure and provenance are valid and observed additions, updates, or removals are supported by source evidence and processed correctly.
- `UNEXPECTED_DATA_CHANGE` — an unexplained change, false duplicate/removal, or provenance failure remains.
- `PARSER_REGRESSION` — a required route, parser, pagination step, or stable identifier/provenance check failed.

Counts alone do not determine regression success. A legitimate new record or update is a successful live-source result. `app/regression.py` implements the state selection after structural and data-integrity review.

## Removal safety

Only a complete successful population snapshot may participate in deletion reconciliation. A restricted, failed, or unparseable route cannot contribute a zero count and cannot cause removals. NHC continues to set `reconciliation_safe=false` because its public pages expose categories and qualification flows, not an enumerable itemized inventory.

## Consequences

Route-level monitoring can report an external access limitation without hiding the source's health. Operators can distinguish public-coverage limits from adapter failures, while prior observations remain available for comparison and audit.

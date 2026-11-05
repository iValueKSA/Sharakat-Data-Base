# ADR: PIF public opportunity coverage

**Status:** Accepted  
**Date:** 2026-10-12

## Context

Official PIF Private Sector Hub search-index results expose item-level opportunity content for ecosystem and company-opportunity routes. Current public page reads for the tested routes show the opportunity heading and filter controls followed by “No results found”. The local direct HTTP client returned HTTP 403 during the final review, while earlier normal unauthenticated syncs reached the routes and captured their empty listing shell. The official page reader also reports the current no-results page state. No access-control bypass, crawler impersonation, private API, or authentication was used.

The official annualreport.pif.gov.sa host has the same opportunity page shell, but the tested route has no item cards and no visible report year or as-of date. Indexed snippets cannot be attributed safely to its opportunity GUID query. The annualreport surface is UNKNOWN rather than a proven current inventory or a dated historical snapshot.

## Decision

The production PIF source is limited to current, directly verifiable content from unauthenticated PIF public pages and payloads. Search-index results and the unclassified annualreport surface are discovery or historical evidence only. They do not create current SourceOpportunity or Master records.

The adapter must distinguish:

- Technical health: whether the defined public routes are successfully monitored and show expected listing markers.
- Coverage status: whether current public opportunity items and the company roster can be enumerated.

An expected current no-results state on a reachable listing is a healthy monitor observation. It does not establish that the national opportunity population is empty. If routes fail, markers disappear, or the response becomes unrecognizable, technical health becomes WARNING.

While the current roster is not enumerable, PIF remains HEALTHY / PUBLIC_COVERAGE_LIMITED, source_collection_complete=false, and reconciliation_safe=false. Current records are not removed based on this limited snapshot.

## Defined scope

Monitor the publicly accessible PIF Private Sector Hub Explore Opportunities landing page, all publicly discoverable ecosystem routes, publicly discoverable company-opportunity routes, and current public opportunity content exposed by those routes without authentication. Authenticated services, private APIs, guessed company filters, and search-index ingestion are outside scope.

## Identity

Query GUID semantics remain UNKNOWN until a live public item payload proves the relationship. A query-string GUID alone is not an opportunity identity. A current item payload may supply its own item ID; otherwise use a deterministic content fingerprint. The company filter in a URL remains context only; actual portfolio company attribution must come from the current item itself.

## Monitoring and recovery

Keep the adapter enabled. When a known indexed title appears directly in a current public card or payload, or an item-bearing endpoint becomes public, record PIF_PUBLIC_DATA_REAPPEARED / SOURCE_COVERAGE_CHANGED and run full population reconciliation. Search-index evidence alone does not trigger ingestion.

## Consequences

- PIF no longer blocks platform readiness solely because the public source has an inconsistent or non-enumerable listing.
- The source dashboard reports technical health separately from limited coverage.
- No stale or index-only record enters current Master data.
- Annual report content with no clear date or current status remains outside current opportunity ingestion.
- Coverage must be reviewed again if the public listing, company roster, page markers, or payload structure changes.

# ADR: Public source completeness and source health

- Status: Accepted
- Date: 2026-10-12

## Context

Government investment platforms expose different public scopes. A source may provide a complete public announcement archive while keeping its full investor pipeline behind an authenticated or private API. Other sources may publish current product information without a live location-level availability inventory. Treating both cases as scraper failures blocks expansion for information that is not legitimately available. Treating an empty response as complete would also hide real collection failures.

## Decision

Expansion gates use **PUBLIC_COMPLETENESS**: complete collection of the source's discoverable, legitimate, unauthenticated public opportunity surface within a documented adapter scope. **ABSOLUTE_SOURCE_COMPLETENESS** is a separate claim and remains unknown where a broader authenticated pipeline exists.

Technical health and source coverage are stored independently. A source can be technically healthy with limited public coverage. A source can also have a collection warning while its documented public scope remains limited.

Coverage values are:

- `COMPLETE_PUBLIC_SOURCE`
- `COMPLETE_FOR_DEFINED_SCOPE`
- `PUBLIC_COVERAGE_LIMITED`
- `AUTHENTICATED_SOURCE_REQUIRED`
- `PRIVATE_API_REQUIRED`
- `PARTIAL_OFFICIAL_COVERAGE`
- `UNKNOWN_COVERAGE`

Technical health values are:

- `HEALTHY`
- `WARNING`
- `FAILED`
- `BLOCKED`
- `RATE_LIMITED`
- `PARSER_BROKEN`

## Rules

- Never bypass authentication, access controls, private-network boundaries, or public API denials.
- Do not claim absolute completeness when the official source does not expose it publicly.
- Keep limitations as source-level records with evidence, verification dates, completeness impact, and resolution notes.
- Preserve only verifiable official records. Map polygons, factory counts, allocated areas, and historical summaries do not become opportunities without current availability evidence.
- Within one publisher, merge duplicate announcement aliases only when the official URL and normalized project title match exactly; keep both source observations and audit the merge.
- Do not interpret an empty or rejected response as a complete zero inventory.
- Monitor documented public pages, feeds, datasets, and APIs within the defined scope. Treat failures that prevent that collection as technical warnings or blocks.
- Keep coverage methodology at source level; opportunity rows retain provenance and evidence.

## Wave 3 application

- MODON is `PUBLIC_COVERAGE_LIMITED` because its public catalog exposes product and location filters but no complete live Al-Ahsa availability inventory. Its documented open-data metadata and resource API is monitored, but its aggregate datasets are reference evidence only.
- NCP is `COMPLETE_FOR_DEFINED_SCOPE` for the full public English News archive and linked official articles. Its broader investor pipeline is `PRIVATE_API_REQUIRED`; no private API request is made.
- NCP's duplicate Food Safety Labs article alias was consolidated under the exact URL/title rule. Both source rows and event evidence remain stored, and the merge is reversible through its merge audit.

## Consequences

A source can be production-ready for its documented public scope while clearly showing a public coverage limitation. Expansion decisions no longer require access to data the publisher does not make public. A failed public collection still blocks the gate until it is repaired or the scope is explicitly narrowed with evidence.

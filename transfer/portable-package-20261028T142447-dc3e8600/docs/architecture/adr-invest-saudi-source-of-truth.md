# ADR: Invest Saudi authoritative source population

- **Status:** Accepted
- **Date:** 2026-10-12
- **Scope:** Invest Saudi discovery, completeness, lifecycle monitoring, and its separation from the Al-Ahsa classification layer.

## Context

Invest Saudi exposes four public, paginated opportunity datasets: Opportunities, Investment projects, PIF opportunities, and Regional opportunities. The complete 2026-10-12 snapshot returned 2,524 endpoint rows with 2,524 distinct official numeric IDs and no cross-dataset overlap. Thirty-one Investment projects IDs seen in a prior complete snapshot were absent after three complete successful missing checks and remain stored historically.

The public Investment Opportunities page displays a hero counter of 2,197. Inspection of the frontend bundle confirms that the value is a hard-coded literal, not a count supplied by the current four APIs. The page and APIs do not document the population or cutoff intended by that value. It is therefore not a valid completeness denominator or source lifecycle signal.

## Decision

For Invest Saudi, the current public API datasets and their official identifiers are authoritative for opportunity discovery, completeness validation, and source lifecycle monitoring.

The current source population is:

```text
current_unique_source_opportunities = unique official IDs returned by a fully paginated, internally consistent current API snapshot
```

The current value is **2,524**. Historical records absent from the current snapshot are tracked separately (**31**) and are never added to the current source population. They remain retained with original IDs, raw observations, first/last-seen timestamps, prior classification evidence, and dataset membership history. After three successful complete misses, an endpoint membership is marked non-current; this is the available source-removal state because Invest Saudi exposes no official lifecycle status. The records are not labeled cancelled or deleted.

The UI observation is metadata only:

```text
ui_displayed_counter = 2197
ui_counter_type = STATIC_FRONTEND_VALUE
ui_counter_authoritative = false
ui_counter_semantics = UNKNOWN
classification = UNRESOLVED_NON_AUTHORITATIVE_UI_METADATA
```

It is excluded from `source_total_reported`, API collection completeness, source health, and missing-record reconciliation. A source is healthy only when its expected endpoints respond, their pagination completes, reported endpoint totals match the received rows, official IDs are extractable, the endpoint-row/unique-ID/membership counts reconcile, and sync behavior is reproducible. The 2,197 value is not part of those conditions.

## Alternatives Rejected

- Treating 2,197 as the Invest Saudi `source_total_reported` or as a target for API completeness.
- Truncating or filtering current API records to force the API union to equal the frontend counter.
- Inferring that the 327 difference consists of archived, inactive, unpublished, language-duplicate, or otherwise excluded records without official evidence.
- Adding the 31 historical-only records to the current source total.

## Reason

The frontend number is static and has no verified relationship to the four current APIs. The API union is independently reproducible from official IDs and fully paginated responses; it is the only machine-readable population with documented membership and completeness evidence.

## Consequences

- Current API health is based on four API datasets and the exact union of their official IDs.
- Current source population is reported separately from retained historical source-only identities.
- The UI counter remains recorded as non-authoritative reconnaissance evidence. If it changes, record old/new values, observation time, page/asset version, and fingerprint in [`data/reconciliation/invest-saudi-ui-counter-history.csv`](../../data/reconciliation/invest-saudi-ui-counter-history.csv). Do not alter API health logic automatically.
- If a future release exposes a live count endpoint, reassess its data definition and identity relationship before using it.
- Al-Ahsa classification continues once per unique official API identity and is unaffected by the UI counter.
- This decision closes the Wave 2 reconciliation gate; it does not implement any Wave 3 sources.

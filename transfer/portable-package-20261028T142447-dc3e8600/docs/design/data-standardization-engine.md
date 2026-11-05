# Data Standardization Engine

## Purpose

`app/standardization.py` is the shared, deterministic engine for derived opportunity values. It is called from the existing synchronization path after an adapter has constructed a `RawOpportunity`, and before geographic eligibility, matching, or Master Opportunity updates are applied. Filter canonicalization is now a compatibility import from this engine rather than a separate rule set.

The data flow is:

```text
official response → source adapter → RawOpportunity + raw payload/fingerprint
                   → standardize_opportunity → eligibility → existing match rules
                   → SourceOpportunity evidence + Master projection
                   → API filters/dashboard/exports
```

Adapters keep source-specific collection, qualification, and taxonomy extraction. Common Unicode cleanup, canonical aliases, identity keys, validation, and field audit metadata live in the engine. The Invest Saudi and other source-specific taxonomy records remain preserved in their existing tables.

## Persistence and provenance

`SourceOpportunity.source_owner`, `source_sector`, `source_subsector`, `raw_location`, `raw_area`, `raw_value`, `raw_dates`, `raw_status`, `source_url`, `raw_data_json`, and content hashes remain source evidence. The engine does not rewrite them. The raw payload is hashed before the standardization call, so formatting changes at a publisher still trigger the existing source-change detection.

Migration `0017_data_standardization` adds `standardized_data_json` and `standardization_version`. Each field entry records raw value, comparison form, canonical ID/label where known, mapping status, rule name, and version. Structured parsing issues are retained beside the derived field. Master merge identity, review state, and raw evidence are outside this metadata write.

Migration `0018_sector_activity` adds nullable Master `activity` and source `source_activity` projections. `raw_data_json`, source payloads, identifiers, hashes, and source records remain unchanged by taxonomy backfills. `source_sector` now receives only an explicit source sector field; source activity is recorded separately. A publisher activity value may populate a Master Sector only when it exactly matches an approved canonical sector label.

The `OrganizationAlias` registry is applied only when its source scope is global or matches the active adapter. The applicable aliases are loaded once per source sync and reused for each record, avoiding per-record alias lookup queries. `TaxonomyMapping` continues to preserve source-specific taxonomy decisions. The small global alias set for confirmed dimensions is version-controlled in `standardization.py`; it is deliberately not a fuzzy or open-ended transliteration map. A newly approved universal alias is added there, covered by tests, and appears with its rule in each subsequent source metadata record. Source-scoped entity aliases use the existing database registry.

## Normalization and identity policy

- `standardize_text` applies Unicode NFKC, strips diacritics, tatweel, and zero-width format controls, and collapses whitespace. Comparison keys additionally fold Alef variants and case.
- Both safe display normalization and comparison keys preserve `ة/ه` and `ى/ي`. An unmapped identity uses a display-safe key; Alef folding only discovers a candidate and does not merge it.
- Unknown values remain in their own unmapped identity. Missing values, `Unknown`, `أخرى`, and source-specific values do not fall into one bucket. The platform's pre-existing status label `غير محددة` is retained for an absent source status; explicit `Unknown` remains distinct.
- Sector, Activity, and Opportunity Type are separate fields. The sector registry includes exact canonical IDs for approved labels and aliases; `بقية القطاعات` maps to `sector:other` / `أخرى`. Null, blank, `قيمة مفقودة`, and wrong-dimension sector values map to `sector:unspecified` / `غير محدد`; `أخرى` stays distinct. Unknown sector labels are set to `غير محدد` in the derived projection and flagged for taxonomy review. Substring matching never assigns a sector.
- Decorative paired quotation marks are stripped before identity lookup on Sector, Activity, and Opportunity Type values, matching the existing safe display normalization; raw source values remain unchanged.
- Location labels are standardized only when the exact governorate alias is approved. Geographic acceptance remains owned by the existing location evidence and confidence logic.
- Owner, publication platform, and source adapter are separate fields. A source key is persisted as its own identity.
- Lifecycle labels preserve `DELETED_FROM_SOURCE`, `REMOVED_FROM_SOURCE`, `CANCELLED`, `EXPIRED`, and `AWARDED` as separate IDs.

canonical_id is used by API filter option metadata, filtering, and backend aggregation. Labels are presentation values; values with an approved alias share the same ID. Invalid or undetermined sectors use the stable sector:unspecified ID. Standardization version 11 maps only Furas `attributes.OPPORTUNITYTYPE=TemporaryRental/TempRental` to `opportunity_type:temporary_rental` / تأجير مؤقت. The mapping is source-scoped: the same English token from another publisher remains missing/reviewable. Generic publication classes map to the stable `opportunity_type:missing` / غير محدد identity. Lease/PPP contract structures remain in separate investment_model metadata only when supported by explicit or source-specific evidence. KFU's commercial-facility classifier does not alone prove an operating model; its model evidence remains review-required. Asset/site labels remain source evidence rather than Opportunity Type. Raw payloads and provenance remain unchanged; metadata-only refreshes increment the engine version.

## Structured fields

- ISO dates are parsed into metadata. Ambiguous dates such as `01/02/2026` are retained as provided and reported as review-required; the engine does not guess a locale.
- Numeric parsing accepts one unambiguous value, Arabic or Western digits, validated grouping, known currency/area/duration units, and a decimal point. Ambiguous punctuation or unsupported units fail closed. A contract duration explicitly expressed in months or days is converted to years; its raw string remains stored.
- Currency-symbol values such as `$1,500` are not assigned to the platform's SAR amount field without a source-specific currency rule.
- URLs are validated as absolute HTTP(S) URLs. Metadata stores a safe normalized URL; the actual source URL and deep link are unchanged.
- Reference numbers keep their exact source text while `normalize_reference` derives a comparison identifier through the central engine. External source IDs remain source-scoped identities; matching them across different adapters is not implied.
- The current opportunity schema has no business-facing contact fields. Any contact data present in an official raw payload remains in that raw payload and is not guessed into new Master fields.

## Consumers

- `/api/filters` exposes canonical labels, aggregated counts, and canonical IDs. Selecting one ID-backed label resolves all approved aliases in SQL.
- Data Dashboard counts are grouped by canonical ID in the backend. Aggregation is not moved into the browser.
- Opportunity API output and CSV/XLSX exports use the same canonical labels. Source URLs, source names, and source counts remain traceable.
- Export columns and source observations are not expanded or removed by this change.

## Existing-data backfill

`scripts/standardization_audit.py --dry-run` inventories distinct Master values and source evidence and writes CSV/JSON. `scripts/backfill_standardization.py --dry-run` calculates the derived metadata projection. Its optional `--apply` mode writes only the two new derived metadata columns in bounded, restart-safe batches. It does not rewrite Master values, raw columns/payloads, merge links, or review decisions. Applying the current version again is a no-op.

## Scope limitations

Ambiguous non-ISO dates, unrecognized units, unmapped taxonomy/entity labels, and similar-but-not-approved names remain preserved and auditable. Fuzzy similarity is not used for canonicalization or opportunity merging. Source collectors that store non-opportunity content in dedicated content/event tables remain outside Master standardization because those records do not feed business opportunity filters or Master fields.

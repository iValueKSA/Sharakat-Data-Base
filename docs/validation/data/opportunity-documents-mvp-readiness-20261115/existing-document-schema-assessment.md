# Live opportunity_documents schema assessment

**Assessment date:** 2026-11-15  
**Mode:** Read-only inspection of the running project database. No schema or data changes.

## Observed live structure

The live relation opportunity_documents is empty (0 rows) and currently contains:

| Column | Observed type | Nullability / role |
|---|---|---|
| id | integer | NOT NULL primary key |
| opportunity_id | integer | NOT NULL; FK to opportunities.id |
| source_id | integer | NOT NULL; FK to sources.id |
| title | varchar | NOT NULL |
| url | varchar | NOT NULL |
| document_type | varchar | nullable |
| first_seen_at | timestamp with time zone | NOT NULL |

Observed indexes are the primary key and a btree index on opportunity_id. No uniqueness constraint was observed. There is no foreign key to a SourceOpportunity record and no fields for source publication ID, official source page, access/login/payment, price/currency, rights, verification time, content type, or provenance status.

## Consequence for MVP

Do not populate the table from the candidate register yet. A Master-only association cannot preserve the source publication identity needed to adjudicate duplicated KFU page links or unlinked Ta'adeen rows. The current schema also cannot represent “public preview, purchase required to bid” separately from paid document access, nor distinguish unknown rights from permission to reuse.

## Future separately authorized schema proposal

Keep the existing table and add (or otherwise persist) source provenance: source_opportunity_id FK, provider document ID, canonical official document URL, source page URL, official title/category/format, and verification timestamp/status. Model access (PUBLIC, LOGIN_REQUIRED, PAYMENT_REQUIRED, UNKNOWN) independently from participation purchase requirement, price amount and currency. Add rights status and terms/attribution reference. Preserve unknowns explicitly. Add source-scoped stable deduplication only after identity policy review. Do not store, proxy, cache, rehost, or copy source files in the MVP.

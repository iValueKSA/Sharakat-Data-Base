# Data Standardization Engine Validation

**Gate:** implementation and current-data backfill verified. The operational checklist and remaining limits are below.

## Architecture audited

The ten adapters in `app/adapters.py` return `RawOpportunity` records. `service.sync_source` is their shared persistence path; `_safe_record` is the common point that applies locality eligibility, entity resolution, SourceOpportunity persistence, provenance, and Master updates. `raw_data_json`, source-specific observation tables, `content_hash`, and SourceOpportunity raw columns already provide provenance. NCP events, MODON locations, and AHDA content items also have dedicated side tables.

Before this change, `app/normalization.py` handled title/reference/location comparison and `app/filter_canonicalization.py` separately handled business labels. Adapters retained explicit source-specific extraction and taxonomy mappings. Filters/options were generated in `app/main.py`; Data Dashboard aggregation also lives there; CSV is generated in `app/main.py`; XLSX presentation lives in `app/excel_export.py`.

## Database and backfill

- Alembic advanced from `0016_source_type_text` to `0017_data_standardization (head)` on the running local PostgreSQL database.
- The migration was exercised on a disposable SQLite database through upgrade, downgrade, and re-upgrade. The downgrade only removes the two derived columns.
- PostgreSQL backups completed before the additive changes and metadata refreshes: `20261014T082312Z-55c50503` (3,405,715 bytes), `20261014T082730Z-248e7003` (3,870,873 bytes), `20261014T083308Z-8fec4e78` (3,919,709 bytes), and `20261014T083646Z-5f567ef0` (3,973,881 bytes).
- Read-only audit: 11,123 distinct-value rows across 26 dimensions; 289 current non-merged Master records and 2,896 source rows were inspected.
- Rule set 4 was dry-run against all 2,896 source rows before backfill: 68,649 derived field entries, 716 approved alias matches, 13,658 preserved unmapped fields, and 0 validation issues. The preview reported 5,760 value-to-canonical projection differences; these were derived metadata only.
- Backfill applied in 15 batches. It changed only `standardized_data_json` and `standardization_version`: **0 Master rows, 0 raw source values, and 0 review decisions were changed**. A repeat rule-set-4 dry-run found 0 rows to update.

## Current value inventory

The machine-readable audit includes every value, frequency, source, mapping disposition, canonical ID/label, and candidate aliases in [standardization-value-audit.csv](standardization/standardization-value-audit.csv) and [standardization-audit-summary.json](standardization/standardization-audit-summary.json).

| Dimension | Records | Distinct observed values | Distinct IDs after projection | Candidate groups | Unmapped values preserved |
|---|---:|---:|---:|---:|---:|
| Activity / sector | 289 | 20 | 20 | 0 | 14 |
| Opportunity type | 289 | 20 | 20 | 0 | 18 |
| Master owner | 289 | 10 | 7 | 2 | 5 |
| City | 289 | 8 | 8 | 0 | 7 |
| Location (district/city) | 289 | 8 | 8 | 0 | 7 |
| Master status | 289 | 6 | 6 | 0 | 1 |
| Publication platform | 289 | 6 | 6 | 0 | 6 |
| Raw source owner | 2,872 non-empty values | 67 | 67 | 1 | 67 |
| Raw source sector | 2,772 non-empty values | 133 | 133 | 0 | 133 |
| Raw source status | 334 non-empty values | 8 | 7 comparison IDs | 1 | 8 |
| Raw source location | 2,672 non-empty values | 146 | 146 | 0 | 145 |
| Master reference number | 289 | 183 | 183 | 0 | 182 |
| Raw source area | 741 non-empty values | 375 | 341 validated numeric identities | 30 validated formatting groups | 0 |
| Raw source deadline | 284 non-empty values | 51 | 51 validated ISO dates | 0 | 0 |
| Raw source publication date | 221 non-empty values | 73 | 73 validated ISO dates | 0 | 0 |
| Raw source reference | 2,731 non-empty values | 2,729 | 2,729 normalized identifiers | 0 | 0 |
| Official source ID (original) | 2,560 | 2,560 | 2,560 source-scoped values | 0 | Preserved |
| Official source ID (normalized) | 2,555 | 2,555 | 2,555 source-scoped values | 0 | Preserved |
| Raw source URL | 2,896 records | 2,112 | 2,112 validated URLs | 0 | 0 |
| Investment model | 44 values | 5 | 5 | 0 | 5 |
| Project stage | 50 values | 7 | 7 | 0 | 7 |

“After projection” is a calculated ID count, not a destructive rewrite. Unknown dimensions remain distinct and unchanged. Raw source owner spelling variants and source status case variants are explicitly marked `candidate_review`; source columns were kept intact.

The verified Master owner mappings are:

- `أمانة الأحساء`, `أمانة الاحساء`, and `أمانة محافظة الأحساء` → `al_ahsa_municipality` / `أمانة الأحساء` (267 records in this inventory).
- `the Ministry of Municipalities` and `وزارة البلديات والإسكان` → `momah` / `وزارة البلديات والإسكان` (5 records).

The data audit contains no uncertain Master entity merges. Source-level owner spelling and source-status case variants remain candidate-only; no fuzzy mapping was approved. The 30 area groups are numerically validated formatting variants, not semantic entities. Other aliases remain as recorded.

## Consumer and regression validation

- Filters aggregate counts by canonical identity; aliases resolve to all corresponding stored values. `/api/filters` also exposes `option_ids` while retaining the existing label-based UI contract.
- Dashboard aggregation groups on the same canonical IDs in backend code.
- CSV and XLSX continue using the canonical Master projection and preserve official source names/URLs.
- Future-ingestion test confirms `امانة الاحساء` and `اخرى` automatically produce their confirmed canonical IDs while source owner/status/raw payload and content fingerprint remain intact.
- Arabic normalization tests cover Alef, diacritics, tatweel, zero-width characters, repeated whitespace, `ة/ه`, and `ى/ي`; ambiguity tests cover date and numeric parsing.
- Full automated suite: **121 passed**. This includes API filters, dashboard, CSV/XLSX, ingestion/matching safety, adapters, security, review and merge behavior.
- Disposable migration check: upgrade → downgrade → upgrade succeeded. Local PostgreSQL is at Alembic head.
- Live service smoke checks returned HTTP 200 for the readiness endpoint, dashboard, data dashboard, filters, sources, source health, schedules, jobs, duplicate/location/qualification review queues, conflicts, and alerts. Opportunity search, two pages, detail, CSV, and XLSX also returned HTTP 200.
- Live system status reported API, PostgreSQL, Redis, Celery worker, and Celery scheduler healthy. Filter API returned `al_ahsa_municipality` with 267 opportunities; CSV and XLSX streamed successfully.
- Final local runtime check confirmed all 2,896 source rows carry standardization version `4` and Alembic is at `0017_data_standardization (head)`. Three repeat export comparisons each returned 289 data rows in both CSV and XLSX; the workbook retained right-to-left layout. Readiness and system-status endpoints returned HTTP 200, and the live dashboard/export count was 289.
- Current observed API snapshot: 289 non-merged Masters, 2,896 source records, 8 multi-source Masters, 26 pending duplicate candidates, 17 pending location reviews, 0 qualification reviews, and 36 open conflicts (27 taxonomy, 9 field). This is the live data state observed during validation; it is not evidence that the derived-metadata backfill changed review queues. The backfill reports zero review decisions modified.

## Files and reports

- Rule-set-4 dry-run details before applying: [backfill-v4-dry-run-summary.json](standardization/backfill-v4-dry-run-summary.json), [backfill-v4-dry-run-projection.csv](standardization/backfill-v4-dry-run-projection.csv).
- Applied backfill result: [backfill-v4-apply-summary.json](standardization/backfill-v4-apply-summary.json).
- Post-backfill idempotency dry-run: [backfill-dry-run-summary.json](standardization/backfill-dry-run-summary.json).
- Implementation: [data-standardization-engine.md](../../design/data-standardization-engine.md).

## Limitations

The engine intentionally does not infer a date format from ambiguous input, turn unsupported currency into SAR, map an unknown entity by similarity, or change source geographic eligibility. Unmapped values and the source-level candidate groups require an explicit reviewed rule before they can receive a shared business identity.

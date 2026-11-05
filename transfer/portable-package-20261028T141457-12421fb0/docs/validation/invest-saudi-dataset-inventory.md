# Invest Saudi dataset inventory

Inventory snapshot fetched **2026-10-12** from the public site. All four endpoints are public WordPress REST API collections. Collection used HTTP `GET` with `page` and `per_page=100`; no server-side filters were applied. Each request page was saved, and each endpoint's reported total matched collected rows. The complete payload is preserved in [`data/reconciliation/invest-saudi-snapshot-2026-10-12.json`](../../data/reconciliation/invest-saudi-snapshot-2026-10-12.json).

The schema inspection found no lifecycle/status or publication fields in any collection. Therefore “active” and “inactive” cannot be counted from these payloads; returned rows are simply public API rows. No language field or language parameter was exposed. Investment Projects contains 95 Arabic-script titles, but this does not establish a separate Arabic-language representation.

## Opportunities

- **Endpoint:** `https://investsaudi.sa/backend/wp-json/v3/opportunities`
- **HTTP method / parameters:** `GET`; `page`, `per_page=100` (no filters)
- **Requests / page size:** 18 / 100
- **Reported total / collected rows:** 1,771 / 1,771
- **Unique official IDs / duplicate IDs within dataset:** 1,771 / 0
- **Active / inactive records:** not exposed / not exposed
- **Status / publication / language fields:** none
- **Sector fields:** `sector_name`; filters metadata also exposes sectors
- **Location fields:** `location`, `region`; filters metadata also exposes regions
- **Other identity/detail fields:** `id`, `slug`, `link`, `opportunity_type`, `pdf_url`, `pdf_file`, `inner_data`
- **Pagination metadata:** `total`, `totalPages`, `page`, `per_page`

## Investment projects

- **Endpoint:** `https://investsaudi.sa/backend/wp-json/v3/investment-projects`
- **HTTP method / parameters:** `GET`; `page`, `per_page=100` (no filters)
- **Requests / page size:** 5 / 100
- **Reported total / collected rows:** 431 / 431 (the earlier 2026-10-11 snapshot reported 462)
- **Unique official IDs / duplicate IDs within dataset:** 431 / 0
- **Active / inactive records:** not exposed / not exposed
- **Status / publication / language fields:** none; language is not specified
- **Sector fields:** `category`, `activity`, `subActivity`
- **Location fields:** `location`, `region`, `municipality`, `modalData.location`
- **Other identity/detail fields:** `id`, `type`, `description`, investment/job/GDP/IRR/payback metrics in row and `modalData`; `modalData.opportunityNumber` is present and unique across all 431 rows
- **Pagination metadata:** `total`, `total_pages`, `page`, `per_page`

## PIF opportunities

- **Endpoint:** `https://investsaudi.sa/backend/wp-json/v3/pif-opportunities`
- **HTTP method / parameters:** `GET`; `page`, `per_page=100` (no filters)
- **Requests / page size:** 2 / 100
- **Reported total / collected rows:** 184 / 184
- **Unique official IDs / duplicate IDs within dataset:** 184 / 0
- **Active / inactive records:** not exposed / not exposed
- **Status / publication / language fields:** none
- **Sector fields:** `sector` object (`id`, `slug`, `name`); nested `company` and `details`
- **Location fields:** none exposed in rows
- **Pagination metadata:** `total`, `totalPages`, `page`, `per_page`

## Regional opportunities

- **Endpoint:** `https://investsaudi.sa/backend/wp-json/v3/regional-opportunities`
- **HTTP method / parameters:** `GET`; `page`, `per_page=100` (no filters)
- **Requests / page size:** 2 / 100
- **Reported total / collected rows:** 138 / 138
- **Unique official IDs / duplicate IDs within dataset:** 138 / 0
- **Active / inactive records:** not exposed / not exposed
- **Status / publication / language fields:** none
- **Sector fields:** `category` and `sector` objects (`value`, `label`)
- **Location fields:** `location`, `city`, `Coordinates`
- **Other detail fields:** investment, jobs, GDP, IRR, ROI metrics, `description`, `pdf`
- **Pagination metadata:** `total`, `totalPages`, `page`, `per_page`

## Identity and membership

Each endpoint supplies an integer `id`; within this API host, the same normalized numeric ID is the strongest observed stable key. The application persists `official_source_id_original` (the original decimal string) and `official_source_id_normalized` (canonical decimal representation) and uses `investsaudi:<id>` as the source-level key. Investment Projects' unique `modalData.opportunityNumber` is a secondary endpoint-specific identifier, not a cross-collection key. No GUID or cross-language ID mapping was exposed.

Endpoint representations are grouped by exact official ID before source-level ingestion. Dataset membership, raw endpoint observations, and taxonomy memberships are stored independently. Titles are not used to merge identities. The seven exact normalized title-collision pairs have different official IDs and remain distinct; see [`data/reconciliation/invest-saudi-exact-title-collisions.csv`](../../data/reconciliation/invest-saudi-exact-title-collisions.csv). Current set cardinalities and the overlap matrix are in the [reconciliation report](invest-saudi-dataset-reconciliation.md) and [`data/reconciliation/invest-saudi-endpoint-overlap.csv`](../../data/reconciliation/invest-saudi-endpoint-overlap.csv).

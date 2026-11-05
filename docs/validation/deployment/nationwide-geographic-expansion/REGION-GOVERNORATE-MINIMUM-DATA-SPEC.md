# Minimum Official Data Specification — Region and Governorate

**Purpose:** an acquisition and acceptance specification for the first nationwide geographic reference. This document does not approve a source or authorize production use.

## Phase 1 — required machine-readable reference

The provider may deliver two linked tables or one equivalent normalized file set. CSV, XLSX, JSON, GeoJSON, or a documented API is acceptable. Stable identifiers must be preserved exactly as supplied, including leading zeroes.

### `regions`

| Field | Required | Meaning |
|---|---:|---|
| `region_id` | Yes | Stable unique key for the region in this reference. |
| `official_region_code` | Yes | Official published code, if distinct from the record key. |
| `region_name_ar` | Yes | Official Arabic name. |
| `region_name_en` | Preferred | Official English name, if maintained. |
| `effective_from` | Yes | Date this record/version is effective. |
| `effective_to` | Conditional | End date for a superseded/retired record, if applicable. |
| `status` | Yes | Active, retired, or the provider's documented equivalent. |
| `dataset_version` | Yes | Version/issue identifier for the complete delivered dataset. |
| `source_authority` | Yes | Responsible issuing/custodian authority. |

### `governorates`

| Field | Required | Meaning |
|---|---:|---|
| `governorate_id` | Yes | Stable unique key for the governorate in this reference. |
| `official_governorate_code` | Yes | Official published code, if distinct from the record key. |
| `governorate_name_ar` | Yes | Official Arabic name. |
| `governorate_name_en` | Preferred | Official English name, if maintained. |
| `parent_region_id` or `official_region_code` | Yes | Explicit, resolvable parent region key. |
| `effective_from` | Yes | Date this record/version is effective. |
| `effective_to` | Conditional | End date for a superseded/retired record, if applicable. |
| `status` | Yes | Active, retired, or the provider's documented equivalent. |
| `dataset_version` | Yes | Same release/version contract as the linked region table. |
| `source_authority` | Yes | Responsible issuing/custodian authority. |

## Provider statements required

1. Confirm complete nationwide coverage for one stated effective version and the number of region and governorate records in it. Phase 1 must confirm 13 current regions and the governorate count for that specific version.
2. Explain what each code means and whether codes are stable across releases, including the policy for renamed, moved, split, merged, retired, or newly established units.
3. Provide explicit Region → Governorate relationships in the data, not relationships inferred from names or row order.
4. State version/issue date, effective date, last-updated date, update frequency, change notification method, and archive/version availability.
5. Provide the dataset-specific license/permission text and required attribution. It must explicitly address internal/private database storage, use by an investment-opportunities information platform, normalization/matching, display in filters, caching, retention for audit, and redistribution of derived application output.
6. State whether a separate geospatial-activity license, permit, or fee is required for this use. Dataset reuse permission and permission to perform a regulated geospatial activity are separate questions.

## Optional Phase 2 — cities / administrative centers

| Field | Required when Phase 2 is requested | Meaning |
|---|---:|---|
| `city_or_center_id` | Yes | Stable unique key. |
| `official_code` | Yes, if issued | Official code. |
| `name_ar` | Yes | Official Arabic name. |
| `name_en` | Preferred | Official English name. |
| `parent_governorate_id` | Yes | Explicit governorate key. |
| `parent_region_id` | Yes | Explicit region key or deterministic link through the governorate. |
| `administrative_type` | Yes | City, administrative center, or provider-defined class. |
| `effective_from`, `effective_to`, `status` | Yes | Record lifecycle. |
| `dataset_version`, `source_authority` | Yes | Provenance. |

City coverage is optional and must not delay Phase 1 if Phase 1 passes its own acceptance criteria. No high-resolution boundary data is required to activate Region + Governorate filters; if geometry is supplied or later needed, it requires separate provenance and reuse review.


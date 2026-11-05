# GASTAT Governorate Count Conflict — 2026-11-01

## Decision

**GOVERNORATE_150_151_CONFLICT = UNRESOLVED.** The reviewed publications describe statistical reference areas or survey strata, not a single versioned administrative roster with membership IDs. The different totals therefore cannot establish which count is the current administrative truth.

| Source | Publication / date | Reference period | Count | Definition and scope | Evidence |
|---|---|---|---:|---|---|
| GASTAT, [Methodology and Quality Report for Household Energy Statistics 2024](https://www.stats.gov.sa/en/w/methodology-and-quality-report-for-household-energy-statistics-2024) | Methodology report; public page published about 2025 (page metadata does not give an exact issue date) | Household survey 2025 sample design using 2022 Census frame; indicator coverage for household energy 2024 | 150 | “Actual strata” used to produce survey indicators separately for each governorate. The report describes sample-frame stratification and allocation, not a legal/admin unit inventory. | The report explicitly ties 150 to governorate strata and says the 2022 Census was used as the sampling frame. |
| GASTAT, [Methodology and Quality Report for Household Environment Statistics 2024](https://stats.gov.sa/en/w/methodology-and-quality-report-for-household-environment-statistics-2024) | Methodology report; public page published about 2026-01 | Household Environment Statistics 2024 | 150 | Governorates used as sample strata for national and governorate-level estimates; sample allocation is based on second-stage census housing-unit counts. | Methodology states estimates are sought for each of 150 governorates (strata). |
| GASTAT, [Methodology and Quality Report for Health and Safety at Work Statistics 2025](https://stats.gov.sa/en/w/methodology-and-quality-report-for-health-and-safety-at-work-statistics-2025) | Latest methodology update 2026-04-29 | Data collection reference date 2025-07-06; publication coverage 2023–2025 | 151 | Reference area described as 13 administrative regions and 151 affiliated governorates for a statistical product. It does not provide an administrative membership list or explain the unit-count change from the 150-stratum survey methods. | Its reference-area section explicitly reports 151; the 2024 health and safety methodology also reports 151 for its product. |
| GASTAT, [Methodology and Quality Report for Health and Safety at Work Statistics](https://www.stats.gov.sa/en/w/methodology-and-quality-report-for-health-safety-at-work-statistics-publication) | Methodology page published about 2025-06 | Data available for 2024; base year 2023 | 151 | Statistical reference area for a household/employee health and safety product; the page identifies statistical units and population separately from geographic coverage. | Reference area states 13 regions and 151 governorates. |

## Assessment of possible explanations

- **Survey frame / statistical scope:** evidenced as relevant for the 150 count. The household energy and environment methods explicitly use governorates as strata, and household energy identifies the 2022 Census as its frame.
- **Effective date or administrative change:** possible, but the reviewed publications do not document a boundary/order change that adds one governorate.
- **Regional capital treatment:** not established. The publications do not state whether regional capitals are counted as governorates, administrative centers, or in another way for these totals.
- **Terminology or scope:** plausible because these are distinct statistical products and one describes strata while another describes its coverage; no source supplies a reconciliation.
- **Publication error:** cannot be ruled in or out from the reviewed records.

The NCAR [Unified Coding Guide for Regions, Governorates and Administrative Centers](https://ncar.gov.sa/regions-coding) is a useful coded reference candidate, but the public PDF does not state a clear effective date or reuse license and is not a machine-readable roster. The guide itself describes a Royal Order-based arrangement and distinct code assignment practices; it does not reconcile GASTAT's 150/151 denominators.

## Operational treatment

Do not choose, hardcode, or synthesize 150 or 151. Do not derive a roster from a statistical denominator. If an authority later provides a licensed versioned register, store that dataset's stated version/effective date, its explicit unit membership and counts, and report totals by that version. The unresolved statistical discrepancy would not itself block a separately verified versioned reference.

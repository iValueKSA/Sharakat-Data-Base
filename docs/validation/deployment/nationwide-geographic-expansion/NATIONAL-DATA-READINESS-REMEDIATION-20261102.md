# National data readiness remediation — 2026-11-02

**Result: COMPLETE.** The canonical national population and the geographic reference are operational. National UI and map feature flags remain off in the live application pending activation approval.

## Preservation and backup

- Verified logical backup: `backups/20261102T094506Z-pre-national-data-remediation.dump`
- SHA-256: `4c438751374584293f9015b86b9d9dbc088e6a313151015fdf13d9001817b29e` (29,471,162 bytes), created `2026-11-02T09:45:06Z`.
- Restore test passed in isolated PostgreSQL 16. Backup manifest records Alembic `0025_source_geographic_coverage`, 6,644 Master rows (6,623 current), 9,290 SourceOpportunity rows, and 6,546 Furas rows.
- No source sync was started. This remediation created no Masters, changed no source links, did not touch the 53 deferred Furas identity/duplicate cases, did not alter Jobs 692/694/696, and did not enable removal reconciliation.

## Public official geography reference

Loaded the public Saudi Ministry of Industry and Mineral Resources Taadeen GIS administrative layers: [MapServer service](https://gis.taadeen.sa/server/rest/services/Common/BaseMaps/MapServer), Emirates/regions layer 3 and Governorates layer 2. Anonymous public REST queries returned 13 regions and 149 governorates. The operational hierarchy contains 1 country, 13 regions, 149 governorates, and 0 cities. City coverage is explicitly unavailable. No synthetic geography rows were imported and no formal license claim was added.

The current dataset is `taadeen-public-gis-20261102-v3`, digest `ec0f22308cc4b6960c5c39aad416f7d7dafa5c13d5b2c7afd56a13f9dc634b8b`. Source GeoJSON and the imported payload are retained under `docs/validation/deployment/nationwide-geographic-expansion/evidence/`. Exact official codes, normalized names, known aliases, and parent relationships drive assignments. The 54 Furas rows without a usable region (`47` with empty region fields, `7` with `NA`) remain unassigned; no defaults or fuzzy matches were applied.

Current Master coverage: 6,439 have an official region identity (3,329 at region level and 3,110 at governorate level); 3,110 have a governorate identity; 0 have a city identity. Scope counts are 6,057 `SPECIFIC_LOCATION` and 566 `UNSPECIFIED`. Geographic completeness does not gate the country total.

## Filters, quick view, and exports

- Region and governorate selectors return HTTP 200 (13 region options; governorates are parent-filtered). A valid governorate selection returns 200; unknown IDs remain 422. City selection remains safely unavailable because the reference has no city layer.
- `location=saudi_arabia`, `country_id=SA`, and `country_id=saudi_arabia` each return 6,623 unique current Masters, equal to the unfiltered current Master population. `UNSPECIFIED` returns 566. `NATIONWIDE` is a separate scope and currently returns 0.
- Region 5 (Eastern) returns 975, including 518 in official Governorate 501 (Al-Ahsa). Region filters exclude `NATIONWIDE` rows. Region 1 (Riyadh) returns 800.
- The Al-Ahsa quick-view slug now resolves the Arabic label against the current official governorate reference, constrained to the official Eastern Region parent. The 518 Master IDs exactly match `governorate_id=501`: false positives 0, false negatives 0. This excludes title-only matches. The UI label comparison accepts the exact Arabic orthographic variant `الاحساء` used by the public layer.
- API/CSV/XLSX data-row parity passed for all seven cases below. XLSX row counting skips its five preamble rows and the header row.

| Filter | API | CSV rows | XLSX data rows |
|---|---:|---:|---:|
| All Saudi Arabia | 6,623 | 6,623 | 6,623 |
| Al-Ahsa | 518 | 518 | 518 |
| Eastern Region | 975 | 975 | 975 |
| Riyadh Region | 800 | 800 | 800 |
| Al-Ahsa Governorate | 518 | 518 | 518 |
| `UNSPECIFIED` | 566 | 566 | 566 |
| `NATIONWIDE` | 0 | 0 | 0 |

Pagination returned all 6,623 national Master IDs over 14 pages of 500 with no duplicates; repeated title-ascending first-page results were stable. Search combined with Al-Ahsa governorate returned 58 rows with HTTP 200. The isolated browser evidence in `NATIONAL-UI-BROWSER-VALIDATION-20261101.md` records 56 passed checks across City-present and City-absent test references, including dependent filters, quick-view resolution, search, sorting, paging/reset, exports, dashboard/map interactions, and RTL overflow at 1920×1080, 1440×900, 1366×768, 768×900, and 390×844. The current UI script was additionally confirmed served with HTTP 200; its orthographic name match was normalized. This browser suite uses isolated synthetic test Masters, while the counts above were checked against the live canonical database.

## Map and coordinate evidence

The read-only Furas coordinate verifier matched every linked source record to its raw `geometry.x/y`, source opportunity identity, HTTPS record URL, and existing Master coordinate. It evaluated 6,493 direct Furas coordinate records: 6,312 fell inside official Saudi region polygons (`verified=true`, method `DIRECT_SOURCE_COORDINATE`); 181 were classified `SOURCE_COORDINATE_OUTSIDE_SAUDI_REVIEW` and retained without movement. Invalid coordinates, missing Furas coordinates, identity mismatches, Master/source coordinate mismatches, and fabricated coordinates: 0. There are 45 repeated coordinate rows across 6,448 distinct points.

Across current Masters, 6,312 carry verified coordinate provenance, 130 have no coordinates, 181 have coordinate-bearing but unverified/outside evidence, and 0 are invalid. The isolated national map API (flags enabled only inside a read-only TestClient process) returned the 6,623 Master list universe and 5,889 verified physical markers across 5,847 point groups. All 734 non-marker Masters remained in the list; this includes broad/unspecified scopes and out-of-boundary evidence. It returned zero outside-boundary, fabricated, centroid, `NATIONWIDE`, or `UNSPECIFIED` markers. The earlier isolated browser run verified clustering, map/list filtering, marker details navigation, and viewport behavior. Live map remains disabled.

## Lifecycle, scheduler, DQ, and dashboard

- The four Invest Saudi status conflicts were resolved under `SOURCE_SCOPED_REMOVAL_WITH_LIVE_LINKED_SUPPORT_V1`. The rule required lifecycle-confirmed source removals plus current live linked Furas support consistent with the existing canonical Master status. Source canonical status and observation history were preserved; the 46 identity and 7 same-source duplicate cases were untouched.
- Scheduled Furas behavior is national-or-skip: national mode selects `SAUDI_NATIONAL_V1`; when disabled, the scheduled Furas task is skipped and cannot fall back to `AL_AHSA_SUBSET_V1`. Manual trigger behavior is unchanged. Removals remain disabled. The unit suite covers the disabled scheduler path; no Furas task was run here.
- Full live DQ completed read-only: **129 PASS, 5 WARNING, 0 FAIL**. The remaining warnings are non-blocking source freshness, generic source-page coverage, runtime-anomaly, and quantitative-field review signals; no DQ gate was weakened.
- Dashboard API aggregates unique Masters: 6,623 total, 6,517 active, 85 historical, and 21 with unspecified/unknown status classifications in its status breakdown. Sector counts sum to 6,623. Source membership is non-additive (Furas 6,493; other platforms may also link the same Masters). Geographic summary reports region and governorate memberships, 5,889 mapped unique Masters, 734 unmapped, 6,057 specific-scope, 566 unspecified, and no nationwide rows. Memberships are labeled non-additive so geographic/source sums are not mistaken for the national total.
- Full regression: **663 passed, 1 skipped, 42 warnings**. The skip is the PostgreSQL-only concurrency test under the isolated SQLite test run. The final run used `REDIS_URL=''` and an isolated SQLite database.

## Readiness and live state

`NATIONAL_UI_READINESS=READY` and `NATIONAL_MAP_READINESS=READY` based on the API/export parity, zero-fail DQ, exact canonical Al-Ahsa set, current verified coordinate evidence, and isolated UI/map validation. These are readiness findings only; no live feature gate was opened. At report time `NATIONAL_UI_ENABLED=false`, `NATIONAL_MAP_ENABLED=false`, `NATIONAL_DASHBOARD_ENABLED=false`, `FURAS_NATIONAL_ENUMERATION_ENABLED=false`, and `FURAS_NATIONAL_REMOVAL_RECONCILIATION_ENABLED=false`.

The temporary all-scheduled-sync pause used during deployment was restored to its original state (setting absent) after validation and report generation, with a `NATIONAL_READINESS_SCHEDULER_RESUMED` audit event. The Furas national-mode flag remains false, so scheduled Furas ingestion remains skipped.

# Geographic Coverage Metric Correction — Deployment and Acceptance

**Status:** `GEOGRAPHIC_METRIC_CORRECTION = DEPLOYED_AND_VERIFIED`  
**Date:** 2026-11-15  
**Compose project:** `alahsa-local`  
**Live URL:** http://localhost:8080/

## Change isolation and deployment

Deployed only the approved metric correction and its dashboard labels. The API candidate started from the exact running production image and overlaid only `/app/app/main.py` with the isolated geographic metric patch. The frontend candidate started from the exact running frontend image and overlaid only `static/data-dashboard.js`. No whole dirty worktree build was used. The deployed candidate retains all current API authentication/RBAC behavior and the deployed `app.js` and `national-geography.js` assets byte-for-byte.

Compose recreated only `api` and `frontend` using `--no-deps --no-build --force-recreate`. Worker, Scheduler/Beat, PostgreSQL and Redis container IDs and start times remained unchanged. No migration, bootstrap job, database restore, source sync or schedule activation was run.

| Runtime | Before | After |
|---|---|---|
| API image | `sha256:1536c3e3229684fd2feee62aa3bf896c2b3d35d1bf585522abed3d7d6d62a59a` | `sha256:0063b9161c8529d882e8bec878b17fee78c73d63a70a207f24c915c47eb036ca` |
| Frontend image | `sha256:09be96dfe2a9834fd5df3997cd3a2534f32cf291accc3122aab4e9cdce4e5e6e` | `sha256:24835b8fde13d543348b70e9655754caae5e6fe183072dddfee3425712335a31` |

Deployed API source SHA-256: `0fd75cc67b6d5a96f9f88c2b51016f380cd21ad93a2360f416d4895930843ef6`.  
Deployed `data-dashboard.js` SHA-256: `bbc7845b4d66de2096b5b00981a60b661a9642324110b4553d3fb246abd7cb06`.  
Preserved `app.js` SHA-256: `0f6b6b83170abacb85b51874f21584dc909b996f8af2f48096db1940d2a7eabc`.  
Preserved `national-geography.js` SHA-256: `0aacc95241636c6e0689125a8a6e4be71a53b0819bd09a77b5be72ffbfe09b25`.

## Live metric reconciliation

The API keeps the legacy `missing_coordinates`, `coordinate_records`, `exact_mapped` and `unmapped` keys and their pre-deployment values. New fields independently report complete coordinate-pair presence and existing map eligibility.

| Scope | Total | Eligible | Ineligible | Truly missing | Coordinates present, ineligible | Legacy missing |
|---|---:|---:|---:|---:|---:|---:|
| National | 6,659 | 6,309 | 350 | 166 | 184 | 350 |
| Al-Ahsa, governorate 501 | 518 | 447 | 71 | 0 | 71 | 71 |
| Eastern governorate 503 | 15 | 15 | 0 | 0 | 0 | 0 |
| Riyadh governorate 107 | 9 | 9 | 0 | 0 | 0 | 0 |
| Eastern region 5, post-deployment check | 975 | 797 | 178 | 0 | 178 | 178 |

All population and ineligible-coordinate equations reconcile. Exact sorted eligible Master ID sets match the pre-deployment snapshot for national, Al-Ahsa 501, Eastern governorate 503, and Riyadh governorate 107. Their ID-set SHA-256 values are respectively:

- National: `1d5638d5c67e63ac48bbcdf28b61f9b3915b9b600cad8518bf0ef71c25205145`
- Al-Ahsa 501: `239bb6e69e6c307e55c3d8822e1dabab2506544f4a293d5f827459762526fd5007`
- Eastern 503: `11ab98f4129a4d6c21db001441065bac2499dc0fb122b50f7302c4370214cf59`
- Riyadh 107: `f31a07f7f277ba8da8768d14b6a80367b52fe8c46d1e65a575aeacdd55299e0b`
The Al-Ahsa full population and its eligible/excluded partition were also compared by ID: 518 Masters match the accepted snapshot, 447 eligible IDs are identical before/after, and the same 71 excluded IDs remain excluded. Excluded-set SHA-256 before/after: `2e2514cd2ba74e0f6a555182154d920894a4a7bbf4f4673396ea8e3d93e20cfa`.

Region 5 was additionally checked after deployment; its eligible IDs are a subset of the unchanged national set. A separate pre-deployment region-5 ID snapshot was not captured, so no direct before/after region-5 hash comparison is claimed.

## Tests and live browser

The exact isolated API candidate passed:

- 25 focused dashboard, security/RBAC and map-partition tests.
- 41 broader data-quality and geography-summary tests.
- API Python compilation, dashboard JavaScript syntax and candidate Nginx configuration checks.

Warnings were test-runtime/deprecation and read-only cache warnings; there were no failures.

A fresh Playwright Chromium context was used with zero cookies and no administrator profile. It verified the exact Al-Ahsa display (`518 / 447 / 71 / 0 / 71`), corrected Arabic labels, RTL, loaded Ahda Text, map tiles and attribution, region 5 → governorate 501 filtering, invalid-governorate clearing on region changes, stale-response protection with a delayed Riyadh response, heat mode, cluster expansion, map popup → opportunity list, and opportunity details navigation. Nine geographic tile images were loaded. No JavaScript exception or failed API request occurred; the observed anonymous `/api/auth/me` 401 was expected. Some superseded tile requests were cancelled by Leaflet during map view transitions.

Screenshot: [live Al-Ahsa dashboard](live-dashboard-al-ahsa-20261115.png).

## Security, data and rollback

Post-deployment anonymous `/api/auth/me` and `/api/admin/users` both return 401. The candidate security suite verifies session and role restrictions. Worker ping returned `PONG`; Scheduler remained running and was not restarted.

Read-only database verification reports Alembic head `0026_source_identity_aliases`, 6,659 current Masters, 21 merged Masters, 9,470 source-opportunity rows, 75 active Furas aliases and 75 corresponding `APPLIED` audit rows in one batch. Furas national enumeration/removals and RCU scheduled sync remain disabled. Production business-data mutations: **zero**. A pre-deployment read-only startup probe confirmed `create_all` required no schema DDL, `seed_sources` required no source/alias DML, and the bootstrap Admin already existed.

Rollback images and exact runtime source backups are stored at:

`C:\Users\QusaiAbdElhalim\AppData\Local\Sharakat Data Base\deployments\geo-metric-20261115-125421`

Rollback tags preserve API `sha256:1536c3e3229684fd2feee62aa3bf896c2b3d35d1bf585522abed3d7d6d62a59a` and frontend `sha256:09be96dfe2a9834fd5df3997cd3a2534f32cf291accc3122aab4e9cdce4e5e6e`. Restore each tag to its canonical image name and recreate only `api frontend` with the same Compose `--no-deps --no-build --force-recreate` command if rollback is required. Rollback was not needed.

Full hashes, before/after ID snapshots, and rollback manifest are in the runtime evidence directory above and in `runtime-evidence-20261115.json` alongside this report.


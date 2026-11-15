# Governorate Selector Isolated Fix

**Date:** 2026-11-11  
**Preview:** `http://127.0.0.1:8081/`  
**Deployment:** not performed; production services were not restarted.

## Diagnosis

Earlier guest-session evidence reproduced a governorate select that stayed disabled after selecting a region, while catalog/options APIs were ready and populated. Source inspection found that the shared selector controller relied on a deferred initialization and a truthiness check of `region.value` to manage the disabled state; it did not validate the selected region against the actual child-option set, and the dashboard could initialize the controller more than once while requests were in flight. Dashboard requests also had no latest-request guard. This left initialization and filter-result state vulnerable to drift/races.

The precise runtime trigger for the earlier observation was not confirmed in a fresh post-fix browser session: the user stopped computer control with Escape before that check. The source-level state/race risks were corrected, but browser acceptance remains pending.

## Changes

- `app/static/national-geography.js`: pre-index regions and governorates by stable IDs; synchronously rebuild child options; enable the governorate select only for a valid region with available child options; clear invalid prior selections; set `aria-disabled`; keep no-region and empty-list states disabled.
- `app/static/app.js`: deduplicate the dashboard geography-controller initialization and ignore stale dashboard responses, preserving the latest filter selection.

No HTML, CSS, backend, database, authentication, RBAC, or business data was changed.

## Validation

- JavaScript syntax: `node --check` passed for both modified scripts.
- Selector controller simulated-DOM regression: PASS for default disabled state, valid-region enablement, child-option filtering, governorate selection, clearing stale selections on region change, region clearing, empty child list, and reset.
- Isolated preview serves the current `national-geography.js` source with `X-UI-Preview: isolated-source-tree`; response matches the local file.
- Read-only preview API checks: Al-Ahsa (`region_id=5&governorate_id=501`) returned HTTP 200, 518 total, 447 exact-mapped, 447 unique Master IDs, 444 point buckets, and 0 duplicate IDs. Riyadh region returned 800 unique map IDs; governorates 107 and 102 returned 9 and 171 unique IDs, each a subset of Riyadh. Eastern Region returned 975 total/797 mapped IDs; governorates 501 and 503 returned 447 and 15 unique IDs, each a subset of the region. No duplicate IDs observed.
- The preview's guest/read-only API requests succeeded. No authenticated role session was tested; the change does not touch permissions.

## Pending browser acceptance

The requested real UI workflow was not completed. Computer Use returned “stopped by the user with the physical Escape key”; per the computer-use safety instructions, no more UI input was issued. Consequently, no post-fix browser screenshot was captured, and marker rendering, cluster expansion, popup/details navigation, visual regressions, and browser console errors remain unverified. The simulated-DOM and API checks do not replace those checks.

## Safety

- Production data mutations: 0.
- Production deployment: not performed.
- Production services restarted: 0.
- Synchronization or ingestion triggered: no.
- Existing dirty worktree changes were preserved; only the selector-related sections above were changed in the source files.

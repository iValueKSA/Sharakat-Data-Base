# National Go-Live Blocker Remediation — 2026-11-04

## Decision

**NATIONAL_GO_LIVE = PARTIAL.** Evidence-backed Al-Ahsa and RCU corrections were completed, regression and DQ passed, and accepted code was deployed to `alahsa-local`. National UI, dashboard, and map remain disabled because a valid authorized account could not be used for authenticated browser acceptance. No password was reset, no authentication bypass was used, and no live feature flag was enabled.

## Authentication blocker

- **Root cause:** `STALE_TEST_CREDENTIALS`. The configured bootstrap account exists, is active, and has the `admin` role, but the configured bootstrap password does not match the stored password hash. Account initialization only creates a user when the email is absent; it does not rotate an existing user's password.
- Authentication configuration, login verification, session creation, cookie attributes, and role checks showed no demonstrated defect. The account was not locked; the saved browser state received `401` from `/api/auth/me`.
- **Authenticated login/browser:** not validated. No current authorized password was available. The UI harness's synthetic test credentials were not used for acceptance.
- **Minimal next step:** an authorized administrator signs in normally at `http://localhost:8080` using the current account password, then asks for the authenticated Playwright acceptance to be completed. Do not use the stale bootstrap value from `.env.local`.

## Remediation and evidence

- Al-Ahsa's 84 previously unresolved display rows already had exact current-reference Governorate 501 membership evidence. Projection logic now displays the verified Governorate while preserving raw city/district data. All 518 records were independently reconciled; report: [ALAHSA-84-GEOGRAPHY-RECONCILIATION-20261104.json](ALAHSA-84-GEOGRAPHY-RECONCILIATION-20261104.json).
- RCU status: six rows retain conservative canonical `حالة غير معروفة`; source booleans do not prove application availability. Status review conflicts remain open.
- RCU deadlines: six offset-free source datetimes are timezone-ambiguous and are rejected by the parser. Their raw payloads remain unchanged; the invalid Master projections were cleared, six open deadline conflicts were corrected to select `غير محدد`, and audit/change-history events were written. No conflict was resolved. Report: [RCU-12-CONFLICTS-REVIEW-20261104.json](RCU-12-CONFLICTS-REVIEW-20261104.json).
- A fresh backup was restored successfully in an isolated PostgreSQL container before the RCU write. SHA-256: `049A102BBA9C69D4F0D519DF2E3EB49F7F4194CF8234AD4A2EFA67B7E786CE71`; restore details are in [restore-verification.json](../../../../backups/national-go-live-20261104/restore-verification.json).
- No source sync was manually run; no Master or SourceOpportunity rows were created by this remediation; no Furas flags were changed.

## Validation

- Focused regression: **66 passed, 1 skipped, 0 failed**.
- Full applicable regression: **688 passed, 1 justified skip, 0 failed**.
- Full-scope DQ: **128 pass, 6 warning, 0 fail**. Warnings are existing freshness, generic source-link, runtime, and quantitative-field review items; there are no failing gates.
- Current Masters: **6,657** (6,678 total, including 21 merged). SourceOpportunity rows: **9,468**; configured sources: **14**.
- Al-Ahsa API/dashboard/CSV/XLSX: **518 each**. Independent membership review: 518 verified, 0 unresolved membership, 0 false positives, 0 false negatives. Display unresolved: **84 before, 0 after**.
- Isolated national map preview: **5,889** unique verified direct-source coordinate Masters; 0 outside-boundary markers. Map browser drilldown was not tested.
- Live API health: 200. Readiness: 200; PostgreSQL, Redis, and worker checks report healthy. Celery worker ping: `pong`; no queued/running sync jobs or active worker tasks were present before the service rebuild.
- Live feature catalog after deployment: reference ready; national UI/dashboard/map disabled. Authenticated interaction, national responsive filters, UI/export parity in a signed-in browser, and map drilldown remain unvalidated.

## Final state

| Gate / measure | Result |
|---|---|
| Authenticated login and browser validation | NOT VALIDATED — stale test credentials; current authorized password required |
| DQ fail | 0 |
| Regression failed | 0 |
| Al-Ahsa canonical/API/dashboard/CSV/XLSX | 518 / 518 / 518 / 518 / 518 |
| Al-Ahsa false positives / false negatives | 0 / 0, supported by independent record-level evidence |
| RCU open status / deadline conflicts | 6 / 6 |
| RCU incorrect current status / deadline | 0 / 0 |
| Dashboard/list and API/export parity | API preview passed; authenticated UI parity not validated |
| Responsive authenticated UI tests | NOT VALIDATED |
| Verified map Masters / outside-boundary markers | 5,889 / 0 |
| Map drilldown | NOT TESTED |
| National UI / map enabled | FALSE / FALSE |
| Manual syncs / new Masters / new source rows | 0 / 0 / 0 |
| Furas national enumeration / removals | FALSE / FALSE |


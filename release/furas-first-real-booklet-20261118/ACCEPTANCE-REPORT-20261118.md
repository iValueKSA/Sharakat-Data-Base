# First real Furas booklet — release preparation acceptance

**Prepared:** 2026-11-18  
**Mode:** isolated release preparation; browser interaction prohibited; no production changes.

## Decision

`FIRST_REAL_BOOKLET_RELEASE = TECHNICALLY_READY_PENDING_BROWSER_ACCEPTANCE`

The API and frontend candidates were built from the exact images currently running on the local production platform. The preview API returns the exact proposed page-only document record for Master 597 with an unavailable-download note state, no file URL, and null price/currency. Browser acceptance and explicit production publication approval remain pending. The row has not been inserted into production and no document was published there.

## Candidate images and compatibility

| Item | Candidate | Immutable candidate image ID / digest | Exact base |
|---|---|---|---|
| API | `opportunity-documents-mvp-api:furas-booklet-20261118` | `sha256:1eab3bfeded9a77af3520051eefdd287bd7a4c10b2bc8261fcdb789b77669825` | Running API: `sha256:be0e5ac43f9030bbcf441c4a3e96b08fcad3c1ea1bfe1977d5eedd31ab123ba4` |
| Frontend | `opportunity-documents-mvp-frontend:furas-booklet-20261118` | `sha256:e07c53b4d491399396111e76c850a267a00295c8979b654a9cc9c619810a2602` | Running frontend: `sha256:defb9fd08a2cedda79ba23d8bbf64a3a4420952dc004b52976e1d634173bdcd5` |

The running services remained up with those same base image IDs and their original start times. `http://127.0.0.1:8080/` returned HTTP 200 after candidate builds.

The API build context overlays only `app/documents.py`. Candidate hashes: `documents.py` `1555a830661a72b3ff9a3ee470129f711c5eaf67cddc9717b6e82980c7deefe1`; inherited `main.py` `866d1c43fb9c15b1ba37add8d63e2b686c1a80e0a12165e50c12bdcd62ba686a`; `models.py` `3b9f7a03eed9830e406b6410e89309e869a4ca17cd94567c9e22ffa8a5cb4009`; `security.py` `3d4f6b3074c9296f028a8be04b005ddffd0f5030c77edd546603ef8ef7cdbb29`.

The frontend build context overlays only `/usr/share/nginx/html/static/app.js`. Its SHA-256 is `9bfa150da6aaa30c00b8d27ab6d0efcaad27e0a8196a85924620bc46056b6383`. The accepted baseline hashes for `ui-theme.css`, `data-dashboard.js` and `national-geography.js` remain `68c7c6042c137cf743e5d6479882f3d71f4a9ed59cd36bc76d603abe55d66e4c`, `bbc7845b4d66de2096a5b00981a60b661a9642324110b4553d3fb246abd7cb06` and `0aacc95241636c6e0689125a8a6e4be71a53b0819bd09a77b5be72ffbfe09b25`. No dirty-checkout dashboard, map, geography, authentication, export, migration or other frontend files entered either candidate.

## Validation results

- Focused candidate API/security/platform suite: **56 passed**, 6 non-failing framework/configuration/cache warnings. Included booklet API and 0027 migration guard, production security/RBAC, dashboard, geography, opportunity search/count, filters, and export storage/presentation.
- Candidate JavaScript: `node --check` passed.
- Exact SQL insertion procedure: tested against a disposable clone. First execution inserted one DRAFT row; second execution inserted zero additional rows; exact row count stayed one with both price fields NULL. The targeted rollback removed exactly that one DRAFT row; resulting count was zero.
- Isolated candidate API detail: `GET /api/opportunities/597` returned HTTP 200, Master 597 / reference `01-26-017001-42008`, one page-only document, exact Furas opportunity page URL, `PUBLIC_SOURCE_PAGE`, `SOURCE_PAGE_LINK_ONLY`, `UNAVAILABLE`, and null price/currency. Search by exact reference returned only Master 597.
- Preview HTML and opportunity UI search route returned HTTP 200. The static JavaScript served by preview has the exact candidate SHA. Preview CSP remains same-origin `connect-src 'self'`.
- Preview `/api/auth/me` returned 401 without a session. No account was created and no auth/RBAC settings were weakened.
- Browser UI/layout interaction, screenshot, clicking the page link, desktop/mobile presentation and manual Furas page acceptance were **not run**, in accordance with the user's interruption and no-browser instruction.

The preview database was created only for the disposable app. Its current schema comes from the API's 0027-era SQLAlchemy models and its Alembic marker is `0027_opportunity_documents_mvp`; the real 0027 transition is separately covered by the passing isolated migration test. The preview has one approved *isolated fixture* so the document card can be reviewed. This is not a production publication.

An exploratory full Alembic upgrade from an empty database stopped at historical migration 0022 with a duplicate `canonical_status` column. The platform migration history assumes its established predecessor schema; this does not indicate a 0027 failure. The relevant isolated migration test starts at 0026 and passed. The preview DB was therefore initialized from current model metadata and stamped at 0027 for app preview only; no migration was run on production.

## Prepared record

Identity: SourceOpportunity `3188` → Master `597`; provider `01-26-017001-42008`; provider document reference `270741756`. Page URL: `https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-42008?type=Investment`.

Proposed schema values: category `TERMS_AND_CONDITIONS_BOOKLET`; title `كراسة الشروط والمواصفات`; type `HTML_SOURCE_PAGE`; `url` and `source_opportunity_url` equal the exact opportunity page; access `PUBLIC_SOURCE_PAGE`; rights `SOURCE_PAGE_LINK_ONLY`; link verification `VERIFIED_SOURCE_PAGE`; direct download `UNAVAILABLE` in provenance only; participation `PURCHASE_REQUIRED_FOR_PARTICIPATION`; purchase URL and purchase URL verification NULL; booklet amount NULL; currency NULL; version `1`; dedupe key `8cc33bf2d6e8825d1d0f7592ce7826ae98de5b6e18bfa0bf795bca9f3e03c42c`; initial production publication state `DRAFT`.

The raw displayed amount `1500` and label `سعر الكراسة` are evidence only. No currency was displayed or verified. The failed attachment URL is not stored in `url`, `source_opportunity_url`, or API output.

The prepared DRAFT insert, read-only verification and targeted rollback are in the neighboring SQL files. No SQL file was executed against production.

## Official page and manual acceptance

A read-only HTTP GET on 2026-11-18 at 07:35:02 UTC returned HTTP 200 from the exact official page. Extracted page text included the exact provider reference, a live countdown of 39 days 17 hours, `تاريخ فتح المظاريف: 2026-12-28 10:00:00`, the booklet section, `شراء الكراسة`, and `سعر الكراسة` with `1500`. This indicates a live countdown at observation time, but is not a final active-status determination. The user must verify the date meaning and current status in a normal browser. Earlier same-day evidence records the attachment ID returning HTTP 302 to `/list-opportunities` (HTML, not a booklet file). The purchase action destination was not verified and is deliberately absent from the record.

### Manual desktop checklist

1. Open [isolated preview](http://127.0.0.1:8082/?view=opportunities&q=01-26-017001-42008). Select the single matching opportunity and open its details.
2. Confirm Arabic RTL, Ahda Text, dark design and readable document card.
3. Confirm the card says `رابط تحميل الكراسة غير متاح حاليًا` and offers `عرض الفرصة لدى المصدر الرسمي`; it must not offer a booklet download.
4. Confirm there is no published `1500` amount, currency, direct attachment URL, or verified purchase URL.
5. Open the official-page link and confirm it lands on the exact opportunity, not the general list.
6. Separately inspect the official page's current lifecycle/status, exact date labels, booklet section, purchase action destination, attachment destination and any explicit currency. Do not sign in, purchase, or submit an application. If expired, mark historical and stop publication.

### Manual mobile checklist

1. Open the same preview URL on a mobile viewport or device and open Master 597 details.
2. Confirm RTL order, Ahda Text, legible text, no horizontal overflow, and that the document note and both action labels remain visible and tappable.
3. Confirm opening the source page takes the user to the exact opportunity and repeat the lifecycle/currency checks above.

## Deployment and rollback

See [controlled-deployment-plan.md](controlled-deployment-plan.md). The current inspected rollback images are the API and frontend base digests in the table above. Migration rollback is not part of image rollback; keep additive migration 0027. Remove only a never-published DRAFT with the targeted SQL. If ever approved/public, revoke and preserve it.

## Safety and outstanding gates

| Gate | Status |
|---|---|
| Candidate image isolation / exact production base | PASS |
| Disposable 0027-compatible DB / exact record and API | PASS |
| SQL idempotency and targeted DRAFT rollback | PASS |
| Security and focused platform regressions | PASS |
| Production deployment / migration / insert / sync / restart | NOT PERFORMED; zero mutations |
| Production documents published | 0 |
| Preview browser acceptance / screenshots | PENDING_USER_BROWSER_REVIEW |
| Official-page normal-browser verification | PENDING_USER_BROWSER_REVIEW |
| Explicit per-record production publication approval | PENDING |

The preview is available at `http://127.0.0.1:8082/`. The isolated preview containers and disposable database are running; the current live app at port 8080 was not changed.

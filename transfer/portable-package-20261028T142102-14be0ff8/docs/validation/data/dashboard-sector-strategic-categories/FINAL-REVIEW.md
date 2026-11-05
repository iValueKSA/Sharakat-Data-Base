# Dashboard Tourism and Agriculture Buckets — Final Review

**Status:** COMPLETE  
**Review date:** 2026-10-21  
**Scope:** Dashboard sector chart and its canonical filters only

## Root cause and current behavior

The API aggregation in `app/main.py` groups every current Master opportunity by its canonical sector and returns all buckets in `by_sector`. The dashboard renderer in `app/static/data-dashboard.js` applies a top-seven display limit and folds the remaining non-strategic sectors into the clickable `أخرى` aggregate. Without exceptions, low-count sectors such as Tourism and Agriculture would fall into that tail.

The current served dashboard implementation already contains the required correction: `sector:tourism` and `sector:agriculture` are pinned outside the top-seven ranking and excluded from tail aggregation. The renderer gives them distinct colors and retains each canonical ID on its own chart control. The current live frontend serves this behavior. No application source, business data, or sector assignment needed modification during this verification.

## Live reconciliation

| Measure | Live result |
|---|---:|
| Current dashboard opportunities | 525 |
| API sector bucket total | 525 |
| Tourism | 1 |
| Agriculture | 1 |
| Canonical `أخرى` | 9 |
| Displayed `أخرى` including tail | 19 |
| Remaining tail included in `أخرى` | 10 |
| Chart total | 525 |

The ten tail opportunities are the logistics (4), education (3), and healthcare (3) buckets. Tourism and Agriculture are separate chart entries and absent from the aggregate's member IDs. Thus `أخرى` is 9 + 10 = 19 and the displayed chart sums to 525 without double counting.

The API filters `sector:tourism` and `sector:agriculture` each return one Master, with IDs `AH-20261011132402-2e8227c3` and `AH-20261011132403-f9ccf144`, respectively. Clicking each chart column selected the matching canonical filter and showed only that Arabic sector in the opportunity list.

## Browser verification

Playwright checked 1920×1080, 1440×900, 1366×768, 768×900, and 390×844. Both Arabic labels and their live counts remained visible at every size; Western digits and distinct sector colors were used; RTL was active; chart labels stayed within the SVG; and neither the page nor body had horizontal overflow. The chart click filters passed and the browser reported no page errors.

Detailed evidence is in `playwright-results.json`; screenshots are `dashboard-1440x900.png` and `dashboard-390x844.png`.

## Data safety and services

This task performed no application or database writes. Final live counts were 546 opportunity rows (525 current Masters), 3,137 source rows, and 662 review rows (558 open). Sector assignments modified: 0. Master/source identities changed: 0. Reviews created/resolved: 0. Manual source sync started: false.

Natural scheduled jobs 405 and 406 completed before this verification window, each reporting 0 new and 0 updated records. A pre-existing job 212 was observed with status `RUNNING`, started on 2026-10-13, and no finish time; it was left untouched. No service was restarted.

## Regression

The full project suite passed: **288 passed, 0 failed** (22 existing deprecation warnings). Tests ran in a disposable container with networking disabled and an SQLite file under `/tmp`, separate from the live PostgreSQL database. The initial unrestricted collection attempt encountered duplicate test module names in archived `tmp/` copies; the successful run explicitly collected `tests/` only.

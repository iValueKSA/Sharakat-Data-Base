# Deadline card single-row layout validation

## Result

`DEADLINE_CARD_5_COLUMN_LAYOUT_FIX = COMPLETE`

The live dashboard now renders the deadline distribution as five equal-width CSS Grid columns in one row. The fifth “بدون موعد محدد” bucket stays in the same row at all five tested viewports. RTL order is preserved: the first bucket is at the right, followed toward the left by the remaining four.

## Live measurements

| Viewport | Columns | Rows | Card height | Equal columns | Baseline aligned | Page overflow |
|---|---:|---:|---:|---|---|---|
| 1920×1080 | 5 | 1 | 104 px | Yes | Yes | No |
| 1440×900 | 5 | 1 | 104 px | Yes | Yes | No |
| 1366×768 | 5 | 1 | 104 px | Yes | Yes | No |
| 768×900 | 5 | 1 | 104 px | Yes | Yes | No |
| 390×844 | 5 | 1 | 102 px | Yes | Yes | No |

The previous live build measured 167 px on desktop/tablet and 165 px at 390 px. The compact card is 38% shorter at desktop/tablet. All labels, counts, and five colors are visible; labels may wrap inside their own narrow columns on mobile. The 36 px maximum bar width keeps the bars proportional and balanced.

## Data and behavior preserved

The live dashboard still returns `0 / 21 / 39 / 44 / 370`, with total and active count both 474. The colors remain `#378AA4`, `#006E61`, `#C39853`, `#7953A9`, and `#989899`. Bucket mapping is verified against the API key, Arabic label, count, and color. No API, classification, deadline calculation, active status, drill-down, or export behavior changed. Changes are limited to this card's CSS and its static label/count rendering plus asset cache versions.

Playwright passed on all five viewports. It reported zero JavaScript errors, zero unexpected HTTP errors, no label clipping, no overlap, and no horizontal overflow. The frontend-only asset was rebuilt and deployed; API, database, worker, and scheduler were not restarted. No business data was written and no manual source sync was started.

## Evidence

- `deadline-card-single-row-playwright.json`
- `deadline-card-layout-comparison.json`
- `screenshots/deadline-card-1920x1080.png`
- `screenshots/deadline-card-1440x900.png`
- `screenshots/deadline-card-1366x768.png`
- `screenshots/deadline-card-768x900.png`
- `screenshots/deadline-card-390x844.png`

```ini
FIVE_COLUMNS_SINGLE_ROW = TRUE
SECOND_ROW_CREATED = FALSE
COLUMN_WIDTHS_EQUAL = TRUE
BAR_BASELINE_ALIGNED = TRUE
CARD_HEIGHT_MATCHES_PREVIOUS_DESIGN = TRUE
ALL_5_LABELS_VISIBLE = TRUE
FIVE_DISTINCT_COLORS = TRUE
BAR_LABEL_VALUE_MAPPING = CORRECT
BUCKET_VALUES_CHANGED = FALSE
DEADLINE_BUSINESS_LOGIC_CHANGED = FALSE
JAVASCRIPT_ERRORS = 0
HORIZONTAL_PAGE_OVERFLOW = FALSE
OTHER_DASHBOARD_COMPONENTS_CHANGED = FALSE
BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
```

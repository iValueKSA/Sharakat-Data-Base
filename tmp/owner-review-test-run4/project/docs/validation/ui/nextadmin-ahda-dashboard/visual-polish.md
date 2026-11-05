# AHDA dashboard visual polish

**Status:** `NEXTADMIN_AHDA_VISUAL_POLISH_COMPLETE`  
**Date:** 2026-10-14  
**Scope:** Visual refinement of the existing Arabic data dashboard, responsive layout, and browser regression checks.

## Summary

This pass refined the dashboard's card hierarchy, ranked charts, time series, and map presentation while retaining the AHDA identity, Arabic content, and RTL layout. The chart and map continue to use the existing dashboard API and active dashboard filters. No opportunity records, review records, source settings, API behavior, export behavior, or ingestion settings were changed.

The visual structure was compared with the live NextAdmin analytics demo and the checked-in NextAdmin reference source. The pass adopts its clear card boundaries, chart spacing, grid lines, axes, and hover feedback while retaining the AHDA palette and Arabic presentation.

## A. Problems found before the pass

- KPI content competed for attention: icon/action decoration, title, number, and note lacked a clear reading order, and the cards were too short for some Arabic notes.
- Long labels had insufficient width constraints and could push or clip card content. Long opportunity names could expand their grid track.
- Several ranking charts were bare SVG bars without a numeric scale, grid, or clear hover feedback. RTL text anchoring placed some Arabic labels poorly; dense sector/type distributions were hard to scan in one long column.
- Trend charts had sparse axis context and similarly weak interaction feedback. The activity chart had no classified data and needed a truthful empty state.
- Map controls and its summary needed stronger hierarchy as a primary dashboard section.

The comparison screenshots show the difference in structure: NextAdmin groups its analytics under explicit chart-card headers with scale, grid, and chart-specific spacing; the original AHDA visualizations were closer to unframed bar lists. The final AHDA cards now use that same deliberate chart-container structure while preserving the Arabic RTL reading direction.

## What changed

### Cards and page layout

- Reordered the KPI content into label, value, and explanatory context; moved decorative icons out of the reading order and removed repeated visible detail-action text.
- Set KPI minimum heights to 158px on desktop, 150px at tablet widths, and 151px on mobile. Labels and explanatory text wrap inside the cards.
- Kept filters, map controls, map summary figures, and dashboard cards within the existing responsive grid. Long opportunity titles and category names no longer expand their parent card.
- Clarified unknown statuses with the Arabic label **غير محددة**.
- Preserved RTL alignment, AHDA colors, and the existing Arabic navigation and labels.

### Charts

- Rebuilt the ranked analytics charts around responsive SVG dimensions, RTL-safe Arabic labels, category wrapping, a readable numeric scale, subtle vertical grid lines, sorted bars, and hover/focus tooltips with counts and shares.
- Split the dense sector and opportunity-type distributions into two columns on desktop and one column on mobile. The type chart now has enough desktop width for its 20 categories.
- Added explicit scale/grid treatment and responsive sizing to the timeline and deadline trend. Keyboard and pointer activation of filterable chart rows remain available.
- Kept the chart states data-backed. Activity currently has no classified values, so it displays an empty-state message. The opportunity timeline currently has one month of data; the single point is shown without fabricating a trend.
- Dense charts can scroll within their own chart area on narrow screens; this does not cause page-level horizontal scrolling.

#### Chart-by-chart treatment

Dimensions below are the rendered chart-container dimensions at 1440×900 after applying the default, unfiltered dashboard state. Ranking axes list the number of visible tick labels; the single-series charts do not need a separate categorical legend.

| Chart | Previous visual issue | New treatment and 1440×900 dimensions | Tooltip and scale | Responsive behavior |
| --- | --- | --- | --- | --- |
| Sector (`dashBySector`) | 20 long categories crowded a single list; no numeric scale or clear chart hover state. | Two sorted columns with wrapped RTL labels, restrained tracks, colored values, and shared header structure; **592×505px**, 20 categories. | Custom label/count/share tooltip on hover or keyboard focus; two 5-tick numeric scales. | Two columns on desktop, one column on narrow screens; mobile chart region can scroll internally. |
| Status (`dashByStatus`) | Status bars lacked scale and hover context; unknown status wording was unclear. | Compact six-row sorted chart, including the Arabic unknown label; **408×337px**, 6 categories. | Custom label/count/share tooltip; 5-tick scale. | Fits the single-column tablet/mobile dashboard grid; labels wrap. |
| Source (`dashBySource`) | Long source names were difficult to associate with values and lacked axis context. | Ten-row ranked chart with wrapped Arabic source names and consistent spacing; **500×475px**, 10 categories. | Custom tooltip; 5-tick scale. | Labels wrap instead of widening the card; chart remains in the responsive card grid. |
| Owner (`dashByOwner`) | Owner comparisons had weak value context and no chart-level hover feedback. | Seven-row ranked chart with consistent labels/tracks; **500×335px**, 7 categories. | Custom tooltip; 5-tick scale. | Card collapses into the single-column layout without changing the data. |
| Activity (`dashByActivity`) | No classified activity data to draw; empty chart area could imply a broken widget. | Replaced the empty plot with an explicit Arabic no-data message; no SVG/dimensions while empty. | No tooltip or numeric axis while there are no points; no misleading legend. | Message stays within its card at all viewport sizes. |
| Opportunity type (`dashByType`) | 20 categories made the old chart overly tall and dense, with no scale. | Two balanced ranked columns with RTL wrapping; **684×505px**, 20 categories. | Custom tooltip; two 5-tick numeric scales. | Two columns on desktop, one on mobile with the chart contained in its card. |
| Location (`dashByLocation`) | Location list had no scale and risked long place names competing with bars. | Eight-row ranked chart, wrapped Arabic place names, and consistent bar scale; **390×469px**, 8 categories. | Custom tooltip; 5-tick scale. | Uses the standard card grid; chart area scrolls internally on narrow screens if needed. |
| Opportunity timeline (`dashTimeline`) | Sparse history looked like an unfinished plot and gave little axis context. | Explicit grid and labeled numeric scale; at the current single-month state it shows one centered point and baseline without a connecting line or filled area; **402×221px**, 1 month. | Custom period/count tooltip; 3 numeric tick labels. | Responsive container with a narrow-screen chart viewport; no synthetic periods are added. |
| Deadline trend (`dashDeadlineTrend`) | Multi-period deadline data appeared as an unstructured series with weak reading cues. | Responsive area/line chart with 13 observed periods, grid, scale and period hit targets; **592×264px**, 13 periods. | Custom period/count tooltip; 3 numeric tick labels. | Adapts to card width; dense periods can scroll within the chart on mobile. |

Chart rows that support filtering remain keyboard-focusable buttons and activate the same existing dashboard filters. Custom tooltips are rendered inside their chart cards and do not create additional API calls.

### Map

- Gave the map and its controls, display-mode toggle, and six summary metrics a consistent AHDA card treatment and more usable responsive height.
- Retained the existing Leaflet point/cluster and heatmap modes, current filter integration, and marker-to-opportunity drilldown.
- The current API reports 175 exact mapped records, 114 unmapped records, and one record outside the local reference boundary. That boundary is a local reference only, not an official cadastral or planning boundary; see [the geography data notes](../../../../app/static/geo/README.md).

## Validation

The final browser run returned HTTP 200, produced 18 screenshots, and reported no browser console/page errors. It covered these viewport sizes:

| Viewport | Page horizontal overflow | KPI height |
| --- | --- | ---: |
| 1920 × 1080 | None | 158px |
| 1440 × 900 | None | 158px |
| 1366 × 768 | None | 158px |
| 768 × 900 | None | 150px |
| 390 × 844 | None | 151px |

Card-width overflow, KPI text overflow, and SVG-label overflow checks were empty at all five sizes. The mobile chart containers keep their own limited horizontal scrolling for dense chart content.

The browser interaction checks passed for custom chart tooltips; heatmap and cluster toggles; CSV and XLSX exports; global filters updating both dashboard and map; reset and chart keyboard drilldown; opportunity list and detail; map marker and KPI drilldown; source health; guest/admin control visibility; and local admin login/role controls. These checks exercised the existing UI and API without changing business records.

The post-build platform check reported Docker, PostgreSQL, Redis, API, frontend, worker, and scheduler running, with readiness `RUNNING` and `/api/health` returning `ok`. The dashboard API still reports 289 opportunities and 10 sources. Geography still reports 175 exact mapped, 114 unmapped, and one outside the local boundary. No database migration or data synchronization was run. The pre-existing 122-test validation belongs to the earlier analytics milestone; this visual pass used the targeted browser regression above and did not rerun backend tests.

## Screenshots

All final screenshots and the machine-readable QA summary are in [`visual-polish/screenshots/`](visual-polish/screenshots/):

- `dashboard-1920x1080-top.png`, `dashboard-1440x900-top.png`, `dashboard-1366x768-top.png`, and `dashboard-768x900-top.png` — dashboard header, filters, KPIs, and map beginning.
- `dashboard-chart-*.png` and `dashboard-map-*.png` — chart and map sections at desktop/tablet viewports.
- `dashboard-mobile-kpis-390x844.png`, `dashboard-mobile-sector-390x844.png`, and `dashboard-mobile-timeline-390x844.png` — mobile layout and scrollable chart treatment.
- `dashboard-categories-1440x900.png` and `chart-tooltip-1440x900.png` — dense category charts and tooltip detail.
- `nextadmin-analytics-1440x900.png` — live NextAdmin visual reference used for comparison.
- `qa-summary.json` — viewport, overflow, chart, interaction, and screenshot results.

The five requested sizes have visual evidence in the linked directory: 1920×1080 top/chart/map; 1366×768 top/chart; 1440×900 top/chart/map; 768×900 top/chart/map; and 390×844 KPI, sector, and timeline captures. I reviewed the rendered desktop, tablet, and mobile captures after the final CSS build, including the live NextAdmin reference image.

## E. Visual comparison

The final visual uses the NextAdmin patterns that matter to chart readability: distinct card boundaries, consistent card padding and headings, an explicit plotting area, readable scales, subtle grid lines, and contextual tooltips. Its two-column handling for 20-item distributions manages density in a way that parallels the reference's larger chart cards and separate device visualization. KPI hierarchy and whitespace are now deliberate, and the AHDA map receives a full dashboard section rather than a small chart-sized slot. The same visual tier is retained in Arabic RTL, with AHDA typography and colors rather than copied NextAdmin content or controls.

## F. Regression and data preservation

All interaction results above passed in the browser run. The final status check also confirmed all platform services, including worker and scheduler, were running and API readiness was healthy. No scheduled sync was triggered, and the local Start Platform script was not edited or invoked because the platform was already running. No business data or reviews were modified; API totals remain at 289 opportunities and 10 sources.

The prior analytics milestone report at [visual-analytics.md](visual-analytics.md) remains unchanged.

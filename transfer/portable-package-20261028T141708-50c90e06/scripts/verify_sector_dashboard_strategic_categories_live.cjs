const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const fs = require("fs");
const path = require("path");

const base = "http://localhost:8080";
const artifactDir = path.join(process.cwd(), "docs/validation/data/dashboard-sector-strategic-categories");
const viewportSizes = [[1920, 1080], [1440, 900], [1366, 768], [768, 900], [390, 844]];
const assert = (condition, message) => { if (!condition) throw new Error(message); };

(async () => {
  fs.mkdirSync(artifactDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe" });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const result = { started_at: new Date().toISOString(), base_url: base, viewport_sizes: viewportSizes, scenarios: {}, errors };
    await page.goto(`${base}/?view=data-dashboard`, { waitUntil: "networkidle" });
    await page.locator("#rdSectorChart .rd-column").first().waitFor({ state: "visible", timeout: 15000 });
    const api = await page.evaluate(async () => {
      const [dashboardResponse, filtersResponse] = await Promise.all([fetch("/api/data-dashboard"), fetch("/api/filters")]);
      return { dashboard: await dashboardResponse.json(), filters: await filtersResponse.json() };
    });
    const sectors = api.dashboard.by_sector || [];
    const counts = Object.fromEntries(sectors.map(row => [row.canonical_id, Number(row.count)]));
    const total = Number(api.dashboard.kpis.total);
    const tourism = sectors.find(row => row.canonical_id === "sector:tourism");
    const agriculture = sectors.find(row => row.canonical_id === "sector:agriculture");
    assert(tourism?.name === "السياحة", "API does not expose the canonical Arabic Tourism bucket");
    assert(agriculture?.name === "الزراعة", "API does not expose the canonical Arabic Agriculture bucket");
    assert(sectors.reduce((sum, row) => sum + Number(row.count || 0), 0) === total, "API sector buckets do not reconcile to dashboard opportunities");
    const other = sectors.find(row => row.canonical_id === "sector:other");
    assert(other, "API canonical Other bucket is missing");

    const chart = page.locator("#rdSectorChart");
    const tourismBar = chart.locator('[data-dash-filter="sector"][data-dash-value="sector:tourism"]');
    const agricultureBar = chart.locator('[data-dash-filter="sector"][data-dash-value="sector:agriculture"]');
    await tourismBar.waitFor({ state: "visible", timeout: 15000 });
    await agricultureBar.waitFor({ state: "visible", timeout: 15000 });
    const visible = await page.evaluate(() => {
      const rows = [...document.querySelectorAll("#rdSectorChart .rd-column")];
      const aggregate = rows.find(row => row.hasAttribute("data-dash-values"));
      return {
        labels: rows.map(row => row.querySelector(".rd-column-label")?.textContent.replace(/\s+/g, " ").trim()),
        bars: rows.map(row => ({ id: row.dataset.dashValue || null, name: row.querySelector(".rd-column-label")?.textContent.replace(/\s+/g, " ").trim(), count: Number(row.querySelector(".rd-column-value")?.textContent.replace(/,/g, "")), aria: row.getAttribute("aria-label"), color: row.querySelector(".rd-column-bar")?.style.getPropertyValue("--rd-column-color") })),
        aggregateValues: aggregate ? JSON.parse(aggregate.dataset.dashValues) : [],
        aggregateCount: aggregate ? Number(aggregate.querySelector(".rd-column-value")?.textContent.replace(/,/g, "")) : null,
        chartTotalLabel: document.querySelector("#rdSectorChart .rd-columns-svg")?.getAttribute("aria-label"),
        direction: getComputedStyle(document.documentElement).direction,
      };
    });
    const visibleById = Object.fromEntries(visible.bars.filter(row => row.id).map(row => [row.id, row]));
    for (const [id, label, count] of [["sector:tourism", "السياحة", counts["sector:tourism"]], ["sector:agriculture", "الزراعة", counts["sector:agriculture"]]]) {
      const bar = visibleById[id];
      assert(bar, `${label} is aggregated or absent in the chart`);
      assert(bar.name === label && bar.count === count && bar.aria.includes(label), `${label} display count or Arabic label mismatches API`);
      assert(!visible.aggregateValues.includes(id), `${label} is included in the clickable Other aggregate`);
    }
    assert(visible.chartTotalLabel?.includes(String(total)), "Chart total does not match the API total");
    assert(visible.direction === "rtl", "Dashboard document direction is not RTL");
    assert(new Set(visible.bars.map(row => row.color)).size === visible.bars.length, "Displayed sector colors are not distinct");

    const filterResults = {};
    for (const [id, label, row] of [["sector:tourism", "السياحة", tourism], ["sector:agriculture", "الزراعة", agriculture]]) {
      const list = await page.evaluate(async sector => (await fetch(`/api/opportunities?sector=${encodeURIComponent(sector)}&limit=500`)).json(), id);
      assert(Number(list.total) === Number(row.count), `${label} API filter total differs from chart/API bucket`);
      assert(list.items.length === Number(row.count) && list.items.every(item => item.sector === label), `${label} API filter returned non-canonical sectors`);
      const expectedIds = list.items.map(item => item.canonical_id).sort();
      await page.locator(`#rdSectorChart [data-dash-filter="sector"][data-dash-value="${id}"]`).click();
      await page.waitForURL(/view=opportunities/);
      await page.waitForFunction(value => document.querySelector("#sectorFilter")?.value === value, id);
      await page.waitForFunction(expected => document.querySelector("#tableCount")?.innerText.includes(`من ${expected}`), Number(row.count));
      const ui = await page.evaluate(() => ({
        count: document.querySelector("#tableCount")?.innerText || "",
        sector: document.querySelector("#sectorFilter")?.value || "",
        ids: [...document.querySelectorAll("#opportunityRows tr")].map(tr => tr.querySelector('[data-column="opportunity"] small')?.textContent?.trim()).filter(Boolean),
        sectors: [...document.querySelectorAll('#opportunityRows [data-column="sector"]')].map(td => td.textContent.trim()),
      }));
      assert(ui.sector === id && ui.sectors.length > 0 && ui.sectors.every(value => value === label), `${label} chart click did not keep the canonical sector filter`);
      const firstPage = await page.evaluate(() => [...document.querySelectorAll("#opportunityRows tr")].map(tr => tr.querySelector("[data-detail]")?.dataset.detail).filter(Boolean));
      assert(firstPage.length <= expectedIds.length, `${label} table returned more rows than the filtered API universe`);
      filterResults[id] = { label, api_count: Number(row.count), api_master_ids: expectedIds, chart_click: "PASSED", selected_filter: ui.sector, visible_table_sector_labels: [...new Set(ui.sectors)], table_count: ui.count, first_page_rows: firstPage.length };
      await page.goto(`${base}/?view=data-dashboard`, { waitUntil: "networkidle" });
      await page.locator("#rdSectorChart .rd-column").first().waitFor({ state: "visible", timeout: 15000 });
    }

    const viewportResults = [];
    for (const [width, height] of viewportSizes) {
      await page.setViewportSize({ width, height });
      await page.goto(`${base}/?view=data-dashboard`, { waitUntil: "networkidle" });
      await page.locator("#rdSectorChart .rd-column").first().waitFor({ state: "visible", timeout: 15000 });
      const metrics = await page.evaluate(() => {
        const card = document.querySelector(".rd-sector-card");
        const chart = document.querySelector("#rdSectorChart");
        return {
          width: innerWidth,
          document_scroll_width: document.documentElement.scrollWidth,
          body_scroll_width: document.body.scrollWidth,
          direction: getComputedStyle(document.documentElement).direction,
          card_width: Math.round(card.getBoundingClientRect().width),
          chart_width: Math.round(chart.getBoundingClientRect().width),
          visible_labels: [...chart.querySelectorAll(".rd-column-label")].map(el => el.textContent.replace(/\s+/g, " ").trim()),
          tourism: chart.querySelector('[data-dash-value="sector:tourism"]')?.getAttribute("aria-label"),
          agriculture: chart.querySelector('[data-dash-value="sector:agriculture"]')?.getAttribute("aria-label"),
          western_digits: /[0-9]/.test(chart.innerText) && !/[٠-٩۰-۹]/.test(chart.innerText),
          chart_text_overflow: [...chart.querySelectorAll(".rd-column-label")].some(el => {
            const box = el.getBoundingClientRect();
            const svgBox = el.ownerSVGElement.getBoundingClientRect();
            return box.left < svgBox.left - 1 || box.right > svgBox.right + 1;
          }),
        };
      });
      assert(metrics.document_scroll_width <= width && metrics.body_scroll_width <= width, `Horizontal page overflow at ${width}px`);
      assert(metrics.direction === "rtl", `RTL failed at ${width}px`);
      assert(metrics.tourism?.includes("السياحة") && metrics.agriculture?.includes("الزراعة"), `Strategic labels are missing at ${width}px`);
      assert(metrics.visible_labels.includes("السياحة") && metrics.visible_labels.includes("الزراعة"), `Sector chart labels are absent at ${width}px`);
      assert(metrics.western_digits, `Western digits are missing at ${width}px`);
      assert(!metrics.chart_text_overflow, `Chart labels overflow at ${width}px`);
      viewportResults.push({ width, height, rtl: true, western_digits: true, no_horizontal_page_overflow: true, tourism_visible: true, agriculture_visible: true, chart_labels_within_svg: true, chart_width: metrics.chart_width });
      if (width === 1440 || width === 390) await page.screenshot({ path: path.join(artifactDir, `dashboard-${width}x${height}.png`), fullPage: true });
    }

    result.scenarios = {
      opportunity_total: total,
      api_sector_bucket_sum: sectors.reduce((sum, row) => sum + Number(row.count || 0), 0),
      tourism_count: Number(tourism.count),
      agriculture_count: Number(agriculture.count),
      api_tourism_present: true,
      api_agriculture_present: true,
      chart_tourism_separate: true,
      chart_agriculture_separate: true,
      tourism_in_other: visible.aggregateValues.includes("sector:tourism"),
      agriculture_in_other: visible.aggregateValues.includes("sector:agriculture"),
      chart_other_display_count: visible.aggregateCount,
      api_canonical_other_count: Number(other.count),
      expected_tail_count_in_other: Number(visible.aggregateCount) - Number(other.count),
      chart_reconciliation: Number(visible.bars.reduce((sum, row) => sum + Number(row.count || 0), 0)) === total,
      chart_label_total: visible.chartTotalLabel,
      chart_click_filters: filterResults,
      visible_chart: visible,
    };
    assert(result.scenarios.chart_reconciliation, "Displayed chart buckets do not reconcile to all opportunities");
    assert(!result.scenarios.tourism_in_other && !result.scenarios.agriculture_in_other, "Tourism or Agriculture is grouped in Other");
    assert(result.scenarios.chart_other_display_count === Number(other.count) + result.scenarios.expected_tail_count_in_other, "Other aggregation is not based on the canonical Other bucket and the undisplayed tail");
    assert(result.scenarios.expected_tail_count_in_other >= 0, "Other tail total is negative");
    assert(errors.length === 0, `Browser console errors: ${JSON.stringify(errors)}`);
    result.viewport_checks = viewportResults;
    result.finished_at = new Date().toISOString();
    result.result = "PASS";
    fs.writeFileSync(path.join(artifactDir, "playwright-results.json"), JSON.stringify(result, null, 2), "utf8");
    process.stdout.write(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.stack || error); process.exit(1); });

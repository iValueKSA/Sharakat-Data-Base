const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const fs = require("fs");
const path = require("path");

const base = "http://localhost:8080";
const artifactDir = path.join(process.cwd(), "docs/validation/data/sector-inference-status-consolidation");
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
    await page.goto(`${base}/?view=opportunities`, { waitUntil: "networkidle" });
    await page.locator("#opportunityRows tr").first().waitFor({ state: "visible", timeout: 15000 });
    const api = await page.evaluate(async () => {
      const [filtersResponse, dashboardResponse] = await Promise.all([fetch("/api/filters"), fetch("/api/data-dashboard")]);
      return { filters: await filtersResponse.json(), dashboard: await dashboardResponse.json() };
    });
    assert(api.filters.statuses.includes("متاحة"), "Available status is missing from user-facing filters");
    assert(!api.filters.statuses.includes("منشورة"), "Published appears as a distinct user-facing status");
    assert(Object.keys(api.filters.option_ids.statuses).filter(label => label === "متاحة").length === 1, "Available status filter is duplicated");
    const statusBuckets = Object.fromEntries(api.dashboard.by_status.map(row => [row.canonical_id, Number(row.count)]));
    const statusSum = Object.values(statusBuckets).reduce((sum, count) => sum + count, 0);
    assert(statusSum === Number(api.dashboard.global_total), `Status buckets ${statusSum} do not reconcile to ${api.dashboard.global_total}`);
    assert(!api.dashboard.by_status.some(row => row.canonical_id === "status:published" || row.name === "منشورة"), "Published is present in dashboard status buckets");
    const availableId = api.filters.option_ids.statuses["متاحة"];
    const availableStatus = api.dashboard.by_status.find(row => row.canonical_id === availableId);
    const legacyPublished = await page.evaluate(async () => (await fetch("/api/opportunities?status=PUBLISHED&limit=500")).json());
    assert(availableStatus && Number(availableStatus.count) === legacyPublished.total, "PUBLISHED compatibility filter does not match AVAILABLE count");
    assert(legacyPublished.items.every(item => item.status === "متاحة"), "Legacy PUBLISHED filter returns a non-canonical user-facing status");
    await page.locator("#statusFilter").selectOption(availableId);
    await page.waitForFunction(expected => document.querySelector("#tableCount")?.innerText.includes(`من ${expected}`), Number(availableStatus.count));
    await page.locator("#opportunityRows tr").first().waitFor({ state: "visible" });
    const availableBadges = await page.locator('#opportunityRows [data-column="status"]').allInnerTexts();
    assert(availableBadges.length > 0 && availableBadges.every(label => label.trim() === "متاحة"), "Available status badges are incorrect");
    const tableCount = await page.locator("#tableCount").innerText();
    assert(tableCount.includes(String(availableStatus.count)), "Available filter count is not shown in the list");
    result.scenarios.status = {
      filters: api.filters.statuses,
      available_filter_id: availableId,
      available_count: Number(availableStatus.count),
      status_bucket_sum: statusSum,
      dashboard_total: Number(api.dashboard.global_total),
      published_bucket_count: 0,
      legacy_published_filter_total: Number(legacyPublished.total),
      available_badges: [...new Set(availableBadges.map(label => label.trim()))],
      available_badge_rows_checked: availableBadges.length,
      table_count: tableCount,
    };

    const sectors = api.dashboard.by_sector;
    const sectorCounts = Object.fromEntries(sectors.map(row => [row.canonical_id, Number(row.count)]));
    for (const [key, arabic] of [["sector:tourism", "السياحة"], ["sector:agriculture", "الزراعة"]]) {
      const row = sectors.find(item => item.canonical_id === key);
      assert(row, `${arabic} is missing from the canonical sector dashboard data`);
      const list = await page.evaluate(async sector => (await fetch(`/api/opportunities?sector=${encodeURIComponent(sector)}&limit=500`)).json(), key);
      assert(Number(row.count) === Number(list.total), `${arabic} dashboard count ${row.count} does not match sector Master count ${list.total}`);
      assert(list.items.every(item => item.sector === arabic), `${arabic} sector filter returned a different canonical sector`);
      result.scenarios[key] = { label: arabic, count: Number(row.count), list_count: Number(list.total), filter_exact: true };
    }
    const tourismCount = sectorCounts["sector:tourism"];
    const agricultureCount = sectorCounts["sector:agriculture"];
    assert(!sectors.some(row => row.canonical_id === "sector:other" && row.aggregate && row.member_values?.includes("sector:tourism")), "Tourism is aggregated into Other");
    assert(!sectors.some(row => row.canonical_id === "sector:other" && row.aggregate && row.member_values?.includes("sector:agriculture")), "Agriculture is aggregated into Other");
    assert(tourismCount > 0 && agricultureCount > 0, "Expected populated Tourism and Agriculture buckets are missing");

    const viewportResults = [];
    for (const [width, height] of viewportSizes) {
      await page.setViewportSize({ width, height });
      await page.goto(`${base}/?view=opportunities`, { waitUntil: "networkidle" });
      await page.locator("#opportunityRows tr").first().waitFor({ state: "visible", timeout: 15000 });
      const metrics = await page.evaluate(() => ({
        width: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        direction: getComputedStyle(document.documentElement).direction,
        countText: document.querySelector("#tableCount")?.innerText || "",
        statusOptions: [...document.querySelectorAll("#statusFilter option")].map(option => option.textContent.trim()),
      }));
      assert(metrics.scrollWidth <= width, `Horizontal overflow at ${width}px: ${metrics.scrollWidth}px`);
      assert(metrics.direction === "rtl", `RTL is not active at ${width}px`);
      assert(/[0-9]/.test(metrics.countText), `Western digits are missing at ${width}px`);
      assert(metrics.statusOptions.includes("متاحة") && !metrics.statusOptions.includes("منشورة"), `Status filter labels mismatch at ${width}px`);
      viewportResults.push({ width, height, horizontal_overflow: false, rtl: true, western_digits: true });
      if (width === 390 || width === 1440) await page.screenshot({ path: path.join(artifactDir, `opportunities-${width}x${height}.png`), fullPage: true });
    }

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${base}/?view=data-dashboard`, { waitUntil: "networkidle" });
    for (const [key, arabic] of [["sector:tourism", "السياحة"], ["sector:agriculture", "الزراعة"]]) {
      const bar = page.locator(`#rdSectorChart [data-dash-filter="sector"][data-dash-value="${key}"]`);
      await bar.waitFor({ state: "visible", timeout: 15000 });
      const labelText = await bar.getAttribute("aria-label");
      assert(labelText.includes(arabic), `Dashboard bar label does not expose ${arabic}`);
      await bar.click();
      await page.waitForURL(/view=opportunities/);
      await page.waitForFunction(value => document.querySelector("#sectorFilter")?.value === value, key);
      const expected = key === "sector:tourism" ? tourismCount : agricultureCount;
      await page.waitForFunction(value => document.querySelector("#tableCount")?.innerText.includes(`من ${value}`), expected);
      const count = await page.locator("#tableCount").innerText();
      assert(count.includes(String(expected)), `${arabic} chart click did not filter to ${expected} opportunities: ${count}`);
      const rows = await page.locator('#opportunityRows [data-column="sector"]').allInnerTexts();
      assert(rows.length > 0 && rows.every(value => value.trim() === arabic), `${arabic} chart click returned an unexpected sector`);
      result.scenarios[key].chart_click_filter = { selected_filter: key, expected_count: expected, table_count: count, first_page_rows: rows.length, exact_sector_rows: true };
      await page.goto(`${base}/?view=data-dashboard`, { waitUntil: "networkidle" });
    }
    await page.screenshot({ path: path.join(artifactDir, "dashboard-sectors-1440x900.png"), fullPage: true });
    result.scenarios.status_chart_labels = await page.locator("#rdStatusLegend .rd-legend-row").allInnerTexts();
    assert(!result.scenarios.status_chart_labels.some(label => label.includes("منشورة")), "Published appears as a distinct dashboard legend item");
    result.scenarios.sector_dashboard_buckets = { tourism_separate: true, agriculture_separate: true, tourism_count: tourismCount, agriculture_count: agricultureCount };
    result.viewport_checks = viewportResults;
    assert(errors.length === 0, `Browser console page errors: ${JSON.stringify(errors)}`);
    result.finished_at = new Date().toISOString();
    result.result = "PASS";
    fs.writeFileSync(path.join(artifactDir, "playwright-results.json"), JSON.stringify(result, null, 2), "utf8");
    process.stdout.write(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.stack || error); process.exit(1); });

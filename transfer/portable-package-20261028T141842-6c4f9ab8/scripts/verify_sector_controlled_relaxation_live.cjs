const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const fs = require("fs");
const path = require("path");

const base = "http://localhost:8080";
const artifact = path.join(process.cwd(), "docs/validation/data/sector-controlled-relaxation/playwright-results.json");
const viewports = [[1920, 1080], [1440, 900], [1366, 768], [768, 900], [390, 844]];
const targets = [
  ["sector:unspecified", "غير محدد"],
  ["sector:tourism", "السياحة"],
  ["sector:agriculture", "الزراعة"],
  ["sector:other", "أخرى"],
];
const assert = (ok, message) => { if (!ok) throw new Error(message); };

(async () => {
  fs.mkdirSync(path.dirname(artifact), { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe" });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const result = { started_at: new Date().toISOString(), base_url: base, viewports: [], sector_counts: {}, filter_checks: [], browser_errors: errors };

    for (const [width, height] of viewports) {
      await page.setViewportSize({ width, height });
      await page.goto(`${base}/?view=data-dashboard`, { waitUntil: "networkidle" });
      await page.locator("#rdSectorChart .rd-column").first().waitFor({ state: "visible", timeout: 15000 });
      const state = await page.evaluate(async () => {
        const response = await fetch("/api/data-dashboard");
        const dashboard = await response.json();
        return {
          total: Number(dashboard.kpis.total),
          buckets: Object.fromEntries((dashboard.by_sector || []).map(row => [row.canonical_id, { label: row.name, count: Number(row.count) }])),
          direction: getComputedStyle(document.documentElement).direction,
          document_width: document.documentElement.scrollWidth,
          body_width: document.body.scrollWidth,
          viewport_width: innerWidth,
        };
      });
      assert(state.direction === "rtl", `RTL failed at ${width}x${height}`);
      assert(state.document_width <= width && state.body_width <= width, `Horizontal overflow at ${width}x${height}`);
      assert(Object.values(state.buckets).reduce((sum, row) => sum + row.count, 0) === state.total, `Sector totals fail to reconcile at ${width}x${height}`);
      result.sector_counts = { total: state.total, ...state.buckets };
      result.viewports.push({ width, height, rtl: true, no_horizontal_overflow: true, dashboard_total: state.total, sector_bucket_sum: Object.values(state.buckets).reduce((sum, row) => sum + row.count, 0) });

      await page.goto(`${base}/?view=opportunities`, { waitUntil: "networkidle" });
      await page.locator("#sectorFilter").waitFor({ state: "visible", timeout: 15000 });
      for (const [id, label] of targets) {
        const expected = state.buckets[id]?.count;
        assert(Number.isInteger(expected), `Missing dashboard bucket ${id}`);
        const option = await page.locator("#sectorFilter option").evaluateAll((options, targetLabel) => options.map(item => ({ value: item.value, label: item.textContent.trim() })).find(item => item.label === targetLabel), label);
        assert(option && option.value === id, `Missing canonical filter option ${label} at ${width}x${height}`);
        await page.locator("#sectorFilter").selectOption(id);
        await page.waitForFunction(({ id, expected, label }) => {
          const filter = document.querySelector("#sectorFilter");
          const text = document.querySelector("#tableCount")?.textContent || "";
          const digits = text.replace(/[٠-٩]/g, char => String("٠١٢٣٤٥٦٧٨٩".indexOf(char)));
          const rows = [...document.querySelectorAll('#opportunityRows [data-column="sector"]')].map(cell => cell.textContent.trim());
          return filter?.value === id && new RegExp(`من\\s*${expected}\\b`).test(digits) && rows.length > 0 && rows.every(value => value === label);
        }, { id, expected, label }, { timeout: 15000 });
        const rows = await page.locator("#opportunityRows tr").evaluateAll(rows => rows.map(row => row.querySelector('[data-column="sector"]')?.textContent.trim()).filter(Boolean));
        assert(rows.length > 0 && rows.every(value => value === label), `Filter ${label} returned sectors ${JSON.stringify(rows)} at ${width}x${height}`);
        const countText = await page.locator("#tableCount").textContent();
        result.filter_checks.push({ viewport: `${width}x${height}`, sector_id: id, label, expected_count: expected, displayed_count_text: countText.trim(), visible_rows: rows.length, returned_sector_labels: [...new Set(rows)] });
      }
    }
    assert(errors.length === 0, `Browser page errors: ${JSON.stringify(errors)}`);
    result.finished_at = new Date().toISOString();
    result.result = "PASS";
    fs.writeFileSync(artifact, JSON.stringify(result, null, 2), "utf8");
    process.stdout.write(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.stack || error); process.exit(1); });

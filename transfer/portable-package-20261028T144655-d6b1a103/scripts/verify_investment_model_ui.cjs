const fs = require("fs");
const path = require("path");
const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");

(async () => {
  const outputDir = path.resolve("docs/validation/data/investment-model-taxonomy/screenshots");
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe" });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    await page.goto("http://localhost:8080/?view=opportunities", { waitUntil: "networkidle" });
    await page.waitForFunction(() => document.querySelectorAll("#investmentModelFilter option").length > 1);
    await page.waitForFunction(() => document.querySelectorAll("#opportunityRows tr").length > 0);

    const evidence = await page.evaluate(async () => {
      const [filtersResponse, dashboardResponse] = await Promise.all([fetch("/api/filters"), fetch("/api/data-dashboard")]);
      const filters = await filtersResponse.json();
      const dashboard = await dashboardResponse.json();
      const labels = filters.investment_models || [];
      const options = labels.map(label => ({ label, id: filters.option_ids.investment_models[label], count: filters.option_counts.investment_models[label] }));
      const queryCounts = {};
      for (const option of options) {
        const response = await fetch(`/api/opportunities?${new URLSearchParams({ investment_model: option.id, limit: "500" })}`);
        const payload = await response.json();
        queryCounts[option.id] = payload.total;
      }
      const exports = {};
      for (const [id, label] of options.map(option => [option.id, option.label])) {
        const params = new URLSearchParams({ investment_model: id });
        const [csvResponse, xlsxResponse] = await Promise.all([fetch(`/api/export.csv?${params}`), fetch(`/api/export.xlsx?${params}`)]);
        const csv = await csvResponse.text();
        const xlsx = new Uint8Array(await xlsxResponse.arrayBuffer());
        exports[id] = { label, csvStatus: csvResponse.status, csvRows: Math.max(0, csv.trim().split(/\r?\n/).length - 1), csvHasCanonicalLabel: csv.includes(label), xlsxStatus: xlsxResponse.status, xlsxSignature: String.fromCharCode(...xlsx.slice(0, 2)), xlsxBytes: xlsx.byteLength };
      }
      return {
        validatedAt: new Date().toISOString(), direction: document.documentElement.getAttribute("dir"),
        viewport: { width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth },
        total: dashboard.global_total, options,
        dashboardBuckets: dashboard.by_investment_model,
        dashboardCoverage: dashboard.investment_model_coverage,
        queryCounts, exports,
      };
    });

    if (evidence.direction !== "rtl") throw new Error("The opportunity page is not RTL.");
    if (evidence.total !== 291) throw new Error(`Unexpected eligible Master count: ${evidence.total}`);
    if (evidence.viewport.scrollWidth > evidence.viewport.width) throw new Error("The opportunity page has horizontal overflow at 1920px.");
    for (const option of evidence.options) {
      if (!option.id.startsWith("investment_model:")) throw new Error(`Noncanonical model filter identity for ${option.label}: ${option.id}`);
      if (evidence.queryCounts[option.id] !== option.count) throw new Error(`Filter count/query mismatch for ${option.label}`);
      const exported = evidence.exports[option.id];
      if (exported.csvStatus !== 200 || exported.csvRows !== option.count || !exported.csvHasCanonicalLabel) throw new Error(`CSV mismatch for ${option.label}`);
      if (exported.xlsxStatus !== 200 || exported.xlsxSignature !== "PK" || exported.xlsxBytes < 1000) throw new Error(`XLSX mismatch for ${option.label}`);
    }
    const optionCounts = Object.fromEntries(evidence.options.map(item => [item.id, item.count]));
    if (optionCounts["investment_model:lease"] !== 4 || optionCounts["investment_model:eomt"] !== 1 || optionCounts["investment_model:missing"] !== 286) throw new Error("Investment Model option counts are not reconciled.");
    if (evidence.dashboardCoverage?.total !== 291 || evidence.dashboardCoverage?.canonical !== 5 || evidence.dashboardCoverage?.unspecified !== 286 || evidence.dashboardCoverage?.review !== 2) throw new Error("Dashboard coverage does not reconcile.");

    await page.locator("#investmentModelFilter").selectOption("investment_model:lease");
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("4"));
    await page.locator("#opportunityRows [data-detail]").first().click();
    await page.waitForFunction(() => document.querySelector("#modal")?.classList.contains("show"));
    const detailText = await page.locator("#modalBody").innerText();
    if (!detailText.includes("نموذج الاستثمار") || !detailText.includes("التأجير")) throw new Error("Opportunity Details does not show canonical Investment Model.");
    if (/\b(?:PPP_PROJECT|LEASE_OPPORTUNITY|BOOT|DBFOM|investment_model:)/.test(detailText)) throw new Error("A technical Investment Model enum leaked into Opportunity Details.");
    evidence.detailsHasCanonicalModel = true;
    await page.screenshot({ path: path.join(outputDir, "investment-model-lease-filter.png"), fullPage: true });
    await page.locator("#modalClose").click();
    await page.locator("#resetFilters").click();
    await page.waitForFunction(() => document.querySelector("#investmentModelFilter")?.value === "");
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("291"));
    evidence.resetWorks = true;
    evidence.screenshot = "investment-model-lease-filter.png";
    fs.writeFileSync(path.join(outputDir, "investment-model-ui-verification.json"), JSON.stringify(evidence, null, 2), "utf8");
    console.log(JSON.stringify(evidence, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

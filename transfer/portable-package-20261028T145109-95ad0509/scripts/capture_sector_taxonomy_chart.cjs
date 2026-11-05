const fs = require("fs");
const path = require("path");
const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");

(async () => {
  const outputDir = path.resolve("docs/validation/data/sector-taxonomy/screenshots");
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    await page.goto("http://localhost:8080/?view=data-dashboard", { waitUntil: "networkidle" });
    await page.waitForSelector("#rdSectorChart svg", { timeout: 15000 });
    await page.evaluate(() => document.fonts.ready);
    const chartText = await page.locator(".rd-sector-card").innerText();
    const labels = await page.locator("#rdSectorChart svg text").allTextContents();
    const apiData = await page.evaluate(async () => {
      const response = await fetch("/api/data-dashboard");
      if (!response.ok) throw new Error(`dashboard API returned ${response.status}`);
      return response.json();
    });
    const forbidden = ["قيمة مفقودة", "بقية القطاعات", "فرصة استثمارية"];
    const forbiddenInChart = forbidden.filter((label) => chartText.includes(label));
    if (forbiddenInChart.length) throw new Error(`invalid sector labels in chart: ${forbiddenInChart.join(", ")}`);
    await page.locator(".rd-sector-card").screenshot({ path: path.join(outputDir, "after-sector-chart.png") });
    fs.writeFileSync(path.join(outputDir, "after-api.json"), JSON.stringify(apiData, null, 2), "utf8");
    console.log(JSON.stringify({
      viewport: page.viewportSize(),
      chartText,
      labels,
      sectorCount: apiData.by_sector.reduce((sum, item) => sum + item.count, 0),
      total: apiData.kpis.total,
      screenshot: path.join(outputDir, "after-sector-chart.png"),
    }, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });

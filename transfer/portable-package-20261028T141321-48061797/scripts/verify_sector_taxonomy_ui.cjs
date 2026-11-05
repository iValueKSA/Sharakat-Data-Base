const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    await page.goto("http://localhost:8080/?view=opportunities", { waitUntil: "networkidle" });
    await page.waitForFunction(() => document.querySelectorAll("#opportunityRows tr").length > 0);
    const direction = await page.locator("html").getAttribute("dir");
    const sectorOptions = await page.locator("#sectorFilter option").allTextContents();
    const forbidden = ["قيمة مفقودة", "بقية القطاعات", "فرصة استثمارية"];
    if (direction !== "rtl") throw new Error(`unexpected document direction: ${direction}`);
    if (forbidden.some((label) => sectorOptions.includes(label))) throw new Error("invalid sector option remains in filter");

    await page.locator("#sectorFilter").selectOption({ label: "أخرى" });
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("من 17"));
    const otherRows = await page.locator("#opportunityRows tr").count();
    const otherSectors = await page.locator("#opportunityRows tr td:nth-child(3)").allTextContents();
    if (otherRows !== 17 || otherSectors.some((value) => value.trim() !== "أخرى")) throw new Error("canonical Other filter did not return 17 rows");

    await page.locator("#resetFilters").click();
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("من 291"));
    await page.locator("#searchInput").fill("تطوير فنادق 5 نجوم");
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("من 1"));
    const searchWorked = (await page.locator("#opportunityRows tr").count()) === 1;
    await page.locator("#resetFilters").click();
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("من 291"));

    const next = page.locator("#nextPage");
    if (await next.isDisabled()) throw new Error("next page is unexpectedly disabled");
    await next.click();
    await page.waitForFunction(() => document.querySelector("#pageSummary")?.textContent.includes("2 من"));
    await page.locator("#resetFilters").click();
    await page.waitForFunction(() => document.querySelector("#pageSummary")?.textContent.includes("1 من"));

    await page.locator("#opportunityRows [data-detail]").first().click();
    await page.waitForFunction(() => document.querySelector("#modal")?.classList.contains("show"));
    const detailText = await page.locator("#modalBody").innerText();
    if (!detailText.includes("القطاع") || !detailText.includes("النشاط")) throw new Error("detail view does not expose separate Sector and Activity fields");

    const exportChecks = await page.evaluate(async () => {
      const query = new URLSearchParams({ sector: "sector:other" });
      const csvResponse = await fetch(`/api/export.csv?${query}`);
      const csv = await csvResponse.text();
      const xlsxResponse = await fetch(`/api/export.xlsx?${query}`);
      const bytes = new Uint8Array(await xlsxResponse.arrayBuffer());
      const csvHeader = csv.replace(/^\uFEFF/, "").split(/\r?\n/)[0];
      return {
        csvStatus: csvResponse.status,
        csvHeader,
        csvRows: csv.trim().split(/\r?\n/).length - 1,
        xlsxStatus: xlsxResponse.status,
        xlsxSignature: String.fromCharCode(...bytes.slice(0, 2)),
        xlsxBytes: bytes.length,
      };
    });
    if (exportChecks.csvStatus !== 200 || exportChecks.csvRows !== 17 || !exportChecks.csvHeader.includes("القطاع") || !exportChecks.csvHeader.includes("النشاط")) throw new Error("CSV canonical sector/activity export check failed");
    if (exportChecks.xlsxStatus !== 200 || exportChecks.xlsxSignature !== "PK" || exportChecks.xlsxBytes < 1000) throw new Error("XLSX export check failed");
    const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    if (horizontalOverflow) throw new Error("page has horizontal overflow at 1920px");
    console.log(JSON.stringify({ direction, sectorOptions, otherRows, searchWorked, paginationPage: "2 ثم reset إلى 1", detailDimensions: ["القطاع", "النشاط"], exportChecks, horizontalOverflow }, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });

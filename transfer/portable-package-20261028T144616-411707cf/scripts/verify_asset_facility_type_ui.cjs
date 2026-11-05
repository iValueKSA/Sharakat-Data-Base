const fs = require("fs");
const path = require("path");
const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");

(async () => {
  const root = path.resolve("app/static");
  const outputDir = path.resolve("docs/validation/data/asset-facility-type-taxonomy/screenshots");
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe" });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    await page.goto("http://localhost:8080/?view=opportunities", { waitUntil: "networkidle" });
    await page.waitForFunction(() => document.querySelectorAll("#assetFacilityTypeFilter option").length > 1);
    const initial = await page.evaluate(() => ({ direction: document.documentElement.getAttribute("dir"), width: innerWidth,
      scrollWidth: document.documentElement.scrollWidth, optionValues: [...document.querySelectorAll("#assetFacilityTypeFilter option")].map(option => option.value),
      optionText: [...document.querySelectorAll("#assetFacilityTypeFilter option")].map(option => option.textContent) }));
    if (initial.direction !== "rtl") throw new Error("RTL direction is missing.");
    if (initial.scrollWidth > initial.width) throw new Error("Page has horizontal overflow at 1920px.");
    if (!initial.optionValues.includes("asset_facility_type:building")) throw new Error("Canonical building option is missing.");

    await page.locator("#assetFacilityTypeFilter").selectOption("asset_facility_type:building");
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("1 من 1"));
    const rowText = await page.locator("#opportunityRows tr").first().innerText();
    if (!rowText.includes("المباني")) throw new Error("Opportunity list does not render the asset/site type.");
    const csvLink = page.locator('#view-opportunities .heading-actions a[href="/api/export.csv"]');
    const csvLinkHandle = await csvLink.elementHandle();
    await page.evaluate(link => { link.addEventListener("click", event => event.preventDefault(), { once: true, capture: true }); link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })); }, csvLinkHandle);
    const csvHref = await csvLinkHandle.getAttribute("href");
    if (!csvHref.includes("asset_facility_type=asset_facility_type%3Abuilding")) throw new Error(`CSV link omitted the asset/site type filter: ${csvHref}`);
    const xlsxLink = page.locator('#view-opportunities .heading-actions a[href="/api/export.xlsx"]');
    const xlsxLinkHandle = await xlsxLink.elementHandle();
    await page.evaluate(link => { link.addEventListener("click", event => event.preventDefault(), { once: true, capture: true }); link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })); }, xlsxLinkHandle);
    const xlsxHref = await xlsxLinkHandle.getAttribute("href");
    if (!xlsxHref.includes("asset_facility_type=asset_facility_type%3Abuilding")) throw new Error("XLSX link omitted the asset/site type filter.");
    await page.locator('#opportunityRows [data-detail]').first().click();
    await page.waitForFunction(() => document.querySelector("#modal")?.classList.contains("show"));
    const details = await page.locator("#modalBody").innerText();
    if (!details.includes("نوع الأصل أو الموقع") || !details.includes("المباني")) throw new Error("Opportunity details omit the asset/site type.");
    await page.screenshot({ path: path.join(outputDir, "asset-facility-type-building.png"), fullPage: true });
    await page.locator("#modalClose").click();
    await page.locator("#resetFilters").click();
    await page.waitForFunction(() => document.querySelector("#assetFacilityTypeFilter")?.value === "");
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("291 فرصة"));
    const evidence = { validated_at: new Date().toISOString(), viewport: { width: initial.width, scrollWidth: initial.scrollWidth },
      direction: initial.direction, options: initial.optionText, selected_option: "asset_facility_type:building",
      list_contains_type: true, details_contains_type: true, csv_filter_link: csvHref, xlsx_filter_link: xlsxHref,
      reset_restores_291: true, screenshot: "asset-facility-type-building.png" };
    fs.writeFileSync(path.join(outputDir, "ui-verification.json"), JSON.stringify(evidence, null, 2), "utf8");
    console.log(JSON.stringify(evidence, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

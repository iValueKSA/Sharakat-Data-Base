const fs = require("fs");
const path = require("path");
const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");

(async () => {
  const outputDir = path.resolve("docs/validation/data/opportunity-type-taxonomy/screenshots");
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe" });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    await page.goto("http://localhost:8080/?view=opportunities", { waitUntil: "networkidle" });
    await page.waitForFunction(() => document.querySelectorAll("#typeFilter option").length > 1);
    await page.evaluate(() => document.fonts.ready);
    const evidence = {
      viewport: page.viewportSize(),
      direction: await page.locator("html").getAttribute("dir"),
      opportunityTypeOptions: await page.locator("#typeFilter option").allTextContents(),
      horizontalOverflow: await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
    };
    await page.locator("#typeFilter").click();
    await page.screenshot({ path: path.join(outputDir, "current-before-review.png") });
    fs.writeFileSync(path.join(outputDir, "current-before-review.json"), JSON.stringify(evidence, null, 2), "utf8");
    console.log(JSON.stringify(evidence, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });

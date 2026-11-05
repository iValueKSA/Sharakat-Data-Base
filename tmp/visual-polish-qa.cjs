const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const fs = require("node:fs/promises");
const path = require("node:path");

const base = "http://localhost:8080/?view=data-dashboard";
const out = path.resolve("docs/validation/ui/nextadmin-ahda-dashboard/visual-polish/screenshots");
const sizes = [
  { width: 1920, height: 1080, name: "1920x1080" },
  { width: 1440, height: 900, name: "1440x900" },
  { width: 1366, height: 768, name: "1366x768" },
  { width: 768, height: 900, name: "768x900" },
  { width: 390, height: 844, name: "390x844" },
];

(async () => {
  await fs.mkdir(out, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe" });
  const page = await browser.newPage({ viewport: sizes[0], deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error" && !message.text().includes("401 (Unauthorized)")) errors.push(message.text()); });
  page.on("requestfailed", request => { if (!request.url().includes("tile.openstreetmap.org")) errors.push(`${request.url()} ${request.failure()?.errorText}`); });
  const response = await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#dataKpis .data-kpi b")?.textContent && document.querySelector("#dashBySector svg") && document.querySelector("#geoStats")?.textContent.includes("175"), { timeout: 30000 });
  await page.waitForSelector("#opportunityMap .leaflet-marker-icon", { timeout: 15000 });

  const summary = { http: response.status(), screenshots: [], viewports: [], charts: {}, overflow: [], interactions: {}, errors };
  for (const viewport of sizes) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.waitForTimeout(220);
    const baseline = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      width: innerWidth,
      kpis: [...document.querySelectorAll(".data-kpi")].map(card => ({
        label: card.querySelector(".data-kpi-label")?.innerText,
        height: Math.round(card.getBoundingClientRect().height),
        clientWidth: card.clientWidth,
        scrollWidth: card.scrollWidth,
        textBoxes: [...card.querySelectorAll(".data-kpi-label,.data-kpi b,.data-kpi small")].map(el => ({ text: el.innerText, width: Math.round(el.getBoundingClientRect().width), height: Math.round(el.getBoundingClientRect().height), scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }))
      })),
      cards: [...document.querySelectorAll(".data-widget,.data-filters,.geo-panel,.recent-dashboard-panel")].map(card => ({ id: card.id || card.className.split(" ").at(-1), left: Math.round(card.getBoundingClientRect().left), right: Math.round(card.getBoundingClientRect().right), width: Math.round(card.getBoundingClientRect().width), scrollWidth: card.scrollWidth, clientWidth: card.clientWidth, overflowingChildren: [...card.querySelectorAll("*")].filter(el => el.scrollWidth > el.clientWidth + 1 || el.getBoundingClientRect().right > card.getBoundingClientRect().right + 1).slice(0, 5).map(el => ({ tag: el.tagName, id: el.id, cls: String(el.className?.baseVal || el.className || ""), text: String(el.innerText || "").slice(0, 42), client: el.clientWidth, scroll: el.scrollWidth, right: Math.round(el.getBoundingClientRect().right) })) })),
      chartWidths: [...document.querySelectorAll(".data-widget .analytics-svg")].map(svg => Math.round(svg.getBoundingClientRect().width)),
      labelBounds: [...document.querySelectorAll(".data-widget .analytics-label")].map(el => { const b = el.getBBox(), svg = el.ownerSVGElement; return { text: el.textContent, x: Math.round(b.x), right: Math.round(b.x + b.width), width: Number(svg.viewBox.baseVal.width) }; }).filter(b => b.x < 0 || b.right > b.width + 1),
    }));
    summary.viewports.push({ ...viewport, ...baseline, noHorizontalOverflow: baseline.scrollWidth <= baseline.width });
    const suffix = viewport.name;
    const snap = async (name, selector) => {
      await page.locator(selector).scrollIntoViewIfNeeded();
      await page.waitForTimeout(180);
      const file = path.join(out, `${name}-${suffix}.png`);
      await page.screenshot({ path: file });
      summary.screenshots.push(path.relative(process.cwd(), file));
    };
    if (viewport.width >= 1000) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: path.join(out, `dashboard-${suffix}-top.png`) });
      summary.screenshots.push(path.relative(process.cwd(), path.join(out, `dashboard-${suffix}-top.png`)));
      await snap("dashboard-chart", "#dashSectorPanel");
      await snap("dashboard-map", ".geo-panel");
    } else if (viewport.width > 500) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: path.join(out, `dashboard-${suffix}-top.png`) });
      summary.screenshots.push(path.relative(process.cwd(), path.join(out, `dashboard-${suffix}-top.png`)));
      await snap("dashboard-chart", "#dashSectorPanel");
      await snap("dashboard-map", ".geo-panel");
    } else {
      await page.evaluate(() => window.scrollTo(0, 0));
      await snap("dashboard-mobile-kpis", "#dataKpis");
      await snap("dashboard-mobile-sector", "#dashSectorPanel");
      await snap("dashboard-mobile-timeline", "#dashTimeline");
    }
  }

  summary.overflow = summary.viewports.map(v => ({
    viewport: v.name,
    kpiTextOverflow: v.kpis.flatMap(kpi => kpi.textBoxes.filter(box => box.scrollWidth > box.clientWidth + 1).map(box => ({ label: kpi.label, text: box.text }))),
    cardWidthOverflow: v.cards.filter(card => card.scrollWidth > card.clientWidth + 1).map(card => card.id),
    svgLabelOverflow: v.labelBounds,
  }));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(240);
  await page.evaluate(() => window.scrollTo(0, 0));
  summary.charts = await page.evaluate(() => Object.fromEntries(["dashBySector", "dashByStatus", "dashBySource", "dashByOwner", "dashByActivity", "dashByType", "dashByLocation", "dashTimeline", "dashDeadlineTrend"].map(id => {
    const node = document.getElementById(id), svg = node?.querySelector("svg");
    return [id, { svg: !!svg, width: Math.round(svg?.getBoundingClientRect().width || 0), height: Math.round(svg?.getBoundingClientRect().height || 0), categories: node?.querySelectorAll(".analytics-row").length || 0, axes: node?.querySelectorAll(".analytics-axis-label,.trend-axis-label").length || 0, tooltip: !!node?.querySelector(".analytics-tooltip"), labels: [...(node?.querySelectorAll(".analytics-label") || [])].slice(0, 3).map(el => el.textContent) }];
  })));
  summary.typeLayout = await page.evaluate(() => { const host = document.querySelector("#dashByType"), grid = host?.closest(".classification-grid"); return { chartWidth: Math.round(host?.getBoundingClientRect().width || 0), gridTemplate: getComputedStyle(grid).gridTemplateColumns, columns: host?.querySelectorAll(".analytics-column-separator").length ? 2 : 1 }; });
  const tooltipRow = page.locator("#dashBySector .analytics-row[role='button']").first();
  summary.interactions.firstSectorRow = { role: await tooltipRow.getAttribute("role"), tabIndex: await tooltipRow.getAttribute("tabindex"), filter: await tooltipRow.getAttribute("data-dash-filter"), value: await tooltipRow.getAttribute("data-dash-value") };
  await tooltipRow.hover();
  await page.waitForTimeout(100);
  await page.screenshot({ path: path.join(out, "chart-tooltip-1440x900.png") });
  summary.screenshots.push(path.relative(process.cwd(), path.join(out, "chart-tooltip-1440x900.png")));
  summary.interactions.customTooltip = await page.locator("#dashBySector .analytics-tooltip").isVisible();
  summary.interactions.tooltipHasMetrics = (await page.locator("#dashBySector .analytics-tooltip").innerText()).includes("فرصة");
  await page.locator(".widget-classification").scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(out, "dashboard-categories-1440x900.png") });
  summary.screenshots.push(path.relative(process.cwd(), path.join(out, "dashboard-categories-1440x900.png")));
  await page.locator('[data-map-mode="heat"]').click();
  await page.waitForSelector("#opportunityMap canvas.leaflet-heatmap-layer", { timeout: 5000 });
  summary.interactions.heatmapToggle = true;
  await page.locator('[data-map-mode="clusters"]').click();
  summary.interactions.clusterToggle = await page.locator("#opportunityMap .leaflet-marker-icon").count() > 0;
  const exportCsv = await page.request.get("http://localhost:8080/api/export.csv");
  const exportXlsx = await page.request.get("http://localhost:8080/api/export.xlsx");
  summary.interactions.csvExport = exportCsv.status() === 200 && (await exportCsv.text()).split(/\r?\n/).length > 2;
  summary.interactions.xlsxExport = exportXlsx.status() === 200 && Number(exportXlsx.headers()["content-length"] || 0) > 1000;
  summary.interactions.initialCount = await page.locator("#dataKpis .data-kpi b").first().innerText();
  summary.interactions.chartKeyboardDrilldown = await tooltipRow.getAttribute("role") === "button" && await tooltipRow.getAttribute("tabindex") === "0" && Boolean(await tooltipRow.getAttribute("data-dash-value"));
  summary.interactions.filterControlsPresent = await page.locator("#dashPeriod,#dashStatus,#dashSector,#dashLifecycle,#dashReset").count() === 5;
  summary.interactions.mapSummaryPresent = (await page.locator("#geoStats").innerText()).includes("175");
  const number = value => Number(String(value || "").replace(/[٠-٩]/g, digit => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit))).replace(/[^0-9]/g, ""));
  const sectorValue = await page.locator("#dashSector option").nth(1).getAttribute("value");
  await page.locator("#dashSector").selectOption(sectorValue);
  await page.waitForFunction(() => { const val = String(document.querySelector("#dataKpis .data-kpi b")?.textContent || "").replace(/[٠-٩]/g, digit => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit))).replace(/[^0-9]/g, ""); return Number(val) < 289 && document.querySelector("#geoStats")?.textContent.includes("إجمالي الفرص ضمن المرشحات"); }, { timeout: 15000 });
  summary.interactions.globalFilterUpdatesDashboardAndMap = number(await page.locator("#dataKpis .data-kpi b").first().innerText()) < 289 && (await page.locator("#geoStats").innerText()).includes("ضمن المرشحات");
  await page.locator("#dashReset").click();
  await page.waitForFunction(() => Number(String(document.querySelector("#dataKpis .data-kpi b")?.textContent || "").replace(/[٠-٩]/g, digit => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit))).replace(/[^0-9]/g, "")) === 289, { timeout: 15000 });
  await page.locator("#dashBySector .analytics-row[role='button']").first().focus();
  await page.locator("#dashBySector .analytics-row[role='button']").first().press("Enter");
  await page.waitForURL(/view=opportunities/, { timeout: 15000 });
  const sectorDrill = new URL(page.url()).searchParams.get("sector");
  summary.interactions.chartKeyboardDrilldown = Boolean(sectorDrill);
  await page.waitForSelector("#opportunityRows button[data-detail]", { timeout: 15000 });
  await page.locator("#opportunityRows button[data-detail]").first().click();
  await page.locator("#modal.show").waitFor({ state: "visible", timeoutMs: 15000 });
  summary.interactions.opportunityListAndDetails = await page.locator("#modal.show").isVisible();
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#geoStats")?.textContent.includes("175"), { timeout: 30000 });
  await page.locator("#opportunityMap .leaflet-marker-icon").first().click();
  if (!(await page.locator("#opportunityMap .leaflet-popup button[data-map-open]").count())) {
    await page.waitForTimeout(400);
    await page.locator("#opportunityMap .leaflet-marker-icon").first().click();
  }
  await page.locator("#opportunityMap .leaflet-popup button[data-map-open]").waitFor({ state: "visible", timeoutMs: 10000 });
  await page.locator("#opportunityMap .leaflet-popup button[data-map-open]").click();
  await page.waitForURL(/view=opportunities/, { timeout: 15000 });
  summary.interactions.mapDrilldown = Boolean(new URL(page.url()).searchParams.get("map_ids"));
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#geoStats")?.textContent.includes("175"), { timeout: 30000 });
  await page.locator('[data-kpi-action="active"]').click();
  await page.waitForURL(/view=opportunities/, { timeout: 15000 });
  summary.interactions.kpiDrilldown = new URL(page.url()).searchParams.get("lifecycle") === "active";
  await page.goto("http://localhost:8080/?view=sources", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll(".source-card").length === 10, { timeout: 15000 });
  summary.interactions.sourceHealthVisible = await page.locator(".source-card").count() === 10;
  summary.interactions.guestAdminControlsHidden = await page.locator('[data-view="admin"]').evaluate(el => getComputedStyle(el).display === "none");
  await page.locator("#userButton").click();
  const credentialText = await fs.readFile(path.resolve("Local Admin Credentials.txt"), "utf8");
  const email = credentialText.match(/^Email:\s*(.+)$/m)?.[1]?.trim();
  const password = credentialText.match(/^Password:\s*(.+)$/m)?.[1]?.trim();
  if (!email || !password) throw new Error("Local admin credentials file has no usable email/password fields.");
  await page.locator("#loginEmail").fill(email);
  await page.locator("#loginPassword").fill(password);
  await page.locator('#loginForm button[type="submit"]').click();
  await page.waitForFunction(() => !document.querySelector("#loginDialog")?.open && document.querySelector("#userLabel")?.textContent !== "زائر", { timeout: 15000 });
  summary.interactions.authenticationLogin = true;
  summary.interactions.adminRoleControlsVisible = await page.locator('[data-view="admin"]').evaluate(el => getComputedStyle(el).display !== "none");
  summary.errors = errors.splice(0);
  await page.goto("https://demo.nextadmin.co/analytics", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1800);
  await page.waitForSelector(".recharts-wrapper", { timeout: 20000 });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: path.join(out, "nextadmin-analytics-1440x900.png") });
  summary.screenshots.push(path.relative(process.cwd(), path.join(out, "nextadmin-analytics-1440x900.png")));
  await fs.writeFile(path.join(out, "qa-summary.json"), JSON.stringify(summary, null, 2), "utf8");
  await browser.close();
  process.stdout.write(JSON.stringify({ http: summary.http, screenshots: summary.screenshots.length, viewports: summary.viewports.map(({ name, noHorizontalOverflow, width, scrollWidth }) => ({ name, noHorizontalOverflow, width, scrollWidth })), charts: summary.charts, interactions: summary.interactions, errors: summary.errors }, null, 2));
})().catch(error => { console.error(error); process.exit(1); });

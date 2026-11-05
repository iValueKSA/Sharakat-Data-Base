const { chromium } = require("playwright");
const fs = require("node:fs/promises");
const path = require("node:path");

const base = "http://localhost:8080/?view=data-dashboard";
const output = path.resolve("docs/validation/ui/nextadmin-ahda-dashboard/visual-analytics/screenshots");
const viewports = [
  { width: 1920, height: 1080, name: "1920x1080" },
  { width: 1440, height: 900, name: "1440x900" },
  { width: 1366, height: 768, name: "1366x768" },
  { width: 768, height: 900, name: "768x900" },
  { width: 390, height: 844, name: "390x844" },
];

(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe" });
  const page = await browser.newPage({ viewport: viewports[0], deviceScaleFactor: 1 });
  const errors = [];
  const expectedAuthWarnings = [];
  page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
  page.on("console", message => { if (message.type() === "error" && message.text().includes("401 (Unauthorized)")) expectedAuthWarnings.push(message.text()); else if (message.type() === "error") errors.push(`console: ${message.text()}`); });
  page.on("requestfailed", request => { if (!request.url().includes("tile.openstreetmap.org")) errors.push(`request: ${request.url()} ${request.failure()?.errorText}`); });
  const response = await page.goto(base, { waitUntil: "domcontentloaded" });
  if (response.status() !== 200) throw new Error(`Dashboard returned HTTP ${response.status()}`);
  await page.waitForFunction(() => document.querySelector("#geoStats")?.textContent.includes("175") && document.querySelector("#dashBySector svg") && document.querySelector("#opportunityMap .leaflet-overlay-pane"), { timeout: 30000 });
  await page.waitForSelector("#opportunityMap .leaflet-marker-icon", { timeout: 15000 });
  const summary = { http: response.status(), viewports: [], charts: {}, geo: {}, checks: {} };
  summary.geo = await page.evaluate(() => ({ text: document.querySelector("#geoStats")?.innerText, mapHeight: Math.round(document.querySelector("#opportunityMap").getBoundingClientRect().height), points: document.querySelectorAll("#opportunityMap .leaflet-marker-icon").length }));
  summary.initialUiTotal = await page.locator("#dataKpis .data-kpi b").first().innerText().then(v=>Number(v.replace(/[٠-٩]/g,d=>String("٠١٢٣٤٥٦٧٨٩".indexOf(d))).replace(/[^0-9]/g,"")));
  summary.charts = await page.evaluate(() => Object.fromEntries(["dashBySector","dashByStatus","dashBySource","dashByOwner","dashByActivity","dashByType","dashByLocation","dashTimeline","dashDeadlineTrend"].map(id => [id, { svg: !!document.querySelector(`#${id} svg`), marks: document.querySelectorAll(`#${id} svg rect, #${id} svg circle`).length }])));
  summary.recentRows = await page.locator("#dashRecentOpportunities tr").count();
  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.waitForTimeout(350);
    const dimensions = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, height: innerHeight, mapWidth: Math.round(document.querySelector("#opportunityMap").getBoundingClientRect().width), mapHeight: Math.round(document.querySelector("#opportunityMap").getBoundingClientRect().height), overflowers: [...document.querySelectorAll("body *")].filter(el => { const r=el.getBoundingClientRect(); return r.width>innerWidth+1 || r.right>innerWidth+1; }).slice(0,8).map(el => ({tag:el.tagName,id:el.id,classes:String(el.className?.baseVal||el.className||''),width:Math.round(el.getBoundingClientRect().width),right:Math.round(el.getBoundingClientRect().right)})) }));
    await page.screenshot({ path: path.join(output, `dashboard-${viewport.name}.png`), fullPage: true });
    summary.viewports.push({ ...viewport, ...dimensions, noHorizontalOverflow: dimensions.scrollWidth <= dimensions.width });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#geoStats")?.textContent.includes("175"));
  await page.locator("#opportunityMap .leaflet-marker-icon").first().waitFor({ state: "visible", timeout: 15000 });
  await page.locator('[data-map-mode="heat"]').click();
  await page.waitForSelector("#opportunityMap canvas.leaflet-heatmap-layer", { timeout: 5000 });
  await page.locator("#opportunityMap").scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, "map-heat-1440x900.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#geoStats")?.textContent.includes("175") && document.querySelector("#dashBySector svg"), { timeout: 30000 });
  await page.waitForSelector("#opportunityMap .leaflet-marker-icon", { timeout: 15000 });
  const deadlinePoint = page.locator("#dashDeadlineTrend .trend-period-hit").first();
  if (await deadlinePoint.count()) {
    await deadlinePoint.press("Enter");
    await page.waitForURL(/view=opportunities/);
    const deadlineParams = new URL(page.url()).searchParams;
    summary.deadlineDrilldown = Boolean(deadlineParams.get("deadline_after") && deadlineParams.get("deadline_before") && deadlineParams.get("lifecycle") === "active");
  } else summary.deadlineDrilldown = false;
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#geoStats")?.textContent.includes("175") && document.querySelector("#dashBySector svg"), { timeout: 30000 });
  await page.waitForSelector("#opportunityMap .leaflet-marker-icon", { timeout: 15000 });
  await page.locator('[data-map-mode="heat"]').click();
  await page.waitForSelector("#opportunityMap canvas.leaflet-heatmap-layer", { timeout: 5000 });
  summary.checks.heatToggleShowsCanvas = await page.locator("#opportunityMap canvas.leaflet-heatmap-layer").count() > 0;
  await page.locator('[data-map-mode="clusters"]').click();
  await page.waitForSelector("#opportunityMap .leaflet-marker-icon", { timeout: 5000 });
  summary.checks.clusterModeShowsMarkers = await page.locator("#opportunityMap .leaflet-marker-icon").count() > 0;
  summary.checks.clusterDebug = await page.locator("#opportunityMap .leaflet-marker-icon").count();
  const sectorOptions = await page.locator("#dashSector option").evaluateAll(items => items.filter(option => option.value).map(option => option.value));
  if (sectorOptions.length) {
    await page.locator("#dashSector").selectOption(sectorOptions[0]);
    await page.waitForFunction(() => {
      const number = value => Number(String(value || "").replace(/[٠-٩]/g, digit => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit))).replace(/[^0-9]/g, ""));
      const total = number(document.querySelector("#dataKpis .data-kpi b")?.textContent);
      const mapRaw = document.querySelector("#geoStats")?.textContent?.match(/إجمالي الفرص ضمن المرشحات\s*([\d٠-٩]+)/)?.[1];
      const mapTotal = number(mapRaw);
      return total > 0 && mapTotal > 0 && total === mapTotal && total < 289;
    }, { timeout: 15000 });
    summary.checks.globalFilterUpdatesChartsAndMap = true;
  } else summary.checks.globalFilterUpdatesChartsAndMap = false;
  const sectorRow = page.locator('#dashBySector .analytics-row[role="button"][data-dash-value]').first();
  const sectorValue = await sectorRow.getAttribute("data-dash-value");
  await sectorRow.press("Enter");
  await page.waitForURL(/view=opportunities/);
  summary.checks.chartKeyboardDrilldown = new URL(page.url()).searchParams.get("sector") === sectorValue;
  const geo = await page.request.get("http://localhost:8080/api/data-dashboard/geography");
  const geoData = await geo.json();
  const dashboardApi = await (await page.request.get("http://localhost:8080/api/data-dashboard")).json();
  summary.api = { total: dashboardApi.kpis.total, enabledSources: dashboardApi.kpis.enabled_sources, sourceRows: dashboardApi.by_source.length, sectorsSum: dashboardApi.by_sector.reduce((sum,row)=>sum+row.count,0), statusesSum: dashboardApi.by_status.reduce((sum,row)=>sum+row.count,0), typesSum: dashboardApi.by_type.reduce((sum,row)=>sum+row.count,0), mapped: geoData.counts.exact_mapped, unmapped: geoData.counts.unmapped };
  summary.checks.apiTotalsCanonical = summary.api.sectorsSum === summary.api.total && summary.api.statusesSum === summary.api.total && summary.api.typesSum === summary.api.total;
  summary.checks.tenSourceRows = summary.api.sourceRows === summary.api.enabledSources;
  summary.checks.recentTableUsesLiveData = summary.recentRows > 0;
  summary.checks.apiUiCountMatch = summary.initialUiTotal === dashboardApi.kpis.total;
  const firstId = geoData.points[0]?.ids?.[0];
  const drill = await page.request.get(`http://localhost:8080/api/opportunities?map_ids=${firstId}`);
  summary.checks.mapIdDrilldown = drill.status() === 200 && (await drill.json()).total === 1;
  summary.errors = errors;
  summary.expectedAuthWarnings = expectedAuthWarnings;
  summary.checks.activityEmptyState = await page.locator("#dashByActivity .analytics-empty").count() === 1;
  const offlinePage = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await offlinePage.route("https://tile.openstreetmap.org/**", route => route.abort());
  await offlinePage.goto(base, { waitUntil: "domcontentloaded" });
  await offlinePage.waitForFunction(() => document.querySelector("#geoStats")?.textContent.includes("175"), { timeout: 30000 });
  await offlinePage.waitForSelector("#opportunityMap .leaflet-marker-icon", { timeout: 15000 });
  await offlinePage.waitForFunction(() => !document.querySelector("#mapNotice").hidden, { timeout: 15000 });
  summary.checks.tileFailureShowsNotice = await offlinePage.locator("#mapNotice").innerText().then(text => text.includes("تعذر تحميل خريطة الأساس"));
  summary.checks.tileFailureKeepsBoundary = await offlinePage.locator("#opportunityMap .leaflet-overlay-pane canvas").count() > 0;
  summary.checks.tileFailureKeepsOpportunityClusters = await offlinePage.locator("#opportunityMap .leaflet-marker-icon").count() > 0;
  await offlinePage.close();
  summary.checks.deadlineDrilldown = summary.deadlineDrilldown;
  summary.ok = summary.viewports.every(v => v.noHorizontalOverflow) && Object.entries(summary.charts).every(([key, chart]) => key === "dashByActivity" ? !chart.svg : chart.svg) && Object.entries(summary.checks).every(([key,value]) => key === "clusterDebug" ? true : value) && errors.length === 0;
  await fs.writeFile(path.join(output, "qa-summary.json"), JSON.stringify(summary, null, 2), "utf8");
  await browser.close();
  process.stdout.write(JSON.stringify(summary, null, 2));
  if (!summary.ok) process.exitCode = 1;
})().catch(error => { console.error(error); process.exit(1); });

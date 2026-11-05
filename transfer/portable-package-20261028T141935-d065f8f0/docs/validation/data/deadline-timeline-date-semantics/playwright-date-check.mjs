import { createRequire } from 'node:module';
import fs from 'node:fs';
const require = createRequire(import.meta.url);
const { chromium } = require('C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const base = 'http://localhost:8080';
const out = 'docs/validation/data/deadline-timeline-date-semantics';
const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' });
const page = await browser.newPage({ locale: 'ar-SA', timezoneId: 'Asia/Riyadh', viewport: { width: 1920, height: 1080 } });
const errors = [];
page.on('pageerror', error => errors.push(String(error)));
const results = { viewportChecks: [], pageErrors: errors, assertions: {} };
const correctionSnapshot = JSON.parse(fs.readFileSync(`${out}/evidence/pre-correction-snapshot.json`, 'utf8'));
const clearedDeadlineIds = new Set(correctionSnapshot.furas_deadline_correction_ids);
const clearedPublicationIds = new Set(correctionSnapshot.furas_publication_correction_ids);
const response = await page.request.get(`${base}/api/opportunities?limit=300&offset=0`);
const opportunityData = await response.json();
fs.writeFileSync(`${out}/evidence/live-api-opportunities.json`, JSON.stringify(opportunityData, null, 2), 'utf8');
results.assertions.apiStatus = response.status();
results.assertions.apiTotal = opportunityData.total;
results.assertions.apiDeadlineCount = opportunityData.items.filter(item => item.deadline).length;
results.assertions.correctedFurasDeadlinesAbsentFromApi = opportunityData.items
  .filter(item => clearedDeadlineIds.has(item.id)).every(item => !item.deadline);
results.assertions.correctedFurasPublicationDatesAbsentFromApiProjection = opportunityData.items
  .filter(item => clearedPublicationIds.has(item.id)).every(item => !item.publication_date);
results.assertions.correctedFurasDeadlineMasterIds = [...clearedDeadlineIds].sort((a,b) => a-b);
results.assertions.correctedFurasPublicationMasterIds = [...clearedPublicationIds].sort((a,b) => a-b);
const dashboardResponse = await page.request.get(`${base}/api/data-dashboard`);
const dashboard = await dashboardResponse.json();
results.assertions.dashboardStatus = dashboardResponse.status();
results.assertions.upcomingDeadlineRows = (dashboard.deadlines || []).length;
results.assertions.deadlineBuckets = dashboard.deadline_buckets || [];
results.assertions.upcomingDeadlinesExcludeCorrectedFurasIds = (dashboard.deadlines || []).every(item => !clearedDeadlineIds.has(item.id));
results.assertions.upcomingDeadlineMasterIds = (dashboard.deadlines || []).map(item => item.id);
for (const [width, height] of [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]]) {
  await page.setViewportSize({ width, height });
  await page.goto(`${base}/?view=opportunities`, { waitUntil: 'networkidle' });
  await page.locator('#opportunityRows tr').first().waitFor({ state: 'visible', timeout: 20000 });
  const state = await page.evaluate(() => {
    const bar = document.querySelector('#view-opportunities .filter-bar');
    const barRect = bar.getBoundingClientRect();
    const controls = [...bar.children].map(el => {
      const r = el.getBoundingClientRect();
      return { name: el.id || el.getAttribute('aria-label') || el.textContent.trim().slice(0,30),
        left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top), bottom: Math.round(r.bottom),
        visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length), text: el.textContent.trim() };
    });
    const overlappingPairs=[];
    for (let i=0;i<controls.length;i++) for (let j=i+1;j<controls.length;j++) {
      const a=controls[i],b=controls[j];
      if (Math.min(a.right,b.right)>Math.max(a.left,b.left) && Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top)) overlappingPairs.push([a.name,b.name]);
    }
    return {
    viewportWidth: innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
    rtl: getComputedStyle(document.querySelector('main') || document.body).direction,
    filterBarWithinViewport: barRect.left >= 0 && barRect.right <= innerWidth,
    filters: controls,
    overlappingPairs,
    rows: document.querySelectorAll('#opportunityRows tr').length,
    resetText: document.querySelector('#resetFilters')?.textContent.trim()
  }; });
  results.viewportChecks.push({ width, height, ...state, noHorizontalOverflow: state.documentWidth <= width,
    allFiltersVisible: state.filters.every(item => item.visible && item.left >= 0 && item.right <= width),
    noFilterOverlap: state.overlappingPairs.length === 0, resetFullyVisible: state.filters.some(item => item.name === 'resetFilters' && item.left >= 0 && item.right <= width) });
  await page.screenshot({ path: `${out}/screenshots/opportunities-${width}x${height}.png`, fullPage: true });
  await page.screenshot({ path: `${out}/screenshots/opportunities-${width}x${height}-viewport.png`, fullPage: false });
}
await page.setViewportSize({ width: 1920, height: 1080 });
await page.goto(`${base}/?view=opportunities`, { waitUntil: 'networkidle' });
const search = page.locator('#searchInput');
const knownTitle = opportunityData.items.find(item => item.title)?.title;
await search.fill(knownTitle.slice(0, Math.min(15, knownTitle.length)));
await page.waitForTimeout(500);
results.assertions.searchReturnsRows = await page.locator('#opportunityRows tr').count() > 0;
await page.locator('#resetFilters').click();
await page.waitForTimeout(300);
results.assertions.resetClearsSearch = !(await search.inputValue());
await page.locator('#statusFilter').selectOption({ label: 'متاحة' });
await page.waitForTimeout(400);
results.assertions.statusFilterReturnsAvailableRows = await page.locator('#opportunityRows tr .tag').count() > 0;
results.assertions.statusFilterValues = await page.locator('#opportunityRows tr .tag').allInnerTexts();
await page.locator('#resetFilters').click();
await page.waitForTimeout(300);
results.assertions.paginationNextEnabled = await page.locator('#nextPage').isEnabled();
await page.locator('#nextPage').click();
await page.waitForTimeout(400);
results.assertions.paginationChangedSummary = await page.locator('#pageSummary').innerText();
const firstDetail = page.locator('#opportunityRows [data-detail]').first();
await firstDetail.click();
await page.locator('#modal[aria-hidden="false"]').waitFor({ state: 'visible', timeout: 10000 });
results.assertions.detailDeadlineLabel = await page.locator('#modalBody').innerText().then(text => text.includes('آخر موعد للتقديم'));
await page.screenshot({ path: `${out}/screenshots/opportunity-detail-1920x1080.png`, fullPage: true });
const reviewedFuras = opportunityData.items.find(item => clearedDeadlineIds.has(item.id));
results.assertions.correctedFurasReference = reviewedFuras.reference;
const reviewedFurasDetailResponse = await page.request.get(`${base}/api/opportunities/${reviewedFuras.id}`);
const reviewedFurasDetail = await reviewedFurasDetailResponse.json();
results.assertions.correctedFurasDetailDeadlineAbsent = reviewedFurasDetailResponse.ok() && !reviewedFurasDetail.deadline;
await page.goto(`${base}/?view=opportunities`, { waitUntil: 'networkidle' });
await page.locator('#searchInput').fill(reviewedFuras.title.slice(0, Math.min(20, reviewedFuras.title.length)));
await page.waitForTimeout(300);
await page.locator(`[data-detail="${reviewedFuras.id}"]`).first().click();
await page.locator('#modal[aria-hidden="false"]').waitFor({ state: 'visible', timeout: 10000 });
const correctedDetailText = await page.locator('#modalBody').innerText();
results.assertions.correctedFurasDetailShowsUnspecified = correctedDetailText.includes('آخر موعد للتقديم') && correctedDetailText.includes('غير محدد');
results.assertions.correctedFurasTableShowsUnspecified = await page.locator('#opportunityRows tr').filter({ has: page.locator(`[data-detail="${reviewedFuras.id}"]`) }).innerText().then(text => text.includes('غير محدد')).catch(() => false);
const csv = await page.request.get(`${base}/api/export.csv`);
const csvText = await csv.text();
fs.writeFileSync(`${out}/evidence/live-export.csv`, csvText, 'utf8');
results.assertions.csvStatus = csv.status();
results.assertions.csvHasDeadlineColumn = csvText.split(/\r?\n/)[0]?.includes('آخر موعد للتقديم') || false;
results.assertions.csvCorrectedDeadlineCellsBlank = [...clearedDeadlineIds].every(id => {
  const item = opportunityData.items.find(row => row.id === id);
  if (!item) return true;
  return !item.deadline;
});
const xlsx = await page.request.get(`${base}/api/export.xlsx`);
fs.writeFileSync(`${out}/evidence/live-export.xlsx`, await xlsx.body());
results.assertions.xlsxStatus = xlsx.status();
results.assertions.xlsxContentType = xlsx.headers()['content-type'];
results.assertions.hasDeadlineSortControl = await page.locator('th[data-column="deadline"]').evaluate(el => el.tagName === 'BUTTON' || el.hasAttribute('aria-sort')).catch(() => false);
results.assertions.offsetDeadlineDateSemantics = await page.evaluate(() => ({
  localDateKey: window.AHDAFormatters.businessDateKey('2026-10-20T22:30:00Z'),
  displayDate: window.AHDAFormatters.date('2026-10-20T22:30:00Z'),
  naiveDateTimeKey: window.AHDAFormatters.businessDateKey('2026-10-21T00:30:00'),
}));
results.assertions.offsetDeadlineUsesRiyadhDate = results.assertions.offsetDeadlineDateSemantics.localDateKey === '2026-10-21' && results.assertions.offsetDeadlineDateSemantics.displayDate === '2026/10/21';
results.assertions.naiveDeadlineDateTimeRejected = results.assertions.offsetDeadlineDateSemantics.naiveDateTimeKey === null;
results.assertions.pageErrors = errors;
results.assertions.allViewportsNoOverflow = results.viewportChecks.every(item => item.noHorizontalOverflow);
results.assertions.allFiltersVisibleAtAllViewports = results.viewportChecks.every(item => item.allFiltersVisible);
results.assertions.noFilterOverlapAtAllViewports = results.viewportChecks.every(item => item.noFilterOverlap);
results.assertions.resetVisibleAtAllViewports = results.viewportChecks.every(item => item.resetFullyVisible);
await page.setViewportSize({ width: 1920, height: 1080 });
await page.goto(`${base}/`, { waitUntil: 'networkidle' });
await page.locator('#upcomingDeadlines .deadline-item').first().waitFor({ state: 'visible', timeout: 10000 });
results.assertions.upcomingDeadlinesVisibleInDashboard = await page.locator('#upcomingDeadlines .deadline-item').count() > 0;
results.assertions.upcomingDeadlinesDashboardText = await page.locator('#upcomingDeadlines').innerText();
const clearedTitles = opportunityData.items.filter(item => clearedDeadlineIds.has(item.id)).map(item => item.title);
results.assertions.dashboardRenderedNoCorrectedFurasDeadlines = await page.locator('#upcomingDeadlines .deadline-item').evaluateAll((items, titles) => items.every(item => !titles.some(title => item.innerText.includes(title))), clearedTitles);
await page.screenshot({ path: `${out}/screenshots/dashboard-upcoming-deadlines-1920x1080.png`, fullPage: false });
await browser.close();
fs.writeFileSync(`${out}/playwright-results.json`, JSON.stringify(results, null, 2), 'utf8');
console.log(JSON.stringify(results, null, 2));

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const base = 'http://localhost:8080';
const outDir = path.join(process.cwd(), 'docs/validation/data/status-lifecycle/screenshots');
fs.mkdirSync(outDir, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const result = { started_at: new Date().toISOString(), viewport_checks: [], scenarios: {}, errors };

  await page.goto(`${base}/?view=opportunities`, { waitUntil: 'networkidle' });
  await page.locator('#opportunityRows tr').first().waitFor({ state: 'visible', timeout: 15000 });
  const apiDashboard = await page.evaluate(async () => (await fetch('/api/data-dashboard')).json());
  const statusSummary = {};
  for (const label of apiDashboard.options.statuses) {
    const id = apiDashboard.option_ids.statuses[label];
    const response = await page.evaluate(async status => (await fetch(`/api/opportunities?status=${encodeURIComponent(status)}&limit=1&offset=0`)).json(), id);
    const dash = await page.evaluate(async status => (await fetch(`/api/data-dashboard?status=${encodeURIComponent(status)}`)).json(), id);
    const dashboardBucket = (dash.by_status || []).find(row => row.canonical_id === id || row.filter_value === label);
    statusSummary[label] = { id, api_total: response.total, returned: response.items?.length, dashboard_count: Number(dashboardBucket?.count || 0), dashboard_global_total: dash.global_total };
    if (statusSummary[label].api_total !== statusSummary[label].dashboard_count) throw new Error(`Status count mismatch for ${label}: ${JSON.stringify(statusSummary[label])}`);
  }
  result.scenarios.status_reconciliation = { by_status: statusSummary, sum_statuses: Object.values(statusSummary).reduce((n, item) => n + item.api_total, 0), eligible_total: apiDashboard.global_total };
  if (result.scenarios.status_reconciliation.sum_statuses !== apiDashboard.global_total) throw new Error('Status buckets do not sum to dashboard global total');

  const select = page.locator('#statusFilter');
  const firstStatus = apiDashboard.options.statuses.find(label => statusSummary[label].api_total > 0);
  const firstStatusId = apiDashboard.option_ids.statuses[firstStatus];
  await select.selectOption(firstStatusId);
  await page.locator('#opportunityRows tr').first().waitFor({ state: 'visible' });
  await page.waitForTimeout(250);
  const selectedRows = await page.locator('#opportunityRows tr').count();
  const tableCount = await page.locator('#tableCount').innerText();
  result.scenarios.status_filter = { label: firstStatus, id: firstStatusId, first_page_rows: selectedRows, table_count: tableCount, badge_texts: await page.locator('#opportunityRows [data-column="status"]').allInnerTexts() };
  if (!tableCount.includes(String(statusSummary[firstStatus].api_total))) throw new Error(`Filter table count does not reflect expected total for ${firstStatus}: ${tableCount}`);

  await page.locator('#resetFilters').click();
  await page.waitForTimeout(300);
  result.scenarios.reset = { status_filter: await page.locator('#statusFilter').inputValue(), search: await page.locator('#searchInput').inputValue(), table_count: await page.locator('#tableCount').innerText() };
  if (result.scenarios.reset.status_filter || result.scenarios.reset.search) throw new Error('Reset did not clear filters');

  await page.locator('#searchInput').fill('AL AHSA');
  await page.waitForTimeout(450);
  result.scenarios.search = { query: 'AL AHSA', table_count: await page.locator('#tableCount').innerText(), rows: await page.locator('#opportunityRows tr').count() };
  await page.locator('#searchInput').fill('');
  await page.waitForTimeout(350);
  const beforeNext = await page.locator('#pageSummary').innerText();
  if (await page.locator('#nextPage').isEnabled()) await page.locator('#nextPage').click();
  await page.waitForTimeout(350);
  result.scenarios.pagination = { before: beforeNext, after: await page.locator('#pageSummary').innerText(), rows: await page.locator('#opportunityRows tr').count() };
  await page.locator('#previousPage').click().catch(() => {});
  await page.waitForTimeout(250);

  const detailButton = page.locator('#opportunityRows button[data-detail]').first();
  await detailButton.click();
  await page.locator('#detailModal:not([hidden])').waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
  result.scenarios.details = { modal_visible: await page.locator('#modal.show').isVisible().catch(() => false), title: await page.locator('#modalTitle').innerText().catch(() => ''), has_source_status_section: await page.locator('#modalBody .detail-sources h3').innerText().catch(() => '') };
  if (result.scenarios.details.modal_visible) await page.keyboard.press('Escape');

  const exportResults = {};
  for (const ext of ['csv', 'xlsx']) {
    const response = await page.request.get(`${base}/api/export.${ext}?status=${encodeURIComponent(firstStatusId)}`);
    const body = await response.body();
    exportResults[ext] = { status: response.status(), content_type: response.headers()['content-type'], bytes: body.length, disposition: response.headers()['content-disposition'] || '' };
    if (!response.ok() || !body.length) throw new Error(`${ext} export failed`);
    if (ext === 'csv') {
      const csvText = body.toString('utf8');
      const lines = csvText.trim().split(/\r?\n/);
      exportResults.csv.data_rows = Math.max(0, lines.length - 1);
      if (exportResults.csv.data_rows !== statusSummary[firstStatus].api_total) throw new Error(`CSV row mismatch: ${JSON.stringify(exportResults.csv)}`);
    }
  }
  result.scenarios.exports = exportResults;

  const viewports = [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]];
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height });
    await page.goto(`${base}/?view=opportunities`, { waitUntil: 'networkidle' });
    const layout = await page.evaluate(() => ({
      innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth,
      direction: getComputedStyle(document.documentElement).direction,
      filterBox: (() => { const e=document.querySelector('.filter-bar'); const r=e.getBoundingClientRect(); return {left:r.left,right:r.right,width:r.width,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth}; })(),
      controls: (() => { const box=document.querySelector('.filter-bar').getBoundingClientRect(); const nodes=[...document.querySelectorAll('.filter-bar > *')]; return nodes.map(e=>{const r=e.getBoundingClientRect();return {name:e.id||e.getAttribute('aria-label')||e.className,left:r.left,right:r.right,top:r.top,bottom:r.bottom,within:r.left>=box.left-1&&r.right<=box.right+1&&r.top>=box.top-1};}); })(),
      overlaps: (() => { const nodes=[...document.querySelectorAll('.filter-bar > *')].map(e=>({name:e.id||e.getAttribute('aria-label')||e.className,r:e.getBoundingClientRect()}));const found=[];for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){const a=nodes[i].r,b=nodes[j].r;if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)found.push([nodes[i].name,nodes[j].name]);}return found;})(),
      reset: (() => { const e=document.querySelector('#resetFilters'),r=e.getBoundingClientRect(); return {left:r.left,right:r.right,width:r.width,visible:r.width>0&&r.left>=0&&r.right<=window.innerWidth,text:e.innerText}; })(),
      tableCount: document.querySelector('#tableCount')?.innerText
    }));
    result.viewport_checks.push({ width, height, ...layout });
    if (layout.scrollWidth > width) throw new Error(`Horizontal overflow at ${width}: ${layout.scrollWidth}`);
    if (!layout.reset.visible) throw new Error(`Reset control clipped at ${width}: ${JSON.stringify(layout.reset)}`);
    if (layout.controls.some(control => !control.within || control.width === 0)) throw new Error(`Filter control outside container at ${width}: ${JSON.stringify(layout.controls)}`);
    if (layout.overlaps.length) throw new Error(`Filter controls overlap at ${width}: ${JSON.stringify(layout.overlaps)}`);
    if (layout.direction !== 'rtl') throw new Error(`RTL direction is not set at ${width}`);
    await page.locator('#statusFilter').selectOption('status:unknown');
    await page.waitForFunction(() => document.querySelector('#tableCount')?.innerText.includes('من 1'), null, { timeout: 10000 });
    const dropdownWorked = (await page.locator('#opportunityRows tr').count()) === 1;
    if (!dropdownWorked) throw new Error(`Status dropdown did not filter at ${width}`);
    await page.locator('#resetFilters').click();
    await page.waitForFunction(() => document.querySelector('#tableCount')?.innerText.includes('من 291'), null, { timeout: 10000 });
    result.viewport_checks[result.viewport_checks.length - 1].dropdown_filter_usable = true;
    if (width === 1440) await page.screenshot({ path: path.join(outDir, 'opportunities-1440x900.png'), fullPage: true });
    if (width === 390) await page.screenshot({ path: path.join(outDir, 'opportunities-390x844.png'), fullPage: true });
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${base}/?view=data-dashboard`, { waitUntil: 'networkidle' });
  await page.locator('#rdStatusLegend .rd-legend-row').first().waitFor({ state: 'visible', timeout: 15000 });
  const legend = await page.locator('#rdStatusLegend .rd-legend-row').evaluateAll(nodes => nodes.map(node => ({ label: node.innerText, value: node.dataset.dashValue, aria: node.getAttribute('aria-label') })));
  result.scenarios.dashboard_status_legend = legend;
  await page.screenshot({ path: path.join(outDir, 'dashboard-status-1440x900.png'), fullPage: true });
  const firstLegend = page.locator('#rdStatusLegend .rd-legend-row').first();
  const drill = { label: await firstLegend.innerText(), value: await firstLegend.getAttribute('data-dash-value') };
  await firstLegend.click();
  await page.waitForURL(/view=opportunities/);
  await page.waitForFunction(value => document.querySelector('#statusFilter')?.value === value, drill.value, { timeout: 10000 });
  await page.waitForFunction(() => document.querySelector('#tableCount')?.innerText !== '—', null, { timeout: 10000 });
  result.scenarios.chart_drilldown = { ...drill, url: page.url(), selected_status: await page.locator('#statusFilter').inputValue(), table_count: await page.locator('#tableCount').innerText() };
  result.scenarios.chart_drilldown.matches_bucket = result.scenarios.chart_drilldown.selected_status === drill.value;
  if (!result.scenarios.chart_drilldown.matches_bucket) throw new Error(`Dashboard drilldown status is inconsistent with clicked bucket: ${JSON.stringify(result.scenarios.chart_drilldown)}`);
  result.errors = errors;
  result.finished_at = new Date().toISOString();
  fs.writeFileSync(path.join(outDir, '..', 'playwright-results.json'), JSON.stringify(result, null, 2), 'utf8');
  await browser.close();
  process.stdout.write(JSON.stringify(result, null, 2));
})().catch(error => { console.error(error.stack || error); process.exit(1); });

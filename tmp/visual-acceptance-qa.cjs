const { chromium } = require('C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs/promises');
const path = require('node:path');

const out = path.resolve('docs/validation/ui/tabler-ahda-dashboard-visual-acceptance/screenshots');
const sizes = [
  { width: 1920, height: 1080, name: '1920x1080' },
  { width: 1440, height: 900, name: '1440x900' },
  { width: 1366, height: 768, name: '1366x768' },
  { width: 768, height: 900, name: '768x900' },
  { width: 390, height: 844, name: '390x844' },
];

(async () => {
  await fs.mkdir(out, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: sizes[0], deviceScaleFactor: 1 });
  const errors = [], failed = [], shots = [], viewportChecks = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !m.text().includes('401 (Unauthorized)')) errors.push(m.text()); });
  page.on('requestfailed', r => { if (!r.url().includes('tile.openstreetmap.org')) failed.push(`${r.url()} ${r.failure()?.errorText}`); });
  page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 400 && !(r.status() === 401 && r.url().includes('/api/auth/'))) failed.push(`HTTP ${r.status()} ${r.url()}`); });

  await page.goto('http://localhost:8080/?view=data-dashboard', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.querySelector('#rdTotalValue')?.textContent.trim() !== '—', { timeout: 30000 });
  await page.waitForFunction(() => document.querySelector('#rdGeoStats b')?.textContent.trim() !== '', { timeout: 30000 });
  await page.waitForTimeout(400);
  const api = await page.evaluate(async () => {
    const data = await (await fetch('/api/data-dashboard')).json();
    const geo = await (await fetch('/api/data-dashboard/geography')).json();
    return { total: data.kpis.total, active: data.kpis.active, sources: data.kpis.enabled_sources, sectors: data.by_sector.length, statuses: data.by_status.length, owners: data.by_owner.length, types: data.by_type.length, timeline: data.timeline.length, exactMapped: geo.counts.exact_mapped, unmapped: geo.counts.unmapped };
  });

  for (const size of sizes) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.waitForTimeout(180);
    const info = await page.evaluate(() => {
      const root = document.querySelector('#view-data-dashboard');
      const cards = [...root.querySelectorAll('.rd-card')];
      return {
        viewport: `${innerWidth}x${innerHeight}`, documentWidth: document.documentElement.scrollWidth,
        rtl: getComputedStyle(document.body).direction === 'rtl', visible: root.classList.contains('visible'),
        total: document.querySelector('#rdTotalValue')?.textContent.trim(),
        charts: { columns: document.querySelectorAll('.rd-columns-svg').length, donut: document.querySelectorAll('.rd-donut-svg').length, timeSeries: document.querySelectorAll('.rd-trend-svg').length, limitedHistoryIndicator: document.querySelectorAll('.rd-trend-single').length, rank: document.querySelectorAll('.rd-rank-row').length },
        mapHeight: Math.round(document.querySelector('#rdOpportunityMap').getBoundingClientRect().height),
        overflowingCards: cards.filter(c => c.scrollWidth > c.clientWidth + 1).map(c => c.className),
        narrowTextOverflows: [...root.querySelectorAll('.rd-card-head h2,.rd-card-head p,.rd-title-group h1,.rd-title-group p,.rd-rank-label,.rd-source-health-row>b')].filter(el => el.scrollWidth > el.clientWidth + 2).map(el => el.innerText.slice(0, 35)),
      };
    });
    viewportChecks.push(info);
    const full = path.join(out, `dashboard-${size.name}-full.png`);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: full, fullPage: true }); shots.push(path.relative(process.cwd(), full));
    if (size.name === '390x844') {
      const mobile = path.join(out, 'dashboard-mobile-first-390x844.png');
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: mobile, fullPage: false }); shots.push(path.relative(process.cwd(), mobile));
    }
    if (size.name === '1920x1080') {
      const first = path.join(out, 'dashboard-desktop-first-1920x1080.png');
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: first, fullPage: false }); shots.push(path.relative(process.cwd(), first));
      await page.locator('.rd-primary-analysis').screenshot({ path: path.join(out, 'dashboard-charts-and-map-1920x1080.png') }); shots.push(path.relative(process.cwd(), path.join(out, 'dashboard-charts-and-map-1920x1080.png')));
      await page.locator('.rd-map-card').screenshot({ path: path.join(out, 'dashboard-map-1920x1080.png') }); shots.push(path.relative(process.cwd(), path.join(out, 'dashboard-map-1920x1080.png')));
    }
  }

  const functional = {};
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator('#rdFilterPanel > summary').click();
  await page.locator('#dashSector').selectOption({ index: 1 });
  await page.waitForTimeout(700);
  const sector = await page.locator('#dashSector').inputValue();
  const sectorApi = await page.evaluate(async value => await (await fetch(`/api/data-dashboard?sector=${encodeURIComponent(value)}`)).json(), sector);
  const sectorGeo = await page.evaluate(async value => await (await fetch(`/api/data-dashboard/geography?sector=${encodeURIComponent(value)}`)).json(), sector);
  functional.sectorFilterMatchesApi = (await page.locator('#rdTotalValue').innerText()).trim() === new Intl.NumberFormat('en-US-u-nu-latn').format(sectorApi.kpis.total);
  await page.waitForFunction(total => document.querySelector('#rdGeoStats b')?.textContent.trim() === new Intl.NumberFormat('en-US-u-nu-latn').format(total), sectorGeo.counts.total, { timeout: 10000 });
  functional.sectorFilterMapMatchesApi = (await page.locator('#rdGeoStats b').first().innerText()).trim() === new Intl.NumberFormat('en-US-u-nu-latn').format(sectorGeo.counts.total);
  functional.sectorFilterUpdatedUrl = new URL(page.url()).searchParams.has('sector');
  await page.locator('#dashReset').click();
  await page.waitForFunction(total => document.querySelector('#rdTotalValue')?.textContent.trim() === new Intl.NumberFormat('en-US-u-nu-latn').format(total) && !new URL(location.href).searchParams.has('sector'), api.total, { timeout: 12000 });
  functional.resetRestoredTotal = (await page.locator('#rdTotalValue').innerText()).trim() === new Intl.NumberFormat('en-US-u-nu-latn').format(api.total);
  await page.locator('#rdStatusDonut .rd-donut-segment').first().focus();
  await page.keyboard.press('Enter');
  await page.waitForURL(/view=opportunities.*status=/, { timeout: 10000 });
  functional.statusDonutDrilldown = new URL(page.url()).searchParams.has('status');
  await page.goto('http://localhost:8080/?view=data-dashboard', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.querySelector('#rdTotalValue')?.textContent.trim() !== '—');
  await page.locator('#rdOwnerRank [data-dash-filter="owner"]').first().click();
  await page.waitForURL(/view=opportunities.*owner=/, { timeout: 10000 });
  functional.ownerDrilldown = new URL(page.url()).searchParams.has('owner');
  await page.goto('http://localhost:8080/?view=data-dashboard', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.querySelector('#rdTotalValue')?.textContent.trim() !== '—');
  await page.locator('[data-rd-map-mode="heat"]').click();
  functional.heatMapToggle = await page.locator('[data-rd-map-mode="heat"]').getAttribute('aria-pressed') === 'true' && await page.locator('#rdOpportunityMap canvas.leaflet-heatmap-layer').count() === 1;
  await page.locator('[data-rd-map-mode="clusters"]').click();
  functional.clusterToggle = await page.locator('[data-rd-map-mode="clusters"]').getAttribute('aria-pressed') === 'true';
  for (let i = 0; i < 3 && !await page.locator('.rd-map-popup').count(); i++) {
    const marker = page.locator('#rdOpportunityMap .leaflet-marker-icon').first();
    if (!await marker.count()) break;
    await marker.evaluate(el => el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))); await page.waitForTimeout(450);
  }
  functional.mapPopup = await page.locator('.rd-map-popup').count() > 0;
  if (functional.mapPopup) {
    await page.locator('.rd-map-popup [data-map-open]').evaluate(el => el.click());
    await page.waitForURL(/view=opportunities.*map_ids=/, { timeout: 10000 });
    functional.mapPopupDrilldown = new URL(page.url()).searchParams.has('map_ids');
    await page.waitForFunction(() => document.querySelector('#tableCount')?.textContent.trim() !== '');
  } else functional.mapPopupDrilldown = false;
  await page.goto('http://localhost:8080/?view=data-dashboard', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.querySelector('#rdTotalValue')?.textContent.trim() !== '—');
  const firstDetail = page.locator('#rdRecentRows [data-detail]').first();
  if (await firstDetail.count()) { await firstDetail.click(); await page.locator('#modal.show').waitFor({ timeout: 6000 }); functional.opportunityDetail = true; await page.keyboard.press('Escape'); }
  else functional.opportunityDetail = false;
  const [csv] = await Promise.all([page.waitForEvent('download'), page.locator('#dashExportCsv').click()]);
  functional.csvExport = (await fs.stat(await csv.path())).size > 20;
  const [xlsx] = await Promise.all([page.waitForEvent('download'), page.locator('#dashExportXlsx').click()]);
  const xlsxBuffer = await fs.readFile(await xlsx.path()); functional.xlsxExport = xlsxBuffer.subarray(0, 2).toString() === 'PK';

  for (const view of ['opportunities', 'sources']) {
    await page.goto(`http://localhost:8080/?view=${view}`, { waitUntil: 'networkidle' });
    functional[`route_${view}`] = await page.locator(`#view-${view}.visible`).count() === 1;
  }
  functional.guestAdminHidden = await page.locator('[data-view="admin"]').evaluate(el => getComputedStyle(el).display === 'none').catch(() => false);
  await page.locator('#userButton').click().catch(() => {});
  functional.loginDialogAvailable = await page.locator('#loginDialog').evaluate(el => el.open).catch(() => false);
  const credsPath = path.resolve('Local Admin Credentials.txt');
  try {
    const text = await fs.readFile(credsPath, 'utf8');
    const email = text.match(/^Email:\s*(.+)$/m)?.[1]?.trim();
    const password = text.match(/^Password:\s*(.+)$/m)?.[1]?.trim();
    if (email && password) {
      if (!await page.locator('#loginDialog').evaluate(el => el.open).catch(() => false)) await page.locator('#userButton').click().catch(() => {});
      await page.locator('#loginEmail').fill(email); await page.locator('#loginPassword').fill(password);
      await page.locator('#loginForm button[type="submit"]').click();
      await page.waitForFunction(() => !document.querySelector('#loginDialog')?.open && document.querySelector('#userLabel')?.textContent !== 'زائر', { timeout: 12000 });
      functional.localLogin = true;
      functional.adminRouteVisibleAfterLogin = await page.locator('[data-view="admin"]').evaluate(el => getComputedStyle(el).display !== 'none');
      for (const view of ['review', 'alerts', 'admin']) {
        await page.goto(`http://localhost:8080/?view=${view}`, { waitUntil: 'networkidle' });
        functional[`route_${view}`] = await page.locator(`#view-${view}.visible`).count() === 1;
      }
      await page.goto('http://localhost:8080/?view=opportunities', { waitUntil: 'networkidle' });
      await page.waitForFunction(() => document.querySelector('#tableCount')?.textContent.trim() !== '');
      const next = page.locator('#nextPage');
      if (await next.count() && await next.isEnabled()) {
        const before = await page.locator('#pageSummary').innerText(); await next.click(); await page.waitForTimeout(350);
        functional.opportunityPagination = (await page.locator('#pageSummary').innerText()) !== before;
        await page.locator('#previousPage').click(); await page.waitForTimeout(350);
      } else functional.opportunityPagination = false;
      await page.locator('#searchInput').fill('مستودع');
      await page.waitForTimeout(600);
      functional.opportunitySearch = await page.locator('#opportunityRows tr').count() > 0;
      await page.locator('#searchInput').fill(''); await page.waitForTimeout(400);
      const oppDetail = page.locator('#opportunityRows [data-detail]').first();
      await oppDetail.waitFor({ timeout: 10000 }).catch(() => {});
      if (await oppDetail.count()) { await oppDetail.click(); await page.locator('#modal.show').waitFor({ timeout: 6000 }); functional.opportunityListDetail = true; await page.keyboard.press('Escape'); }
      else functional.opportunityListDetail = false;
    } else functional.localLogin = 'credentials not configured';
  } catch (error) { functional.authWorkflowError = error.message; if (functional.localLogin !== true) functional.localLogin = 'failed'; }
  await page.goto('http://localhost:8080/?view=data-dashboard', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.querySelector('#rdTotalValue')?.textContent.trim() !== '—');
  await page.locator('[data-view="data-dashboard"]').click();
  functional.dashboardNavigationItem = new URL(page.url()).searchParams.get('view') === 'data-dashboard';
  await page.screenshot({ path: path.join(out, 'dashboard-desktop-first-1440x900.png'), fullPage: false }); shots.push(path.relative(process.cwd(), path.join(out, 'dashboard-desktop-first-1440x900.png')));
  const audits = await page.evaluate(() => {
    const root = document.querySelector('#view-data-dashboard');
    const visibleAndAccessible = [...root.querySelectorAll('*'), ...document.querySelectorAll('#navCount,#topbarUpdateLabel,#dataDashboardUpdated')].flatMap(el => [el.textContent, ...[...el.attributes].map(attr => attr.value)]).join(' ');
    const categoryText = ['#rdSectorChart','#rdTypeChart','#rdStatusLegend','#rdSourceList'].map(selector => document.querySelector(selector)?.innerText || '').join(' ');
    return {
      noArabicIndicNumerals: !/[\u0660-\u0669\u06f0-\u06f9]/.test(visibleAndAccessible),
      noRawTechnicalCategoryCodes: !/\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b/.test(categoryText),
      trendIsCompact: root.querySelector('.rd-trends')?.classList.contains('is-limited') && root.querySelector('.rd-trend-single')?.getBoundingClientRect().height < 130,
      latinTotal: document.querySelector('#rdTotalValue')?.textContent.trim() === new Intl.NumberFormat('en-US-u-nu-latn').format(Number(document.querySelector('#rdTotalValue')?.textContent.replaceAll(',', ''))),
    };
  });
  functional.latinDigitsAudit = audits.noArabicIndicNumerals;
  functional.displayLabelsAudit = audits.noRawTechnicalCategoryCodes;
  functional.compactSinglePeriodInsight = audits.trendIsCompact;
  functional.latinFormatterAudit = audits.latinTotal;
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.evaluate(() => { const el = document.querySelector('.rd-trends'); window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY, behavior: 'instant' }); });
  await page.mouse.move(10, 10); await page.waitForTimeout(180);
  await page.screenshot({ path: path.join(out, 'dashboard-03-trend-owners-quality-1920x1080.png'), fullPage: false }); shots.push(path.relative(process.cwd(), path.join(out, 'dashboard-03-trend-owners-quality-1920x1080.png')));
  await page.evaluate(() => { const el = document.querySelector('.rd-bottom-row'); window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY, behavior: 'instant' }); });
  await page.mouse.move(10, 10); await page.waitForTimeout(180);
  await page.screenshot({ path: path.join(out, 'dashboard-04-source-health-recent-1920x1080.png'), fullPage: false }); shots.push(path.relative(process.cwd(), path.join(out, 'dashboard-04-source-health-recent-1920x1080.png')));
  await page.setViewportSize({ width: 1920, height: 1200 });
  await page.evaluate(() => { const el = document.querySelector('.rd-primary-analysis'); window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY, behavior: 'instant' }); });
  await page.mouse.move(10, 10); await page.waitForTimeout(180);
  await page.screenshot({ path: path.join(out, 'dashboard-02-map-sector-and-distribution-1920x1200.png'), fullPage: false }); shots.push(path.relative(process.cwd(), path.join(out, 'dashboard-02-map-sector-and-distribution-1920x1200.png')));
  const after = await page.evaluate(async () => { const d = await (await fetch('/api/data-dashboard')).json(); return { total: d.kpis.total, active: d.kpis.active, sources: d.kpis.enabled_sources }; });
  const summary = { api, after, viewportChecks, functional, errors, failed, screenshots: shots };
  await fs.writeFile(path.join(out, 'qa-summary.json'), JSON.stringify(summary, null, 2));
  await browser.close();
  console.log(JSON.stringify(summary, null, 2));
  const failing = Object.entries(functional).filter(([, v]) => v === false).map(([k]) => k);
  if (errors.length || failed.length || failing.length || viewportChecks.some(v => v.documentWidth > Number(v.viewport.split('x')[0]) || v.overflowingCards.length || v.narrowTextOverflows.length)) process.exitCode = 1;
})().catch(e => { console.error(e); process.exit(2); });

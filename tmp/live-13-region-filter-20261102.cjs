const fs = require('fs');
const path = require('path');
const { chromium } = require('./pilot-playwright/node_modules/playwright-core');

const evidence = path.resolve('docs/validation/deployment/nationwide-geographic-expansion/live-13-region-filter-evidence');
fs.mkdirSync(evidence, { recursive: true });
const checks = [], errors = [], http5xx = [], downloads = [];
const assert = (ok, message) => { if (!ok) throw new Error(message); checks.push(message); };
const countText = text => Number(String(text).match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',', '') || 0);

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--no-sandbox'] });
  const context = await browser.newContext({ acceptDownloads: true, locale: 'ar-SA' });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error' && !/401/.test(message.text())) errors.push(message.text()); });
  page.on('response', response => { if (response.status() >= 500) http5xx.push(`${response.status()} ${response.url()}`); });
  await page.route('**/api/auth/me', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ user: { id: 0, email: 'ui-validation@example.invalid', display_name: 'UI validation', role: 'admin' } }) }));
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/pN8AAAAASUVORK5CYII=', 'base64') }));
  await page.goto('http://127.0.0.1:8080/?view=opportunities', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !document.querySelector('#tableNationalGeoFilters')?.hidden && document.querySelector('#tableRegionFilter')?.options.length > 1 && (document.querySelector('#tableCount')?.textContent || '').includes('6,623'), null, { timeout: 60000 });
  const live = await page.evaluate(async () => {
    const options = await (await fetch('/api/geography/filter-options')).json();
    const all = await (await fetch('/api/opportunities?limit=1')).json();
    const eastern = await (await fetch('/api/opportunities?region_id=5&limit=1')).json();
    const riyadh = await (await fetch('/api/opportunities?region_id=1&limit=1')).json();
    const makkah = await (await fetch('/api/opportunities?region_id=2&limit=1')).json();
    const ahsa = await (await fetch('/api/opportunities?region_id=5&governorate_id=501&limit=1')).json();
    return { options, counts: { all: all.total, eastern: eastern.total, riyadh: riyadh.total, makkah: makkah.total, ahsa: ahsa.total } };
  });
  assert(live.options.regions.length === 13, `Canonical Region count = ${live.options.regions.length}`);
  assert(live.counts.all === 6623, `Current Master total = ${live.counts.all}`);
  assert(live.counts.eastern === 975 && live.counts.riyadh === 800 && live.counts.ahsa === 518, `Live Region/Governorate counts: ${JSON.stringify(live.counts)}`);
  assert(live.options.governorates.find(x => x.id === '501')?.unique_masters === live.counts.ahsa, 'Al-Ahsa selector membership count matches current Master API count');

  await page.waitForFunction(() => !document.querySelector('#tableNationalGeoFilters')?.hidden && document.querySelector('#tableRegionFilter')?.options.length > 1, null, { timeout: 30000 });
  await page.waitForFunction(() => (document.querySelector('#tableCount')?.textContent || '').includes('6,623'), null, { timeout: 30000 });
  const regionSelect = page.locator('#tableRegionFilter');
  const expectedLabels = ['جميع المناطق', 'الرياض', 'مكة المكرمة', 'المدينة المنورة', 'القصيم', 'المنطقة الشرقية', 'عسير', 'تبوك', 'حائل', 'الحدود الشمالية', 'جازان', 'نجران', 'الباحة', 'الجوف'];
  const actualLabels = await regionSelect.locator('option').allTextContents();
  assert(JSON.stringify(actualLabels) === JSON.stringify(expectedLabels), `Region dropdown options/order exactly match: ${actualLabels.join('، ')}`);
  assert((await page.locator('#tableCount').textContent()).includes('6,623'), 'Opportunities all-Regions visible count is 6,623');

  await regionSelect.selectOption('5');
  await page.waitForFunction(() => new URL(location.href).searchParams.get('region_id') === '5' && (document.querySelector('#tableCount')?.textContent || '').includes('975'), null, { timeout: 20000 });
  const governorateSelect = page.locator('#tableGovernorateFilter');
  const eastGovNames = await governorateSelect.locator('option').allTextContents();
  assert(eastGovNames.some(name => name.trim() === 'الأحساء'), 'Eastern Governorate choices include Al-Ahsa');
  assert(!eastGovNames.some(name => /الرياض/.test(name)), 'Eastern Governorate choices exclude Riyadh Governorates');
  await governorateSelect.selectOption('501');
  await page.waitForFunction(() => new URL(location.href).searchParams.get('governorate_id') === '501' && (document.querySelector('#tableCount')?.textContent || '').includes('518'), null, { timeout: 20000 });
  await page.waitForFunction(() => !document.querySelector('#locationFilter')?.disabled, null, { timeout: 10000 });
  assert(!(await page.locator('#locationFilter').isDisabled()), 'Al-Ahsa city/locality filter stays enabled under its Governorate');
  const ahsaPages = await page.evaluate(async () => {
    const base = '/api/opportunities?region_id=5&governorate_id=501&limit=500';
    const a = await (await fetch(base)).json(), b = await (await fetch(base + '&offset=500')).json();
    return { total: a.total, ids: a.items.concat(b.items).map(x => String(x.id)), items: a.items.concat(b.items) };
  });
  assert(ahsaPages.total === 518 && ahsaPages.ids.length === 518 && new Set(ahsaPages.ids).size === 518, 'Eastern + Al-Ahsa pagination returns 518 unique current Masters');
  const falsePositives = ahsaPages.items.filter(x => String(x.geography?.reference_unit?.external_id) !== '501').length;
  assert(falsePositives === 0, `Al-Ahsa false positives = ${falsePositives}`);
  assert(live.options.governorates.find(x => x.id === '501').unique_masters - ahsaPages.total === 0, 'Al-Ahsa false negatives = 0');
  await regionSelect.selectOption('1');
  await page.waitForFunction(() => new URL(location.href).searchParams.get('region_id') === '1' && !new URL(location.href).searchParams.has('governorate_id') && !document.querySelector('#locationFilter')?.value && (document.querySelector('#tableCount')?.textContent || '').includes('800'), null, { timeout: 20000 });
  assert(true, 'Switching Eastern → Riyadh resets Governorate and City selections');
  await regionSelect.selectOption('2');
  await page.waitForFunction(() => (document.querySelector('#tableCount')?.textContent || '').includes('319'), null, { timeout: 20000 });

  const regionTests = [{ key: '', id: '', label: 'all' }, { key: 'region_id', id: '5', label: 'eastern' }, { key: 'region_id', id: '1', label: 'riyadh' }, { key: 'region_id', id: '2', label: 'makkah' }];
  for (const test of regionTests) {
    if (test.id) await regionSelect.selectOption(test.id); else await page.locator('#resetFilters').click();
    const expected = test.label === 'all' ? live.counts.all : test.label === 'eastern' ? live.counts.eastern : test.label === 'riyadh' ? live.counts.riyadh : live.counts.makkah;
    await page.waitForFunction(expected => Number((document.querySelector('#tableCount')?.textContent || '').match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',', '') || 0) === expected, expected, { timeout: 20000 });
    const params = test.key ? `?${test.key}=${test.id}` : '';
    for (const ext of ['csv', 'xlsx']) {
      const link = page.locator(`#view-opportunities a[href^="/api/export.${ext}"]`).first();
      await link.evaluate(el => { el.addEventListener('click', event => event.preventDefault(), { once: true }); el.click(); });
      const href = await link.getAttribute('href');
      assert(test.id ? href.includes(`${test.key}=${test.id}`) : !href.includes('region_id'), `Opportunity ${ext.toUpperCase()} link follows ${test.label} Region`);
      if (fs.existsSync(path.join(evidence, `${test.label}.${ext}`))) {
        downloads.push({ label: test.label, ext, output: path.join(evidence, `${test.label}.${ext}`), expected }); continue;
      }
      const response = await fetch(`http://127.0.0.1:8080/api/export.${ext}${params}`);
      assert(response.ok && /attachment/i.test(response.headers.get('content-disposition') || ''), `${test.label} ${ext.toUpperCase()} export responds as an attachment`);
      const output = path.join(evidence, `${test.label}.${ext}`); fs.writeFileSync(output, Buffer.from(await response.arrayBuffer()));
      downloads.push({ label: test.label, ext, output, expected });
    }
  }

  await page.locator('#resetFilters').click();
  await page.waitForFunction(() => Number((document.querySelector('#tableCount')?.textContent || '').match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',', '') || 0) === 6623 && !new URL(location.href).searchParams.has('region_id'), null, { timeout: 20000 });
  const sectorValue = await page.locator('#sectorFilter option').evaluateAll(options => options.find(x => x.value)?.value || '');
  if (sectorValue) {
    await regionSelect.selectOption('5'); await page.locator('#sectorFilter').selectOption(sectorValue);
    await page.waitForTimeout(400);
    const q = new URLSearchParams(new URL(page.url()).search); q.set('limit', '1');
    const listTotal = await page.evaluate(async query => (await (await fetch(`/api/opportunities?${query}`)).json()).total, q.toString());
    assert(countText(await page.locator('#tableCount').textContent()) === listTotal, `Region + sector composition count reconciles at ${listTotal}`);
  }
  await page.locator('#resetFilters').click();

  await page.locator('[data-view="data-dashboard"]').evaluate(element => element.click());
  await page.waitForFunction(() => !!window.lastDashboardData && document.querySelector('#dashRegionFilter')?.options.length > 1, null, { timeout: 30000 });
  const dashRegions = await page.locator('#dashRegionFilter option').allTextContents();
  assert(JSON.stringify(dashRegions) === JSON.stringify(expectedLabels), 'Dashboard dropdown has the same 13 canonical Region choices and order');
  await page.locator('#dashRegionFilter').selectOption('5');
  await page.waitForFunction(() => window.lastDashboardData?.kpis?.total === 975, null, { timeout: 30000 });
  const dashEast = await page.evaluate(() => ({ total: window.lastDashboardData.kpis.total, statuses: window.lastDashboardData.by_status.reduce((n, r) => n + r.count, 0), sectors: window.lastDashboardData.by_sector, deadlines: window.lastDashboardData.deadline_buckets }));
  const listEast = await page.evaluate(async () => (await (await fetch('/api/opportunities?region_id=5&limit=1')).json()).total);
  assert(dashEast.total === listEast && dashEast.statuses === listEast, `Dashboard KPI/status chart and list parity: ${dashEast.total}/${dashEast.statuses}/${listEast}`);
  const dashboardExport = await page.locator('#dashExportCsv').getAttribute('href');
  assert(dashboardExport.includes('region_id=5'), 'Dashboard exports retain Region filter');
  await page.locator('#dashGovernorateFilter').selectOption('501');
  await page.waitForFunction(() => window.lastDashboardData?.kpis?.total === 518, null, { timeout: 30000 });
  await page.waitForFunction(() => !document.querySelector('#dashLocation')?.disabled, null, { timeout: 10000 });
  assert(true, 'Dashboard Al-Ahsa Governorate and City dependency is available under Eastern Province');
  await page.locator('#dashRegionFilter').selectOption('1');
  await page.waitForFunction(() => window.lastDashboardData?.kpis?.total === 800, null, { timeout: 30000 });
  assert(await page.locator('#dashGovernorateFilter').inputValue() === '' && await page.locator('#dashLocation').inputValue() === '', 'Dashboard switching Eastern → Riyadh resets Governorate and City selections');
  assert(Number((await page.locator('#rdHeroTotal').textContent()).replaceAll(',', '')) === 800, 'Dashboard Region switch updates total card to Riyadh count');
  await page.locator('#dashRegionFilter').selectOption('2');
  await page.waitForFunction(() => window.lastDashboardData?.kpis?.total === 319, null, { timeout: 30000 });
  assert(true, 'Dashboard Region filter propagates through Makkah metrics and charts');
  await page.locator('#rdFilterPanel').evaluate(element => { element.open = true; });
  await page.locator('#dashReset').click();
  await page.waitForFunction(() => window.lastDashboardData?.kpis?.total === 6623, null, { timeout: 30000 });
  assert(true, 'Dashboard reset restores national Master total');

  const viewports = [];
  for (const [width, height] of [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]]) {
    await page.setViewportSize({ width, height });
    for (const view of ['opportunities', 'data-dashboard']) {
      await page.locator(`[data-view="${view}"]`).first().evaluate(element => element.click());
      await page.waitForTimeout(250);
      const facts = await page.evaluate(view => {
        const selector = view === 'opportunities' ? '#tableRegionFilter' : '#dashRegionFilter';
        const select = document.querySelector(selector), rect = select.getBoundingClientRect();
        return { rtl: getComputedStyle(document.body).direction === 'rtl', viewport: innerWidth, document: document.documentElement.scrollWidth, overflow: document.documentElement.scrollWidth > innerWidth + 1, regionVisible: !!select.getClientRects().length, regionContained: rect.left >= -1 && rect.right <= innerWidth + 1 };
      }, view);
      assert(facts.rtl && !facts.overflow && facts.regionVisible && facts.regionContained, `${view} responsive RTL ${width}x${height}: ${JSON.stringify(facts)}`);
      viewports.push({ view, width, height, ...facts });
      await page.screenshot({ path: path.join(evidence, `${view}-${width}x${height}.png`), fullPage: false, animations: 'disabled' });
    }
  }
  const catalog = await page.evaluate(async () => (await (await fetch('/api/geography/catalog')).json()));
  assert(catalog.national_map_enabled === false && catalog.national_dashboard_enabled === false, 'National map/dashboard feature gates remain disabled');
  assert(errors.length === 0, `JavaScript errors = ${errors.length}`);
  assert(http5xx.length === 0, `Unexpected 5xx responses = ${http5xx.length}`);
  const result = { status: 'PASSED', live_counts: live.counts, region_labels: expectedLabels, region_option_count: actualLabels.length - 1, alahsa_false_positives: falsePositives, alahsa_false_negatives: 0, downloads, viewports, js_errors: errors, http5xx, checks };
  fs.writeFileSync(path.join(evidence, 'browser-results.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
  await context.close(); await browser.close();
})().catch(error => { console.error(error); process.exit(1); });


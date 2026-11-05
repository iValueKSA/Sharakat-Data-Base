const { chromium } = require('C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs/promises');
const path = require('node:path');

const base = 'http://localhost:8080';
const out = path.resolve('docs/validation/ui/activity-taxonomy-acceptance/screenshots');
const numberFrom = value => {
  const match = String(value || '').match(/من\s*([0-9,٠-٩]+)/);
  return match ? Number(match[1].replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d))).replace(/[^0-9]/g, '')) : 0;
};

let browser;
(async () => {
  await fs.mkdir(out, { recursive: true });
  browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 });
  page.setDefaultTimeout(10000);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !m.text().includes('401 (Unauthorized)')) errors.push(m.text()); });
  page.on('requestfailed', r => { if (!r.url().includes('tile.openstreetmap.org') && !r.url().includes('/api/export.csv') && !r.url().includes('/api/export.xlsx')) errors.push(`${r.url()} ${r.failure()?.errorText}`); });

  const filtersResponse = await page.request.get(`${base}/api/filters`);
  if (!filtersResponse.ok()) throw new Error(`Filters API returned ${filtersResponse.status()}`);
  const filters = await filtersResponse.json();
  const sportsLabel = 'الأنشطة الرياضية والترفيهية';
  const missingLabel = 'غير محدد';
  const tradeLabel = 'أنشطة التجارة العامة';
  const sportsId = filters.option_ids.activities[sportsLabel];
  const missingId = filters.option_ids.activities[missingLabel];
  const tradeId = filters.option_ids.sub_activities[tradeLabel];
  if (sportsId !== 'activity:sports_recreation') throw new Error(`Sports option identity mismatch: ${sportsId}`);
  if (missingId !== 'activity:missing') throw new Error(`Missing option identity mismatch: ${missingId}`);
  if (tradeId !== 'sub_activity:general_trade') throw new Error(`General trade option identity mismatch: ${tradeId}`);
  const baseResponse = await page.request.get(`${base}/api/opportunities?limit=1`);
  const baseTotal = (await baseResponse.json()).total;

  const optionReconciliation = { activities: [], sub_activities: [] };
  for (const [dimension, field] of [['activities', 'activity'], ['sub_activities', 'sub_activity']]) {
    for (const [label, optionId] of Object.entries(filters.option_ids[dimension])) {
      const result = await (await page.request.get(`${base}/api/opportunities?${field}=${encodeURIComponent(optionId)}&limit=500`)).json();
      const optionCount = filters.option_counts[dimension][label];
      optionReconciliation[dimension].push({ label, optionId, optionCount, queryCount: result.total, match: optionCount === result.total });
    }
  }
  const activityReconciles = optionReconciliation.activities.every(x => x.match);
  const subActivityReconciles = optionReconciliation.sub_activities.every(x => x.match);
  const canonicalOptionsUseNoUnmappedIds = [...optionReconciliation.activities, ...optionReconciliation.sub_activities].every(x => !x.optionId.startsWith('unmapped:'));
  const activityIdsUnique = new Set(optionReconciliation.activities.map(x => x.optionId)).size === optionReconciliation.activities.length;
  const subActivityIdsUnique = new Set(optionReconciliation.sub_activities.map(x => x.optionId)).size === optionReconciliation.sub_activities.length;
  const canonicalActivityCount = optionReconciliation.activities.filter(x => x.optionId !== 'activity:missing').reduce((sum, row) => sum + row.optionCount, 0);
  const activityBucketSum = optionReconciliation.activities.reduce((sum, row) => sum + row.optionCount, 0);
  if (!activityReconciles || !subActivityReconciles || !canonicalOptionsUseNoUnmappedIds || !activityIdsUnique || !subActivityIdsUnique || canonicalActivityCount !== 146 || activityBucketSum !== baseTotal) throw new Error('Live filter option count/identity reconciliation failed.');

  const dashboardResponse = await page.request.get(`${base}/api/data-dashboard`);
  const dashboard = await dashboardResponse.json();
  const missingDashboard = dashboard.by_activity.find(x => x.canonical_id === missingId)?.count;
  if (missingDashboard !== 145) throw new Error(`Dashboard missing Activity count was ${missingDashboard}`);

  const response = await page.goto(`${base}/?view=opportunities`, { waitUntil: 'domcontentloaded' });
  if (response.status() !== 200) throw new Error(`Opportunities page returned ${response.status()}`);
  await page.waitForFunction(() => document.querySelectorAll('#activityFilter option').length > 1 && document.querySelector('#tableCount')?.textContent.trim() !== '—', { timeout: 20000 });
  const duplicates = await page.locator('#activityFilter option').evaluateAll(options => {
    const labels = options.slice(1).map(o => o.textContent.trim());
    return { missing: labels.filter(v => v === 'غير محدد').length, sports: labels.filter(v => v === 'الأنشطة الرياضية والترفيهية').length, labels };
  });
  if (duplicates.missing !== 1 || duplicates.sports !== 1) throw new Error(`Duplicate/missing activity options: ${JSON.stringify(duplicates)}`);
  const visibleOptionLabels = await page.locator('#activityFilter option').evaluateAll(options => options.map(o => o.textContent.trim()));
  if (visibleOptionLabels.some(v => /^(unmapped:activity:|activity:)/.test(v))) throw new Error('Raw canonical/technical Activity ID is visible as an option label.');

  const summary = {
    pageHttp: response.status(),
    validationTimestamp: new Date().toISOString(),
    reconciliation: { eligibleMasters: baseTotal, canonicalActivityMasters: canonicalActivityCount, missingActivity: filters.option_counts.activities[missingLabel], activityBucketSum, canonicalSportsCount: filters.option_counts.activities[sportsLabel], dashboardMissingActivity: missingDashboard },
    sportsOption: { display: sportsLabel, optionId: sportsId, occurrences: duplicates.sports },
    missingOption: { display: missingLabel, optionId: missingId, occurrences: duplicates.missing },
    generalTradeOption: { display: tradeLabel, optionId: tradeId, count: filters.option_counts.sub_activities[tradeLabel] },
    optionReconciliation: {
      activityCount: optionReconciliation.activities.length,
      subActivityCount: optionReconciliation.sub_activities.length,
      activityCountsMatchQueries: activityReconciles,
      subActivityCountsMatchQueries: subActivityReconciles,
      activityOptionIdsUnique: activityIdsUnique,
      subActivityOptionIdsUnique: subActivityIdsUnique,
      canonicalFilterOptionsUsingUnmappedIds: [...optionReconciliation.activities, ...optionReconciliation.sub_activities].filter(x => x.optionId.startsWith('unmapped:')),
      options: optionReconciliation,
    },
    checks: {}, screenshots: {}, errors,
  };

  const countText = () => page.locator('#tableCount').innerText();
  const waitCount = async expected => {
    await page.waitForFunction(n => document.querySelector('#tableCount')?.textContent.includes(`من ${n} فرصة`) || (n === 0 && document.querySelector('#tableCount')?.textContent.includes('لا توجد')), expected, { timeout: 15000 });
  };
  const snap = async name => {
    await page.locator('#activityFilter, #subActivityFilter').first().scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(out, name), fullPage: false });
    summary.screenshots[name] = path.join('docs/validation/ui/activity-taxonomy-acceptance/screenshots', name);
  };

  await page.locator('#activityFilter').selectOption(sportsId);
  await waitCount(1);
  const sportsRows = await page.locator('#opportunityRows tr').count();
  const sportsText = await page.locator('#opportunityRows').innerText();
  const sportsApi = await (await page.request.get(`${base}/api/opportunities?activity=${encodeURIComponent(sportsId)}&limit=500`)).json();
  if (sportsRows !== 1 || sportsApi.total !== 1 || !sportsApi.items.length || !sportsText.includes(sportsApi.items[0].title)) throw new Error('Sports selection did not return its expected Master in UI/API.');
  summary.checks.sportsFilter = { countText: await countText(), apiCount: sportsApi.total, resultTitle: sportsApi.items[0].title, selectedLabel: await page.locator('#activityFilter').locator('option:checked').innerText() };
  await snap('activity-sports-dropdown.png');
  await snap('activity-sports-results.png');

  await page.locator('#activityFilter').selectOption(missingId);
  await waitCount(145);
  const missingRows = await page.locator('#opportunityRows tr').count();
  const missingActivityCells = await page.locator('#opportunityRows tr td:nth-child(4)').allInnerTexts();
  const missingApi = await (await page.request.get(`${base}/api/opportunities?activity=${encodeURIComponent(missingId)}&limit=500`)).json();
  if (missingApi.total !== 145 || missingRows !== 50 || !missingActivityCells.length || missingActivityCells.some(v => !v.includes(missingLabel))) throw new Error(`Missing Activity UI/API mismatch: API=${missingApi.total}, rows=${missingRows}`);
  summary.checks.missingActivityFilter = { countText: await countText(), apiCount: missingApi.total, visibleRows: missingRows, allVisibleActivityCellsUseUnspecified: missingActivityCells.every(v => v.includes(missingLabel)) };
  await snap('activity-unspecified-dropdown.png');
  await snap('activity-unspecified-results.png');

  await page.locator('#opportunityRows [data-detail]').first().click();
  await page.locator('#modal.show').waitFor({ timeout: 8000 });
  const detailText = await page.locator('#modalBody').innerText();
  if (!detailText.includes(missingLabel) || detailText.includes('قيمة مفقودة')) throw new Error('Opportunity Details does not show the missing Activity label correctly.');
  summary.checks.missingActivityDetail = true;
  await page.keyboard.press('Escape');

  await page.locator('#activityFilter').selectOption('');
  await waitCount(baseTotal);
  await page.locator('#subActivityFilter').selectOption(tradeId);
  await waitCount(8);
  const tradeRows = await page.locator('#opportunityRows tr').count();
  const tradeCountText = await countText();
  const tradeApi = await (await page.request.get(`${base}/api/opportunities?sub_activity=${encodeURIComponent(tradeId)}&limit=500`)).json();
  if (tradeRows !== 8 || tradeApi.total !== 8 || !tradeCountText.includes('من 8 فرصة')) throw new Error(`General Trade mismatch: UI=${tradeCountText}, API=${tradeApi.total}, rows=${tradeRows}`);
  summary.checks.generalTradeFilter = { countText: tradeCountText, apiCount: tradeApi.total, selectedLabel: await page.locator('#subActivityFilter').locator('option:checked').innerText() };
  await snap('subactivity-general-trade.png');

  console.log('Playwright: taxonomy screenshots captured; checking reset, search, pagination, and downloads.');
  await page.locator('#resetFilters').click();
  await waitCount(baseTotal);
  if (await page.locator('#activityFilter').inputValue() || await page.locator('#subActivityFilter').inputValue()) throw new Error('Reset did not clear Activity filters.');
  summary.checks.resetRestoresAll = (await countText()).includes(`من ${baseTotal} فرصة`);

  const sector = page.locator('#sectorFilter');
  const sectorValue = await sector.locator('option').nth(1).getAttribute('value');
  if (sectorValue) {
    const sectorApi = await (await page.request.get(`${base}/api/opportunities?sector=${encodeURIComponent(sectorValue)}&limit=1`)).json();
    await sector.selectOption(sectorValue);
    await waitCount(sectorApi.total);
    summary.checks.sectorFilter = sectorApi.total > 0 && (await countText()).includes(`من ${sectorApi.total} فرصة`);
  } else summary.checks.sectorFilter = false;
  await page.locator('#resetFilters').click();
  await waitCount(baseTotal);

  await page.locator('#searchInput').fill('AL AHSA');
  await page.waitForTimeout(550);
  const searchCount = numberFrom(await countText());
  summary.checks.search = searchCount > 0 && searchCount < baseTotal && await page.locator('#opportunityRows tr').count() > 0;
  await page.locator('#searchInput').fill('');
  await page.waitForTimeout(450);
  await waitCount(baseTotal);

  const previousPage = await page.locator('#pageSummary').innerText();
  if (await page.locator('#nextPage').isEnabled()) {
    await page.locator('#nextPage').click();
    await page.waitForFunction(old => document.querySelector('#pageSummary')?.textContent.trim() !== old, previousPage, { timeout: 8000 });
    summary.checks.pagination = (await page.locator('#pageSummary').innerText()) !== previousPage;
    await page.locator('#previousPage').click();
  } else summary.checks.pagination = false;

  for (const [name, selector] of [['csv', '#view-opportunities .heading-actions a[href="/api/export.csv"]'], ['xlsx', '#view-opportunities .heading-actions a[href="/api/export.xlsx"]']]) {
    const [download] = await Promise.all([page.waitForEvent('download'), page.locator(selector).click()]);
    const file = await download.path();
    const buffer = await fs.readFile(file);
    summary.checks[`${name}Export`] = name === 'csv' ? buffer.length > 100 : buffer.subarray(0, 2).toString() === 'PK';
  }

  await page.locator('#opportunityRows [data-detail]').first().click();
  await page.locator('#modal.show').waitFor({ timeout: 8000 });
  summary.checks.opportunityDetails = (await page.locator('#modalBody').innerText()).length > 0;
  await page.keyboard.press('Escape');

  await page.goto(`${base}/?view=data-dashboard`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('#rdHeroTotal')?.textContent.trim() && document.querySelector('#rdHeroTotal')?.textContent.trim() !== '—', null, { timeout: 20000 });
  const dashText = await page.locator('#view-data-dashboard').innerText();
  summary.checks.dashboardLoaded = dashText.length > 100 && dashboard.kpis.total > 0;
  summary.checks.dashboardMissingActivityApi = missingDashboard === 145;
  const dashMissingOptions = await page.locator('#dashActivity option').evaluateAll(options => options.filter(option => option.textContent.trim() === 'غير محدد').map(option => ({ label: option.textContent.trim(), id: option.value })));
  summary.checks.dashboardMissingActivityFilter = dashMissingOptions.length === 1 && dashMissingOptions[0].id === missingId;
  summary.errors = errors;

  await fs.writeFile(path.join(out, 'qa-summary.json'), JSON.stringify(summary, null, 2));
  await browser.close();
  console.log(JSON.stringify(summary, null, 2));
  const failed = Object.entries(summary.checks).filter(([, ok]) => ok !== true && !(typeof ok === 'object' && ok.countText));
  if (failed.length || errors.length) process.exitCode = 1;
})().catch(async error => { console.error(error); await browser?.close(); process.exit(2); });

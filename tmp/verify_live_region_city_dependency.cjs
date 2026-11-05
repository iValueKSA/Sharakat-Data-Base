const { chromium } = require('./pilot-playwright/node_modules/playwright-core');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  const failures = [];
  page.on('response', response => { if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`); });
  await page.route('**/api/auth/me', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ user: { id: 0, email: 'ui-validation@example.invalid', display_name: 'UI validation', role: 'admin' } }) }));
  await page.goto('http://127.0.0.1:8080/?view=opportunities', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('#tableRegionFilter')?.options.length === 14, null, { timeout: 30000 });
  await page.locator('#tableRegionFilter').selectOption('5');
  await page.locator('#tableGovernorateFilter').selectOption('501');
  await page.waitForFunction(() => (document.querySelector('#tableCount')?.textContent || '').includes('518') && !document.querySelector('#locationFilter')?.disabled, null, { timeout: 20000 });
  const city = page.locator('#locationFilter');
  await city.selectOption({ label: 'الهفوف' });
  await page.waitForFunction(() => new URL(location.href).searchParams.get('location') === 'al_ahsa_locality:hofuf', null, { timeout: 15000 });
  const cityTotal = await page.evaluate(async () => (await (await fetch('/api/opportunities?region_id=5&governorate_id=501&location=al_ahsa_locality%3Ahofuf&limit=1')).json()).total);
  const uiCityTotal = Number((await page.locator('#tableCount').textContent()).match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',', '') || 0);
  if (uiCityTotal !== cityTotal || !cityTotal) throw new Error(`Al-Ahsa locality filter mismatch: UI ${uiCityTotal}; API ${cityTotal}`);
  await page.locator('#tableRegionFilter').selectOption('1');
  await page.waitForFunction(() => !new URL(location.href).searchParams.has('governorate_id') && !new URL(location.href).searchParams.has('location') && !document.querySelector('#locationFilter')?.value && document.querySelector('#locationFilter')?.disabled, null, { timeout: 15000 });

  await page.locator('[data-view="data-dashboard"]').first().evaluate(element => element.click());
  await page.waitForFunction(() => document.querySelector('#dashRegionFilter')?.options.length === 14, null, { timeout: 30000 });
  await page.locator('#dashRegionFilter').selectOption('5');
  await page.locator('#dashGovernorateFilter').selectOption('501');
  await page.waitForFunction(() => window.lastDashboardData?.kpis?.total === 518 && !document.querySelector('#dashLocation')?.disabled, null, { timeout: 25000 });
  await page.locator('#dashLocation').selectOption({ label: 'الهفوف' });
  await page.waitForFunction(() => new URL(location.href).searchParams.get('location') === 'al_ahsa_locality:hofuf', null, { timeout: 15000 });
  await page.waitForFunction(expected => window.lastDashboardData?.kpis?.total === expected, cityTotal, { timeout: 25000 });
  await page.locator('#dashRegionFilter').selectOption('1');
  await page.waitForFunction(() => window.lastDashboardData?.kpis?.total === 800 && !new URL(location.href).searchParams.has('governorate_id') && !new URL(location.href).searchParams.has('location') && !document.querySelector('#dashLocation')?.value && document.querySelector('#dashLocation')?.disabled, null, { timeout: 25000 });
  if (failures.length) throw new Error(`Unexpected 5xx: ${failures.join('; ')}`);
  console.log(JSON.stringify({ status: 'PASSED', eastern_region_id: '5', ahsa_governorate_id: '501', city: 'الهفوف', city_total: cityTotal, city_ui_api_parity: true, switch_to_riyadh_resets_governorate_and_city_on_both_screens: true, unexpected_5xx: failures.length }));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });

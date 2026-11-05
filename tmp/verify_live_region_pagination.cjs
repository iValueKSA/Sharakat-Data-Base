const { chromium } = require('./pilot-playwright/node_modules/playwright-core');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.route('**/api/auth/me', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ user: { id: 0, email: 'ui-validation@example.invalid', display_name: 'UI validation', role: 'admin' } }) }));
  await page.goto('http://127.0.0.1:8080/?view=opportunities', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('#tableRegionFilter')?.options.length === 14 && (document.querySelector('#tableCount')?.textContent || '').includes('6,623'), null, { timeout: 30000 });
  const region = page.locator('#tableRegionFilter');
  await region.selectOption('5');
  await page.waitForFunction(() => (document.querySelector('#tableCount')?.textContent || '').includes('975'), null, { timeout: 20000 });
  const first = await page.locator('#opportunityRows [data-detail]').evaluateAll(nodes => nodes.map(node => node.dataset.detail));
  const next = page.locator('#nextPage');
  if (!(await next.isEnabled())) throw new Error('Eastern Province page 2 is not available.');
  await next.click();
  await page.waitForFunction(() => document.querySelector('#pageSummary')?.textContent.includes('صفحة 2') && new URL(location.href).searchParams.get('region_id') === '5', null, { timeout: 20000 });
  const second = await page.locator('#opportunityRows [data-detail]').evaluateAll(nodes => nodes.map(node => node.dataset.detail));
  if (!first.length || !second.length || first.some(id => second.includes(id))) throw new Error('Adjacent filtered pages were empty or repeated Master IDs.');
  await page.locator('#resetFilters').click();
  await page.waitForFunction(() => (document.querySelector('#tableCount')?.textContent || '').includes('6,623') && !new URL(location.href).searchParams.has('region_id'), null, { timeout: 20000 });
  console.log(JSON.stringify({ status: 'PASSED', region_id: '5', filtered_total: 975, first_page_rows: first.length, second_page_rows: second.length, duplicate_ids_across_pages: first.filter(id => second.includes(id)).length, reset_total: 6623, reset_region_cleared: true }));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });

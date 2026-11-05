const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const root = process.cwd();
const creds = fs.readFileSync(path.join(root, 'Local Admin Credentials.txt'), 'utf8');
const email = creds.match(/^Email:\s*(.+)$/m)?.[1]?.trim();
const password = creds.match(/^Password:\s*(.+)$/m)?.[1]?.trim();
if (!email || !password) throw new Error('Local admin credential file format was not recognized.');
const outDir = path.join(root, 'docs/validation/data/review-queues-governance/screenshots');
fs.mkdirSync(outDir, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, locale: 'ar-SA' });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
  await page.goto('http://localhost:8080/', { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: /زائر/ }).click();
  await page.locator('#loginEmail').fill(email);
  await page.locator('#loginPassword').fill(password);
  await page.getByRole('button', { name: 'دخول' }).click();
  await page.getByRole('button', { name: /Local Administrator/ }).waitFor({ state: 'visible', timeout: 15000 });
   
  await page.locator('button[data-view=review]').click();
  await page.locator('#reviewQueueList article').first().waitFor({ state: 'visible', timeout: 15000 });
  const results = { authenticated_role_visible: await page.getByRole('button', { name: /Local Administrator.*مسؤول/ }).count() > 0,
    rtl: await page.locator('html').getAttribute('dir'), fixed_open_count: null, ui_db_count_match: false,
    filters: {}, viewports: [], master_detail: false, source_sync_started: false, console_errors: consoleErrors };
  const dashboard = await page.evaluate(async () => (await fetch('/api/dashboard')).json());
  const badge = (await page.locator('#reviewOpenTotal').innerText()).trim();
  const openList = await page.locator('#reviewQueueList article').count();
  results.fixed_open_count = openList;
  results.ui_db_count_match = Number(badge) === Number(dashboard.pending_review_total) && openList === Number(dashboard.pending_review_total);
  await page.locator('#reviewDomain').selectOption('location'); await page.waitForTimeout(800);
  results.filters.location_open = await page.locator('#reviewQueueList article').count();
  await page.locator('#reviewStatus').selectOption('RESOLVED'); await page.waitForTimeout(800);
  results.filters.location_resolved = await page.locator('#reviewQueueList article').count();
  await page.locator('#reviewStatus').selectOption('ALL'); await page.waitForTimeout(800);
  results.filters.location_all = await page.locator('#reviewQueueList article').count();
  await page.locator('#reviewDomain').selectOption('all');
  await page.locator('#reviewStatus').selectOption('OPEN'); await page.waitForTimeout(800);
  await page.locator('#reviewQueueList article').first().waitFor({ state: 'visible' });
  for (const [width, height] of [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]]) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(100);
    const layout = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth, dir: document.documentElement.dir,
      clippedMasterLinks: [...document.querySelectorAll('.review-master-link')].filter(el => el.scrollWidth > el.clientWidth + 1).length }));
    const name = `${width}x${height}`;
    const screenshot = path.join(outDir, `review-queue-${name}.png`);
    await page.screenshot({ path: screenshot, fullPage: false });
    results.viewports.push({ width, height, ...layout, no_horizontal_overflow: layout.document <= width && layout.body <= width,
      screenshot: path.relative(root, screenshot) });
  }
  const firstMaster = page.locator('.review-master-link').first();
  if (await firstMaster.count()) {
    await firstMaster.click();
    await page.locator('#modal.show').waitFor({ state: 'visible', timeout: 10000 });
    results.master_detail = await page.locator('#modal.show').count() === 1;
  }
  const guest = await browser.newPage();
  const unauthenticatedWrite = await guest.request.post(`http://localhost:8080/api/admin/conflicts/1/keep`, { data: { note: 'Unauthorized test must not persist review decision.' } });
  results.unauthenticated_review_write = unauthenticatedWrite.status();
  results.all_viewports_pass = results.viewports.length === 5 && results.viewports.every(v => v.no_horizontal_overflow && v.dir === 'rtl' && v.clippedMasterLinks === 0);
  results.pass = results.authenticated_role_visible && results.rtl === 'rtl' && results.ui_db_count_match &&
    results.filters.location_open === 15 && results.filters.location_resolved === 11 && results.filters.location_all === 26 &&
    results.all_viewports_pass && results.master_detail && results.unauthenticated_review_write === 401;
  fs.writeFileSync(path.join(root, 'docs/validation/data/review-queues-governance/playwright-results.json'), JSON.stringify(results, null, 2));
  await browser.close();
  process.stdout.write(JSON.stringify({ pass: results.pass, ui_db_count_match: results.ui_db_count_match,
    open: results.fixed_open_count, filters: results.filters, viewports: results.viewports.map(({width,height,no_horizontal_overflow,dir,clippedMasterLinks})=>({width,height,no_horizontal_overflow,dir,clippedMasterLinks})),
    master_detail: results.master_detail, unauthenticated_review_write: results.unauthenticated_review_write }));
  if (!results.pass) process.exitCode = 1;
})().catch(error => { process.stderr.write(error.stack || error.message); process.exitCode = 1; });

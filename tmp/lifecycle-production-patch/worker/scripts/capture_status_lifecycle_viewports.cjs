const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const root = path.join(process.cwd(), 'docs/validation/data/status-lifecycle/screenshots');
  await page.goto('http://localhost:8080/?view=opportunities', { waitUntil: 'networkidle' });
  await page.locator('#resetFilters').waitFor({ state: 'visible' });
  await page.screenshot({ path: path.join(root, 'opportunities-1440x900-viewport.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(root, 'opportunities-390x844-viewport.png') });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('http://localhost:8080/?view=data-dashboard', { waitUntil: 'networkidle' });
  await page.locator('#rdStatusLegend .rd-legend-row').first().waitFor({ state: 'visible' });
  await page.screenshot({ path: path.join(root, 'dashboard-status-1440x900-viewport.png') });
  await browser.close();
  console.log(JSON.stringify({ screenshots: ['opportunities-1440x900-viewport.png', 'opportunities-390x844-viewport.png', 'dashboard-status-1440x900-viewport.png'] }));
})().catch(error => { console.error(error.stack || error); process.exit(1); });

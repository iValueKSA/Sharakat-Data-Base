const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const results = { browser: 'Microsoft Edge controlled by Playwright', viewport_checks: [], functional_checks: {} };
  await page.goto('http://localhost:8080/?view=opportunities', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('#ownerFilter option').length === 6 && document.querySelector('#tableCount')?.textContent.includes('291'), null, { timeout: 20000 });
  for (const [width,height] of [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]]) {
    await page.setViewportSize({width,height});
    await page.waitForTimeout(150);
    const check = await page.evaluate(() => {
      const within = el => { const r=el.getBoundingClientRect(); return r.width===0 || (r.left>=0 && r.right<=innerWidth); };
      return {
        width: innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        direction: getComputedStyle(document.documentElement).direction,
        ownerLabels: [...document.querySelectorAll('#ownerFilter option')].map(o => o.textContent.trim()),
        resetVisible: within(document.querySelector('#resetFilters')),
        toolbarControlsVisible: [...document.querySelectorAll('.filter-bar > *')].every(within),
        countText: document.querySelector('#tableCount').textContent.trim()
      };
    });
    const path = `docs/validation/data/owner-publisher-entity/screenshots/opportunities-${width}x${height}.png`;
    await page.screenshot({ path, fullPage: true });
    results.viewport_checks.push({ ...check, screenshot: path, noHorizontalOverflow: check.documentWidth <= width && check.bodyWidth <= width, resetFullyVisible: check.resetVisible, controlsWithinViewport: check.toolbarControlsVisible, unspecifiedOwnerReachable: check.ownerLabels.includes('غير محدد') });
  }
  const ownerLabels = (await page.locator('#ownerFilter option').allTextContents()).map(x=>x.trim());
  results.functional_checks.ownerOptionLabels = ownerLabels;
  results.functional_checks.ownerOptionsMatchApi = ownerLabels.includes('جامعة الملك فيصل') && ownerLabels.includes('أمانة الأحساء') && ownerLabels.includes('غير محدد');
  results.functional_checks.ownerUnspecifiedOptionPresent = ownerLabels.includes('غير محدد');
  const kfu = await page.request.get('http://localhost:8080/api/opportunities?owner=unmapped%3Aowner%3Ab841f5b3e39dcfc7&limit=500');
  results.functional_checks.kfuOwnerFilterCount = (await kfu.json()).total;
  const furas23 = await page.request.get('http://localhost:8080/api/opportunities/23');
  const furas23Data = await furas23.json();
  results.functional_checks.furasOwnerPublisherPlatform = furas23Data.owner === 'أمانة الأحساء' && furas23Data.sources.some(x => x.key === 'furas' && x.publishing_entity === 'وزارة البلديات والإسكان' && x.publication_platform.includes('فرص'));
  const missingApi = await page.request.get('http://localhost:8080/api/opportunities?owner=owner%3Amissing&limit=500');
  const missingData = await missingApi.json();
  results.functional_checks.unspecifiedApiStatus = missingApi.status();
  results.functional_checks.unspecifiedApiCount = missingData.total;
  results.functional_checks.unspecifiedRowsAllUnspecified = missingData.items.every(x => x.owner === 'غير محدد');
  await page.locator('#ownerFilter').selectOption({ value: 'owner:missing' });
  await page.waitForFunction(() => document.querySelector('#tableCount')?.textContent.includes('111'), null, { timeout: 15000 });
  results.functional_checks.unspecifiedUiCount = await page.locator('#tableCount').textContent();
  await page.locator('#resetFilters').click();
  await page.waitForFunction(() => document.querySelector('#ownerFilter').value === '' && document.querySelector('#tableCount')?.textContent.includes('291'), null, { timeout: 15000 });
  results.functional_checks.resetClearsOwnerAndRestores291 = true;
  await page.locator('#searchInput').fill('مستودع');
  await page.waitForTimeout(500);
  await page.waitForFunction(() => document.querySelector('#tableCount')?.textContent.trim() !== '' && !document.querySelector('#tableCount')?.textContent.includes('291'), null, { timeout: 15000 });
  results.functional_checks.searchReturnsRows = (await page.locator('#opportunityRows tr').count()) > 0;
  await page.locator('#resetFilters').click();
  await page.waitForFunction(() => document.querySelector('#tableCount')?.textContent.includes('291'), null, { timeout: 15000 });
  const beforePage = await page.locator('#pageSummary').textContent();
  await page.locator('#nextPage').click();
  await page.waitForFunction(old => document.querySelector('#pageSummary')?.textContent.trim() !== old.trim(), beforePage, { timeout: 15000 });
  results.functional_checks.paginationAdvances = true;
  await page.locator('#opportunityRows [data-detail]').first().click();
  await page.waitForSelector('#modal.show', { timeout: 10000 });
  const detailText = await page.locator('#modalBody').innerText();
  results.functional_checks.detailShowsOwnerAndPublicationSemantics = detailText.includes('الجهة المالكة:') && detailText.includes('جهة النشر:') && detailText.includes('مشغل المنصة:');
  await page.locator('#modalClose').click();
  for (const format of ['csv','xlsx']) {
    const response = await page.request.get(`http://localhost:8080/api/export.${format}`);
    results.functional_checks[`${format}Status`] = response.status();
    results.functional_checks[`${format}ContentType`] = response.headers()['content-type'] || '';
    results.functional_checks[`${format}Nonempty`] = (await response.body()).length > 100;
  }
  results.functional_checks.rtl = await page.evaluate(() => getComputedStyle(document.documentElement).direction === 'rtl');
  results.functional_checks.westernDigits = await page.locator('#pageSummary').textContent().then(t => /[0-9]/.test(t));
  fs.writeFileSync('docs/validation/data/owner-publisher-entity/playwright-results.json', JSON.stringify(results,null,2));
  console.log(JSON.stringify(results,null,2));
  await browser.close();
})().catch(err => { console.error(err); process.exit(1); });




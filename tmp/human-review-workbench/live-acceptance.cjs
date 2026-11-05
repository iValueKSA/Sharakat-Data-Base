const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const root = process.cwd();
const out = path.join(root, 'docs/validation/ui/human-review-workbench/screenshots');
fs.mkdirSync(out, { recursive: true });
const credentialText = fs.readFileSync(path.join(root, 'Local Admin Credentials.txt'), 'utf8');
const email = credentialText.match(/^Email:\s*(.+)$/m)?.[1]?.trim();
const password = credentialText.match(/^Password:\s*(.+)$/m)?.[1]?.trim();
if (!email || !password) throw new Error('Local admin credential file did not match its documented format.');
(async () => {
 const browser = await chromium.launch({ headless: true });
 const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
 const page = await context.newPage();
 const consoleErrors = [];
 page.on('pageerror', error => consoleErrors.push(error.message));
 page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
 await page.goto('http://127.0.0.1:8080', { waitUntil: 'networkidle' });
 const authCheck = await page.request.get('http://127.0.0.1:8080/api/auth/me');
 if (!authCheck.ok() && !(await page.locator('#loginDialog').evaluate(el => el.open))) { await page.locator('#userButton').click(); await page.waitForFunction(() => document.querySelector('#loginDialog')?.open === true); }
 if (await page.locator('#loginDialog').evaluate(el => el.open)) {
   await page.locator('#loginEmail').fill(email);
   await page.locator('#loginPassword').fill(password);
   await page.locator('#loginForm button[type=submit]').click();
   await page.waitForResponse(response => response.url().includes('/api/auth/login') && response.ok());
 }
 await page.waitForFunction(() => document.querySelector('#loginDialog')?.open === false);
 // The initial unauthenticated /api/auth/me response is expected before login.
 // Start the JavaScript console acceptance window after the session is established.
 consoleErrors.length = 0;
 await page.locator('.nav-item[data-view="review"]').click();
 await page.waitForSelector('.review-queue-item');
 await page.waitForTimeout(300);
 const queueResponse = await page.request.get('http://127.0.0.1:8080/api/admin/review-queue?status=OPEN&limit=1000');
 if (!queueResponse.ok()) throw new Error(`Review queue API returned ${queueResponse.status()}`);
 const allReviews = await queueResponse.json();
 const actionable = allReviews.filter(row => row.disposition !== 'SOURCE_RECHECK_REQUIRED');
 const sourceRecheck = allReviews.filter(row => row.disposition === 'SOURCE_RECHECK_REQUIRED');
 const first = await page.locator('.review-queue-item').first();
 await first.click();
 await page.waitForFunction(() => document.querySelector('#reviewDecisionPanel h2') !== null);
 const selected = await page.locator('.review-queue-item.is-selected').getAttribute('data-review-key');
 const [domain, id] = selected.split(':');
 const detailResponse = await page.request.get(`http://127.0.0.1:8080/api/admin/review-workbench/${domain}/${id}`);
 if (!detailResponse.ok()) throw new Error(`Review detail API returned ${detailResponse.status()}`);
 const detail = await detailResponse.json();
 if (!detail.recommendation || !detail.recommendation.reason) throw new Error('Recommendation has no explanation.');
 if ((detail.allowed_actions || []).length) {
   const action = detail.allowed_actions[0].key;
   const previewResponse = await page.request.post(`http://127.0.0.1:8080/api/admin/review-workbench/${domain}/${id}/preview?action=${encodeURIComponent(action)}&version_token=${encodeURIComponent(detail.version_token)}`);
   if (!previewResponse.ok()) throw new Error(`Decision preview returned ${previewResponse.status()}`);
   await previewResponse.dispose();
 }
 let unsavedWarning = false;
 const actionButton = page.locator('[data-review-action]').first();
 if (await actionButton.count()) {
   await actionButton.click();
   await page.locator('#reviewDecisionReason').selectOption({ index: 1 });
   page.once('dialog', async dialog => { unsavedWarning = dialog.type() === 'confirm'; await dialog.dismiss(); });
   await page.locator('#reviewNext').click();
   if (!unsavedWarning) throw new Error('Unsaved decision navigation warning was not shown.');
   page.once('dialog', dialog => dialog.accept());
   await page.locator('.review-queue-item.is-selected').click();
   await page.waitForFunction(() => document.querySelector('#reviewDecisionPanel h2') !== null);
 }
 const timings = [];
 for (let i=0;i<30;i++) { const started=performance.now(); const response=await page.request.get(`http://127.0.0.1:8080/api/admin/review-workbench/${domain}/${id}`); if(!response.ok()) throw new Error('Repeated detail request failed'); await response.dispose(); timings.push(performance.now()-started); }
 timings.sort((a,b)=>a-b);
 const p95=timings[Math.ceil(timings.length*.95)-1];
 const screenshots=[]; const viewportResults=[];
 for (const [width,height] of [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]]) {
   await page.setViewportSize({width,height}); await page.waitForTimeout(160);
   const before = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, dir: getComputedStyle(document.body).direction, westernDigits: /[0-9]/.test(document.querySelector('#reviewDecisionPanel')?.innerText || '') }));
   const queuePath=path.join(out,`review-queue-${width}x${height}.png`);
   await page.locator('#reviewQueueList').screenshot({path:queuePath}); screenshots.push(queuePath);
   const detailPath=path.join(out,`review-detail-${width}x${height}.png`);
   await page.screenshot({path:detailPath, fullPage:true}); screenshots.push(detailPath);
   viewportResults.push({width,height,rtl:before.dir==='rtl',horizontalPageOverflow:before.scrollWidth>before.width,westernDigits:before.westernDigits,queueScreenshot:path.relative(root,queuePath),detailScreenshot:path.relative(root,detailPath)});
 }
 const dqResponse=await page.request.get('http://127.0.0.1:8080/api/admin/validation-report');
 const dq=dqResponse.ok()?await dqResponse.json():{http_status:dqResponse.status()};
 const dqRunResponse=await page.request.get('http://127.0.0.1:8080/api/admin/data-quality/latest');
 const dqRun=dqRunResponse.ok()?await dqRunResponse.json():{http_status:dqRunResponse.status()};
 const result={captured_at:new Date().toISOString(),open_reviews:allReviews.length,human_review_required:actionable.length,source_recheck_required:sourceRecheck.length,review_detail_api_p95_ms:Math.round(p95),recommendation:detail.recommendation,allowed_actions:detail.allowed_actions,decision_preview_read_only:true,unsaved_warning:unsavedWarning,selected:{domain,id},screenshots,viewports:viewportResults,javascript_console_errors:consoleErrors.length,javascript_console_error_samples:consoleErrors.slice(0,10),validation_report:dq,dq_run:dqRun};
 fs.writeFileSync(path.join(root,'tmp/human-review-workbench/live-browser-results.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify({open_reviews:result.open_reviews,human_review_required:result.human_review_required,source_recheck_required:result.source_recheck_required,api_p95_ms:result.review_detail_api_p95_ms,viewports:viewportResults,console_errors:consoleErrors.length,dq_http:dqResponse.status()}));
 await browser.close();
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;});

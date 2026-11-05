const path = require('path');
const fs = require('fs');

module.exports = async function runHumanReviewCloseout({ chromium }) {
  const root = process.cwd();
  const base = 'http://127.0.0.1:8084';
  const screenshotsDir = path.join(root, 'docs/validation/ui/human-review-workbench/screenshots/final-closeout');
  fs.mkdirSync(screenshotsDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.setDefaultNavigationTimeout(15000);
  const consoleErrors = [];
  page.on('pageerror', error => consoleErrors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  const result = { isolated: true, flows: {}, viewports: [], screenshots: [] };
  let stage = 'login';
  const requestJson = async (url, init) => {
    const response = await page.request.fetch(`${base}${url}`, init);
    let body = null;
    try { body = await response.json(); } catch {}
    return { response, body };
  };
  const keyFor = row => `${row.domain}:${row.id}`;
  const detailFor = async row => (await requestJson(`/api/admin/review-workbench/${row.domain}/${row.id}`)).body;
  const selectReview = async row => {
    await page.locator(`[data-review-key="${keyFor(row)}"]`).click();
    await page.waitForFunction(key => document.querySelector('.review-queue-item.is-selected')?.dataset.reviewKey === key, keyFor(row));
    await page.waitForSelector('#reviewDecisionPanel h2');
  };
  const confirmDialog = () => page.once('dialog', dialog => dialog.accept());
  const openAction = async (action, reasonIndex = 1, override = null) => {
    await page.locator(`[data-review-action="${action}"]`).click();
    await page.locator('#reviewDecisionReason').selectOption({ index: reasonIndex });
    if (override) await page.locator('#recommendationOverrideReason').selectOption({ label: override });
    await page.locator('#reviewPreviewButton').click();
    await page.waitForFunction(() => document.querySelector('#reviewDecisionPreview')?.hidden === false);
  };
  const submitAction = async () => {
    confirmDialog();
    const responsePromise = page.waitForResponse(response => /\/api\/admin\/(conflicts|duplicates|location-reviews|qualification-reviews)\//.test(response.url()) && response.request().method() === 'POST')
      .then(response => ({ response }), error => ({ error: error.message }));
    await page.locator('#reviewSubmitButton').click();
    const settled = await responsePromise;
    if (settled.error) throw new Error(settled.error);
    return settled.response;
  };

  try {
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.locator('#userButton').click();
    await page.waitForFunction(() => document.querySelector('#loginDialog')?.open === true);
    await page.locator('#loginEmail').fill('workbench.test@example.invalid');
    await page.locator('#loginPassword').fill('Isolated-Workbench-Test-2026!');
    await page.locator('#loginForm button[type=submit]').click();
    await page.waitForFunction(() => document.querySelector('#loginDialog')?.open === false);
    consoleErrors.length = 0;
    await page.locator('.nav-item[data-view="review"]').click();
    await page.waitForSelector('.review-queue-item');

    let queue = (await requestJson('/api/admin/review-queue?status=OPEN&limit=1000')).body;
    const initialDetails = await Promise.all(queue.map(detailFor));
    const sectorFollow = queue.find((row, i) => row.field === 'sector' && initialDetails[i]?.recommendation?.action === 'keep');
    const activityOverride = queue.find((row, i) => row.field === 'activity' && initialDetails[i]?.recommendation?.action === 'keep');
    if (!sectorFollow || !activityOverride) throw new Error(`Expected explained medium keep recommendations; got ${JSON.stringify(initialDetails.map(d => ({field:d.field,rec:d.recommendation?.action,confidence:d.recommendation?.confidence})))}`);

    // Flow A: follow recommendation, preview, commit, audit and next-review navigation.
    stage = 'flow_A_follow_recommendation';
    await selectReview(sectorFollow);
    if (!(await page.locator('.review-recommendation').innerText()).includes('الإبقاء على القيمة')) throw new Error('Recommendation is not visible in the review detail.');
    await openAction('keep');
    const firstResponse = await submitAction();
    if (!firstResponse.ok()) throw new Error(`Follow decision returned HTTP ${firstResponse.status()}.`);
    await page.waitForTimeout(150);
    const followedDetail = await detailFor(sectorFollow);
    if (!followedDetail.timeline.some(event => event.event_type === 'RECOMMENDATION_FOLLOWED')) throw new Error('Follow recommendation was not shown in the timeline.');
    const nextKey = await page.locator('.review-queue-item.is-selected').getAttribute('data-review-key');
    if (!nextKey || nextKey === keyFor(sectorFollow)) throw new Error('The UI did not navigate to another review after submission.');
    result.flows.follow_recommendation = 'PASSED';

    // Flow B: override requires a reason; failed submit stays open, then override is audited.
    stage = 'flow_B_override_recommendation';
    await selectReview(activityOverride);
    await openAction('use_source');
    let overridePostsWithoutReason = 0;
    const countOverridePosts = request => { if (request.url().includes(`/api/admin/conflicts/${activityOverride.id}/use_source`) && request.method() === 'POST') overridePostsWithoutReason++; };
    page.on('request', countOverridePosts);
    await page.locator('#reviewSubmitButton').click();
    await page.waitForFunction(() => document.querySelector('#toast')?.textContent.includes('سبب تجاوز التوصية مطلوب'));
    page.off('request', countOverridePosts);
    if (overridePostsWithoutReason !== 0) throw new Error('UI sent an override without a reason.');
    if ((await page.locator('#reviewDecisionPanel').innerText()).includes('تجاوز التوصية')) {
      await page.locator('#recommendationOverrideReason').selectOption({ label: 'تعارض في الأدلة' });
      await page.locator('#reviewPreviewButton').click();
      await page.waitForFunction(() => document.querySelector('#reviewDecisionPreview')?.hidden === false);
      const response = await submitAction();
      if (!response.ok()) throw new Error(`Override decision returned HTTP ${response.status()}.`);
    } else throw new Error('Override reason control is missing.');
    const overriddenDetail = await detailFor(activityOverride);
    if (!overriddenDetail.timeline.some(event => event.event_type === 'RECOMMENDATION_OVERRIDDEN')) throw new Error('Recommendation override is absent from the timeline.');
    result.flows.override_recommendation = 'PASSED';

    // Flow C: reopen a resolved case, preserve its original decision and resolve it again.
    stage = 'flow_C_reopen';
    await page.locator('#reviewQueueStatus').selectOption('RESOLVED');
    await page.waitForFunction(() => document.querySelectorAll('.review-queue-item').length >= 2);
    await selectReview(sectorFollow);
    await page.locator('#reviewReopenReason').selectOption({ label: 'ظهور دليل جديد' });
    await page.locator('#reviewReopenPreviewButton').click();
    await page.waitForFunction(() => document.querySelector('#reviewReopenPreview')?.hidden === false);
    const reopenPreviewText = await page.locator('#reviewReopenPreview').innerText();
    if (!reopenPreviewText.includes('FIELD_KEEP')) throw new Error(`Reopen preview did not show the original decision: ${reopenPreviewText}`);
    confirmDialog();
    const reopenPromise = page.waitForResponse(response => response.url().includes(`/api/admin/review-workbench/${sectorFollow.domain}/${sectorFollow.id}/reopen`) && response.request().method() === 'POST')
      .then(response => ({ response }), error => ({ error: error.message }));
    await page.locator('#reviewReopenSubmit').click();
    const reopenSettled = await reopenPromise;
    if (reopenSettled.error) throw new Error(reopenSettled.error);
    const reopenResponse = reopenSettled.response;
    if (!reopenResponse.ok()) throw new Error('Governed reopen failed.');
    await page.waitForTimeout(120);
    const reopenedDetail = await detailFor(sectorFollow);
    const lifecycle = reopenedDetail.timeline.map(event => event.event_type);
    if (!lifecycle.includes('RESOLVED') || !lifecycle.includes('REOPENED')) throw new Error(`Unified timeline lost decision/reopen history: ${lifecycle}`);
    const reopenCurrent = await detailFor(sectorFollow);
    const resolveAgain = await requestJson(`/api/admin/conflicts/${sectorFollow.id}/keep`, { method:'POST',
      headers:{'Content-Type':'application/json'}, data:{note:'Resolved again after governed reopen.',version_token:reopenCurrent.version_token,recommendation_version:reopenCurrent.recommendation_version} });
    if (!resolveAgain.response.ok()) throw new Error(`Reopened review could not be resolved again: HTTP ${resolveAgain.response.status()}.`);
    const resolvedAgain = await detailFor(sectorFollow);
    if (resolvedAgain.status !== 'RESOLVED') throw new Error(`Reopened review status did not return to resolved: ${resolvedAgain.status}.`);
    result.flows.reopen_preserve_and_resolve_again = 'PASSED';

    // Flow D: select two identical deterministic field signatures and commit atomically.
    stage = 'flow_D_batch_commit';
    queue = (await requestJson('/api/admin/review-queue?status=OPEN&limit=1000')).body;
    const batchRows = queue.filter(row => row.domain === 'field_conflict' && row.field === 'sector' && row.title.startsWith('فرصة دفعة ')).slice(0,2);
    if (batchRows.length !== 2) throw new Error(`Expected at least two deterministic batch reviews, found ${batchRows.length}.`);
    for (const row of batchRows) await page.locator(`[data-batch-review="${keyFor(row)}"]`).check();
    await page.locator('#reviewBatchReason').selectOption({ index: 1 });
    const batchPreviewPromise = page.waitForResponse(response => response.url().includes('/api/admin/review-workbench/batch/preview') && response.request().method() === 'POST');
    await page.locator('#reviewBatchPreviewButton').click();
    const batchPreviewResponse = await batchPreviewPromise;
    const batchPreviewBody = await batchPreviewResponse.json();
    result.batch_preview = { eligible:batchPreviewBody.eligible, signature_count:batchPreviewBody.signature_count,
      item_count:batchPreviewBody.items?.length, excluded_count:batchPreviewBody.excluded?.length };
    if (!batchPreviewResponse.ok() || !batchPreviewBody.eligible) throw new Error(`Deterministic batch preview was not eligible: ${JSON.stringify(batchPreviewBody)}`);
    await page.waitForFunction(() => document.querySelector('#reviewBatchPreview')?.hidden === false);
    if (!(await page.locator('#reviewBatchPreview').innerText()).includes('توقيع')) throw new Error('Batch preview did not show its deterministic signature.');
    confirmDialog();
    const batchResponsePromise = page.waitForResponse(response => response.url().includes('/api/admin/review-workbench/batch/commit') && response.request().method() === 'POST')
      .then(response => ({ response }), error => ({ error: error.message }));
    await page.locator('#reviewBatchCommitButton').click();
    const batchSettled = await batchResponsePromise;
    if (batchSettled.error) throw new Error(batchSettled.error);
    const batchResult = batchSettled.response;
    if (!batchResult.ok()) throw new Error(`Batch commit returned HTTP ${batchResult.status()}.`);
    const batchBody = await batchResult.json();
    if (batchBody.individual_audit_count !== 2) throw new Error(`Expected two individual audits; got ${batchBody.individual_audit_count}.`);
    result.flows.deterministic_batch_commit = 'PASSED';

    // Flow E: a mixed sector/activity selection is previewed and remains ineligible.
    stage = 'flow_E_mixed_batch';
    queue = (await requestJson('/api/admin/review-queue?status=OPEN&limit=1000')).body;
    const mixed = queue.find(row => row.domain === 'field_conflict' && row.field === 'activity' && row.title === 'فرصة نشاط مختلط');
    const sectorOpen = queue.find(row => row.domain === 'field_conflict' && row.field === 'sector');
    if (!mixed || !sectorOpen) throw new Error('Mixed batch fixture is missing.');
    for (const row of [mixed, sectorOpen]) await page.locator(`[data-batch-review="${keyFor(row)}"]`).check();
    await page.locator('#reviewBatchReason').selectOption({ index: 1 });
    const mixedPreviewPromise = page.waitForResponse(response => response.url().includes('/api/admin/review-workbench/batch/preview') && response.request().method() === 'POST');
    await page.locator('#reviewBatchPreviewButton').click();
    const mixedPreviewResponse = await mixedPreviewPromise;
    const mixedPreviewBody = await mixedPreviewResponse.json();
    result.mixed_batch_preview = { eligible:mixedPreviewBody.eligible, signature_count:mixedPreviewBody.signature_count,
      item_count:mixedPreviewBody.items?.length, excluded_count:mixedPreviewBody.excluded?.length };
    await page.waitForFunction(() => document.querySelector('#reviewBatchPreview')?.hidden === false);
    if (!mixedPreviewResponse.ok() || mixedPreviewBody.eligible || mixedPreviewBody.signature_count < 2) throw new Error(`Mixed-signature batch was not rejected: ${JSON.stringify(mixedPreviewBody)}`);
    if (!(await page.locator('#reviewBatchPreview').innerText()).includes('غير مؤهلة')) throw new Error('Mixed-signature rejection was not shown in the preview.');
    if (!(await page.locator('#reviewBatchCommitButton').isHidden())) throw new Error('Ineligible mixed batch exposes a commit button.');
    result.flows.mixed_batch_rejected = 'PASSED';

    // Flow F: stale version is rejected with a conflict response.
    stage = 'flow_F_stale_version';
    const staleDetail = await detailFor(mixed);
    const stale = await requestJson(`/api/admin/review-workbench/${mixed.domain}/${mixed.id}/preview?action=keep&version_token=${'0'.repeat(64)}`, { method: 'POST' });
    if (stale.response.status() !== 409) throw new Error(`Stale version returned HTTP ${stale.response.status()}, expected 409.`);
    result.flows.stale_version_rejected = 'PASSED';

    stage = 'review_detail_performance';
    const performanceSamples = [];
    for (let index = 0; index < 30; index++) {
      const started = performance.now();
      const response = await page.request.get(`${base}/api/admin/review-workbench/${mixed.domain}/${mixed.id}`);
      if (!response.ok()) throw new Error(`Review detail benchmark request returned HTTP ${response.status()}.`);
      performanceSamples.push(performance.now() - started);
    }
    performanceSamples.sort((a,b) => a-b);
    result.performance = { requests:performanceSamples.length, current_review_detail_api_p95_ms:Math.round(performanceSamples[Math.ceil(.95*performanceSamples.length)-1]),
      previous_review_detail_api_p95_ms:337 };
    result.performance.p95_delta_ms = result.performance.current_review_detail_api_p95_ms - result.performance.previous_review_detail_api_p95_ms;

    // Unsaved edits warn before moving to another review and never submit.
    await selectReview(mixed);
    await page.locator('[data-review-action]').first().click();
    await page.locator('#reviewDecisionReason').selectOption({ index: 1 });
    let unsavedWarning = false;
    page.once('dialog', async dialog => { unsavedWarning = dialog.type() === 'confirm'; await dialog.dismiss(); });
    await page.locator('#reviewNext').click();
    if (!unsavedWarning) throw new Error('Unsaved-change navigation warning was not shown.');
    result.flows.unsaved_change_warning = 'PASSED';

    // UI and responsive acceptance, using the current isolated review detail.
    stage = 'responsive_acceptance';
    await selectReview(mixed);
    for (const [width, height] of [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]]) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(100);
      const state = await page.evaluate(() => {
        const elements = [...document.querySelectorAll('#reviewDecisionPanel button, #reviewDecisionPanel select, #reviewBatchPanel button')]
          .filter(el => !el.hidden && getComputedStyle(el).display !== 'none');
        const boxes = elements.map(el => { const r=el.getBoundingClientRect(); return {x:r.x,right:r.right,y:r.y,bottom:r.bottom}; });
        let overlaps=0;
        for (let i=0;i<boxes.length;i++) for (let j=i+1;j<boxes.length;j++) {
          const a=boxes[i],b=boxes[j]; if (Math.min(a.right,b.right)-Math.max(a.x,b.x)>2 && Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y)>2) overlaps++;
        }
        return { width:innerWidth, scrollWidth:document.documentElement.scrollWidth,
          rtl:getComputedStyle(document.body).direction==='rtl', westernDigits:/[0-9]/.test(document.querySelector('#reviewDecisionPanel')?.innerText||''),
          clippedButtons:boxes.filter(box=>box.x < -1 || box.right > innerWidth+1).length, overlappingControls:overlaps,
          responsiveColumns:getComputedStyle(document.querySelector('.review-workbench')).gridTemplateColumns,
          responsiveColumnCount:getComputedStyle(document.querySelector('.review-workbench')).gridTemplateColumns.trim().split(/\s+/).length,
          reviewText:document.querySelector('#reviewDecisionPanel')?.innerText||'' };
      });
      const pathName = path.join(screenshotsDir, `closeout-review-${width}x${height}.png`);
      await page.screenshot({ path:pathName, fullPage:true });
      result.screenshots.push(path.relative(root,pathName));
      result.viewports.push({ viewport:`${width}x${height}`, rtl:state.rtl, western_digits:state.westernDigits,
        horizontal_overflow:state.scrollWidth>state.width, clipped_buttons:state.clippedButtons,
        overlapping_controls:state.overlappingControls, responsive_columns:state.responsiveColumns,
        responsive_collapse:width>700 || state.responsiveColumnCount===1 });
      if (!state.rtl || state.scrollWidth>state.width || state.clippedButtons || state.overlappingControls || !state.westernDigits || (width<=700 && state.responsiveColumnCount!==1))
        throw new Error(`Viewport acceptance failed at ${width}x${height}: ${JSON.stringify(state)}`);
    }
    result.flows.viewports_rtl_digits_overflow_clipping_overlap = 'PASSED';
    result.console_errors = consoleErrors;
    if (consoleErrors.length) throw new Error(`Browser console errors: ${consoleErrors.join(' | ')}`);
    result.javascript_console_errors = 0;
    result.captured_at = new Date().toISOString();
    return result;
  } catch (error) {
    result.failed_at = stage;
    result.error = error.message;
    result.console_errors = consoleErrors;
    try {
      const pathName = path.join(screenshotsDir, `failure-${stage}.png`);
      await page.screenshot({ path:pathName, fullPage:true });
      result.failure_screenshot = path.relative(root,pathName);
    } catch {}
    return result;
  } finally {
    await browser.close();
  }
};

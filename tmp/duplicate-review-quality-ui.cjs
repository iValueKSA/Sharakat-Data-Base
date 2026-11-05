const fs = require('fs');
const path = require('path');
const { chromium } = require('./pilot-playwright/node_modules/playwright-core');

(async () => {
  const base = 'http://localhost:8080';
  const cases = [
    { id: 32, expected: 'same-source ambiguous' },
    { id: 46, expected: 'cross-source ambiguous' },
    { id: 34, expected: 'frozen pilot duplicate' },
  ];
  const details = {};
  const reviewIds = [32,33,34,35,36,37,38,39,46,47];
  const auditReviews = [];
  for (const id of reviewIds) {
    const response = await fetch(`${base}/api/admin/review-workbench/duplicate/${id}`);
    if (!response.ok) throw new Error(`Read-only detail GET ${id} returned ${response.status}`);
    details[id] = await response.json();
    const comparison = details[id].duplicate_comparison;
    if (!comparison || !(comparison.human_review_reason || comparison.blocking_reason)) {
      throw new Error(`Review ${id} lacks comparison or human-review reason`);
    }
    const changedCount = (comparison.different_fields || []).length + (comparison.missing_on_left || []).length + (comparison.missing_on_right || []).length;
    if (details[id].status !== 'OPEN' || changedCount === 0 || !comparison.compared_fields?.length) throw new Error(`Review ${id} failed open-state, meaningful-difference, or expanded-field audit`);
    auditReviews.push({ review_id:id, status:details[id].status, same_source:comparison.same_source,
      comparison_classification:comparison.classification, meaningful_difference_count:changedCount,
      compared_fields:comparison.compared_fields, matched_fields:comparison.matched_fields,
      different_fields:comparison.different_fields, missing_on_left:comparison.missing_on_left,
      missing_on_right:comparison.missing_on_right, human_review_reason:comparison.human_review_reason,
      auto_resolution_allowed:comparison.auto_resolution_allowed });
  }
  fs.writeFileSync('docs/validation/ui/human-review-pilot/duplicate-review-difference-audit.json', JSON.stringify({
    generated_at:new Date().toISOString(), read_only:true, accepted_working_classification:{open:10,same_source_ambiguous:7,cross_source_ambiguous:3},
    deterministic_auto_resolved:0, records:auditReviews }, null, 2) + '\n');

  const browser = await chromium.launch({ headless: true, executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const errors = [];
  const blockedWrites = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('**/api/**', async route => {
    if (route.request().method() !== 'GET') {
      blockedWrites.push({ method: route.request().method(), url: route.request().url() });
      return route.fulfill({ status: 204, body: '' });
    }
    return route.continue();
  });

  const sizes = [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]];
  const results = [];
  const outputDir = 'docs/validation/ui/human-review-pilot/screenshots';
  fs.mkdirSync(outputDir, { recursive: true });
  for (const item of cases) {
    const detail = details[item.id];
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.evaluate(d => {
      document.querySelectorAll('.page-view').forEach(v => { v.hidden = true; v.classList.remove('visible'); });
      const view = document.querySelector('#view-review');
      view.hidden = false;
      view.classList.add('visible');
      renderWorkbenchDetail(d);
    }, detail);
    await page.waitForSelector('.duplicate-difference-panel');
    const summary = page.locator('.duplicate-matches summary');
    await summary.click();
    const holdButton = page.locator('[data-review-keep-open]');
    if (await holdButton.count()) await holdButton.click();

    for (const [width, height] of sizes) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(80);
      const state = await page.evaluate(() => {
        const panel = document.querySelector('.duplicate-difference-panel');
        const text = panel?.innerText || '';
        return {
          width: innerWidth,
          height: innerHeight,
          rtl: getComputedStyle(document.documentElement).direction === 'rtl',
          horizontal_overflow: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) > document.documentElement.clientWidth,
          difference_panel_visible: !!panel && panel.getBoundingClientRect().width > 0,
          meaningful_difference_count: document.querySelectorAll('.duplicate-difference-row').length,
          human_reason_visible: text.includes('لماذا تتطلب هذه الحالة مراجعة بشرية؟') && !!document.querySelector('.duplicate-human-reason p')?.innerText.trim(),
          matches_expander_visible: !!document.querySelector('.duplicate-matches summary'),
          matching_fields_expanded: document.querySelector('.duplicate-matches')?.open === true,
          matching_field_count: document.querySelectorAll('.duplicate-matches li').length,
          action_labels: [...document.querySelectorAll('[data-review-action], [data-review-keep-open]')].map(el => el.innerText.trim()),
        };
      });
      state.review_id = item.id;
      state.expected_case = item.expected;
      state.passed = state.rtl && !state.horizontal_overflow && state.difference_panel_visible &&
        state.meaningful_difference_count > 0 && state.human_reason_visible && state.matches_expander_visible &&
        state.matching_fields_expanded && state.matching_field_count > 0 &&
        state.action_labels.includes('ليستا نفس الفرصة') && state.action_labels.includes('نفس الفرصة — دمج') &&
        state.action_labels.includes('غير محسوم / إبقاء للمراجعة');
      results.push(state);
      await page.screenshot({ path: path.join(outputDir, `duplicate-review-${item.id}-${width}x${height}.png`), fullPage: true });
    }
  }

  const report = {
    status: results.every(r => r.passed) && errors.length === 0 && blockedWrites.every(x => x.url.includes('/recommendation-shown?')) ? 'PASSED' : 'FAILED',
    cases: cases.map(({id, expected}) => ({review_id:id, expected_case:expected, source_relation:details[id].duplicate_comparison.same_source ? 'same-source' : 'cross-source', status:details[id].status})),
    viewports: results,
    javascript_errors: errors,
    api_write_requests_blocked: blockedWrites,
    unexpected_api_write_requests: blockedWrites.filter(x => !x.url.includes('/recommendation-shown?')),
    decisions_submitted: 0,
  };
  fs.writeFileSync('docs/validation/ui/human-review-pilot/duplicate-review-playwright.json', JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ status: report.status, cases: report.cases, viewport_count: results.length,
    all_viewports_passed: results.every(r => r.passed), javascript_errors: errors,
    api_write_requests_blocked: blockedWrites, decisions_submitted: 0 }));
  await browser.close();
  if (report.status !== 'PASSED') process.exitCode = 1;
})().catch(error => { console.error(error.stack || error); process.exit(1); });

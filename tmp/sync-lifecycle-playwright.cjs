const fs = require('fs');
const path = require('path');
const { chromium } = require('C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

const root = process.cwd();
const base = 'http://localhost:8080';
const output = path.join(root, 'docs/validation/operations/scheduled-sync-job-lifecycle');
const screenshot = path.join(output, 'admin-job-lifecycle-1920x1080.png');
fs.mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const result = { verified_at: new Date().toISOString(), browser: 'Microsoft Edge via Playwright', url: base + '/?view=activity', auth: 'Test-only admin identity stub; sync-job row fixture', checks: {} };
  try {
    await page.route('**/api/auth/me', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ user: { id: 0, role: 'admin', display_name: 'مستخدم الاختبار' } }) }));
    await page.route('**/api/admin/jobs', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{ id: 212, source_id: 5, started_at: '2026-10-13T07:39:10Z', queued_at: '2026-10-13T07:39:10Z', finished_at: '2026-10-21T12:08:07Z', status: 'ABANDONED', job_state: 'ABANDONED', attempt_number: 1, heartbeat_at: '2026-10-13T07:39:10Z', pages_scanned: 0, raw_count: 0, ahsa_count: 0, new_count: 0, update_count: 0, error: 'Recovered after worker loss; no source scan began.' }]) }));
    await page.goto(base + '/', { waitUntil: 'networkidle', timeout: 30000 });
    await page.locator('[data-view="activity"]').click();
    await page.locator('#jobRows tr').first().waitFor({ state: 'visible', timeout: 15000 });
    const actual = await page.evaluate(async () => {
      const response = await fetch('/api/admin/jobs', { credentials: 'same-origin' });
      const jobs = response.ok ? await response.json() : [];
      const row = document.querySelector('#jobRows tr');
      return {
        api_status: 'TEST_FIXTURE',
        job_count: jobs.length,
        fields_present: jobs.length > 0 && ['finished_at', 'attempt_number', 'heartbeat_at', 'error', 'job_state'].every(key => Object.prototype.hasOwnProperty.call(jobs[0], key)),
        headers: Array.from(document.querySelectorAll('#view-activity thead th')).map(node => node.innerText.trim()),
        first_row_cells: row ? Array.from(row.cells).map(node => node.innerText.trim()) : [],
        direction: getComputedStyle(document.documentElement).direction,
        viewport_width: innerWidth,
        document_width: document.documentElement.scrollWidth,
        body_width: document.body.scrollWidth,
      };
    });
    result.checks.actual_jobs = actual;
    result.checks.rtl = actual.direction === 'rtl';
    result.checks.no_document_horizontal_overflow = actual.document_width <= actual.viewport_width && actual.body_width <= actual.viewport_width;
    result.checks.recovery_indicator_fixture = actual.first_row_cells[3]?.includes('توقف بعد انقطاع العامل') && actual.first_row_cells[10]?.includes('Recovered after worker loss');
    if (actual.api_status !== 'TEST_FIXTURE' || !actual.fields_present || actual.headers.length !== 11 || !result.checks.rtl || !result.checks.no_document_horizontal_overflow || !result.checks.recovery_indicator_fixture) throw new Error('Admin sync lifecycle view checks failed.');
    await page.screenshot({ path: screenshot, fullPage: true });
    result.screenshot = screenshot;
    result.checks.page_errors = errors;
    result.status = result.checks.recovery_indicator_fixture && errors.length === 0 ? 'PASSED' : 'FAILED';
    fs.writeFileSync(path.join(output, 'playwright-results.json'), JSON.stringify(result, null, 2), 'utf8');
    if (result.status !== 'PASSED') process.exitCode = 1;
    console.log(JSON.stringify({ status: result.status, checks: result.checks, screenshot: result.screenshot }));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack);
  process.exit(1);
});

const { chromium } = require('C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const base = 'http://localhost:8080';
  const sizes = [
    { width: 1920, height: 1080 }, { width: 1440, height: 900 },
    { width: 1366, height: 768 }, { width: 768, height: 900 }, { width: 390, height: 844 },
  ];
  const screens = ['overview', 'data-dashboard', 'opportunities', 'sources'];
  const output = path.resolve('docs/validation/final-readiness');
  const screenshotDir = path.join(output, 'screenshots');
  await fs.mkdir(screenshotDir, { recursive: true });
  const result = {
    captured_at: new Date().toISOString(),
    authentication_context: 'anonymous; no credentials submitted',
    public_routes: [], screenshots: [], viewport_results: [],
    javascript_errors: [], expected_guest_401_console_events: [], http_5xx: [], failed_requests: [],
    api_reconciliation: {}, export_reconciliation: {}, accessibility: {},
    admin_workbench: { live_playwright_capture: 'NOT_RUN', reason: 'admin route requires authenticated session; no password retried' },
  };
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', args: ['--no-sandbox'] });
  try {
    const context = await browser.newContext({ viewport: sizes[0], acceptDownloads: true });
    const page = await context.newPage();
    page.on('pageerror', error => result.javascript_errors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error' && /401\s*\(Unauthorized\)/i.test(message.text())) result.expected_guest_401_console_events.push(message.text());
      else if (message.type() === 'error') result.javascript_errors.push(message.text());
    });
    page.on('response', response => { if (response.status() >= 500) result.http_5xx.push({ url: response.url(), status: response.status() }); });
    page.on('requestfailed', request => { if (!request.url().includes('tile.openstreetmap.org')) result.failed_requests.push({ url: request.url(), error: request.failure()?.errorText }); });

    await page.goto(`${base}/?view=overview`, { waitUntil: 'domcontentloaded' });
    await page.locator('#userButton').click();
    await page.locator('#loginDialog[open]').waitFor();
    result.accessibility.login = await page.evaluate(() => ({
      dialog_open: !!document.querySelector('#loginDialog[open]'),
      focus_inside: document.querySelector('#loginDialog')?.contains(document.activeElement) || false,
      all_inputs_labeled: [...document.querySelectorAll('#loginDialog input')].every(input => !!input.labels?.length),
      visible_button_labels: [...document.querySelectorAll('#loginDialog button')].map(button => button.innerText.trim()).filter(Boolean),
    }));
    const loginFile = path.join(screenshotDir, 'login-1440x900.png');
    await page.screenshot({ path: loginFile });
    result.screenshots.push(path.relative(process.cwd(), loginFile));

    await page.evaluate(() => document.querySelector('#loginDialog')?.close());
    const api = await page.evaluate(async () => {
      const get = async url => { const response = await fetch(url); return { status: response.status, data: response.ok ? await response.json() : null }; };
      return {
        first: await get('/api/opportunities?limit=1&offset=0'),
        dashboard: await get('/api/data-dashboard'),
        legacy_dashboard: await get('/api/dashboard'),
        filters: await get('/api/filters'),
        geography: await get('/api/data-dashboard/geography'),
        sources: await get('/api/sources'),
        coverage: await get('/api/source-coverage'),
      };
    });
    result.api_statuses = Object.fromEntries(Object.entries(api).map(([key, value]) => [key, value.status]));
    const total = api.first.data.total;
    const ids = [];
    for (let offset = 0; offset < total; offset += 100) {
      const response = await page.evaluate(async offset => {
        const value = await fetch(`/api/opportunities?limit=100&offset=${offset}`);
        return { status: value.status, data: value.ok ? await value.json() : null };
      }, offset);
      if (response.status !== 200) throw new Error(`Pagination returned ${response.status} at offset ${offset}`);
      ids.push(...response.data.items.map(item => item.id));
    }
    const uniqueIds = new Set(ids);
    const geography = api.geography.data;
    const points = geography.points || [];
    result.api_reconciliation = {
      database_current_masters: 566,
      api_total: total,
      dashboard_total: api.dashboard.data.kpis.total,
      legacy_dashboard_total: api.legacy_dashboard.data.global_total ?? api.legacy_dashboard.data.total ?? null,
      legacy_dashboard_keys: Object.keys(api.legacy_dashboard.data),
      paginated_rows: ids.length,
      unique_ids: uniqueIds.size,
      duplicate_rows: ids.length - uniqueIds.size,
      missing_rows: Math.max(0, total - ids.length),
      geography_counts: geography.counts,
      map_point_count: points.length,
      map_master_ids: points.flatMap(point => point.ids || []),
    };
    result.api_reconciliation.unique_map_masters = new Set(result.api_reconciliation.map_master_ids).size;
    result.api_reconciliation.map_master_duplication = result.api_reconciliation.map_master_ids.length - result.api_reconciliation.unique_map_masters;
    delete result.api_reconciliation.map_master_ids;

    const viewportStates = [];
    for (const size of sizes) {
      await page.setViewportSize(size);
      const viewport = `${size.width}x${size.height}`;
      const state = { viewport, screens: {} };
      for (const screen of screens) {
        await page.goto(`${base}/?view=${screen}`, { waitUntil: 'domcontentloaded' });
        await page.locator(`#view-${screen}.visible`).waitFor({ timeout: 10000 });
        if (screen === 'data-dashboard') await page.waitForFunction(() => document.querySelector('#rdHeroTotal')?.textContent.trim() && document.querySelector('#rdHeroTotal').textContent.trim() !== '—', { timeout: 15000 });
        if (screen === 'opportunities') await page.waitForFunction(() => document.querySelector('#tableCount')?.textContent.trim() && document.querySelector('#tableCount').textContent.trim() !== '—', { timeout: 15000 });
        if (screen === 'sources') await page.waitForFunction(() => document.querySelectorAll('#sourceCards .source-card').length > 0, { timeout: 15000 });
        await page.waitForTimeout(1200);
        await page.evaluate(() => window.scrollTo(0, 0));
        const visible = await page.evaluate(screen => {
          const view = document.querySelector(`#view-${screen}.visible`);
          const root = document.documentElement;
          const controls = view ? [...view.querySelectorAll('button,a,input,select,[role="button"]')].filter(element => {
            const style = getComputedStyle(element), rect = element.getBoundingClientRect();
            return element.checkVisibility() && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
          }) : [];
          const clipped = controls.filter(element => { const rect = element.getBoundingClientRect(); return rect.bottom > 0 && rect.top < innerHeight && (rect.left < -1 || rect.right > innerWidth + 1); }).map(element => ({text: element.textContent.trim().slice(0, 80), rect: (() => { const r = element.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}; })()}));
          const text = view?.innerText || '';
          const unlabeledButtons = controls.filter(element => element.tagName === 'BUTTON' && !(element.textContent.trim() || element.getAttribute('aria-label'))).map(element => ({
            html: element.outerHTML.slice(0, 220),
            title: element.getAttribute('title'),
          }));
          return {
            visible: !!view,
            rtl: getComputedStyle(document.body).direction === 'rtl',
            horizontal_overflow: root.scrollWidth > innerWidth + 1,
            clipped_primary_controls: clipped.length,
            clipped_controls: clipped,
            western_digits: !/[٠-٩۰-۹]/.test(text),
            page_text_sample: text.slice(0, 160),
            rendered_record_count: screen === 'overview' ? document.querySelector('#metricTotal')?.textContent.trim() || null
              : screen === 'data-dashboard' ? document.querySelector('#rdHeroTotal')?.textContent.trim() || null
                : screen === 'opportunities' ? document.querySelector('#tableCount')?.textContent.trim() || null
                  : document.querySelectorAll('#sourceCards .source-card').length,
            visible_buttons_labeled: unlabeledButtons.length === 0,
            unlabeled_buttons: unlabeledButtons,
          };
        }, screen);
        state.screens[screen] = visible;
        const file = path.join(screenshotDir, `${screen}-${viewport}.png`);
        await page.screenshot({ path: file, fullPage: false });
        result.screenshots.push(path.relative(process.cwd(), file));
        if (screen === 'opportunities') {
          const detail = page.locator('#opportunityRows [data-detail]').first();
          if (await detail.count()) {
            await detail.click();
            await page.locator('#modal.show').waitFor({ timeout: 8000 });
            const detailFile = path.join(screenshotDir, `opportunity-detail-${viewport}.png`);
            await page.screenshot({ path: detailFile, fullPage: false });
            result.screenshots.push(path.relative(process.cwd(), detailFile));
            state.screens.opportunity_detail = { visible: true };
            await page.keyboard.press('Escape');
          } else state.screens.opportunity_detail = { visible: false };
        }
      }
      viewportStates.push(state);
    }
    result.viewport_results = viewportStates;

    await page.setViewportSize({ width: 1440, height: 900 });
    const downloads = await page.request.get(`${base}/api/export.csv`);
    const csvText = await downloads.text();
    let csvRows = 0, quoted = false;
    for (let index = 0; index < csvText.length; index++) {
      const character = csvText[index];
      if (character === '"') { if (quoted && csvText[index + 1] === '"') index++; else quoted = !quoted; }
      else if (character === '\n' && !quoted) csvRows++;
    }
    if (csvText.length && !csvText.endsWith('\n')) csvRows++;
    csvRows = Math.max(0, csvRows - 1);
    const xlsx = await page.request.get(`${base}/api/export.xlsx`);
    const xlsxBuffer = await xlsx.body();
    const xlsxPath = path.resolve('tmp/final-readiness-public.xlsx');
    await fs.writeFile(xlsxPath, xlsxBuffer);
    const { execFileSync } = require('node:child_process');
    execFileSync('docker', ['cp', xlsxPath, 'alahsa-local-api-1:/tmp/final-readiness-public.xlsx'], { stdio: 'ignore' });
    const xlsxRows = Number(execFileSync('docker', ['exec', 'alahsa-local-api-1', 'python', '-c', "import openpyxl;w=openpyxl.load_workbook('/tmp/final-readiness-public.xlsx',read_only=True,data_only=True);s=w.active;rows=s.iter_rows(values_only=True);header=None;count=0\nfor i,row in enumerate(rows,1):\n if row and row[0]=='اسم الفرصة': header=i; break\nif header is not None:\n for row in s.iter_rows(min_row=header+1,values_only=True):\n  if any(value is not None for value in row): count+=1\nprint(count)"], { encoding: 'utf8' }).trim());
    result.export_reconciliation = {
      csv_status: downloads.status(), csv_rows: csvRows,
      csv_header: csvText.split(/\r?\n/, 1)[0],
      csv_has_arabic: /[\u0600-\u06ff]/.test(csvText),
      csv_western_digits: !/[٠-٩۰-۹]/.test(csvText),
      xlsx_status: xlsx.status(), xlsx_bytes: xlsxBuffer.length, xlsx_rows: xlsxRows,
      csv_matches_api: csvRows === total, xlsx_matches_api: xlsxRows === total,
    };
    await fs.unlink(xlsxPath);
    result.ui_summary = {
      rtl_all_public_viewports: viewportStates.every(viewport => Object.values(viewport.screens).filter(screen => 'rtl' in screen).every(screen => screen.rtl)),
      no_horizontal_overflow_all_public_viewports: viewportStates.every(viewport => Object.values(viewport.screens).filter(screen => 'horizontal_overflow' in screen).every(screen => !screen.horizontal_overflow)),
      zero_clipped_primary_controls: viewportStates.every(viewport => Object.values(viewport.screens).filter(screen => 'clipped_primary_controls' in screen).every(screen => screen.clipped_primary_controls === 0)),
      western_digits: viewportStates.every(viewport => Object.values(viewport.screens).filter(screen => 'western_digits' in screen).every(screen => screen.western_digits)),
      javascript_console_errors: result.javascript_errors.length,
      http_5xx_count: result.http_5xx.length,
    };
    await fs.writeFile(path.join(output, 'final-ui-playwright.json'), JSON.stringify(result, null, 2), 'utf8');
    console.log(JSON.stringify({ api: result.api_reconciliation, exports: result.export_reconciliation, viewports: result.viewport_results.map(value => ({ viewport: value.viewport, screens: Object.keys(value.screens) })), ui: result.ui_summary, screenshots: result.screenshots.length, login: result.accessibility.login, errors: result.javascript_errors, http_5xx: result.http_5xx }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });

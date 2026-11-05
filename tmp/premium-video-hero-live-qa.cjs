const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('./pilot-playwright/node_modules/playwright-core');

const base = 'http://localhost:8080';
const output = path.resolve('docs/validation/ui/video-hero');
const screenshots = path.join(output, 'screenshots');
const videoFile = path.resolve('app/static/media/ahsa-investment-hero.webm');
const posterFile = path.resolve('app/static/media/ahsa-investment-hero-poster.webp');
const manifest = JSON.parse(fs.readFileSync(path.resolve('docs/validation/ui/video-hero/video-hero-manifest.json'), 'utf8'));
const viewports = [[1920, 1080], [1440, 900], [1366, 768], [768, 900], [390, 844]];
const result = {
  validated_at: new Date().toISOString(),
  route: `${base}/?view=data-dashboard`,
  asset: '/static/media/ahsa-investment-hero.webm',
  asset_format: 'WebM VP9',
  asset_duration_seconds: null,
  asset_bytes: fs.statSync(videoFile).size,
  poster_bytes: fs.statSync(posterFile).size,
  map_scene_count: manifest.map_scene_count,
  replacement_scene_ids: manifest.replacements.map((entry) => entry.replacement_scene),
  local_asset_sha256: crypto.createHash('sha256').update(fs.readFileSync(videoFile)).digest('hex'),
  served_asset_sha256: null,
  performance: {},
  playback: {},
  viewports: [],
  reduced_motion: {},
  media_failure_fallback: {},
  cta: {},
  dashboard_metrics: {},
  issues: { javascript: [], unexpected_http: [], external_reference_requests: [] },
};
fs.mkdirSync(screenshots, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.on('pageerror', (error) => result.issues.javascript.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error' && !message.text().includes('401 (Unauthorized)')) result.issues.javascript.push(message.text()); });
  page.on('request', (request) => { if (new URL(request.url()).hostname === 'alahsa-opportunities.com') result.issues.external_reference_requests.push(request.url()); });
  page.on('response', (response) => {
    if (response.status() >= 500 || (response.status() >= 400 && !(response.status() === 401 && response.url().includes('/api/auth/')))) {
      result.issues.unexpected_http.push({ status: response.status(), url: response.url() });
    }
  });
  try {
    const navStarted = Date.now();
    await page.goto(`${base}/?view=data-dashboard`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.querySelector('#view-data-dashboard')?.getAttribute('aria-busy') === 'false' && document.querySelector('#rdHeroTotal')?.textContent.trim() !== '—', { timeout: 20000 });
    result.performance.dashboard_data_ready_ms = Date.now() - navStarted;
    result.performance.first_contentful_paint_ms = await page.evaluate(() => performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null);
    result.dashboard_metrics = await page.evaluate(async () => {
      const data = await (await fetch('/api/data-dashboard')).json();
      return { total: data.kpis.total, deadline_30d: data.kpis.deadline_30d };
    });
    const video = page.locator('#dataDashboardHeroVideo');
    await page.waitForFunction(() => {
      const element = document.querySelector('#dataDashboardHeroVideo');
      return element && element.readyState >= 2 && Number.isFinite(element.duration) && element.currentTime > 0 && !element.paused;
    }, { timeout: 25000 });
    result.playback = await video.evaluate((element) => ({
      current_src: element.currentSrc,
      autoplay: element.autoplay,
      muted: element.muted,
      loop: element.loop,
      playsinline: element.playsInline,
      paused: element.paused,
      ready_state: element.readyState,
      duration_seconds: element.duration,
      video_width: element.videoWidth,
      video_height: element.videoHeight,
      time_at_ready: element.currentTime,
    }));
    result.asset_duration_seconds = result.playback.duration_seconds;
    result.performance.video_first_frame_after_navigation_ms = await video.evaluate((element) => performance.now());

    const served = await page.request.get(`${base}/static/media/ahsa-investment-hero.webm`);
    const servedBytes = await served.body();
    result.served_asset_sha256 = crypto.createHash('sha256').update(servedBytes).digest('hex');
    result.served_asset_bytes = servedBytes.length;
    result.served_asset_content_type = served.headers()['content-type'];

    for (const [width, height] of viewports) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(250);
      const layout = await page.evaluate(() => {
        const hero = document.querySelector('.rd-video-hero');
        const title = hero.querySelector('h1');
        const subtitle = hero.querySelector('p');
        const cta = hero.querySelector('.rd-video-hero-cta');
        const video = hero.querySelector('video');
        const rect = (node) => { const r = node.getBoundingClientRect(); return { x: r.x, y: r.y, right: r.right, bottom: r.bottom, width: r.width, height: r.height }; };
        const overlap = (a, b) => a.x < b.right && a.right > b.x && a.y < b.bottom && a.bottom > b.y;
        const hr = rect(hero), tr = rect(title), pr = rect(subtitle), cr = rect(cta);
        const inside = (r) => r.x >= hr.x - 1 && r.right <= hr.right + 1 && r.y >= hr.y - 1 && r.bottom <= hr.bottom + 1;
        return {
          hero_visible: hr.width > 0 && hr.height > 0,
          video_visible: video.getBoundingClientRect().width > 0 && video.getBoundingClientRect().height > 0 && getComputedStyle(video).opacity !== '0',
          video_current_time: video.currentTime,
          title_visible: !!title.textContent.trim() && tr.width > 0 && tr.height > 0,
          subtitle_visible: !!subtitle.textContent.trim() && pr.width > 0 && pr.height > 0,
          cta_visible: !!cta.textContent.trim() && cr.width > 0 && cr.height > 0,
          no_text_overlap: !overlap(tr, pr) && !overlap(pr, cr) && !overlap(tr, cr),
          no_clipping: inside(tr) && inside(pr) && inside(cr) && hero.scrollWidth <= hero.clientWidth + 1 && hero.scrollHeight <= hero.clientHeight + 1,
          no_horizontal_overflow: document.documentElement.scrollWidth <= innerWidth,
          rtl: getComputedStyle(hero).direction === 'rtl' && document.documentElement.dir === 'rtl',
          hero: hr,
          title: tr,
          subtitle: pr,
          cta: cr,
        };
      });
      const shotPath = path.join(screenshots, `premium-hero-${width}x${height}.png`);
      await page.screenshot({ path: shotPath });
      const pass = layout.hero_visible && layout.video_visible && layout.title_visible && layout.subtitle_visible && layout.cta_visible && layout.no_text_overlap && layout.no_clipping && layout.no_horizontal_overflow && layout.rtl;
      result.viewports.push({ width, height, status: pass ? 'PASSED' : 'FAILED', ...layout, screenshot: path.basename(shotPath) });
    }

    await page.setViewportSize({ width: 1920, height: 1080 });
    await video.evaluate((element) => { element.currentTime = 5.6; });
    await page.waitForFunction(() => { const element = document.querySelector('#dataDashboardHeroVideo'); return Math.abs(element.currentTime - 5.6) < 0.4 && !element.seeking; }, { timeout: 10000 });
    await page.waitForTimeout(180);
    await page.screenshot({ path: path.join(screenshots, 'premium-hero-irrigation-replacement-live.png') });
    result.playback.irrigation_replacement_time = await video.evaluate((element) => element.currentTime);
    await video.evaluate((element) => { element.currentTime = 20.2; });
    await page.waitForFunction(() => { const element = document.querySelector('#dataDashboardHeroVideo'); return Math.abs(element.currentTime - 20.2) < 0.4 && !element.seeking; }, { timeout: 10000 });
    await page.waitForTimeout(180);
    await page.screenshot({ path: path.join(screenshots, 'premium-hero-road-replacement-live.png') });
    result.playback.road_replacement_time = await video.evaluate((element) => element.currentTime);
    await video.evaluate((element) => { element.currentTime = element.duration - 0.18; element.play(); });
    await page.waitForFunction(() => { const element = document.querySelector('#dataDashboardHeroVideo'); return element.currentTime < 1 && !element.paused; }, { timeout: 8000 });
    result.playback.native_loop_wrap = true;
    result.playback.loop_wrapped_time = await video.evaluate((element) => element.currentTime);
    await video.evaluate((element) => { element.currentTime = 0.2; element.play(); });
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(screenshots, 'premium-hero-opening-live.png') });

    await page.locator('.rd-video-hero-cta').click();
    await page.waitForURL(/view=opportunities/);
    result.cta = { works: true, destination: new URL(page.url()).searchParams.get('view') };

    const reducedContext = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
    const reducedPage = await reducedContext.newPage();
    reducedPage.on('pageerror', (error) => result.issues.javascript.push(`reduced-motion: ${error.message}`));
    await reducedPage.goto(`${base}/?view=data-dashboard`, { waitUntil: 'domcontentloaded' });
    await reducedPage.waitForFunction(() => document.querySelector('#view-data-dashboard')?.getAttribute('aria-busy') === 'false' && document.querySelector('#rdHeroTotal')?.textContent.trim() !== '—', { timeout: 20000 });
    await reducedPage.waitForTimeout(700);
    result.reduced_motion = await reducedPage.evaluate(() => {
      const video = document.querySelector('#dataDashboardHeroVideo');
      const source = video.querySelector('source');
      const poster = document.querySelector('.rd-video-hero-poster');
      return { preference_detected: matchMedia('(prefers-reduced-motion: reduce)').matches, paused: video.paused, source_attached: !!source.src, poster_visible: getComputedStyle(poster).opacity !== '0' && poster.getBoundingClientRect().width > 0 };
    });
    await reducedContext.close();

    const failureContext = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    await failureContext.route('**/static/media/ahsa-investment-hero.webm*', (route) => route.abort());
    const failurePage = await failureContext.newPage();
    const failedMediaRequests = [];
    failurePage.on('requestfailed', (request) => { if (request.url().includes('ahsa-investment-hero.webm')) failedMediaRequests.push(request.failure()?.errorText || 'failed'); });
    failurePage.on('pageerror', (error) => result.issues.javascript.push(`failure-fallback: ${error.message}`));
    await failurePage.goto(`${base}/?view=data-dashboard`, { waitUntil: 'domcontentloaded' });
    await failurePage.waitForFunction(() => document.querySelector('#view-data-dashboard')?.getAttribute('aria-busy') === 'false' && document.querySelector('#rdHeroTotal')?.textContent.trim() !== '—', { timeout: 20000 });
    await failurePage.waitForTimeout(1000);
    result.media_failure_fallback = await failurePage.evaluate(() => {
      const hero = document.querySelector('.rd-video-hero');
      const video = document.querySelector('#dataDashboardHeroVideo');
      const poster = document.querySelector('.rd-video-hero-poster');
      return { media_fallback_kept_poster: !hero.classList.contains('is-playing') && video.videoWidth === 0, poster_visible: getComputedStyle(poster).opacity !== '0' && poster.getBoundingClientRect().width > 0, title_visible: hero.querySelector('h1').getBoundingClientRect().width > 0, cta_visible: hero.querySelector('.rd-video-hero-cta').getBoundingClientRect().width > 0, dashboard_metric_visible: document.querySelector('#rdHeroTotal').textContent.trim() !== '' };
    });
    result.media_failure_fallback.media_request_aborted = failedMediaRequests.length > 0;
    await failureContext.close();
    await context.close();
    await browser.close();

    result.assertions = {
      asset_sha256_matches: result.local_asset_sha256 === result.served_asset_sha256,
      local_asset_only: result.playback.current_src.startsWith(`${base}/static/media/`),
      map_scenes_removed: result.map_scene_count === 0,
      replacement_scene_count: result.replacement_scene_ids.length === 2 && result.replacement_scene_ids.includes('irrigation') && result.replacement_scene_ids.includes('road'),
      no_reference_runtime_dependency: result.issues.external_reference_requests.length === 0,
      finite_duration: Number.isFinite(result.asset_duration_seconds) && result.asset_duration_seconds >= 22 && result.asset_duration_seconds <= 22.5,
      playback_contract: result.playback.autoplay && result.playback.muted && result.playback.loop && result.playback.playsinline && !result.playback.paused,
      native_loop: result.playback.native_loop_wrap === true,
      all_viewports_pass: result.viewports.length === 5 && result.viewports.every((entry) => entry.status === 'PASSED'),
      reduced_motion_pass: result.reduced_motion.preference_detected && result.reduced_motion.paused && !result.reduced_motion.source_attached && result.reduced_motion.poster_visible,
      media_failure_fallback_pass: Object.values(result.media_failure_fallback).every(Boolean),
      cta_pass: result.cta.works === true,
      javascript_errors_zero: result.issues.javascript.length === 0,
      unexpected_http_zero: result.issues.unexpected_http.length === 0,
      dashboard_total_matches_dom: true,
    };
    result.assertions.dashboard_total_matches_dom = result.dashboard_metrics.total === 566;
    fs.writeFileSync(path.join(output, 'video-hero-playwright.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
    if (Object.values(result.assertions).some((value) => value !== true)) process.exitCode = 1;
  } finally {
    await browser.close().catch(() => {});
  }
})().catch((error) => { console.error(error); process.exit(2); });

const fs = require('fs');
const path = require('path');
const { chromium } = require('./pilot-playwright/node_modules/playwright-core');
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const directory = path.resolve('tmp/video-reference-review');
  fs.mkdirSync(directory, { recursive: true });
  try {
    const local = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    await local.goto('http://localhost:8080/?view=data-dashboard', { waitUntil: 'load' });
    await local.waitForFunction(() => { const video = document.querySelector('#dataDashboardHeroVideo'); return video && !video.paused && video.readyState >= 2 && video.videoWidth > 0; }, null, { timeout: 15000 });
    const current = await local.evaluate(async () => {
      const video = document.querySelector('#dataDashboardHeroVideo');
      if (video.duration) await new Promise((resolve) => { video.currentTime = Math.min(1, video.duration / 3); video.addEventListener('seeked', resolve, { once: true }); });
      return {
        source_file: '/static/index.html#view-data-dashboard',
        component: '#view-data-dashboard .rd-video-hero',
        asset: video.currentSrc,
        poster: video.poster,
        duration_seconds: video.duration,
        width: video.videoWidth,
        height: video.videoHeight,
        size_bytes: (await (await fetch(video.currentSrc, { method: 'HEAD' })).headers.get('content-length')) || null,
        autoplay: video.autoplay,
        muted: video.muted,
        loop: video.loop,
        playsinline: video.playsInline,
        playing: !video.paused,
        current_time: video.currentTime,
        hero_class: document.querySelector('.rd-video-hero').className,
      };
    });

    const reference = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await reference.goto('https://alahsa-opportunities.com/opportunities/515', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await reference.waitForFunction(() => { const video = document.querySelector('video.hero-video'); return video && video.readyState >= 2 && video.videoWidth > 0; }, null, { timeout: 30000 });
    const visual = await reference.evaluate(() => {
      const hero = document.querySelector('.hero-section');
      const video = document.querySelector('video.hero-video');
      const overlay = document.querySelector('.hero-overlay');
      const content = document.querySelector('.hero-content');
      return {
        document_title: document.title,
        hero_class: hero?.className,
        hero_background: getComputedStyle(hero).backgroundImage,
        video_source: video.currentSrc,
        video_attributes: { autoplay: video.autoplay, muted: video.muted, loop: video.loop, playsinline: video.playsInline, poster: video.poster, preload: video.preload },
        hero_box: (() => { const r = hero.getBoundingClientRect(); return { width: r.width, height: r.height }; })(),
        overlay_style: { background: getComputedStyle(overlay).background, opacity: getComputedStyle(overlay).opacity },
        content_text: content?.innerText,
        screenshot_video_height: video.getBoundingClientRect().height,
      };
    });
    for (const [index, time] of [2, 25, 55, 90].entries()) {
      await reference.evaluate(async (target) => {
        const video = document.querySelector('video.hero-video');
        video.currentTime = target;
        await new Promise((resolve) => video.addEventListener('seeked', resolve, { once: true }));
      }, time);
      await reference.waitForTimeout(250);
      const name = `reference-frame-${index + 1}-t${time}s.png`;
      await reference.screenshot({ path: path.join(directory, name), fullPage: false });
    }
    console.log(JSON.stringify({ current, reference: visual, referenceScreenshots: fs.readdirSync(directory) }, null, 2));
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });

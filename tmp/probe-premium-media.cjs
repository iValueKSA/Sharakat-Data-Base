const http = require('node:http');
const fs = require('node:fs');
const { chromium } = require('./pilot-playwright/node_modules/playwright-core');

const server = http.createServer((request, response) => {
  if (request.url === '/video.webm') {
    response.writeHead(200, { 'content-type': 'video/webm', 'accept-ranges': 'bytes' });
    fs.createReadStream('app/static/media/ahsa-investment-hero.webm').pipe(response);
  } else {
    response.writeHead(200, { 'content-type': 'text/html' });
    response.end('<video id="v" muted playsinline autoplay loop src="/video.webm"></video>');
  }
});
server.listen(0, '127.0.0.1', async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    page.on('pageerror', (error) => console.log('PAGE', error.message));
    page.on('console', (message) => { if (message.type() === 'error') console.log('CONSOLE', message.text()); });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForTimeout(5000);
    console.log(JSON.stringify(await page.locator('#v').evaluate((video) => ({ src: video.currentSrc, error: video.error && { code: video.error.code, message: video.error.message }, duration: video.duration, width: video.videoWidth, height: video.videoHeight, ready: video.readyState, paused: video.paused, time: video.currentTime }))));
  } finally {
    await browser.close();
    server.close();
  }
});

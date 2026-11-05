const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium } = require('./pilot-playwright/node_modules/playwright-core');
const source = fs.readFileSync(path.resolve('app/static/media/ahsa-investment-hero.webm'));
function vintLength(buffer, offset) {
  for (let length = 1; length <= 8; length += 1) if (buffer[offset] & (1 << (8 - length))) return length;
  throw new Error('Invalid EBML variable integer');
}
function readElement(buffer, offset) {
  const idLength = vintLength(buffer, offset);
  let sizeLength = vintLength(buffer, offset + idLength);
  let size = BigInt(buffer[offset + idLength] & (0xff >>> (sizeLength + 1)));
  for (let index = 1; index < sizeLength; index += 1) size = size * 256n + BigInt(buffer[offset + idLength + index]);
  const sizeBytes = buffer.subarray(offset + idLength, offset + idLength + sizeLength);
  const unknown = sizeBytes.every((byte) => byte === 0xff);
  return { idLength, sizeLength, size: unknown ? null : Number(size), dataOffset: offset + idLength + sizeLength };
}
const segment = source.indexOf(Buffer.from([0x18, 0x53, 0x80, 0x67]));
const segmentElement = readElement(source, segment);
const info = source.indexOf(Buffer.from([0x15, 0x49, 0xa9, 0x66]), segmentElement.dataOffset);
const infoElement = readElement(source, info);
if (infoElement.size === null || infoElement.sizeLength !== 1 || infoElement.size + 11 >= 127) throw new Error('Unexpected WebM Info layout');
const durationValue = Buffer.alloc(8);
durationValue.writeDoubleBE(12000, 0);
const durationElement = Buffer.from([0x44, 0x89, 0x88, ...durationValue]);
const newInfoSize = Buffer.from([0x80 | (infoElement.size + durationElement.length)]);
const infoSizeOffset = info + infoElement.idLength;
const infoDataOffset = infoElement.dataOffset;
const infoEnd = infoDataOffset + infoElement.size;
const patched = Buffer.concat([
  source.subarray(0, infoSizeOffset),
  newInfoSize,
  source.subarray(infoDataOffset, infoEnd),
  durationElement,
  source.subarray(infoEnd),
]);
const probePath = path.resolve('tmp/probe-duration.webm');
fs.writeFileSync(probePath, patched);
const server = http.createServer((request, response) => {
  if (request.url === '/video.webm') {
    response.writeHead(200, { 'Content-Type': 'video/webm', 'Content-Length': patched.length });
    response.end(patched);
  } else {
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end('<!doctype html><video id="v" autoplay muted loop playsinline src="/video.webm"></video>');
  }
});
(async () => {
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  try {
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(() => { const video = document.querySelector('#v'); return video && !video.paused && video.readyState >= 2; }, null, { timeout: 10000 });
    const basic = await page.evaluate(() => {
      const video = document.querySelector('#v');
      return { duration: video.duration, readyState: video.readyState, paused: video.paused, seekable: [...Array(video.seekable.length)].map((_, i) => [video.seekable.start(i), video.seekable.end(i)]) };
    });
    if (!Number.isFinite(basic.duration)) throw new Error(`Duration not recognized: ${JSON.stringify(basic)}`);
    await page.evaluate(() => { document.querySelector('#v').currentTime = 11.6; });
    await page.waitForFunction(() => { const video = document.querySelector('#v'); return video.currentTime < 1.5 && !video.paused; }, null, { timeout: 3000 });
    const loop = await page.evaluate(() => ({ duration: document.querySelector('#v').duration, currentTime: document.querySelector('#v').currentTime, paused: document.querySelector('#v').paused }));
    console.log(JSON.stringify({ patched_bytes: patched.length, basic, native_loop_after_seeking_near_end: loop, probePath: path.relative(process.cwd(), probePath) }, null, 2));
  } finally {
    await browser.close();
    server.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });

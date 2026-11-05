const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium } = require('./pilot-playwright/node_modules/playwright-core');

const sceneRoot = path.resolve('tmp/ahsa-premium-scenes');
const sourceFramesDir = path.resolve('docs/validation/ui/video-hero/source-frames');
const mediaDir = path.resolve('app/static/media');
const sceneSources = [
  ['opening', 'C:/Users/QusaiAbdElhalim/.codex/generated_images/01a15d6c-0b28-7b01-808f-7be7afab0dd7/exec-d9a6c854-9107-4cf0-92a7-de40a3c61467.png'],
  ['irrigation', 'C:/Users/QusaiAbdElhalim/.codex/generated_images/01a15d6c-0b28-7b01-808f-7be7afab0dd7/exec-e81b1bc7-9ec7-4e99-99f0-ec7c113234d8.png'],
  ['oasis', 'C:/Users/QusaiAbdElhalim/.codex/generated_images/01a15d6c-0b28-7b01-808f-7be7afab0dd7/exec-63857c45-db66-4a1f-8548-e945dbf7ebde.png'],
  ['heritage', 'C:/Users/QusaiAbdElhalim/.codex/generated_images/01a15d6c-0b28-7b01-808f-7be7afab0dd7/exec-02fc883d-aafa-499d-a91c-d9f6bea1b753.png'],
  ['investment', 'C:/Users/QusaiAbdElhalim/.codex/generated_images/01a15d6c-0b28-7b01-808f-7be7afab0dd7/exec-527a0f98-1662-473e-9f75-e762bd4710b8.png'],
  ['road', 'C:/Users/QusaiAbdElhalim/.codex/generated_images/01a15d6c-0b28-7b01-808f-7be7afab0dd7/exec-d90cdabb-ed91-4bf0-9720-e7a142853410.png'],
];

(async () => {
  fs.mkdirSync(sceneRoot, { recursive: true });
  fs.mkdirSync(sourceFramesDir, { recursive: true });
  fs.mkdirSync(mediaDir, { recursive: true });
  for (const [name, source] of sceneSources) fs.copyFileSync(source, path.join(sceneRoot, `${name}.png`));

  const server = http.createServer((request, response) => {
    const scene = /^\/scene\/(opening|irrigation|oasis|heritage|investment|road)\.png$/.exec(request.url || '');
    if (scene) {
      response.writeHead(200, { 'content-type': 'image/png', 'cache-control': 'no-store' });
      fs.createReadStream(path.join(sceneRoot, `${scene[1]}.png`)).pipe(response);
      return;
    }
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    response.end('<!doctype html><meta charset="utf-8"><title>Local scene render</title>');
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 540 }, deviceScaleFactor: 1 });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    const imageBase64 = {};
    for (const [name] of sceneSources) {
      imageBase64[name] = await page.evaluate(async (key) => {
        const image = new Image();
        image.src = `/scene/${key}.png`;
        await image.decode();
        return image.src;
      }, name);
    }
    const asset = await page.evaluate(async ({ names, duration }) => {
      const WIDTH = 1920, HEIGHT = 540, FRAME_RATE = 24;
      const images = {};
      await Promise.all(names.map(async (name) => {
        const image = new Image();
        image.src = `/scene/${name}.png`;
        await image.decode();
        images[name] = image;
      }));
      const canvas = document.createElement('canvas');
      canvas.width = WIDTH;
      canvas.height = HEIGHT;
      const context = canvas.getContext('2d', { alpha: false });
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = 'high';
      const segments = [
        { scene: 'opening', start: 0, end: 4.0, kind: 'photo' },
        { scene: 'irrigation', start: 3.65, end: 7.65, kind: 'photo', fade: 0.35 },
        { scene: 'oasis', start: 7.3, end: 11.3, kind: 'photo', fade: 0.35 },
        { scene: 'heritage', start: 10.95, end: 14.95, kind: 'photo', fade: 0.35 },
        { scene: 'investment', start: 14.6, end: 18.6, kind: 'photo', fade: 0.35 },
        { scene: 'road', start: 18.25, end: 22.25, kind: 'photo', fade: 0.35, fadeOut: 0.8 },
        { scene: 'loopOpen', start: 21.45, end: 22.25, kind: 'loop', fade: 0.8 },
      ];
      const ease = (value) => { const x = Math.max(0, Math.min(1, value)); return x * x * (3 - 2 * x); };
      const clamp = (value) => Math.max(0, Math.min(1, value));
      const vignette = () => {
        const gradient = context.createLinearGradient(0, 0, WIDTH, 0);
        gradient.addColorStop(0, 'rgba(7,33,38,.20)');
        gradient.addColorStop(.42, 'rgba(7,33,38,.015)');
        gradient.addColorStop(1, 'rgba(7,33,38,.33)');
        context.fillStyle = gradient;
        context.fillRect(0, 0, WIDTH, HEIGHT);
        const lower = context.createLinearGradient(0, 0, 0, HEIGHT);
        lower.addColorStop(0, 'rgba(7,29,33,.03)');
        lower.addColorStop(1, 'rgba(7,29,33,.18)');
        context.fillStyle = lower;
        context.fillRect(0, 0, WIDTH, HEIGHT);
      };
      const drawPhoto = (name, progress, opener = false) => {
        const image = images[name];
        const zoom = opener ? 1.045 + .045 * progress : 1.035 + .075 * progress;
        const fit = Math.max(WIDTH / image.naturalWidth, HEIGHT / image.naturalHeight) * zoom;
        const imageWidth = image.naturalWidth * fit;
        const imageHeight = image.naturalHeight * fit;
        const panX = opener ? Math.sin(progress * Math.PI) * 18 : Math.sin((progress + .1) * Math.PI) * 30;
        const panY = opener ? Math.sin(progress * Math.PI * .6) * 3 : Math.cos(progress * Math.PI) * 6;
        context.drawImage(image, (WIDTH - imageWidth) / 2 + panX, (HEIGHT - imageHeight) / 2 + panY, imageWidth, imageHeight);
        context.fillStyle = 'rgba(8,44,48,.07)';
        context.fillRect(0, 0, WIDTH, HEIGHT);
        vignette();
      };
      const drawSegment = (segment, time) => {
        const span = segment.end - segment.start;
        const progress = clamp((time - segment.start) / span);
        drawPhoto(segment.scene === 'loopOpen' ? 'opening' : segment.scene, progress, segment.scene === 'opening' || segment.scene === 'loopOpen');
      };
      const sceneFade = (segment, index, time) => {
        if (segment.kind === 'loop') return ease(clamp((time - segment.start) / (segment.end - segment.start)));
        const overlapIn = segment.fade || 0;
        const overlapOut = segment.fadeOut || (index < segments.length - 1 ? .35 : 0);
        const inAlpha = index === 0 || !overlapIn ? 1 : ease(clamp((time - segment.start) / overlapIn));
        const outAlpha = !overlapOut ? 1 : ease(clamp((segment.end - time) / overlapOut));
        return Math.min(inAlpha, outAlpha);
      };
      const render = (time) => {
        context.globalAlpha = 1;
        context.fillStyle = '#092d36';
        context.fillRect(0, 0, WIDTH, HEIGHT);
        const active = segments.map((segment, index) => ({ segment, index })).filter(({ segment }) => time >= segment.start && time <= segment.end);
        for (const { segment, index } of active) {
          context.globalAlpha = sceneFade(segment, index, time);
          drawSegment(segment, time);
        }
        context.globalAlpha = 1;
      };
      render(0);
      const poster = canvas.toDataURL('image/webp', .94).split(',')[1];
      const sourceFrames = {};
      for (const [key, scene] of [['01-opening', 'opening'], ['02-irrigation', 'irrigation'], ['03-oasis', 'oasis'], ['04-heritage', 'heritage'], ['05-investment', 'investment'], ['06-road', 'road']]) {
        const image = images[scene];
        const frame = document.createElement('canvas');
        frame.width = image.naturalWidth;
        frame.height = image.naturalHeight;
        frame.getContext('2d').drawImage(image, 0, 0);
        sourceFrames[key] = frame.toDataURL('image/webp', .92).split(',')[1];
      }
      const mimeType = 'video/webm;codecs=vp9';
      if (!MediaRecorder.isTypeSupported(mimeType)) throw new Error(`Unsupported media recorder type: ${mimeType}`);
      const recorder = new MediaRecorder(canvas.captureStream(FRAME_RATE), { mimeType, videoBitsPerSecond: 4500000 });
      const chunks = [];
      recorder.addEventListener('dataavailable', (event) => { if (event.data.size) chunks.push(event.data); });
      const started = performance.now();
      const capture = (now) => {
        const seconds = Math.min(duration, (now - started) / 1000);
        render(seconds);
        if (seconds < duration && recorder.state === 'recording') requestAnimationFrame(capture);
        else if (recorder.state === 'recording') recorder.stop();
      };
      recorder.start();
      requestAnimationFrame(capture);
      const video = await new Promise((resolve, reject) => {
        recorder.addEventListener('stop', async () => {
          try { resolve(await new Blob(chunks, { type: mimeType }).arrayBuffer()); }
          catch (error) { reject(error); }
        }, { once: true });
        recorder.addEventListener('error', (event) => reject(event.error || new Error('MediaRecorder failed')), { once: true });
      });
      const binary = new Uint8Array(video);
      let binaryString = '';
      for (let index = 0; index < binary.length; index += 0x8000) binaryString += String.fromCharCode(...binary.subarray(index, index + 0x8000));
      const videoBase64 = btoa(binaryString);
      return { video: videoBase64, poster, sourceFrames, mimeType, width: WIDTH, height: HEIGHT, frameRate: FRAME_RATE, duration, sceneNames: segments.map((segment) => segment.scene) };
    }, { names: sceneSources.map(([name]) => name), duration: 22.25 });

    const rawVideo = Buffer.from(asset.video, 'base64');
    const segmentId = Buffer.from([0x18, 0x53, 0x80, 0x67]);
    const infoId = Buffer.from([0x15, 0x49, 0xa9, 0x66]);
    const segmentOffset = rawVideo.indexOf(segmentId);
    function vintSizeLength(offset) { for (let length = 1; length <= 8; length += 1) if (rawVideo[offset] & (1 << (8 - length))) return length; throw new Error('Invalid EBML size'); }
    const segmentIdLength = 4;
    const segmentSizeLength = vintSizeLength(segmentOffset + segmentIdLength);
    if (segmentOffset < 0) throw new Error('Unexpected WebM segment layout; Segment element not found');
    const segmentPayloadStart = segmentOffset + segmentIdLength + segmentSizeLength;
    const readVint = (offset, length) => {
      let value = BigInt(rawVideo[offset] & ((1 << (8 - length)) - 1));
      for (let index = 1; index < length; index += 1) value = value * 256n + BigInt(rawVideo[offset + index]);
      return value;
    };
    let infoOffset = -1;
    for (let cursor = segmentPayloadStart; cursor < rawVideo.length;) {
      const elementIdLength = vintSizeLength(cursor);
      const elementId = rawVideo.subarray(cursor, cursor + elementIdLength);
      const elementSizeLength = vintSizeLength(cursor + elementIdLength);
      const elementSize = readVint(cursor + elementIdLength, elementSizeLength);
      if (elementId.equals(infoId)) { infoOffset = cursor; break; }
      if (elementSize === (1n << BigInt(7 * elementSizeLength)) - 1n) break;
      cursor += elementIdLength + elementSizeLength + Number(elementSize);
    }
    if (infoOffset < 0) throw new Error('WebM top-level Info element not found; no duration patch was attempted');
    const infoSizeLength = vintSizeLength(infoOffset + infoId.length);
    let infoSize = 0;
    for (let index = 0; index < infoSizeLength; index += 1) infoSize = infoSize * 256 + rawVideo[infoOffset + infoId.length + index];
    infoSize &= (2 ** (7 * infoSizeLength)) - 1;
    const infoDataStart = infoOffset + infoId.length + infoSizeLength;
    const infoEnd = infoDataStart + infoSize;
    let durationElementOffset = -1;
    for (let cursor = infoDataStart; cursor < infoEnd;) {
      const childIdLength = vintSizeLength(cursor);
      const childId = rawVideo.subarray(cursor, cursor + childIdLength);
      const childSizeLength = vintSizeLength(cursor + childIdLength);
      const childSize = Number(readVint(cursor + childIdLength, childSizeLength));
      if (childId.equals(Buffer.from([0x44, 0x89]))) { durationElementOffset = cursor; break; }
      cursor += childIdLength + childSizeLength + childSize;
    }
    if (durationElementOffset < 0) throw new Error('MediaRecorder output lacks a Duration element; refusing an unsafe index-shifting patch');
    const videoBytes = rawVideo;

    const posterBytes = Buffer.from(asset.poster, 'base64');
    const videoPath = path.join(mediaDir, 'ahsa-investment-hero.webm');
    const posterPath = path.join(mediaDir, 'ahsa-investment-hero-poster.webp');
    fs.writeFileSync(videoPath, videoBytes);
    fs.writeFileSync(posterPath, posterBytes);
    for (const [name, base64] of Object.entries(asset.sourceFrames)) {
      fs.writeFileSync(path.join(sourceFramesDir, `scene-${name}.webp`), Buffer.from(base64, 'base64'));
    }
    console.log(JSON.stringify({
      output: { path: path.relative(process.cwd(), videoPath), bytes: videoBytes.length, duration: asset.duration, dimensions: `${asset.width}x${asset.height}`, frameRate: asset.frameRate, mimeType: asset.mimeType, targetBitrate: 4500000, audioTrack: false },
      poster: { path: path.relative(process.cwd(), posterPath), bytes: posterBytes.length, dimensions: `${asset.width}x${asset.height}` },
      sourceFrames: fs.readdirSync(sourceFramesDir).map((name) => ({ name, bytes: fs.statSync(path.join(sourceFramesDir, name)).size })),
      mapSceneCount: 0,
      sceneSequence: asset.sceneNames,
      durationMetadataPatched: false,
      durationMetadataSource: 'finite Duration element emitted by MediaRecorder; no EBML mutation applied',
    }, null, 2));
  } finally {
    await browser.close();
    server.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });

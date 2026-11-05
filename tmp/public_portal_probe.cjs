const { chromium } = require('./pilot-playwright/node_modules/playwright-core');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--no-sandbox'] });
  const targets = [
    ['rcjy-invest', 'https://invest.rcjy.gov.sa/'],
    ['tourism-opportunities', 'https://tourism.sa/en/e-services/register-an-interest-on-investment-opportunity-service'],
    ['tourism-investing', 'https://tourism.sa/en/tourism-investing'],
  ];
  const out = {};
  for (const [key, url] of targets) {
    const page = await browser.newPage();
    const responses = [];
    page.on('response', response => {
      if (['xhr', 'fetch'].includes(response.request().resourceType()) || /api|map|FeatureServer|arcgis/i.test(response.url())) {
        responses.push({ status: response.status(), url: response.url(), type: response.request().resourceType() });
      }
    });
    try {
      const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForTimeout(6000);
      const dom = await page.evaluate(() => ({
        title: document.title,
        text: (document.body?.innerText || '').slice(0, 12000),
        links: [...document.querySelectorAll('a[href]')].map(a => ({ text: (a.innerText || '').trim().slice(0, 140), url: a.href })).filter(a => a.text || /invest|opportun|map|project/i.test(a.url)).slice(0, 200),
        scripts: [...document.scripts].map(script => script.src).filter(Boolean),
        frames: [...document.querySelectorAll('iframe')].map(frame => frame.src),
        buttons: [...document.querySelectorAll('button,[role=button]')].filter(el => /map|opportun|فرص|خريطة/i.test(el.innerText || '')).map(el => ({ text: (el.innerText || '').trim(), href: el.getAttribute('href'), data: el.getAttribute('data-url') })).slice(0, 20),
      }));
      out[key] = { status: response.status(), url: page.url(), ...dom, responses };
    } catch (error) { out[key] = { error: String(error), responses }; }
    await page.close();
  }
  require('fs').writeFileSync('tmp/public_portal_probe.json', JSON.stringify(out, null, 2));
  for (const [key, item] of Object.entries(out)) {
    console.log(JSON.stringify({ key, status: item.status, url: item.url, title: item.title, text: item.text?.slice(0, 2200), links: item.links?.filter(a => /invest|opportun|map|project|فرص|خريطة/i.test(a.text + ' ' + a.url)).slice(0, 25), scripts: item.scripts?.filter(src => /main|app|chunk|map/i.test(src)), frames: item.frames, buttons: item.buttons, responses: item.responses?.slice(0, 35) }));
  }
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });

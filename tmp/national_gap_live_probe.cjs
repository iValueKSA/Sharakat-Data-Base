const { chromium } = require('./pilot-playwright/node_modules/playwright-core');
const fs = require('fs');

const targets = [
  ['rcjy-en', 'https://www.rcjy.gov.sa/en/web/guest'],
  ['rcjy-ar', 'https://www.rcjy.gov.sa/ar/web/guest'],
  ['ncp-investors', 'https://investors.ncp.gov.sa/home'],
  ['tourism', 'https://mt.gov.sa/tourism-investment'],
  ['rcu', 'https://eservices.rcu.gov.sa/opportunities'],
  ['taadeen', 'https://cms.taadeen.sa/en/mining-bids/round-11'],
];

(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--no-sandbox']});
  const out = {};
  for (const [key, url] of targets) {
    const page = await browser.newPage({ignoreHTTPSErrors:true});
    const entries = [];
    page.on('response', async response => {
      const req = response.request();
      const item = {status:response.status(), url:response.url(), resourceType:req.resourceType(), method:req.method()};
      const type = response.headers()['content-type'] || '';
      if (/json|javascript|text\/html/i.test(type) && response.headers()['content-length'] && Number(response.headers()['content-length']) < 3000000) {
        try { const body = await response.text(); item.body = body.slice(0, 12000); } catch {}
      }
      entries.push(item);
    });
    let nav = {};
    try {
      const resp = await page.goto(url, {waitUntil:'domcontentloaded',timeout:45000});
      nav = {status:resp?.status(), finalUrl:page.url()};
      await page.waitForTimeout(7000);
      const dom = await page.evaluate(() => ({
        title:document.title,
        text:(document.body?.innerText||'').slice(0,25000),
        links:[...document.querySelectorAll('a[href]')].map(a=>({text:(a.innerText||a.getAttribute('aria-label')||'').trim().slice(0,140),href:a.href})).filter(a=>a.text||a.href).slice(0,250),
        scripts:[...document.scripts].map(s=>s.src||'inline').slice(0,100),
        iframes:[...document.querySelectorAll('iframe')].map(i=>i.src),
      }));
      if (key === 'tourism') {
        const mapLink = dom.links.find(l => /interactive map/i.test(l.text));
        if (mapLink) {
          const mp = await browser.newPage({ignoreHTTPSErrors:true});
          const mres=[]; mp.on('response', async r=>{ const t=r.headers()['content-type']||''; const x={status:r.status(),url:r.url(),resourceType:r.request().resourceType()}; if(/json|javascript|html/i.test(t)){try{x.body=(await r.text()).slice(0,12000)}catch{}} mres.push(x); });
          try { const mr=await mp.goto(mapLink.href,{waitUntil:'domcontentloaded',timeout:45000}); await mp.waitForTimeout(7000); dom.map={href:mapLink.href,status:mr?.status(),url:mp.url(),title:await mp.title(),text:(await mp.locator('body').innerText().catch(()=>'' )).slice(0,18000),links:await mp.locator('a[href]').evaluateAll(as=>as.map(a=>({text:a.innerText,href:a.href})).slice(0,100))}; dom.map.responses=mres; } catch(e){dom.map={error:String(e),responses:mres};}
          await mp.close();
        }
      }
      out[key]={nav,dom,responses:entries};
    } catch(e) { out[key]={nav,error:String(e),responses:entries}; }
    await page.close();
  }
  await browser.close();
  fs.writeFileSync('tmp/national_gap_live_probe.json',JSON.stringify(out,null,2));
  for (const [key,v] of Object.entries(out)) console.log(JSON.stringify({key,nav:v.nav,error:v.error,title:v.dom?.title,text:(v.dom?.text||'').slice(0,1400),responses:v.responses?.length,failed:v.responses?.filter(r=>r.status>=400).map(r=>[r.status,r.url]).slice(0,12),map:v.dom?.map&&{href:v.dom.map.href,status:v.dom.map.status,url:v.dom.map.url,title:v.dom.map.title,text:v.dom.map.text?.slice(0,1000)}}));
})().catch(e=>{console.error(e);process.exit(1)});

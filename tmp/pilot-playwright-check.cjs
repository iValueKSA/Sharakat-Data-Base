const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');
(async () => {
  const creds = fs.readFileSync(path.join(process.cwd(), 'Local Admin Credentials.txt'), 'utf8');
  const email = creds.match(/^Email:\s*(.+)$/m)?.[1]?.trim();
  const password = creds.match(/^Password:\s*(.+)$/m)?.[1]?.trim();
  if (!email || !password) throw new Error('Local admin credential file format is invalid.');
  const browser = await chromium.launch({headless:true, executablePath:'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
  const context = await browser.newContext({viewport:{width:1920,height:1080}, deviceScaleFactor:1});
  const page = await context.newPage(); page.setDefaultTimeout(15000);
  const errors=[], unauthorized=[]; page.on('pageerror', e=>errors.push(e.message));
  page.on('console', m=>{if(m.type()==='error') errors.push(m.text());});
  page.on('response', r=>{if(r.status()===401) unauthorized.push(r.url());});
  const base='http://127.0.0.1:8080';
  await page.goto(base,{waitUntil:'networkidle'});
  await page.locator('#userButton').click();
  await page.waitForFunction(()=>document.querySelector('#loginDialog')?.open===true);
  await page.locator('#loginEmail').fill(email);
  await page.locator('#loginPassword').fill(password);
  await page.locator('#loginForm button[type=submit]').click();
  await page.waitForFunction(()=>document.querySelector('#loginDialog')?.open===false);
  errors.length=0;
  await page.locator('.nav-item[data-view="review"]').click();
  await page.waitForFunction(()=>document.querySelector('#pilotStartButton') && document.querySelector('#pilotStatus')?.textContent);
  await page.waitForFunction(()=>document.querySelector('#pilotStartButton')?.hidden===false);
  const pilot=await page.evaluate(async()=>{
    const r=await fetch('/api/admin/review-workbench/pilot'); const s=await r.json();
    return {http_status:r.status,pilot_id:s.pilot_id,started:s.started,events:s.events?.length||0,cases:s.cases?.length,phase_counts:s.phase_counts};
  });
  if(pilot.http_status!==200||pilot.started||pilot.events!==0||pilot.cases!==40) throw new Error('Pilot preflight state unexpected: '+JSON.stringify(pilot));
  const viewports=[]; const shots=path.join(process.cwd(),'docs/validation/ui/human-review-pilot/screenshots'); fs.mkdirSync(shots,{recursive:true});
  for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]]) {
    await page.setViewportSize({width,height}); await page.waitForTimeout(160);
    const snap=await page.evaluate(()=>{
      const start=document.querySelector('#pilotStartButton'); const panel=document.querySelector('.review-pilot-controls');
      const rect=panel?.getBoundingClientRect(), children=[...panel.querySelectorAll('button')].filter(e=>!e.hidden).map(e=>{const r=e.getBoundingClientRect();return {id:e.id,left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};});
      const overlap=[]; for(let i=0;i<children.length;i++)for(let j=i+1;j<children.length;j++)if(children[i].left<children[j].right&&children[i].right>children[j].left&&children[i].top<children[j].bottom&&children[i].bottom>children[j].top)overlap.push([children[i].id,children[j].id]);
      return {width:innerWidth,height:innerHeight,rtl:getComputedStyle(document.documentElement).direction==='rtl',horizontal_overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth,pilot_start_visible:!!start&&!start.hidden,pilot_start_text:start?.textContent.trim(),pilot_controls_rect:rect?{x:rect.x,y:rect.y,width:rect.width,height:rect.height}:null,buttons:children,button_overlaps:overlap};
    });
    snap.passed=snap.rtl&&!snap.horizontal_overflow&&snap.pilot_start_visible&&snap.button_overlaps.length===0; viewports.push(snap);
    await page.screenshot({path:path.join(shots,`pilot-${width}x${height}.png`),fullPage:true});
  }
  const passed=errors.length===0&&viewports.every(v=>v.passed);
  const result={status:passed?'PASSED':'FAILED',verified_at:new Date().toISOString(),url:base,workflow_started:false,decisions_submitted:0,pilot_state:pilot,viewports,console_errors:errors,unauthorized_responses:unauthorized};
  fs.writeFileSync(path.join(process.cwd(),'docs/validation/ui/human-review-pilot/playwright-results.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({status:result.status,workflow_started:false,pilot_state:pilot,viewports:viewports.map(({width,height,rtl,horizontal_overflow,pilot_start_visible,button_overlaps})=>({width,height,rtl,horizontal_overflow,pilot_start_visible,button_overlaps})),console_errors:errors,unauthorized_responses:unauthorized}));
  await browser.close(); if(!passed) process.exitCode=1;
})().catch(e=>{console.error(e.message);process.exit(1)});




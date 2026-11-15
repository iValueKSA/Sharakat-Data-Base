const { createRequire } = await import('node:module');
const require = createRequire(import.meta.url);
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');

const base = process.env.UI_PREVIEW_URL || 'http://localhost:8081/';
const evidence = path.resolve('docs/validation/ui-redesign');
const result = { started_at: new Date().toISOString(), base, pages: {}, viewports: {}, api: [], http_errors: [], console_errors: [], page_errors: [], request_failures: [], screenshots: [], notes: [] };
const redactUrl = value => { try { const u=new URL(value); return u.pathname + (u.search ? '?…' : ''); } catch { return String(value).slice(0,180); } };
const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--no-sandbox'] });
const context = await browser.newContext({ viewport:{width:1440,height:900}, locale:'ar-SA', reducedMotion:'no-preference' });
const page = await context.newPage();
page.setDefaultTimeout(12000);
const started = new Map();
page.on('request', req => started.set(req, Date.now()));
page.on('response', res => {
  const req=res.request(), ms=Date.now()-(started.get(req)||Date.now());
  if(req.url().includes('/api/')) result.api.push({path:redactUrl(req.url()),status:res.status(),duration_ms:ms,method:req.method()});
  if(res.status()>=400) result.http_errors.push({path:redactUrl(res.url()),status:res.status()});
});
page.on('requestfailed', req => result.request_failures.push({path:redactUrl(req.url()),failure:req.failure()?.errorText||'unknown'}));
page.on('pageerror', err => result.page_errors.push(String(err.message||err).slice(0,240)));
page.on('console', msg => { if(msg.type()==='error' && !/api\/auth\/me.*401|status of 401/i.test(msg.text())) result.console_errors.push(msg.text().slice(0,240)); });
const snap = async name => {
  const file=path.join(evidence,name); await page.screenshot({path:file,fullPage:false,animations:'disabled',timeout:20000}); result.screenshots.push(path.relative(process.cwd(),file));
};
const readLayout = async () => page.evaluate(() => ({
  width:innerWidth, document_width:document.documentElement.scrollWidth,
  horizontal_overflow:document.documentElement.scrollWidth>innerWidth+1,
  dir:document.documentElement.dir, body_direction:getComputedStyle(document.body).direction,
  font:getComputedStyle(document.body).fontFamily, background:getComputedStyle(document.body).backgroundColor,
}));
const gotoView = async view => {
  const button=page.locator(`.nav-item[data-view="${view}"]`).first();
  if(await button.count() && !await button.isVisible().catch(()=>false)) {
    const toggle=page.locator('#sidebarToggle'); if(await toggle.isVisible().catch(()=>false)) await toggle.click();
  }
  if(await button.count()) await button.evaluate(el=>el.click());
  else await page.evaluate(v=>window.view?.(v),view);
  await page.waitForTimeout(250);
};
try {
  await fs.mkdir(evidence,{recursive:true});
  await page.goto(base,{waitUntil:'domcontentloaded',timeout:15000});
  await page.waitForFunction(()=>document.querySelector('#view-overview')?.classList.contains('visible'),null,{timeout:10000});
  console.log('overview visible');
  await page.waitForFunction(()=>document.querySelector('#view-overview .metric-card strong')?.textContent?.trim()!=='—',null,{timeout:15000}).catch(()=>{});
  result.pages.overview=await page.evaluate(()=>({title:document.title,rtl:document.documentElement.dir==='rtl',font:getComputedStyle(document.body).fontFamily,video_count:document.querySelectorAll('video').length,metrics:[...document.querySelectorAll('#view-overview .metric-card strong')].map(x=>x.textContent.trim()),theme_loaded:[...document.styleSheets].some(s=>s.href?.includes('ui-theme.css'))}));
  for(const [name,width,height] of [['desktop',1440,900],['tablet',768,900],['mobile',390,844]]){
    await page.setViewportSize({width,height}); await page.waitForTimeout(120);
    result.viewports[`overview_${name}`]=await readLayout();
    if(name==='desktop') await snap('01-overview-desktop-1440x900.png');
    if(name==='mobile') await snap('06-overview-mobile-390x844.png');
  }
  console.log('overview screenshots saved');
  await page.setViewportSize({width:1440,height:900});
  const metric=page.locator('#view-overview .metric-card').first();
  const box=await metric.boundingBox(); if(box){await page.mouse.move(box.x+box.width/2,box.y+box.height/2); await page.waitForTimeout(80); result.pages.overview.spotlight_class=await metric.evaluate(e=>e.classList.contains('ui-glow'));}

  await gotoView('data-dashboard');
  console.log('dashboard navigation sent');
  const dashStart=Date.now();
  const dashboardReady=await page.waitForFunction(()=>{
    const total=document.querySelector('#rdHeroTotal')?.textContent?.trim();
    const busy=document.querySelector('#view-data-dashboard')?.getAttribute('aria-busy');
    const error=document.querySelector('#dataDashboardError');
    return (total && total!=='—' && busy==='false') || (error && !error.hidden);
  },null,{timeout:60000}).then(()=>true).catch(()=>false);
  result.pages.dashboard={ready:dashboardReady,wait_ms:Date.now()-dashStart};
  console.log('dashboard readiness',dashboardReady,result.pages.dashboard.wait_ms);
  if(dashboardReady) {
    const mapStart=Date.now();
    result.pages.dashboard.map_ready=await page.waitForFunction(()=>document.querySelectorAll('#rdOpportunityMap .leaflet-marker-icon').length>0 || document.querySelector('#rdMapNotice:not([hidden])')?.textContent?.trim(),null,{timeout:90000}).then(()=>true).catch(()=>false);
    result.pages.dashboard.map_wait_ms=Date.now()-mapStart;
    result.pages.dashboard.data=await page.evaluate(()=>({total:document.getElementById('rdHeroTotal')?.textContent.trim(),active:document.getElementById('rdHeroActive')?.textContent.trim(),error:document.getElementById('dataDashboardError')?.textContent.trim(),chart_columns:document.querySelectorAll('#rdSectorChart .rd-column').length,donut:!!document.querySelector('#rdStatusDonut svg'),map_canvas:!!document.querySelector('#rdOpportunityMap'),map_markers:document.querySelectorAll('#rdOpportunityMap .leaflet-marker-icon').length,map_title:document.getElementById('rdMapTitle')?.textContent.trim(),video_count:document.querySelectorAll('video').length}));
    result.viewports.dashboard_desktop=await readLayout(); await snap('02-dashboard-desktop-1440x900.png');
    await page.setViewportSize({width:390,height:844}); await page.waitForTimeout(300); result.viewports.dashboard_mobile=await readLayout(); await snap('07-dashboard-mobile-390x844.png');
    await page.setViewportSize({width:1440,height:900}); await page.locator('#rdOpportunityMap').scrollIntoViewIfNeeded({timeout:12000}); await page.waitForTimeout(250); await page.locator('#rdMapTitle').scrollIntoViewIfNeeded({timeout:5000}).catch(()=>{}); await page.locator('#rdOpportunityMap').screenshot({path:path.join(evidence,'04-national-map-desktop.png'),timeout:15000}); result.screenshots.push('docs/validation/ui-redesign/04-national-map-desktop.png');
  } else {
    result.pages.dashboard.partial_state=await page.evaluate(()=>({busy:document.querySelector('#view-data-dashboard')?.getAttribute('aria-busy'),error:document.getElementById('dataDashboardError')?.textContent,sector_children:document.querySelector('#rdSectorChart')?.children.length,map_children:document.querySelector('#rdOpportunityMap')?.children.length})).catch(e=>({evaluation_error:String(e)}));
    result.notes.push('Dashboard did not reach data-ready or error state within 60 seconds.');
  }

  await gotoView('opportunities');
  console.log('opportunities navigation sent');
  const rows=page.locator('#opportunityRows [data-detail]');
  await page.waitForFunction(()=>document.querySelectorAll('#opportunityRows [data-detail]').length>0 || document.querySelector('#emptyTable')?.classList.contains('show'),null,{timeout:90000}).catch(()=>{});
  result.pages.opportunities=await page.evaluate(()=>({row_count:document.querySelectorAll('#opportunityRows tr').length,detail_controls:document.querySelectorAll('#opportunityRows [data-detail]').length,columns:[...document.querySelectorAll('#view-opportunities thead th')].map(x=>x.textContent.trim()),csv:!!document.querySelector('#view-opportunities a[href*="export.csv"],#view-opportunities a[data-export="csv"]'),xlsx:!!document.querySelector('#view-opportunities a[href*="export.xlsx"],#view-opportunities a[data-export="xlsx"]'),search:!!document.querySelector('#searchInput'),sort:!!document.querySelector('#view-opportunities [data-sort-key]'),pagination:!!document.querySelector('#nextPage')}));
  result.viewports.opportunities_desktop=await readLayout(); await snap('03-opportunities-desktop-1440x900.png');
  const headers=await page.locator('#view-opportunities thead th').count();
  if(result.pages.opportunities.detail_controls>0){
    await page.locator('#view-opportunities [data-sort-key="title"]').click();
    await page.locator('#opportunityRows [data-detail]').first().click();
    result.pages.detail_modal=await page.locator('#modal.show').isVisible().catch(()=>false);
    if(result.pages.detail_modal){result.pages.detail_fields=await page.locator('#modal .detail-field').count(); await page.locator('#modalClose').click();}
    if(await page.locator('#nextPage').isEnabled().catch(()=>false)){await page.locator('#nextPage').click(); result.pages.pagination=true;}
  }
  await page.setViewportSize({width:390,height:844}); await page.waitForTimeout(180); result.viewports.opportunities_mobile=await readLayout(); await snap('08-opportunities-mobile-390x844.png');
  result.pages.opportunities.table_headers=headers;

  await page.setViewportSize({width:1440,height:900}); await gotoView('sources');
  console.log('sources navigation sent');
  await page.waitForFunction(()=>document.querySelectorAll('#sourceCards .source-card').length>0 || document.querySelector('#sourceCards [role=alert]'),null,{timeout:60000}).catch(()=>{});
  result.pages.sources=await page.evaluate(()=>({cards:document.querySelectorAll('#sourceCards .source-card').length,visible:document.querySelector('#view-sources')?.classList.contains('visible')})); await snap('05-sources-desktop-1440x900.png');

  await page.emulateMedia({reducedMotion:'reduce'});
  result.pages.reduced_motion=await page.evaluate(()=>({preference:matchMedia('(prefers-reduced-motion: reduce)').matches,entry_animation:getComputedStyle(document.querySelector('.page-view.visible')).animationDuration,spotlight_transition:getComputedStyle(document.querySelector('.ui-glow')||document.body,'::before').transitionDuration}));
  result.pages.admin_navigation=await page.locator('.nav-item[data-view="admin"]').isVisible().catch(()=>false);
  result.finished_at=new Date().toISOString();
} catch(e) { result.fatal=String(e.stack||e).slice(0,1600); }
finally {
  result.api_summary={count:result.api.length,slow:result.api.filter(x=>x.duration_ms>5000),failures:result.api.filter(x=>x.status>=500)};
  await fs.writeFile(path.join(evidence,'playwright-results.json'),JSON.stringify(result,null,2));
  await browser.close().catch(()=>{});
  console.log(JSON.stringify(result,null,2));
}

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', args:['--no-sandbox']});
  const issues = [], failures = [], results = [];
  const outDir = path.resolve('docs/validation/ui/nextadmin-ahda-dashboard/screenshots'); fs.mkdirSync(outDir,{recursive:true});
  for (const [width,height] of [[1920,1080],[1440,900],[1366,768],[390,844],[768,900]]) {
    const page = await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
    page.on('pageerror',e=>issues.push(`${width}x${height}: ${e.message}`));
    page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('401 (Unauthorized)'))issues.push(`${width}x${height}: ${m.text()}`)});
    page.on('requestfailed',r=>failures.push(`${width}x${height}: ${r.url()} ${r.failure()?.errorText}`));
    page.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400&&!(r.status()===401&&r.url().includes('/api/auth/')))failures.push(`${width}x${height}: HTTP ${r.status()} ${r.url()}`)});
    await page.goto('http://localhost:8080/?view=data-dashboard',{waitUntil:'networkidle'}); await page.locator('#dataKpis[aria-busy="false"]').waitFor({timeout:20000});
    const info=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,height:innerHeight,dir:getComputedStyle(document.body).direction,total:document.querySelector('#dataKpis .data-kpi b')?.textContent,panelCount:document.querySelectorAll('.data-widget').length,sourceLogos:document.querySelectorAll('#dashBySource .source-logo').length,menuButton:getComputedStyle(document.querySelector('#sidebarToggle')).display,activeLabel:document.querySelector('#dataDashboardUpdated')?.textContent}));
    if(info.scrollWidth>width)issues.push(`${width}x${height}: horizontal overflow ${info.scrollWidth}`);
    if(info.dir!=='rtl')issues.push(`${width}x${height}: not RTL`);
    if(info.panelCount!==10)issues.push(`${width}x${height}: expected 10 dashboard panels, got ${info.panelCount}`);
    if(width===768){await page.locator('#sidebarToggle').click();await page.locator('body.sidebar-open').waitFor();await page.waitForFunction(()=>document.activeElement?.classList.contains('nav-item'));const focus=await page.evaluate(()=>document.activeElement?.classList.contains('nav-item'));await page.keyboard.press('Escape');await page.locator('body.sidebar-open').waitFor({state:'detached'});const returned=await page.evaluate(()=>document.activeElement?.id==='sidebarToggle');results.push({tabletDrawer:true,focusInsideDrawer:focus,escapeClosedAndRestoredFocus:returned})}
    if(width===390){await page.locator('#sidebarToggle').click();await page.locator('body.sidebar-open').waitFor();await page.waitForFunction(()=>document.activeElement?.classList.contains('nav-item'));const focus=await page.evaluate(()=>document.activeElement?.classList.contains('nav-item'));await page.keyboard.press('Escape');await page.locator('body.sidebar-open').waitFor({state:'detached'});const returned=await page.evaluate(()=>document.activeElement?.id==='sidebarToggle');results.push({mobileDrawer:true,focusInsideDrawer:focus,escapeClosedAndRestoredFocus:returned})}
    await page.screenshot({path:path.join(outDir,`dashboard-${width}x${height}.png`),fullPage:false});results.push({viewport:`${width}x${height}`,...info});await page.close();
  }
  const page=await browser.newPage({viewport:{width:1440,height:900}});page.on('pageerror',e=>issues.push(`interaction: ${e.message}`));page.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400&&!(r.status()===401&&r.url().includes('/api/auth/')))failures.push(`interaction: HTTP ${r.status()} ${r.url()}`)});
  await page.goto('http://localhost:8080/?view=data-dashboard',{waitUntil:'networkidle'});await page.locator('#dataKpis[aria-busy="false"]').waitFor();
  const original=await page.locator('#dataKpis .data-kpi b').first().innerText();
  await page.locator('#dashSector').selectOption({label:'صناعي'});await page.waitForFunction(()=>document.querySelector('#dataKpis .data-kpi b')?.textContent==='59');
  const filterUrl=await page.url(),filtered=await page.locator('#dataKpis .data-kpi b').first().innerText();
  await page.locator('#dashReset').click();await page.waitForFunction(()=>document.querySelector('#dataKpis .data-kpi b')?.textContent==='289'&&!new URL(location.href).searchParams.has('sector'));
  await page.locator('[data-kpi-action="active"]').click();await page.waitForURL(/view=opportunities.*lifecycle=active/);await page.waitForFunction(()=>document.querySelector('#tableCount')?.textContent.includes('283'));
  const activeTotal=await page.locator('#tableCount').innerText();if(await page.locator('#nextPage').isEnabled()){await page.locator('#nextPage').click();await page.waitForFunction(()=>document.querySelector('#pageSummary')?.textContent.includes('٢')||document.querySelector('#pageSummary')?.textContent.includes('2'))}
  const page2=await page.locator('#pageSummary').innerText();await page.locator('#searchInput').fill('مستودع');await page.waitForFunction(()=>document.querySelector('#tableCount')?.textContent.includes('16'));
  const searchCount=await page.locator('#tableCount').innerText(),details=page.locator('#opportunityRows [data-detail]');
  let detailOpen=false,detailEscapeClose=false;if(await details.count()){await details.first().click();await page.locator('#modal.show').waitFor();detailOpen=true;await page.keyboard.press('Escape');await page.locator('#modal.show').waitFor({state:'detached'});detailEscapeClose=true}
  await page.goto('http://localhost:8080/?view=data-dashboard',{waitUntil:'networkidle'});await page.locator('#dataKpis[aria-busy="false"]').waitFor();
  const [csv]=await Promise.all([page.waitForEvent('download'),page.locator('#dashExportCsv').click()]);const csvPath=await csv.path();const csvBytes=csvPath?fs.readFileSync(csvPath):Buffer.alloc(0);
  await page.goto('http://localhost:8080/?view=data-dashboard',{waitUntil:'networkidle'});await page.locator('#dataKpis[aria-busy="false"]').waitFor();
  const [xlsx]=await Promise.all([page.waitForEvent('download'),page.locator('#dashExportXlsx').click()]);const xlsxPath=await xlsx.path();const xlsxBytes=xlsxPath?fs.readFileSync(xlsxPath):Buffer.alloc(0);
  await page.goto('http://localhost:8080/?view=data-dashboard',{waitUntil:'networkidle'});await page.locator('#dataKpis[aria-busy="false"]').waitFor();
  await page.locator('[data-view="sources"]').click();await page.locator('#sourceCards .source-card').first().waitFor();const sourceCards=await page.locator('#sourceCards .source-card').count();
  const apiCounts=await page.evaluate(async()=>{const d=await(await fetch('/api/data-dashboard')).json();return {total:d.kpis.total,active:d.kpis.active,historical:d.kpis.historical,sources:d.kpis.enabled_sources,deadline30:d.kpis.deadline_30d,bySector:d.by_sector.map(x=>[x.name,x.count]),byStatus:d.by_status.map(x=>[x.name,x.count]),byOwner:d.by_owner.map(x=>[x.name,x.count]),byType:d.by_type.map(x=>[x.name,x.count]),byActivity:d.by_activity.map(x=>[x.name,x.count])}});
  if(!detailOpen)issues.push('Opportunity details did not open');if(!detailEscapeClose)issues.push('Opportunity detail Escape close did not work');if(sourceCards!==10)issues.push(`Expected 10 source-health cards, got ${sourceCards}`);if(!csvBytes.toString('utf8').includes('الفرصة')||csvBytes.length===0)issues.push('CSV download was empty or missing Arabic column labels');if(xlsxBytes.subarray(0,2).toString()!=='PK')issues.push('XLSX download did not have a valid ZIP signature');
  results.push({filterUrl,filteredTotal:filtered,originalTotal:original,activeTotal,page2,searchCount,detailOpen,detailEscapeClose,sourceCards,csvBytes:csvBytes.length,xlsxBytes:xlsxBytes.length,xlsxZipSignature:xlsxBytes.subarray(0,2).toString(),apiCounts});
  await page.screenshot({path:path.join(outDir,'dashboard-final-1440x900.png'),fullPage:false});await browser.close();console.log(JSON.stringify({results,issues,failures,outDir},null,2));if(issues.length||failures.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(2)});



const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const outDir=path.resolve(__dirname,'screenshots'); fs.mkdirSync(outDir,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const sizes=[{w:1920,h:1080},{w:1440,h:900},{w:1366,h:768},{w:768,h:900},{w:390,h:844}];
 const results={captured:new Date().toISOString(),url:'http://localhost:8080/?view=opportunities',browser:'Chromium via Playwright',viewports:[],interactions:{},errors:[],networkFailures:[]};
 for(const size of sizes){
  const page=await browser.newPage({viewport:{width:size.w,height:size.h},deviceScaleFactor:1});
  page.on('pageerror',e=>results.errors.push(String(e)));
  page.on('requestfailed',r=>results.networkFailures.push({url:r.url(),error:r.failure()?.errorText||'unknown'}));
  await page.goto(results.url,{waitUntil:'networkidle',timeout:60000});
  await page.waitForSelector('#opportunityRows tr',{timeout:30000});
  await page.waitForTimeout(250);
  const m=await page.evaluate(()=>{
   const bar=document.querySelector('.filter-bar');const b=bar?.getBoundingClientRect();
   const controls=[...bar.querySelectorAll('input,select,button')].map(e=>{const r=e.getBoundingClientRect();return {id:e.id||e.getAttribute('aria-label')||e.tagName,left:Math.round(r.left),right:Math.round(r.right),width:Math.round(r.width),inside:!!b&&r.left>=b.left-1&&r.right<=b.right+1,visible:r.width>0&&r.height>0,text:(e.innerText||e.getAttribute('aria-label')||e.placeholder||'').trim()}});
   return {rtl:document.documentElement.dir,viewportWidth:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,noHorizontalPageOverflow:document.documentElement.scrollWidth<=innerWidth&&document.body.scrollWidth<=innerWidth,filterToolbar:bar?{width:Math.round(b.width),height:Math.round(b.height),scrollWidth:bar.scrollWidth,clientWidth:bar.clientWidth,controls}:null,visibleOpportunityRows:document.querySelectorAll('#opportunityRows tr').length,tableCount:document.querySelector('#tableCount')?.innerText,pageSummary:document.querySelector('#pageSummary')?.innerText};
  });
  const shot=path.join(outDir,`${size.w}x${size.h}-opportunities.png`); await page.screenshot({path:shot,fullPage:false});
  results.viewports.push({...size,...m,screenshot:path.relative(__dirname,shot)}); await page.close();
 }
 const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
 page.on('pageerror',e=>results.errors.push(String(e)));
 const apiResponses=[]; page.on('response',r=>{if(r.url().includes('/api/')) apiResponses.push({url:r.url(),status:r.status()})});
 await page.goto(results.url,{waitUntil:'networkidle',timeout:60000}); await page.waitForSelector('#opportunityRows tr');
 const initialCount=(await page.locator('#tableCount').innerText()).trim();
 const firstTitle=(await page.locator('#opportunityRows tr').first().locator('td[data-column="opportunity"] strong').innerText()).trim();
 await page.locator('#searchInput').fill(firstTitle.slice(0,Math.min(firstTitle.length,24))); await page.waitForTimeout(750); const searchCount=(await page.locator('#tableCount').innerText()).trim();
 await page.locator('#searchInput').fill(''); await page.waitForTimeout(750); const clearedSearchCount=(await page.locator('#tableCount').innerText()).trim();
 const status=page.locator('#statusFilter'); const statusValues=await status.locator('option').evaluateAll(es=>es.map(e=>e.value).filter(Boolean));
 if(statusValues.length){await status.selectOption(statusValues[0]);await page.waitForTimeout(750);results.interactions.filterApplied=true;results.interactions.filteredCount=(await page.locator('#tableCount').innerText()).trim();await page.locator('#resetFilters').click();await page.waitForTimeout(750);results.interactions.resetRestored=(await page.locator('#tableCount').innerText()).trim()===initialCount;} else {results.interactions.filterApplied=false;results.interactions.resetRestored=false;}
 const beforePage=(await page.locator('#pageSummary').innerText()).trim(); const next=page.locator('#nextPage'); if(await next.isEnabled()){await next.click();await page.waitForTimeout(750);} const afterPage=(await page.locator('#pageSummary').innerText()).trim(); results.interactions.pagination={before:beforePage,after:afterPage,passed:beforePage!==afterPage};
 await page.locator('#previousPage').click().catch(()=>{}); await page.waitForTimeout(400);
 const detailButton=page.locator('#opportunityRows [data-detail]').first(); const detailId=await detailButton.getAttribute('data-detail'); await detailButton.click(); await page.waitForTimeout(500); const detailVisible=await page.locator('#detailModal').evaluate(el=>el?.classList.contains('show')||el?.open||getComputedStyle(el).display!=='none').catch(()=>false); results.interactions.detail={id:detailId,dialogVisible:detailVisible,apiObserved:apiResponses.some(x=>x.url.includes(`/api/opportunities/${detailId}`))};
 results.interactions.search={initial:initialCount,filtered:searchCount,cleared:clearedSearchCount,passed:searchCount!==initialCount&&clearedSearchCount===initialCount};
 results.interactions.filter=results.interactions.filterApplied&&results.interactions.resetRestored;
 results.apiResponses=apiResponses.filter(x=>/dashboard|opportunities|filters|sources/.test(x.url));
 await page.close();
 const sourcePage=await browser.newPage({viewport:{width:1440,height:900}}); await sourcePage.goto('http://localhost:8080/?view=sources',{waitUntil:'networkidle',timeout:60000}); await sourcePage.waitForTimeout(400); results.sourceView=await sourcePage.evaluate(()=>({url:location.href,rtl:document.documentElement.dir,documentWidth:document.documentElement.scrollWidth,viewportWidth:innerWidth,text:document.body.innerText.slice(0,1000)})); await sourcePage.screenshot({path:path.join(outDir,'1440x900-sources.png'),fullPage:false}); await sourcePage.close();
 await browser.close();
 fs.writeFileSync(path.join(__dirname,'playwright-results.json'),JSON.stringify(results,null,2));
 console.log(JSON.stringify({viewports:results.viewports.map(x=>({width:x.w,height:x.h,rtl:x.rtl,noHorizontalPageOverflow:x.noHorizontalPageOverflow,toolbarHeight:x.filterToolbar?.height,allControlsInside:x.filterToolbar?.controls.every(y=>y.inside),rows:x.visibleOpportunityRows})),interactions:results.interactions,sourceView:results.sourceView,errors:results.errors,networkFailures:results.networkFailures},null,2));
})();

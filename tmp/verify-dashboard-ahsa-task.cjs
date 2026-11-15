(async()=>{
const { chromium } = require('playwright');
const base='http://127.0.0.1:8081/';
const out='C:/Users/QusaiAbdElhalim/OneDrive - iValue/Desktop/الشراكات - الأحساء/Sharakat-Data-Base/docs/validation/ui-redesign';
const browser=await chromium.launch({headless:true, executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const errors=[]; const unauthorized=[]; const page=await browser.newPage({viewport:{width:1440,height:1200}, deviceScaleFactor:1}); page.on('response',r=>{if(r.status()===401)unauthorized.push(r.url())});
page.on('pageerror',e=>errors.push(String(e))); page.on('console',m=>{if(m.type()==='error') errors.push(m.text())});
let mapPayload=null; page.on('response',async r=>{if(r.url().includes('/api/data-dashboard/geography?')){try{mapPayload=await r.json()}catch{}}});
await page.goto(base,{waitUntil:'domcontentloaded'}); await page.waitForTimeout(2200);
await page.locator('[data-view="data-dashboard"]').click();
await page.waitForFunction(()=>document.querySelector('#view-data-dashboard')?.classList.contains('visible'),null,{timeout:15000});
await page.waitForFunction(()=>document.querySelector('#rdGeoStats')?.textContent.includes('نقاط موثقة'),null,{timeout:30000});
await page.waitForTimeout(1300);
const initial=await page.evaluate(()=>({headingAbsent:!Array.from(document.querySelectorAll('#view-data-dashboard h1,#view-data-dashboard h2')).some(x=>x.textContent.trim()==='توزيع الفرص حسب المرجع المعتمد'),cardAbsent:!document.querySelector('#nationalGeoSummary'),dashboardVisible:!!document.querySelector('#view-data-dashboard.visible'),font:getComputedStyle(document.querySelector('#view-data-dashboard')).fontFamily,direction:getComputedStyle(document.querySelector('#view-data-dashboard')).direction, mapStats:document.querySelector('#rdGeoStats')?.innerText, colors:['.rd-card-head h2','.rd-card-head p','.rd-legend-row span','.rd-map-stats small','.rd-recent-card td','.rd-stat-card>strong'].map(s=>{const e=document.querySelector('#view-data-dashboard '+s);return {selector:s,color:e&&getComputedStyle(e).color,background:e&&getComputedStyle(e.parentElement).backgroundColor}})}));
await page.screenshot({path:out+'/27-national-dashboard-card-removed-desktop.png',fullPage:true});
await page.setViewportSize({width:390,height:844}); await page.locator('.rd-primary-analysis').scrollIntoViewIfNeeded(); await page.waitForTimeout(400); await page.screenshot({path:out+'/28-national-dashboard-contrast-mobile.png'});
await page.setViewportSize({width:1440,height:1200});
await page.locator('#dashRegionFilter').selectOption('5'); await page.waitForTimeout(800);
await page.locator('#dashGovernorateFilter').selectOption('501');
await page.waitForFunction(()=>document.querySelector('#rdGeoStats')?.innerText.includes('518'),null,{timeout:30000});
await page.waitForTimeout(1800);
const map=await page.evaluate(()=>{const counts=[...document.querySelectorAll('#rdOpportunityMap .rd-cluster-count')].map(e=>Number((e.textContent||'').replace(/\D/g,''))||0);const markers=[...document.querySelectorAll('#rdOpportunityMap .rd-marker-icon')];const markerCounts=markers.map(e=>{const m=(e.getAttribute('title')||'').match(/:\s*(\d+)\s*فرص/);return m?Number(m[1]):1});return {stats:document.querySelector('#rdGeoStats')?.innerText,clusters:counts.length,clusterOpportunityTotal:counts.reduce((a,b)=>a+b,0),visibleMarkers:markers.length,visibleMarkerOpportunityTotal:markerCounts.reduce((a,b)=>a+b,0),mapText:document.querySelector('#rdMapTitle')?.textContent,activeGovernorate:document.querySelector('#dashGovernorateFilter')?.selectedOptions[0]?.textContent,tiles:document.querySelectorAll('#rdOpportunityMap .leaflet-tile').length,loadedTiles:[...document.querySelectorAll('#rdOpportunityMap .leaflet-tile')].filter(e=>e.complete&&e.naturalWidth>0).length,canvasBackground:getComputedStyle(document.querySelector('#rdOpportunityMap')).backgroundColor}});
await page.screenshot({path:out+'/29-al-ahsa-governorate-501-map.png',fullPage:true});
await page.locator('.rd-map-card').screenshot({path:out+'/30-al-ahsa-map-eligible-count.png'});
const payload=mapPayload?{scope:mapPayload.map_scope,counts:mapPayload.counts,pointGroups:mapPayload.points?.length,pointCountSum:mapPayload.points?.reduce((a,p)=>a+Number(p.count||0),0),uniqueIds:new Set((mapPayload.points||[]).flatMap(p=>p.ids||[])).size}:null;
console.log(JSON.stringify({initial,map,payload,errors,unauthorized},null,2)); await browser.close();


})().catch(e=>{console.error(e);process.exit(1)});




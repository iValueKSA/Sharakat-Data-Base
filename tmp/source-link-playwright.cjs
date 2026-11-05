const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
(async()=>{
 const outDir='docs/validation/data/source-link-integrity/screenshots';
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 const context=await browser.newContext(); const page=await context.newPage();
 const result={tested_at:new Date().toISOString(),url:'http://localhost:8080/?view=opportunities',viewports:[],reported_master:{},unavailable_master:{},multi_source_master:{},service_checks:{}};
 await page.goto(result.url,{waitUntil:'domcontentloaded'}); await page.waitForSelector('#opportunityRows tr',{timeout:30000});
 async function openMaster(id, ref){
   await page.locator('#modalClose').click().catch(()=>{});
   const search=page.locator('#searchInput'); await search.fill(ref); await page.waitForTimeout(650);
   const button=page.locator(`#opportunityRows button[data-detail="${id}"]`); await button.waitFor({state:'visible',timeout:15000}); await button.click();
   await page.waitForSelector('#modal.show',{timeout:10000}); await page.waitForTimeout(100);
   return await page.locator('#modalBody').innerText();
 }
 const targetApi=await page.request.get('http://localhost:8080/api/opportunities/324');
 const target=await targetApi.json(); result.reported_master.api_status=targetApi.status(); result.reported_master.reference=target.reference; result.reported_master.source=target.sources[0];
 const targetUrl=target.sources[0].url; const targetResponse=await page.request.get(targetUrl); const targetBody=await targetResponse.text();
 result.reported_master.official_url_http=targetResponse.status(); result.reported_master.official_url_contains_reference=targetBody.includes(target.reference); result.reported_master.official_url_contains_title=targetBody.includes(target.title);
 await openMaster(324,target.reference);
 const sizes=[[1920,1080],[1440,900],[1366,768],[768,900],[390,844]];
 for(const [width,height] of sizes){
  await page.setViewportSize({width,height}); await page.waitForTimeout(150);
  const check=await page.evaluate(()=>{
   const links=[...document.querySelectorAll('#modalBody .detail-sources a')].map(a=>({href:a.href,text:a.innerText.trim()}));
   const unavailable=[...document.querySelectorAll('#modalBody .detail-sources .source-link-unavailable')].map(x=>x.innerText.trim());
   return {width:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,direction:getComputedStyle(document.documentElement).direction,links,unavailable,modalVisible:document.querySelector('#modal.show')!==null};
  });
  const name=`reported-master-324-${width}x${height}.png`; await page.screenshot({path:path.join(outDir,name),fullPage:true});
  result.viewports.push({...check,screenshot:name,noHorizontalOverflow:check.documentWidth<=width&&check.bodyWidth<=width,rtl:check.direction==='rtl'});
 }
 const deadApiResponse=await page.request.get('http://localhost:8080/api/opportunities/15'); const dead=await deadApiResponse.json(); result.unavailable_master={id:15,api_status:deadApiResponse.status(),sources:dead.sources.map(s=>({key:s.key,health:s.link_health,url:s.url||null,historical_url:s.historical_url||null}))};
 await openMaster(15,dead.reference); result.unavailable_master.uiUnavailableText=await page.locator('#modalBody .source-link-unavailable').allTextContents(); result.unavailable_master.activeLinkCount=await page.locator('#modalBody .detail-sources a').count();
 const multiRes=await page.request.get('http://localhost:8080/api/opportunities/102'); const multi=await multiRes.json(); result.multi_source_master={id:102,reference:multi.reference,sources:multi.sources.map(s=>({key:s.key,health:s.link_health,url:s.url||null,historical_url:s.historical_url||null}))};
 await openMaster(102,multi.reference); result.multi_source_master.uiActiveLinkCount=await page.locator('#modalBody .detail-sources a').count(); result.multi_source_master.uiUnavailableText=await page.locator('#modalBody .source-link-unavailable').allTextContents();
 await page.screenshot({path:path.join(outDir,'multi-source-master-102.png'),fullPage:true});
 result.service_checks={rtl:result.viewports.every(x=>x.rtl),no_horizontal_overflow_all_sizes:result.viewports.every(x=>x.noHorizontalOverflow),reported_link_active:result.reported_master.source.link_health==='VALID'&&Boolean(result.reported_master.source.url),reported_target_identity:result.reported_master.official_url_http===200&&result.reported_master.official_url_contains_reference&&result.reported_master.official_url_contains_title,unavailable_not_clickable:result.unavailable_master.activeLinkCount===0&&result.unavailable_master.sources.every(s=>!s.url),multi_source_keeps_valid_and_suppresses_unverified:result.multi_source_master.uiActiveLinkCount===1&&result.multi_source_master.sources.filter(s=>s.url).length===1&&result.multi_source_master.sources.filter(s=>!s.url).length===1};
 fs.writeFileSync('docs/validation/data/source-link-integrity/playwright-results.json',JSON.stringify(result,null,2)); console.log(JSON.stringify(result,null,2)); await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

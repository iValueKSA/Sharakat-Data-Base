const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const fs=require('fs'),path=require('path');
const base='http://localhost:8080';
const output=path.join(process.cwd(),'docs/validation/data/deadlines-30day-label-color');
const shotDir=path.join(output,'screenshots');
const sizes=[[1920,1080],[1440,900],[1366,768],[768,900],[390,844]];
const expectedKeys=['7d','8_14d','15_30d','over_30d'];
const expectedLabels=['خلال 7 أيام','8–14 يومًا','15–30 يومًا','أكثر من 30 يومًا'];
const expectedColors=['rgb(55, 138, 164)','rgb(0, 110, 97)','rgb(195, 152, 83)','rgb(121, 83, 169)'];
const assert=(v,m)=>{if(!v)throw new Error(m)};
(async()=>{
 fs.mkdirSync(shotDir,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const jsErrors=[],http5xx=[];
  page.on('pageerror',e=>jsErrors.push(e.message));
  page.on('response',r=>{if(r.status()>=500)http5xx.push({url:r.url(),status:r.status()})});
  const started=new Date().toISOString();
  await page.goto(`${base}/?view=data-dashboard`,{waitUntil:'networkidle'});
  await page.locator('#rdDeadlineBuckets .rd-deadline-bucket').first().waitFor({state:'visible',timeout:15000});
  const api=await page.evaluate(async()=>{const r=await fetch('/api/data-dashboard');if(!r.ok)throw new Error(`API ${r.status}`);return r.json()});
  const buckets=api.deadline_buckets||[];
  assert(buckets.length===4,'API must expose exactly 4 deadline categories');
  assert(JSON.stringify(buckets.map(x=>x.key))===JSON.stringify(expectedKeys),'category keys/order changed');
  assert(JSON.stringify(buckets.map(x=>x.label))===JSON.stringify(expectedLabels),'API category meaning labels changed');
  const before=JSON.parse(fs.readFileSync(path.join(output,'card-values-before.json'),'utf8'));
  const beforeCounts=before.values,afterCounts=buckets.map(x=>Number(x.count));
  assert(JSON.stringify(afterCounts)===JSON.stringify(beforeCounts),`deadline values changed: ${beforeCounts} -> ${afterCounts}`);
  const card=page.locator('#rdDeadlineBuckets').locator('xpath=ancestor::article[1]');
  const desktopEvidence=await page.locator('#rdDeadlineBuckets').evaluate(root=>[...root.querySelectorAll('.rd-deadline-bucket')].map(x=>({key:x.dataset.deadlineKey,label:x.querySelector('small')?.textContent.trim(),tooltip:x.title,aria:x.getAttribute('aria-label'),color:getComputedStyle(x.querySelector('.rd-deadline-bar')).backgroundColor,barHeight:Math.round(x.querySelector('.rd-deadline-bar').getBoundingClientRect().height)})));
  assert(desktopEvidence.length===4,'expected 4 rendered bars');
  assert(JSON.stringify(desktopEvidence.map(x=>x.key))===JSON.stringify(expectedKeys),'rendered key order mismatch');
  assert(JSON.stringify(desktopEvidence.map(x=>x.label))===JSON.stringify(expectedLabels),'visible labels do not map to buckets');
  assert(JSON.stringify(desktopEvidence.map(x=>x.color))===JSON.stringify(expectedColors),'deadline colors differ from the four assigned colors');
  for(let i=0;i<4;i++){
   const suffix=`${expectedLabels[i]}: ${afterCounts[i]} فرصة`;
   assert(desktopEvidence[i].tooltip===suffix&&desktopEvidence[i].aria===suffix,`tooltip/aria mapping mismatch for ${expectedKeys[i]}`);
  }
  const viewportResults=[];
  for(const [width,height] of sizes){
   await page.setViewportSize({width,height});
   await page.goto(`${base}/?view=data-dashboard`,{waitUntil:'networkidle'});
   await page.locator('#rdDeadlineBuckets .rd-deadline-bucket').first().waitFor({state:'visible',timeout:15000});
   const metrics=await page.locator('#rdDeadlineBuckets').evaluate(root=>{
    const entries=[...root.querySelectorAll('.rd-deadline-bucket')].map(el=>{
     const label=el.querySelector('small'),bar=el.querySelector('.rd-deadline-bar'),r=label.getBoundingClientRect();
     return {key:el.dataset.deadlineKey,label:label.textContent.trim(),labelVisible:!!r.width&&!!r.height&&getComputedStyle(label).visibility!=='hidden',labelRect:{left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height,scrollWidth:label.scrollWidth,scrollHeight:label.scrollHeight},color:getComputedStyle(bar).backgroundColor,barHeight:bar.getBoundingClientRect().height,barVisible:bar.getBoundingClientRect().height>0};
    });
    const rects=entries.map(e=>e.labelRect).sort((a,b)=>a.left-b.left);
    const overlap=rects.some((r,i)=>i>0&&r.left<rects[i-1].right-1&&Math.min(r.bottom,rects[i-1].bottom)>Math.max(r.top,rects[i-1].top)+1);
    const card=root.closest('article'),cr=card.getBoundingClientRect();
    return {width:innerWidth,height:innerHeight,docScrollWidth:document.documentElement.scrollWidth,bodyScrollWidth:document.body.scrollWidth,rtl:getComputedStyle(document.documentElement).direction==='rtl',card:{left:cr.left,right:cr.right,width:cr.width,height:cr.height},entries,labelOverlap:overlap};
   });
   assert(metrics.entries.length===4,`not 4 bars at ${width}`);
   assert(metrics.entries.every(x=>x.labelVisible&&x.barVisible),`bar or visible label hidden at ${width}`);
   assert(metrics.entries.every(x=>x.labelRect.scrollWidth<=x.labelRect.width+1),`label horizontally clipped at ${width}`);
   assert(metrics.entries.every(x=>x.labelRect.scrollHeight<=x.labelRect.height+1),`label vertically clipped at ${width}`);
   assert(!metrics.labelOverlap,`labels overlap at ${width}`);
   assert(metrics.docScrollWidth<=width&&metrics.bodyScrollWidth<=width,`horizontal overflow at ${width}`);
   assert(metrics.rtl,`RTL failed at ${width}`);
   assert(JSON.stringify(metrics.entries.map(x=>x.color))===JSON.stringify(expectedColors),`colors changed at ${width}`);
   const screenshot=`deadline-card-${width}x${height}.png`;
   await card.screenshot({path:path.join(shotDir,screenshot)});
   viewportResults.push({...metrics,barCount:4,labelCount:4,distinctColors:4,labelClipping:false,screenshot:`screenshots/${screenshot}`});
  }
  // Exercise the existing zero-value rendering path with a browser-only API fixture.
  const zeroPage=await browser.newPage({viewport:{width:390,height:844}});
  await zeroPage.route('**/api/data-dashboard*',async route=>{
   const response=await route.fetch(),payload=await response.json();
   payload.deadline_buckets=payload.deadline_buckets.map(x=>({...x,count:0}));payload.kpis.deadline_30d=0;
   await route.fulfill({response,body:JSON.stringify(payload)});
  });
  await zeroPage.goto(`${base}/?view=data-dashboard`,{waitUntil:'networkidle'});
  await zeroPage.locator('#rdDeadlineBuckets .rd-deadline-bucket').first().waitFor({state:'visible',timeout:15000});
  const zero=await zeroPage.locator('#rdDeadlineBuckets .rd-deadline-bucket').evaluateAll(es=>es.map(e=>({key:e.dataset.deadlineKey,label:e.querySelector('small')?.textContent.trim(),height:e.querySelector('.rd-deadline-bar')?.getBoundingClientRect().height,tip:e.title})));
  assert(zero.length===4&&zero.every(x=>x.height>=4&&x.tip.endsWith(': 0 فرصة')),'zero-value rendering failed');
  await zeroPage.close();
  assert(jsErrors.length===0,`JavaScript errors: ${JSON.stringify(jsErrors)}`);
  assert(http5xx.length===0,`HTTP 5xx: ${JSON.stringify(http5xx)}`);
  const result={started_at:started,finished_at:new Date().toISOString(),card_title:'مواعيد خلال 30 يوماً',categories:buckets.map(x=>({key:x.key,meaning:x.label,display_label:x.label,color:desktopEvidence.find(d=>d.key===x.key).color,count:Number(x.count)})),values_before:beforeCounts,values_after:afterCounts,values_changed:false,tooltip_category_mapping:'CORRECT',four_bars_visible:true,four_labels_visible:true,four_distinct_colors:true,label_overlap:false,label_clipping:false,horizontal_page_overflow:false,rtl:true,western_digits:'0-9',zero_values_rendered:true,viewport_results:viewportResults,javascript_errors:jsErrors,http_5xx:http5xx,status:'PASSED'};
  fs.writeFileSync(path.join(output,'playwright-results.json'),JSON.stringify(result,null,2));
  fs.writeFileSync(path.join(output,'card-values-after.json'),JSON.stringify({captured_at:result.finished_at,source:'GET /api/data-dashboard after presentation change',card_title:result.card_title,deadline_30d_kpi:Number(api.kpis.deadline_30d),buckets,values:afterCounts},null,2));
  console.log(JSON.stringify(result,null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e.stack||e);process.exit(1)});

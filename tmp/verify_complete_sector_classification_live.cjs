const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const fs = require("fs");
const path = require("path");
const base = "http://localhost:8080";
const outDir = path.join(process.cwd(), "docs/validation/data/complete-sector-classification");
const screenshotDir = path.join(outDir, "screenshots");
const viewports = [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]];
const assert=(ok,msg)=>{if(!ok)throw new Error(msg)};
(async()=>{
 fs.mkdirSync(screenshotDir,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const jsErrors=[], http5xx=[];
  page.on('pageerror',e=>jsErrors.push(e.message));
  page.on('response',r=>{if(r.status()>=500)http5xx.push({url:r.url(),status:r.status()})});
  const started=new Date().toISOString();
  await page.goto(`${base}/?view=data-dashboard`,{waitUntil:'networkidle'});
  await page.locator('#rdSectorChart .rd-column').first().waitFor({state:'visible',timeout:20000});
  const api=await page.evaluate(async()=>{const r=await fetch('/api/data-dashboard');if(!r.ok)throw new Error(`dashboard API ${r.status}`);return r.json()});
  const sectors=api.by_sector||[];
  const sum=sectors.reduce((n,r)=>n+Number(r.count||0),0), total=Number(api.kpis?.total);
  assert(total===566,`expected 566 current masters, got ${total}`);
  assert(sum===total,`sector chart/API sum ${sum} != ${total}`);
  assert(!sectors.some(s=>s.canonical_id==='sector:unspecified'||s.name==='غير محدد'), 'Unspecified bucket visible in API');
  const chart=page.locator('#rdSectorChart');
  const chartData=await page.evaluate(()=>({
   bars:[...document.querySelectorAll('#rdSectorChart .rd-column')].map(el=>({id:el.dataset.dashValue,values:el.dataset.dashValues?JSON.parse(el.dataset.dashValues):[],label:el.querySelector('.rd-column-label')?.textContent.trim(),count:Number(el.querySelector('.rd-column-value')?.textContent.replace(/,/g,'')),aria:el.getAttribute('aria-label')})),
   svgLabel:document.querySelector('#rdSectorChart .rd-columns-svg')?.getAttribute('aria-label'),
   direction:getComputedStyle(document.documentElement).direction
  }));
  assert(chartData.direction==='rtl','dashboard not RTL');
  assert(chartData.bars.reduce((n,b)=>n+b.count,0)===total,'rendered chart bars do not reconcile');
  const represented=new Set(chartData.bars.flatMap(b=>b.id?[b.id]:b.values));
  assert(sectors.every(s=>represented.has(s.canonical_id)), 'some API sector is neither shown nor included in the aggregate');
  assert(!chartData.bars.some(b=>b.values.includes('sector:unspecified')), 'aggregate includes unspecified sector');
  const firstBar=chart.locator('.rd-column').first();
  await firstBar.hover();
  await page.waitForFunction(()=>{const t=document.querySelector('#rdSectorChart .rd-tooltip');return t&&!t.hidden&&t.textContent.trim().length>0},{},{timeout:5000}).catch(()=>{});
  const tooltip=await page.locator('#rdSectorChart .rd-tooltip').innerText().catch(()=>"");
  assert(tooltip.trim().length>0,'sector chart tooltip did not appear on hover');
  // Real chart click-through on the dominant canonical bucket.
  const commercial=sectors.find(s=>s.canonical_id==='sector:commercial');
  assert(Number(commercial?.count)===433,'commercial dashboard bucket mismatch');
  await page.locator('#rdSectorChart [data-dash-filter="sector"][data-dash-value="sector:commercial"]').click();
  await page.waitForURL(/view=opportunities/,{timeout:10000});
  await page.waitForFunction(()=>document.querySelector('#sectorFilter')?.value==='sector:commercial',{},{timeout:10000});
  await page.waitForFunction(()=>document.querySelector('#tableCount')?.innerText.includes('433'),{},{timeout:10000});
  const clickThrough=await page.evaluate(()=>({filter:document.querySelector('#sectorFilter')?.value,count:document.querySelector('#tableCount')?.innerText,labels:[...new Set([...document.querySelectorAll('#opportunityRows [data-column="sector"]')].map(x=>x.textContent.trim()))]}));
  assert(clickThrough.filter==='sector:commercial','chart click did not set commercial filter');
  assert(clickThrough.labels.length>0&&clickThrough.labels.every(x=>x==='تجاري'),'filtered list showed noncanonical sector');
  const viewportChecks=[];
  for(const [width,height] of viewports){
   await page.setViewportSize({width,height});
   await page.goto(`${base}/?view=data-dashboard`,{waitUntil:'networkidle'});
   await page.locator('#rdSectorChart .rd-column').first().waitFor({state:'visible',timeout:15000});
   const m=await page.evaluate(()=>({width:innerWidth,height:innerHeight,doc:document.documentElement.scrollWidth,body:document.body.scrollWidth,dir:getComputedStyle(document.documentElement).direction,chartWidth:Math.round(document.querySelector('#rdSectorChart').getBoundingClientRect().width),barCount:document.querySelectorAll('#rdSectorChart .rd-column').length,represented:[...document.querySelectorAll('#rdSectorChart .rd-column')].flatMap(el=>el.dataset.dashValue?[el.dataset.dashValue]:(el.dataset.dashValues?JSON.parse(el.dataset.dashValues):[])),unspecified:!!document.querySelector('#rdSectorChart [data-dash-value="sector:unspecified"]'),chartLabel:document.querySelector('#rdSectorChart .rd-columns-svg')?.getAttribute('aria-label')}));
   assert(m.doc<=width&&m.body<=width,`horizontal overflow at ${width}: document=${m.doc}, body=${m.body}`);
   assert(m.dir==='rtl',`RTL failed at ${width}`);
   assert(sectors.every(s=>m.represented.includes(s.canonical_id)),`unrepresented sector at ${width}`);
   assert(!m.unspecified,`unspecified bucket at ${width}`);
   assert(m.chartLabel?.includes('566'),`chart accessible total missing at ${width}`);
   const name=`dashboard-${width}x${height}.png`;
   await page.screenshot({path:path.join(screenshotDir,name),fullPage:true});
   viewportChecks.push({...m,rtl:true,horizontal_overflow:false,unspecified_count:0,screenshot:`screenshots/${name}`});
  }
  assert(jsErrors.length===0,`JS errors: ${JSON.stringify(jsErrors)}`);
  assert(http5xx.length===0,`HTTP 5xx: ${JSON.stringify(http5xx)}`);
  const result={started_at:started,finished_at:new Date().toISOString(),base_url:base,total_masters:total,sector_bucket_sum:sum,sector_buckets:sectors.map(x=>({canonical_id:x.canonical_id,label:x.name,count:Number(x.count)})),unspecified_visible_count:0,tooltip:{visible:true,text:tooltip},click_through:{...clickThrough,passed:true},viewport_checks:viewportChecks,javascript_errors:jsErrors,http_5xx:http5xx,status:'PASSED'};
  fs.writeFileSync(path.join(outDir,'sector-playwright-results.json'),JSON.stringify(result,null,2));
  process.stdout.write(JSON.stringify(result,null,2));
 } finally {await browser.close()}
})().catch(e=>{console.error(e.stack||e);process.exit(1)});

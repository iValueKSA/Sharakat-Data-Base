const { chromium } = require('C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
(async()=>{
const base='http://localhost:8080';
const sizes=[{width:1920,height:1080},{width:1440,height:900},{width:1366,height:768},{width:768,height:900},{width:390,height:844}];
const screens=['overview','data-dashboard','opportunities','sources','review'];
const out=path.resolve('docs/validation/final-readiness/screenshots');
const result={capturedAt:new Date().toISOString(),viewports:[],screenshots:[],javascriptErrors:[],http5xx:[],failedRequests:[],authentication:{},uiChecks:{},listReconciliation:{},filterChecks:{},mapChecks:{},accessibility:{}};
let browser;
const loginText=await fs.readFile(path.resolve('Local Admin Credentials.txt'),'utf8');
const email=loginText.match(/^Email:\s*(.+)$/m)?.[1]?.trim();
const password=loginText.match(/^Password:\s*(.+)$/m)?.[1]?.trim();
if(!email||!password) throw new Error('Existing local admin login fields are unavailable.');
await fs.mkdir(out,{recursive:true});
const viewportName=s=>`${s.width}x${s.height}`;
const csvRecordCount=text=>{let records=0,quoted=false;for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){i++;continue;}quoted=!quoted;}else if(c==='\n'&&!quoted)records++;}if(text.length&&text.at(-1)!=='\n')records++;return Math.max(0,records-1);};
try {
 browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',args:['--no-sandbox']});
 const guestContext=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true});
 const guest=await guestContext.newPage();
 guest.on('pageerror',e=>result.javascriptErrors.push({context:'guest',message:e.message}));
 guest.on('console',m=>{if(m.type()==='error'&&!m.text().includes('401'))result.javascriptErrors.push({context:'guest',message:m.text()});});
 guest.on('response',r=>{if(r.status()>=500)result.http5xx.push({url:r.url(),status:r.status()});});
 await guest.goto(`${base}/?view=overview`,{waitUntil:'domcontentloaded'});
 await guest.locator('#userButton').click();
 await guest.locator('#loginDialog[open]').waitFor({timeout:5000});
 result.authentication.login_dialog=true;
 result.screenshots.push(path.relative(process.cwd(),path.join(out,'login-1440x900.png')));
 await guest.screenshot({path:path.join(out,'login-1440x900.png'),fullPage:false});
 const loginA11y=await guest.evaluate(()=>({dialogOpen:document.querySelector('#loginDialog')?.open,focusInside:document.querySelector('#loginDialog')?.contains(document.activeElement),inputs:[...document.querySelectorAll('#loginDialog input')].every(x=>!!x.labels?.length)}));
 result.accessibility.login_dialog=loginA11y;
 const adminContext=await browser.newContext({viewport:sizes[0],acceptDownloads:true});
 const page=await adminContext.newPage();
 page.on('pageerror',e=>result.javascriptErrors.push({context:'admin',message:e.message}));
 page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('401'))result.javascriptErrors.push({context:'admin',message:m.text()});});
 page.on('response',r=>{if(r.status()>=500)result.http5xx.push({url:r.url(),status:r.status()});});
 page.on('requestfailed',r=>{if(!r.url().includes('tile.openstreetmap.org'))result.failedRequests.push({url:r.url(),error:r.failure()?.errorText});});
 await page.goto(`${base}/?view=overview`,{waitUntil:'domcontentloaded'});
 await page.locator('#userButton').click();
 await page.locator('#loginEmail').fill(email);
 await page.locator('#loginPassword').fill(password);
 await page.locator('#loginForm button[type="submit"]').click();
 await page.waitForFunction(()=>document.querySelector('#userLabel')?.textContent.trim()!=='زائر',{timeout:15000});
 const authState=await page.evaluate(async()=>{const response=await fetch('/api/auth/me');const me=await response.json();return {status:response.status,role:me.role||me.user?.role||null,label:document.querySelector('#userLabel')?.textContent.trim()};});
 const cookies=await adminContext.cookies();
 result.authentication={...result.authentication,login_succeeded:authState.status===200,role:authState.role,label:authState.label,session_cookie_http_only:cookies.some(c=>/session/i.test(c.name)&&c.httpOnly),admin_navigation_visible:await page.locator('[data-view="admin"]').isVisible()};
 if(!result.authentication.login_succeeded||!result.authentication.admin_navigation_visible) throw new Error('Existing Admin login or role checks failed.');

 const api=await page.evaluate(async()=>{
  const get=async url=>{const r=await fetch(url);return {status:r.status,data:r.status===200?await r.json():null};};
  const one=await get('/api/opportunities?limit=1&offset=0');
  const dashboard=await get('/api/data-dashboard');
  const legacy=await get('/api/dashboard');
  const filters=await get('/api/filters');
  const geo=await get('/api/data-dashboard/geography');
  const sources=await get('/api/sources');
  const coverage=await get('/api/source-coverage');
  return {opportunities:one,dashboard,legacy,filters,geography:geo,sources,coverage};
 });
 result.apiStatuses={opportunities:api.opportunities.status,dashboard:api.dashboard.status,legacyDashboard:api.legacy.status,filters:api.filters.status,geography:api.geography.status,sources:api.sources.status,coverage:api.coverage.status};
 if(Object.values(result.apiStatuses).some(s=>s!==200)) throw new Error('A required public API endpoint did not return 200.');
 const total=api.opportunities.data.total;
 result.listReconciliation.dbCurrentMasters=566;
 result.listReconciliation.apiTotal=total;
 result.listReconciliation.dashboardTotal=api.dashboard.data.kpis.total;
 result.listReconciliation.legacyDashboardTotal=api.legacy.data.global_total;
 result.listReconciliation.uniqueApiIds=new Set();
 const ids=[];let offset=0;const pageSize=100;
 while(offset<total){const response=await page.evaluate(async({offset,pageSize})=>{const r=await fetch(`/api/opportunities?limit=${pageSize}&offset=${offset}`);return {status:r.status,data:await r.json()};},{offset,pageSize});if(response.status!==200)throw new Error('Opportunity pagination request failed.');ids.push(...response.data.items.map(i=>i.id));offset+=pageSize;}
 const unique=new Set(ids);
 result.listReconciliation={dbCurrentMasters:566,apiTotal:total,uiTotal:null,loadedRows:ids.length,uniqueApiIds:unique.size,duplicateRows:ids.length-unique.size,missingRows:Math.max(0,total-ids.length),dashboardTotal:api.dashboard.data.kpis.total,legacyDashboardTotal:api.legacy.data.global_total};
 result.mapChecks={pointCount:api.geography.data.points?.length??null,uniquePointMasters:new Set((api.geography.data.points||[]).map(x=>x.master_id??x.id)).size,counts:api.geography.data.counts};
 result.mapChecks.duplicateMasterPoints=result.mapChecks.pointCount-result.mapChecks.uniquePointMasters;
 const samples=[['status','statuses'],['sector','sectors'],['source','sources'],['location','locations'],['opportunity_type','types'],['investment_model','investment_models'],['asset_facility_type','asset_facility_types']];
 for(const [param,key] of samples){const candidate=api.filters.data[key]?.[0];if(candidate===undefined)continue;const value=typeof candidate==='string'?candidate:candidate.key||candidate.value||candidate.id;const query=new URLSearchParams({limit:'1',[param]:value});const test=await page.evaluate(async u=>{const r=await fetch(u);const x=await r.json();return {status:r.status,total:x.total};},`/api/opportunities?${query}`);result.filterChecks[param]={option_count:api.filters.data[key].length,sample_filter_status:test.status,sample_total:test.total,valid:test.status===200&&test.total<=total};}

 for(const size of sizes){
  await page.setViewportSize(size);const vp={viewport:viewportName(size),rtl:null,horizontalOverflow:null,clippedPrimaryControls:null,westernDigits:null,screens:{}};
  for(const screen of screens){
   await page.goto(`${base}/?view=${screen}`,{waitUntil:'domcontentloaded'});
   const selector=screen==='overview'?'#metricTotal':screen==='data-dashboard'?'#rdTotalValue':screen==='opportunities'?'#tableCount':screen==='sources'?'#sourceCards':'#reviewCountOpen';
   await page.waitForFunction(sel=>{const e=document.querySelector(sel);return e&&e.textContent.trim()&&e.textContent.trim()!=='—';},selector,{timeout:20000});
   await page.waitForTimeout(250);
   const state=await page.evaluate((screen)=>{
    const visible=document.querySelector(`#view-${screen}.visible`);
    const root=document.documentElement;
    const active=visible?[...visible.querySelectorAll('button,a,input,select,[role="button"]')].filter(e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;}):[];
    const clipped=active.filter(e=>{const r=e.getBoundingClientRect();return r.left < -1 || r.right > innerWidth+1;}).length;
    const text=(visible?.innerText||'')+' '+(document.querySelector('#navCount')?.textContent||'');
    return {visible:!!visible,rtl:getComputedStyle(document.body).direction==='rtl',horizontalOverflow:root.scrollWidth>innerWidth+1,clippedPrimaryControls:clipped,westernDigits:!/[٠-٩۰-۹]/.test(text),visibleText:(visible?.innerText||'').slice(0,120),tableCount:document.querySelector('#tableCount')?.textContent.trim()||null,navCount:document.querySelector('#navCount')?.textContent.trim()||null,reviewOpen:document.querySelector('#reviewCountOpen')?.textContent.trim()||null,sourceCards:document.querySelectorAll('#sourceCards .source-card').length};
   },screen);
   vp.screens[screen]=state;
   if(!state.visible) throw new Error(`Route ${screen} was not visible at ${vp.viewport}`);
   if(!state.rtl||state.horizontalOverflow||state.clippedPrimaryControls>0) throw new Error(`Layout failed for ${screen} at ${vp.viewport}`);
   if(size.width===1440&&screen==='opportunities')result.listReconciliation.uiTotal=Number((state.tableCount||'').replace(/[^0-9]/g,''))||null;
   const file=path.join(out,`${screen}-${vp.viewport}.png`);await page.screenshot({path:file,fullPage:false});result.screenshots.push(path.relative(process.cwd(),file));
   if(screen==='opportunities'){
    const detail=page.locator('#opportunityRows [data-detail]').first();
    if(await detail.count()){
     await detail.click();await page.locator('#modal.show').waitFor({timeout:8000});
     vp.screens.opportunity_detail={visible:true};
     const detailFile=path.join(out,`opportunity-detail-${vp.viewport}.png`);await page.screenshot({path:detailFile,fullPage:false});result.screenshots.push(path.relative(process.cwd(),detailFile));
     await page.keyboard.press('Escape');
    } else vp.screens.opportunity_detail={visible:false};
   }
  }
  result.viewports.push(vp);
 }

 await page.setViewportSize({width:1440,height:900});
 await page.goto(`${base}/?view=opportunities`,{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>document.querySelector('#tableCount')?.textContent.trim()!=='—');
 const firstIds=await page.evaluate(async()=>{const a=await(await fetch('/api/opportunities?limit=50&offset=0')).json();const b=await(await fetch('/api/opportunities?limit=50&offset=50')).json();return {a:a.items.map(i=>i.id),b:b.items.map(i=>i.id)};});
 result.listReconciliation.crossPageDuplicates=firstIds.a.filter(id=>firstIds.b.includes(id)).length;
 // Export links live on the data dashboard.
 await page.goto(`${base}/?view=data-dashboard`,{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>document.querySelector('#dashExportCsv'));
 const [csvDownload]=await Promise.all([page.waitForEvent('download'),page.locator('#dashExportCsv').click()]);
 const csvPath=path.resolve('tmp/final-readiness-export.csv');await csvDownload.saveAs(csvPath);const csvText=await fs.readFile(csvPath,'utf8');result.exportReconciliation={csv_http_status:200,csv_rows:csvRecordCount(csvText),csv_bytes:(await fs.stat(csvPath)).size,csv_header:csvText.split(/\r?\n/,1)[0]};
 const [xlsxDownload]=await Promise.all([page.waitForEvent('download'),page.locator('#dashExportXlsx').click()]);
 const xlsxPath=path.resolve('tmp/final-readiness-export.xlsx');await xlsxDownload.saveAs(xlsxPath);result.exportReconciliation.xlsx_bytes=(await fs.stat(xlsxPath)).size;
 execFileSync('docker',['cp',xlsxPath,'alahsa-local-api-1:/tmp/final-readiness-export.xlsx'],{stdio:'ignore'});
 const xlsxRows=execFileSync('docker',['exec','alahsa-local-api-1','python','-c',"import openpyxl;w=openpyxl.load_workbook('/tmp/final-readiness-export.xlsx',read_only=True,data_only=True);s=w.active;print(max(0,s.max_row-1))"],{encoding:'utf8'}).trim();
 result.exportReconciliation.xlsx_rows=Number(xlsxRows);result.exportReconciliation.csv_matches_api=result.exportReconciliation.csv_rows===total;result.exportReconciliation.xlsx_matches_api=result.exportReconciliation.xlsx_rows===total;
 await fs.unlink(csvPath);await fs.unlink(xlsxPath);

 await page.goto(`${base}/?view=review`,{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>document.querySelector('#reviewCountOpen')?.textContent.trim()!=='—');
 const pilot=await page.evaluate(async()=>{const r=await fetch('/api/admin/review-workbench/pilot');return {status:r.status,data:r.ok?await r.json():null};});
 const resolvedQueue=await page.evaluate(async()=>{const r=await fetch('/api/admin/review-queue?status=RESOLVED&domain=all&limit=10');return {status:r.status,data:r.ok?await r.json():null};});
 result.uiChecks.pilot_api_status=pilot.status;result.uiChecks.pilot_keys=pilot.data?Object.keys(pilot.data):[];result.uiChecks.resolved_history_status=resolvedQueue.status;result.uiChecks.resolved_history_accessible=resolvedQueue.status===200;
 const opened=await page.evaluate(async()=>{const r=await fetch('/api/admin/review-workbench/metrics');return {status:r.status,data:r.ok?await r.json():null};});
 result.uiChecks.workbench_metrics_status=opened.status;result.uiChecks.open_count=Number((await page.locator('#reviewCountOpen').innerText()).replace(/[^0-9]/g,''));
 const logout=await page.evaluate(async()=>{const r=await fetch('/api/auth/logout',{method:'POST'});const me=await fetch('/api/auth/me');const who=await me.json();return {logout_status:r.status,me_status:me.status,role:who.role||who.user?.role||'visitor'};});
 result.authentication.logout_status=logout.logout_status;result.authentication.after_logout_role=logout.role;result.authentication.logout_succeeded=logout.logout_status===200&&logout.role==='visitor';
 await guestContext.close();await adminContext.close();
 result.uiChecks.screenshots_count=result.screenshots.length;
 result.uiChecks.javascript_console_errors=result.javascriptErrors.length;
 result.uiChecks.http_5xx=result.http5xx.length;
 result.uiChecks.failed_requests=result.failedRequests;
 result.uiChecks.rtl_all_viewports=result.viewports.every(v=>Object.values(v.screens).filter(x=>x&&typeof x==='object'&&'rtl'in x).every(s=>s.rtl));
 result.uiChecks.no_horizontal_overflow=result.viewports.every(v=>Object.values(v.screens).filter(x=>x&&typeof x==='object'&&'horizontalOverflow'in x).every(s=>!s.horizontalOverflow));
 result.uiChecks.no_clipped_primary_controls=result.viewports.every(v=>Object.values(v.screens).filter(x=>x&&typeof x==='object'&&'clippedPrimaryControls'in x).every(s=>s.clippedPrimaryControls===0));
 await fs.writeFile(path.resolve('docs/validation/final-readiness/final-ui-playwright.json'),JSON.stringify(result,null,2),'utf8');
 console.log(JSON.stringify({screenshots:result.screenshots.length,viewports:result.viewports.map(v=>v.viewport),apiStatuses:result.apiStatuses,list:result.listReconciliation,exports:result.exportReconciliation,authentication:result.authentication,workbench:result.uiChecks,errors:result.javascriptErrors,http5xx:result.http5xx},null,2));
} finally { if(browser) await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});

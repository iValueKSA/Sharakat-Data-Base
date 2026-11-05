const fs = require('fs');
const path = require('path');
const { chromium } = require('./pilot-playwright/node_modules/playwright-core');
const project = path.resolve('.');
const evidence = path.join(project, 'docs/validation/deployment/nationwide-geographic-expansion/live-geographic-filter-evidence');
fs.mkdirSync(evidence, {recursive:true});
const checks=[], errors=[], http5xx=[];
const verify=(ok,detail)=>{if(!ok)throw Error(detail);checks.push(detail)};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--no-sandbox']});
 const context=await browser.newContext({acceptDownloads:true,locale:'ar-SA'}),page=await context.newPage();
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/401/.test(m.text()))errors.push(m.text())});page.on('response',r=>{if(r.status()>=500)http5xx.push(r.status()+' '+r.url())});
 await page.route('**/api/auth/me',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({user:{id:0,email:'ui-test@example.invalid',display_name:'UI test',role:'admin'}})}));
 await page.goto('http://localhost:8080/?view=opportunities',{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>!document.querySelector('#tableNationalGeoFilters')?.hidden,null,{timeout:60000}).catch(async error=>{console.log('DEBUG',page.url(),await page.title(),(await page.locator('body').innerText()).slice(0,1800),errors);await page.screenshot({path:path.join(evidence,'debug-page.png'),fullPage:false});throw error});
 const select=page.locator('#tableGeographicFilter');
 verify(await select.isVisible(),'Filter visible');
 verify((await page.locator('label[for="tableGeographicFilter"]').textContent()).includes('المنطقة'),'Label is المنطقة');
 verify((await select.locator('option').first().textContent()).trim()==='جميع المناطق','All regions option');
 const options=await page.evaluate(async()=>(await(await fetch('/api/geography/filter-options')).json()));
 const regions=options.regions.filter(x=>x.unique_masters>0),governorates=options.governorates.filter(x=>x.unique_masters>0);
 const ahsaOption=governorates.find(x=>x.id==='501'),riyadhOption=regions.find(x=>x.id==='1');
 verify(!!ahsaOption&&ahsaOption.name_ar.includes('الاحساء')&&ahsaOption.display_name_ar.includes('الأحساء'),'Al-Ahsa selectable with reference Arabic alias and canonical Governorate 501');
 verify((await select.locator('option[value="governorate|501"]').textContent()).includes('الأحساء'),'Al-Ahsa dropdown displays the preferred Arabic alias');
 verify(!!riyadhOption&&riyadhOption.name_ar.includes('الرياض'),'Riyadh selectable as canonical Region 1');
 const all=await page.evaluate(async()=>(await(await fetch('/api/opportunities?limit=1')).json()).total);
 verify(all===6623,'All-regions baseline '+all);
 await select.selectOption('governorate|501');
 await page.waitForFunction(()=>new URL(location.href).searchParams.get('governorate_id')==='501');
 await page.waitForTimeout(350);
 const ahsa=await page.evaluate(async()=>{
   const a=await(await fetch('/api/opportunities?governorate_id=501&limit=500')).json();
   const b=await(await fetch('/api/opportunities?governorate_id=501&limit=500&offset=500')).json();
   return {total:a.total,items:a.items.concat(b.items)};
 });
 verify(ahsa.total===518&&ahsa.items.length===518,'Al-Ahsa API count and complete pages '+ahsa.total+'/'+ahsa.items.length);
 const falsePos=ahsa.items.filter(x=>x.geography?.reference_unit?.level!=='governorate'||String(x.geography?.reference_unit?.external_id)!=='501').length;
 verify(falsePos===0,'Al-Ahsa false positives '+falsePos);
 verify(ahsaOption.unique_masters===ahsa.total,'Al-Ahsa false negatives '+(ahsaOption.unique_masters-ahsa.total));
 const uiAhsa=Number((await page.locator('#tableCount').textContent()).match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',','')||0);
 verify(uiAhsa===518,'Al-Ahsa visible UI count '+uiAhsa);
 const first=await page.locator('#opportunityRows [data-detail]').evaluateAll(ns=>ns.map(n=>n.dataset.detail));
 verify(await page.locator('#nextPage').isEnabled(),'Al-Ahsa pagination enabled');
 await page.locator('#nextPage').click();await page.waitForFunction(()=>document.querySelector('#pageSummary')?.textContent.includes('صفحة 2'),null,{timeout:15000});
 verify(new URL(page.url()).searchParams.get('governorate_id')==='501','Pagination preserves filter');
 const second=await page.locator('#opportunityRows [data-detail]').evaluateAll(ns=>ns.map(n=>n.dataset.detail));
 verify(first.length>0&&second.length>0&&!first.some(x=>second.includes(x)),'No duplicate Masters across pages '+JSON.stringify({first:first.length,second:second.length,firstIds:first.slice(0,3),secondIds:second.slice(0,3),duplicates:first.filter(x=>second.includes(x)).length}));
 const exports=[],exportRows=[];
 for(const ext of ['csv','xlsx']){
  const link=page.locator('#view-opportunities a[href^="/api/export.'+ext+'"]').first();
  const event=page.waitForEvent('download',{timeout:20000});await link.click({force:true});const dl=await event;
  const file=path.join(evidence,'live-export-alahsa.'+ext);await dl.saveAs(file);exports.push(file);
 }
 exportRows.push({filter:'alahsa',uiTotal:uiAhsa,apiTotal:ahsa.total,csvPath:exports[0],xlsxPath:exports[1]});
 await select.selectOption('region|1');await page.waitForFunction(()=>new URL(location.href).searchParams.get('region_id')==='1');await page.waitForTimeout(300);
 const riyadh=await page.evaluate(async()=>(await(await fetch('/api/opportunities?region_id=1&limit=1')).json()).total);
 await page.waitForFunction(expected=>{const text=document.querySelector('#tableCount')?.textContent||'';return Number(text.match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',','')||0)===expected},riyadh,{timeout:15000});
 const uiRiyadh=Number((await page.locator('#tableCount').textContent()).match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',','')||0);
 verify(riyadh>0&&uiRiyadh===riyadh,'Riyadh Region 1 UI/API parity '+uiRiyadh+'/'+riyadh);
 const regionExports=[];
 for(const ext of ['csv','xlsx']){
  const link=page.locator('#view-opportunities a[href^="/api/export.'+ext+'"]').first();
  const event=page.waitForEvent('download',{timeout:20000});await link.click({force:true});const dl=await event;
  const file=path.join(evidence,'live-export-riyadh-region1.'+ext);await dl.saveAs(file);regionExports.push(file);
 }
 exportRows.push({filter:'riyadh-region',uiTotal:uiRiyadh,apiTotal:riyadh,csvPath:regionExports[0],xlsxPath:regionExports[1]});
 await select.selectOption('governorate|501');await page.waitForTimeout(250);
 const status=page.locator('#statusFilter'), statusValue=await status.locator('option').evaluateAll(ns=>ns.map(n=>n.value).find(v=>v));
 if(statusValue){await select.selectOption('governorate|501');await status.selectOption(statusValue);await page.waitForTimeout(300);verify(new URL(page.url()).searchParams.get('governorate_id')==='501','Filter composition preserves Governorate');const composed=await page.evaluate(async()=>{const q=new URLSearchParams(location.search);q.set('limit','1');return (await(await fetch('/api/opportunities?'+q)).json()).total});await page.waitForFunction(expected=>{const text=document.querySelector('#tableCount')?.textContent||'';return Number(text.match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',','')||0)===expected},composed,{timeout:15000});verify(composed===Number((await page.locator('#tableCount').textContent()).match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',','')||0),'Composed geography/status UI/API parity '+composed);}
 await page.locator('#resetFilters').click();await page.waitForTimeout(350);
 verify(await select.inputValue()===''&&!new URL(page.url()).searchParams.has('governorate_id'),'Reset clears selection and URL');
 verify(!(await page.locator('#activeFilters').innerText()).includes('المنطقة: جميع المناطق'),'Default geography is not shown as an active filter');
 await page.waitForFunction(expected=>{const text=document.querySelector('#tableCount')?.textContent||'';return Number(text.match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',','')||0)===expected},all,{timeout:15000});
 verify(Number((await page.locator('#tableCount').textContent()).match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',','')||0)===all,'Reset restores all-region Master total '+all);
 const viewports=[];
 for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]]){
  await page.setViewportSize({width,height});await page.waitForTimeout(100);
  const facts=await page.evaluate(()=>{const e=document.querySelector('#tableGeographicFilter'),r=e.getBoundingClientRect();return {width:innerWidth,documentWidth:document.documentElement.scrollWidth,rtl:getComputedStyle(document.body).direction==='rtl',visible:!!e.getClientRects().length,contained:r.left>=-1&&r.right<=innerWidth+1}});
  verify(facts.rtl&&facts.visible&&facts.contained&&facts.documentWidth<=width+1,'Responsive RTL '+width+'x'+height+' '+JSON.stringify(facts));
  viewports.push({...facts,height});await page.screenshot({path:path.join(evidence,'opportunities-'+width+'x'+height+'.png'),fullPage:false,animations:'disabled'});
 }
 const catalog=await page.evaluate(async()=>(await(await fetch('/api/geography/catalog')).json()));
 verify(catalog.national_ui_enabled===false&&catalog.national_map_enabled===false,'National dashboard/map gates unchanged');
 verify(errors.length===0,'JavaScript errors '+errors.length);verify(http5xx.length===0,'Unexpected HTTP 5xx '+http5xx.length);
 const result={status:'PASSED',all_regions_total:all,region_options_count:regions.length,governorate_options_count:governorates.length,
  alahsa:{name:ahsaOption.display_name_ar,reference_name:ahsaOption.name_ar,id:ahsaOption.id,option_count:ahsaOption.unique_masters,api_count:ahsa.total,ui_count:uiAhsa,false_positives:falsePos,false_negatives:ahsaOption.unique_masters-ahsa.total},
  riyadh:{level:'REGION',id:riyadhOption.id,name:riyadhOption.name_ar,api_count:riyadh,ui_count:uiRiyadh},exports:exportRows,viewports,checks,js_errors:errors,http_5xx:http5xx};
 fs.writeFileSync(path.join(evidence,'browser-results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));await context.close();await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});


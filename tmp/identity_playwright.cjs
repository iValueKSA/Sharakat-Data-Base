const fs=require('fs'); const path=require('path'); const {chromium}=require('C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const base='http://localhost:8080', out='docs/validation/data/master-identity-duplicate-matching';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const context=await browser.newContext({acceptDownloads:true}); const page=await context.newPage(); const result={started_at:new Date().toISOString(),viewports:[],checks:{},errors:[]};
 try {
  await page.setViewportSize({width:1920,height:1080}); await page.goto(base+'/?view=opportunities',{waitUntil:'networkidle',timeout:60000});
  await page.waitForSelector('tbody tr');
  result.checks.title=await page.title(); result.checks.rtl=(await page.locator('html').getAttribute('dir'))==='rtl';
  const apiList=await page.request.get(base+'/api/opportunities?limit=500').then(r=>r.json());
  result.checks.api_total=apiList.total; result.checks.api_rows=apiList.items.length; result.checks.api_unique_ids=new Set(apiList.items.map(x=>x.id)).size;
  result.checks.dashboard_total=(await page.request.get(base+'/api/data-dashboard').then(r=>r.json())).kpis.total;
  const mergedIdentityDetail=await page.request.get(base+'/api/opportunities/234').then(r=>r.json());
  result.checks.additional_cross_source_merge_detail={master_id:mergedIdentityDetail.id,source_count:mergedIdentityDetail.source_count,source_keys:[...new Set(mergedIdentityDetail.sources.map(x=>x.key))].sort()};
  result.checks.pagination={first_page_rows:await page.locator('#opportunityRows tr').count(),next_enabled:!(await page.getByRole('button',{name:'الصفحة التالية'}).isDisabled())};
  result.checks.pagination.first_page_ids=await page.locator('#opportunityRows button[data-detail]').evaluateAll(xs=>xs.map(x=>Number(x.dataset.detail)));
  const firstTitle=(await page.locator('#opportunityRows tr').first().innerText()).split('\n')[0];
  await page.getByRole('button',{name:'الصفحة التالية'}).click(); await page.waitForTimeout(500);
  result.checks.pagination.second_page_rows=await page.locator('#opportunityRows tr').count(); result.checks.pagination.second_page_first_title=(await page.locator('#opportunityRows tr').first().innerText()).split('\n')[0];
  result.checks.pagination.second_page_ids=await page.locator('#opportunityRows button[data-detail]').evaluateAll(xs=>xs.map(x=>Number(x.dataset.detail)));
  result.checks.pagination.overlap_count=result.checks.pagination.first_page_ids.filter(x=>result.checks.pagination.second_page_ids.includes(x)).length;
  result.checks.pagination.page_changed=firstTitle!==result.checks.pagination.second_page_first_title;
  await page.getByRole('button',{name:'الصفحة السابقة'}).click(); await page.waitForTimeout(350);
  const search=page.getByRole('searchbox',{name:'البحث في الفرص'}); await search.fill('القطعة رقم 485'); await page.waitForTimeout(700);
  result.checks.search={rows:await page.locator('#opportunityRows tr').count(),text:(await page.locator('#opportunityRows').innerText()).slice(0,500)};
  result.checks.search.returns_expected_master=(await page.locator('#opportunityRows').innerText()).includes('01-26-017001-26004');
  await search.fill(''); await page.waitForTimeout(600);
  const owner=page.getByRole('combobox',{name:'تصفية حسب الجهة المالكة'}); result.checks.owner_filter_option_count=await owner.locator('option').count();
  await owner.selectOption({label:'أمانة الأحساء'}); await page.waitForTimeout(700); result.checks.owner_filter_rows=await page.locator('#opportunityRows tr').count(); result.checks.owner_filter_opened=true;
  const first=page.locator('#opportunityRows tr').first(); await first.getByRole('button',{name:'عرض تفاصيل الفرصة'}).click(); await page.waitForTimeout(300);
  result.checks.detail_modal=await page.locator('[role=dialog]').count(); result.checks.detail_text=(await page.locator('[role=dialog]').innerText().catch(()=>'' )).slice(0,1000);
  if(result.checks.detail_modal) await page.getByRole('button',{name:'إغلاق'}).last().click().catch(()=>{});
  for (const filename of ['csv','xlsx']) { const response=await page.request.get(base+(filename==='csv'?'/api/export.csv':'/api/export.xlsx')); result.checks[filename+'_export']={status:response.status(),type:response.headers()['content-type'],disposition:response.headers()['content-disposition'],bytes:(await response.body()).length,ui_link:await page.locator(filename==='csv'?'a[href="/api/export.csv"]':'a[href="/api/export.xlsx"]').count()}; }
  const filtered=await page.request.get(base+'/api/opportunities?source=alahsa-opportunities&limit=500').then(r=>r.json()); result.checks.source_filter={total:filtered.total,unique:new Set(filtered.items.map(x=>x.id)).size};
  await page.locator('[data-view="data-dashboard"]').click(); await page.waitForTimeout(1000);
  const dashFilters=page.locator('details').filter({has:page.locator('#dashReset')});
  if(await dashFilters.getAttribute('open')===null) await dashFilters.locator('summary').click();
  await page.locator('#dashReset').click({timeout:5000}); await page.waitForTimeout(1200);
  result.checks.dashboard_ui_text=(await page.locator('body').innerText()).slice(0,2500); result.checks.dashboard_map_markers=await page.locator('.leaflet-marker-icon').count();
  result.checks.dashboard_ui_total_matches_api=result.checks.dashboard_ui_text.includes('إجمالي الفرص\n276');
  await fs.promises.mkdir(path.join(out,'screenshots'),{recursive:true});
  await page.screenshot({path:path.join(out,'screenshots','identity-dashboard-1920x1080.png'),fullPage:true});
  for (const [width,height] of [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]]) {
   await page.setViewportSize({width,height}); await page.goto(base+'/?view=opportunities',{waitUntil:'networkidle',timeout:60000}); await page.waitForSelector('#opportunityRows tr');
   const v=await page.evaluate(()=>({width:innerWidth,document_width:document.documentElement.scrollWidth,body_width:document.body.scrollWidth,rtl:document.documentElement.dir==='rtl',rows:document.querySelectorAll('#opportunityRows tr').length,filter_count:[...document.querySelectorAll('select[aria-label^="تصفية حسب"]')].length}));
   v.no_horizontal_overflow=v.document_width<=width&&v.body_width<=width; result.viewports.push(v);
   if(width===1920) await page.screenshot({path:path.join(out,'screenshots','opportunities-1920x1080.png'),fullPage:false});
   if(width===390) await page.screenshot({path:path.join(out,'screenshots','opportunities-390x844.png'),fullPage:false});
  }
  result.checks.viewport_widths_passed=result.viewports.every(v=>v.no_horizontal_overflow&&v.rtl&&v.rows>0);
 } catch(e){result.errors.push(String(e.stack||e));}
 result.finished_at=new Date().toISOString(); await fs.promises.writeFile(path.join(out,'playwright-results.json'),JSON.stringify(result,null,2),'utf8'); await browser.close();
 if(result.errors.length){console.error(JSON.stringify(result,null,2));process.exit(1);} console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exit(1)});


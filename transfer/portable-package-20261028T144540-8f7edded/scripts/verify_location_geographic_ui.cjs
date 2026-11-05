const fs = require('fs');
const path = require('path');
const { chromium } = require('C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async () => {
  const out=path.resolve('docs/validation/data/location-geographic-eligibility');
  fs.mkdirSync(path.join(out,'screenshots'),{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
    const failures=[]; const responsive=[];
    await page.goto('http://localhost:8080/?view=opportunities',{waitUntil:'networkidle'});
    await page.waitForFunction(()=>document.querySelectorAll('#locationFilter option').length>1);
    const direction=await page.locator('html').getAttribute('dir');
    const options=await page.locator('#locationFilter option').evaluateAll(os=>os.map(o=>({value:o.value,label:o.textContent.trim()})));
    for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]]) {
      await page.setViewportSize({width,height}); await page.waitForTimeout(60);
      const x=await page.evaluate(()=>{const bar=document.querySelector('.filter-bar'),b=bar.getBoundingClientRect();const items=[...bar.querySelectorAll('input,select,button')].map(e=>{const r=e.getBoundingClientRect();return {id:e.id||e.getAttribute('aria-label')||e.className,left:r.left,right:r.right,width:r.width,height:r.height}});return {scrollWidth:document.documentElement.scrollWidth,items,out:items.filter(i=>i.left<b.left-1||i.right>b.right+1||i.width<=0||i.height<=0).map(i=>i.id)}});
      responsive.push({viewport:{width,height},scrollWidth:x.scrollWidth,controls:x.items.length,controlsOutside:x.out});
      if(x.scrollWidth>width)failures.push(`horizontal overflow ${width}x${height}`); if(x.out.length)failures.push(`control outside toolbar ${width}x${height}: ${x.out.join(',')}`);
    }
    await page.setViewportSize({width:1920,height:1080});
    const option=options.find(x=>x.label==='الأحساء'); if(!option)throw new Error('Al-Ahsa option missing');
    await page.locator('#locationFilter').selectOption(option.value);
    await page.waitForFunction(()=>document.querySelector('#tableCount')?.textContent.includes('260 فرصة'));
    const filterCount=await page.locator('#tableCount').innerText();
    const selector=page.locator('#view-opportunities .heading-actions a[href="/api/export.csv"]');
    const csv=await selector.elementHandle();
    await page.evaluate(el=>{el.addEventListener('click',e=>e.preventDefault(),{once:true,capture:true});el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}))},csv);
    const csvHref=await csv.getAttribute('href');
    const selector2=page.locator('#view-opportunities .heading-actions a[href="/api/export.xlsx"]');
    const xlsx=await selector2.elementHandle();
    await page.evaluate(el=>{el.addEventListener('click',e=>e.preventDefault(),{once:true,capture:true});el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}))},xlsx);
    const xlsxHref=await xlsx.getAttribute('href');
    if(!csvHref.includes(`location=${encodeURIComponent(option.value)}`))failures.push('CSV export does not preserve location filter');
    if(!xlsxHref.includes(`location=${encodeURIComponent(option.value)}`))failures.push('XLSX export does not preserve location filter');
    await page.screenshot({path:path.join(out,'screenshots','opportunities-location-filter-1920x1080.png'),fullPage:true});
    await page.locator('#searchInput').fill('44826');
    await page.waitForFunction(()=>document.querySelector('#tableCount')?.textContent.includes('1 من 1'));
    const searchCount=await page.locator('#opportunityRows tr').count();
    await page.locator('#opportunityRows [data-detail]').first().click();
    await page.waitForFunction(()=>document.querySelector('#modal')?.classList.contains('show'));
    const detailText=await page.locator('#modalBody').innerText(); const detail=detailText.includes('الأحساء') || detailText.includes('Al Ahsa');
    await page.locator('#modalClose').click();
    await page.locator('#searchInput').fill('');
    await page.locator('#nextPage').click();
    await page.waitForFunction(()=>document.querySelector('#pageSummary')?.textContent.includes('صفحة 2 من'));
    const page2=await page.locator('#pageSummary').innerText();
    await page.locator('#resetFilters').click();
    await page.waitForFunction(()=>document.querySelector('#tableCount')?.textContent.includes('291 فرصة'));
    await page.waitForFunction(()=>document.querySelector('#pageSummary')?.textContent.includes('صفحة 1 من'));
    const resetCount=await page.locator('#tableCount').innerText();
    if(direction!=='rtl')failures.push('RTL direction missing');
    const evidence={validated_at:new Date().toISOString(),direction,location_option:option,filter_count:filterCount,csv_href:csvHref,xlsx_href:xlsxHref,search_44826_rows:searchCount,detail_has_al_ahsa:detail,pagination_after_next:page2,reset_count:resetCount,responsive,failures};
    fs.writeFileSync(path.join(out,'screenshots','playwright-location-ui.json'),JSON.stringify(evidence,null,2),'utf8');
    console.log(JSON.stringify(evidence,null,2));
    if(!detail)failures.push('details omit Al-Ahsa location evidence'); if(failures.length)process.exitCode=2;
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});


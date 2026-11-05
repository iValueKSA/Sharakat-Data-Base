const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const root = path.resolve('docs/validation/deployment/nationwide-geographic-expansion/ui-evidence');
fs.mkdirSync(root, { recursive: true });
const executablePath = '/ms-playwright/chromium-1187/chrome-linux/chrome';
const results = { cases: [], errors: [], http5xx: [], screenshots: [], exports: [], observations: {} };
results.expectedAuth401 = 0;
const pass = (name, detail = '') => results.cases.push({ name, status: 'PASSED', detail });
const fail = (name, error) => results.cases.push({ name, status: 'FAILED', detail: String(error?.message || error) });
const check = (condition, message) => { if (!condition) throw new Error(message); };
const safe = value => String(value || '').replace(/[^\w .:@/-]/g, '?').slice(0, 200);

async function runCase(name, fn) {
  try { const detail = await fn(); pass(name, detail || ''); }
  catch (error) { fail(name, error); }
}

async function main() {
  const browser = await chromium.launch({ headless: true, executablePath, args: ['--no-sandbox'] });
  const context = await browser.newContext({ acceptDownloads: true, locale: 'ar-SA' });
  const page = await context.newPage();
  const cityOptionRequests=[];
  page.on('request', request=>{if(request.url().includes('/api/geography/options?level=city'))cityOptionRequests.push(request.url())});
  page.on('pageerror', error => results.errors.push(`pageerror:${safe(error.message)}`));
  page.on('console', message => { if (message.type() === 'error' && !/responded with a status of 401/.test(message.text())) results.errors.push(`console:${safe(message.text())}`); });
  page.on('response', response => {
    if (response.status() === 401 && response.url().includes('/api/auth/me')) results.expectedAuth401++;
    if (response.status() >= 500) results.http5xx.push(`${response.status()} ${response.url()}`);
  });
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/pN8AAAAASUVORK5CYII=', 'base64') }));

  async function login(base) {
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(600);
    const dialog = page.locator('#loginDialog');
    if (!await dialog.isVisible().catch(() => false)) await page.locator('#userButton').click();
    await page.waitForFunction(() => !!document.querySelector('#loginDialog')?.open, null, { timeout: 10000 });
    await page.locator('#loginEmail').fill('nwx-ui-test@example.invalid');
    await page.locator('#loginPassword').fill('TestOnlyAdminPassword_2026!');
    await page.locator('#loginForm button[type=submit]').click();
    await page.waitForFunction(() => !document.querySelector('#loginDialog')?.open, null, { timeout: 10000 });
    await page.waitForTimeout(250);
  }
  async function gotoView(view) {
    if (page.viewportSize().width <= 920 && !await page.locator(`[data-view="${view}"]`).first().isVisible()) {
      await page.locator('#sidebarToggle').click();
    }
    await page.locator(`[data-view="${view}"]`).first().evaluate(element => element.click());
    await page.waitForTimeout(500);
  }
  async function selectAndWait(id, value, apiPath = '/api/opportunities') {
    const before = page.waitForResponse(r => r.url().includes(apiPath) && r.request().method() === 'GET', { timeout: 2500 }).catch(() => null);
    await page.locator(`#${id}`).selectOption(value);
    await before;
    await page.waitForTimeout(180);
  }
  async function validateViewport(baseName, view, width, height, screenshotName) {
    await page.setViewportSize({ width, height });
    await gotoView(view);
    await page.waitForTimeout(350);
    const facts = await page.evaluate(() => ({
      rtl: document.documentElement.dir === 'rtl' || getComputedStyle(document.body).direction === 'rtl',
      width: innerWidth, documentWidth: document.documentElement.scrollWidth,
      overflow: document.documentElement.scrollWidth > innerWidth + 1,
      filterPanel: view === 'data-dashboard' ? '#dashNationalGeoFilters' : '#tableNationalGeoFilters',
      visibleControls: [...document.querySelectorAll(`${view === 'data-dashboard' ? '#dashNationalGeoFilters' : '#tableNationalGeoFilters'} select`)].filter(e => e.getClientRects().length).every(e => {
        const r=e.getBoundingClientRect(); return r.width > 0 && r.left >= -1 && r.right <= innerWidth + 1;
      }),
      noTextOverlap: (() => { const boxes=[...document.querySelectorAll(`${view === 'data-dashboard' ? '#dashNationalGeoFilters' : '#tableNationalGeoFilters'} label`)].filter(e=>e.getClientRects().length).map(e=>e.getBoundingClientRect());
        return boxes.every((a,i)=>boxes.slice(i+1).every(b=>a.right<=b.left+1||b.right<=a.left+1||a.bottom<=b.top+1||b.bottom<=a.top+1)); })(),
      mapWidth: document.querySelector('#rdOpportunityMap')?.getBoundingClientRect().width || 0,
      chartCount: document.querySelectorAll('#rdSectorChart > *,#rdStatusDonut > *').length,
    }));
    results.observations[`${width}x${height}`] = facts;
    if (screenshotName) {
      const target = path.join(root, screenshotName);
      await page.screenshot({ path: target, fullPage: false, animations: 'disabled' });
      results.screenshots.push(target);
    }
    check(facts.rtl, `${width}x${height}: RTL missing`);
    check(!facts.overflow, `${width}x${height}: horizontal overflow (${facts.documentWidth}px)`);
    check(facts.visibleControls, `${width}x${height}: dashboard geographic filter controls clipped`);
    check(facts.noTextOverlap, `${width}x${height}: geographic filter labels overlap`);
    return `RTL; width ${facts.width}/${facts.documentWidth}; controls in viewport; labels do not overlap`;
  }

  for (const [name, base, hasCity] of [['city-reference', 'http://host.docker.internal:18089', true], ['no-city-reference', 'http://host.docker.internal:18090', false]]) {
    const cityCallsAtStart=cityOptionRequests.length;
    await login(base);
    const catalog = await page.evaluate(async () => (await fetch('/api/geography/catalog')).json());
    check(catalog.national_ui_enabled && catalog.national_map_enabled && catalog.national_dashboard_enabled, `${name}: feature gates not enabled`);
    await runCase(`${name}:login-and-national-catalog`, () => Promise.resolve(`revision-specific isolated UI active; levels=${catalog.available_selector_levels.join(',')}`));
    await gotoView('opportunities');
    await page.waitForFunction(() => !document.querySelector('#tableNationalGeoFilters')?.hidden, null, { timeout: 8000 });
    const geography = page.locator('#tableGeographicFilter');
    check(await geography.isVisible(), `${name}: combined geography selector missing`);
    check((await geography.locator('option').first().textContent()).trim() === 'جميع المناطق', 'Geography default label mismatch');
    check(await geography.locator('optgroup[label="المناطق"] option').count() === 1, 'Expected positive-coverage Region choice');
    check(await geography.locator('optgroup[label="المحافظات"] option').count() === 2, 'Expected positive-coverage Governorate choices');
    await runCase(`${name}:combined-region-governorate-selector`, () => Promise.resolve('Single list selector shows reference-backed Regions and Governorates with positive unique-Master counts'));

    await selectAndWait('tableGeographicFilter', 'governorate|TEST_GOV_01');
    check(new URL(page.url()).searchParams.get('governorate_id') === 'TEST_GOV_01', 'Governorate selection did not preserve canonical ID in URL');
    check(!new URL(page.url()).searchParams.has('region_id'), 'Governorate selection also applied parent Region filter');
    const govCount = await page.evaluate(async () => (await (await fetch('/api/opportunities?governorate_id=TEST_GOV_01&limit=1')).json()).total);
    await selectAndWait('sectorFilter', 'TEST_SECTOR_A');
    check(Number((await page.locator('#tableCount').textContent()).match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',','') || 0) > 0, 'Geography + sector returned no rows');
    await runCase(`${name}:governorate-id-and-composed-filter`, () => Promise.resolve(`Canonical governorate ID retained; governorate total=${govCount}; sector composition returned rows`));

    await page.locator('#searchInput').fill('فرصة اختبار اصطناعية 001');
    await page.waitForTimeout(450);
    const search = await page.evaluate(async () => (await (await fetch('/api/opportunities?q=001&governorate_id=TEST_GOV_01&limit=500')).json()).total);
    check(search === 1, 'Search + geography did not return exact matching Master');
    await runCase(`${name}:search-and-geography-composition`, () => Promise.resolve(`Search + governorate returned ${search} unique Master`));

    await page.locator('#resetFilters').click();
    await page.waitForTimeout(250);
    await geography.selectOption('region|TEST_REGION_01');
    await page.waitForTimeout(250);
    const selectedCount = await page.evaluate(async () => (await (await fetch('/api/opportunities?region_id=TEST_REGION_01&limit=1')).json()).total);
    const next = page.locator('#nextPage');
    if (await next.isEnabled()) { await next.click(); await page.waitForTimeout(250); }
    check(new URL(page.url()).searchParams.get('region_id') === 'TEST_REGION_01', 'URL did not preserve Region filter');
    await runCase(`${name}:pagination-url-and-filter-state`, () => Promise.resolve(`filtered total ${selectedCount}; URL kept region_id`));
    await page.locator('#resetFilters').click();
    await page.waitForTimeout(250);
    check(await geography.inputValue() === '', 'Reset did not clear geography selection');
    await runCase(`${name}:reset-defaults`, () => Promise.resolve('Geographic selector reset to all'));

    const exportCases = [
      { label: 'region', selection: 'region|TEST_REGION_01', key: 'region_id', id: 'TEST_REGION_01' },
      { label: 'governorate', selection: 'governorate|TEST_GOV_01', key: 'governorate_id', id: 'TEST_GOV_01' },
    ];
    for (const exp of exportCases) {
      await page.locator('#resetFilters').click(); await page.waitForTimeout(120);
      await selectAndWait('tableGeographicFilter', exp.selection);
      const uiTotal = Number((await page.locator('#tableCount').textContent()).match(/من\s+([\d,]+)/)?.[1]?.replaceAll(',','') || 0);
      const params = new URLSearchParams({ [exp.key]: exp.id, limit: '1' });
      const apiTotal = await page.evaluate(async q => (await (await fetch(`/api/opportunities?${q}`)).json()).total, params.toString());
      const csv = page.locator('#view-opportunities a[href^="/api/export.csv"]').first();
      const csvPromise = page.waitForEvent('download', { timeout: 10000 }); await csv.click({ force: true });
      const csvDownload = await csvPromise; const csvPath = path.join(root, `${name}-export-${exp.label}.csv`); await csvDownload.saveAs(csvPath);
      const xlsx = page.locator('#view-opportunities a[href^="/api/export.xlsx"]').first();
      const xlsxPromise = page.waitForEvent('download', { timeout: 10000 }); await xlsx.click({ force: true });
      const xlsxDownload = await xlsxPromise; const xlsxPath = path.join(root, `${name}-export-${exp.label}.xlsx`); await xlsxDownload.saveAs(xlsxPath);
      results.exports.push({ variant: name, filter: exp.label, uiTotal, apiTotal, csvPath, xlsxPath });
      check(uiTotal === apiTotal, `${name} ${exp.label}: UI count ${uiTotal} != API ${apiTotal}`);
    }
    await runCase(`${name}:csv-xlsx-browser-downloads`, () => Promise.resolve('Region and Governorate CSV/XLSX files downloaded from the filtered Opportunities UI; UI/API totals recorded'));
    await runCase(`${name}:sorting-preserves-filters`, async () => {
      await selectAndWait('tableGeographicFilter', 'governorate|TEST_GOV_01');
      await selectAndWait('statusFilter', 'متاحة');
      const sortButton=page.locator('#view-opportunities [data-sort-key="title"]');
      await sortButton.click({force:true}); await page.waitForTimeout(400);
      const current=new URL(page.url()).searchParams;
      const statusValue=await page.locator('#statusFilter').inputValue();
      check(current.get('governorate_id')==='TEST_GOV_01' && !current.has('region_id') && current.get('status')===statusValue, `Sorting dropped active geography/status filters: ${page.url()}`);
      check(current.get('sort_by')==='title' && current.get('sort_order')==='asc', 'Sort state missing from URL');
      const sorted=await page.evaluate(async()=>{const p=new URLSearchParams(location.search);p.set('limit','3');const r=await fetch(`/api/opportunities?${p}`);return await r.json()});
      check(sorted.total>0 && sorted.items[0].title.includes('001'), 'Sorted API results did not apply ascending title order');
      return 'Title sort applied and preserved Governorate and Status URL filters';
    });

    await gotoView('data-dashboard');
    await page.waitForTimeout(1000);
    const summaryResponse = await page.evaluate(async () => {
      const r=await fetch('/api/data-dashboard/geography-summary?q=TEST'); return {status:r.status,body:r.ok?await r.json():await r.text()};
    });
    check(summaryResponse.status === 200, `${name}: national dashboard summary unavailable`);
    check(summaryResponse.body.unique_master_total === 60, `${name}: unique Master total mismatch`);
    check(summaryResponse.body.mapped_unique_masters >= 2, `${name}: expected mapped synthetic Masters`);
    check(summaryResponse.body.membership_counts_are_non_additive, `${name}: membership count not labeled non-additive`);
    check(summaryResponse.body.scope_counts.NATIONWIDE === 1 && summaryResponse.body.scope_counts.UNSPECIFIED === 1,
      `${name}: nationwide/unspecified scope semantics mismatch`);
    await runCase(`${name}:national-dashboard-master-and-scope-semantics`, () => Promise.resolve(`unique=${summaryResponse.body.unique_master_total}; source rows=61; mapped=${summaryResponse.body.mapped_unique_masters}; nationwide=${summaryResponse.body.scope_counts.NATIONWIDE}; unspecified=${summaryResponse.body.scope_counts.UNSPECIFIED}`));
    await runCase(`${name}:national-map-follows-region-filter`, async () => {
      const mapPromise=page.waitForResponse(r=>r.url().includes('/api/data-dashboard/geography?')&&r.request().method()==='GET',{timeout:8000});
      await page.locator('#dashRegionFilter').selectOption('TEST_REGION_01');
      const mapResult=await (await mapPromise).json();
      const tableResult=await page.evaluate(async()=>{const p=new URLSearchParams(location.search);p.set('q','TEST');p.set('limit','1');const r=await fetch(`/api/opportunities?${p}`);return await r.json()});
      check(mapResult.map_scope==='NATIONAL'&&mapResult.counts.total===tableResult.total,`Filtered map and table totals diverged: map=${mapResult.counts.total}; table=${tableResult.total}; URL=${page.url()}`);
      return `filtered table/map Master totals=${tableResult.total}; URL region=${new URL(page.url()).searchParams.get('region_id')}`;
    });
    await page.goto(`${new URL(page.url()).origin}/?view=data-dashboard`,{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.querySelector('#rdOpportunityMap')&&document.querySelector('#dashRegionFilter'),null,{timeout:10000});
    await page.waitForTimeout(900);
    await runCase(`${name}:map-popup-list-and-opportunity-detail`, async () => {
      let popupButton=page.locator('#rdOpportunityMap [data-map-open]').first();
      for(let attempt=0;attempt<14&&await popupButton.count()===0;attempt++){
        const icons=page.locator('#rdOpportunityMap .leaflet-marker-icon');
        check(await icons.count()>0,'No map marker or cluster was available to open');
        await icons.last().click({force:true}); await page.waitForTimeout(250);
      }
      check(await popupButton.count()>0,'Map marker popup did not expose its filtered-opportunities link');
      const ids=await popupButton.getAttribute('data-map-open');
      check(ids,'Map popup had no Master IDs');
      const opportunityResponse=page.waitForResponse(r=>r.url().includes('/api/opportunities?')&&new URL(r.url()).searchParams.get('map_ids')===ids,{timeout:15000});
      await popupButton.click({force:true}); await opportunityResponse;
      const params=new URL(page.url()).searchParams;
      check(params.get('map_ids')===ids,'Map popup navigation IDs did not match marker IDs');
      const detail=page.locator('#opportunityRows [data-detail]').first();
      await page.waitForFunction(() => document.querySelectorAll('#opportunityRows [data-detail]').length>0, null, {timeout:10000}).catch(()=>{});
      check(await detail.count()>0,`Map popup destination table had no opportunity detail control: ${page.url()}`);
      await detail.click({force:true}); await page.waitForTimeout(350);
      check(await page.locator('#modal.show').count()>0,'Opportunity detail did not open from map-filtered table');
      await page.locator('#modalClose').click({force:true});
      return `Popup Master IDs ${ids}; detail opened from matching table row`;
    });
    await gotoView('data-dashboard');
    await runCase(`${name}:national-dashboard-drilldown`, async () => {
      const regionButton=page.locator('#nationalGeoSummaryValues [data-national-geo-filter="region"]').first();
      check(await regionButton.count()>0,'No dashboard region drilldown control rendered');
      await regionButton.click({force:true}); await page.waitForTimeout(500);
      const params=new URL(page.url()).searchParams;
      check(params.get('view')==='opportunities'&&params.get('region_id')==='TEST_REGION_01','Region drilldown did not navigate with the reference ID');
      return 'Region summary button opened Opportunities with TEST_REGION_01 filter';
    });
    await gotoView('data-dashboard');
    const mapResponse = await page.evaluate(async () => { const r=await fetch('/api/data-dashboard/geography?q=TEST'); return {status:r.status,body:r.ok?await r.json():await r.text()}; });
    check(mapResponse.status === 200 && mapResponse.body.map_scope === 'NATIONAL', `${name}: national map contract unavailable`);
    check(mapResponse.body.counts.total === 60, `${name}: map/table universe mismatch`);
    check(mapResponse.body.points.length > 0 && mapResponse.body.points.length < 60, `${name}: invalid marker count`);
    const ids = mapResponse.body.points.flatMap(p => p.ids);
    check(new Set(ids).size === 2 && ids.length === 3, `${name}: expected two mapped Masters represented by three marker memberships`);
    const allScopeRows = await page.evaluate(async () => {
      const results={}; for (const s of ['NATIONWIDE','REGION_WIDE','UNSPECIFIED','SPECIFIC_LOCATION','MULTIPLE_VERIFIED_LOCATIONS']) {
        const r=await fetch(`/api/opportunities?geographic_scope=${s}&limit=500`); results[s]=(await r.json()).total;
      } return results;
    });
    check(allScopeRows.NATIONWIDE === 1 && allScopeRows.UNSPECIFIED === 1 && allScopeRows.REGION_WIDE === 1,
      `${name}: scope filter counts wrong`);
    await runCase(`${name}:national-map-excludes-broad-scope-and-has-points`, () => Promise.resolve(`points=${mapResponse.body.points.length}; mapped Masters=${ids.length}; scopes=${JSON.stringify(allScopeRows)}`));

    await page.locator('#rdOpportunityMap').scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);
    const mapMarkers = await page.locator('#rdOpportunityMap .leaflet-marker-icon').count().catch(() => 0);
    const clusters = await page.locator('#rdOpportunityMap .marker-cluster').count().catch(() => 0);
    results.observations[`${name}:map-render`] = { mapMarkers, clusters };
    if (mapMarkers + clusters > 0) await runCase(`${name}:leaflet-map-renders-markers-or-clusters`, () => Promise.resolve(`markers=${mapMarkers}; clusters=${clusters}`));
    else await runCase(`${name}:leaflet-map-renders-markers-or-clusters`, () => { check(false, 'No Leaflet markers or clusters in rendered map'); });
    const title = await page.locator('#rdMapTitle').textContent().catch(() => '');
    results.observations[`${name}:map-title`] = title;
    await runCase(`${name}:map-title-reflects-current-scope`, () => { check((title || '').includes('الوطنية'), `Map title is not dynamic for national scope: ${title}`); });

    for (const spec of [
      [1920,1080,`${name}-dashboard-1920x1080.png`], [1440,900,null], [1366,768,`${name}-dashboard-1366x768.png`],
      [768,900,null], [390,844,`${name}-dashboard-390x844.png`],
    ]) await runCase(`${name}:viewport-${spec[0]}x${spec[1]}`, () => validateViewport(name,'data-dashboard',spec[0],spec[1],spec[2]));
    for (const spec of [
      [1920,1080,`${name}-opportunities-1920x1080.png`], [1440,900,`${name}-opportunities-1440x900.png`],
      [1366,768,`${name}-opportunities-1366x768.png`], [768,900,`${name}-opportunities-768x900.png`],
      [390,844,`${name}-opportunities-390x844.png`],
    ])
      await runCase(`${name}:opportunities-viewport-${spec[0]}x${spec[1]}`, () => validateViewport(name,'opportunities',spec[0],spec[1],spec[2]));
    await runCase(`${name}:viewport-map-1920x1080`, async () => {
      await page.setViewportSize({width:1920,height:1080}); await gotoView('data-dashboard'); await page.locator('#rdOpportunityMap').scrollIntoViewIfNeeded(); await page.waitForTimeout(250);
      const target=path.join(root,`${name}-map-1920x1080.png`); await page.screenshot({path:target,animations:'disabled'}); results.screenshots.push(target); return 'map card captured at desktop viewport';
    });
    await runCase(`${name}:viewport-map-390x844`, async () => {
      await page.setViewportSize({width:390,height:844}); await gotoView('data-dashboard'); await page.locator('#rdOpportunityMap').scrollIntoViewIfNeeded(); await page.waitForTimeout(250);
      const target=path.join(root,`${name}-map-390x844.png`); await page.locator('#rdOpportunityMap').screenshot({path:target}); results.screenshots.push(target); return 'map canvas captured';
    });
  }
  results.errorCount = results.errors.length;
  results.http5xxCount = results.http5xx.length;
  await fs.promises.writeFile(path.join(root,'browser-results.json'), JSON.stringify(results,null,2));
  await browser.close();
  console.log(JSON.stringify({cases:results.cases, errors:results.errors, http5xx:results.http5xx, screenshots:results.screenshots},null,2));
}

main().catch(error => { console.error(error.stack || error); process.exit(1); });

const fs = require('fs');
const path = require('path');
const { chromium } = require('./pilot-playwright/node_modules/playwright-core');

(async () => {
  const browser = await chromium.launch({ headless:true, executablePath:'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' });
  const page = await browser.newPage({ viewport:{width:1920,height:1080} });
  const errors = [], blockedWrites = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('**/api/**', async route => {
    if (route.request().method() !== 'GET') {
      blockedWrites.push({method:route.request().method(),url:route.request().url()});
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true})});
    }
    return route.continue();
  });
  await page.goto('http://localhost:8080', {waitUntil:'networkidle'});
  await page.evaluate(() => { state.user={role:'analyst',display_name:'Analyst QA'}; applyRoleVisibility(); });
  await page.locator('.nav-item[data-view="review"]').click();
  await page.waitForSelector('#pilotStartButton');
  await page.locator('#pilotStartButton').click();
  await page.waitForFunction(() => document.querySelector('#pilotPosition')?.textContent.includes('الحالة 1 من 20') && document.querySelector('#reviewQueueList [data-review-key]')?.dataset.reviewKey === 'duplicate:32');
  await page.locator('[data-review-key="duplicate:32"]').waitFor({state:'visible'});
  const sizes=[[1920,1080],[1440,900],[1366,768],[768,900],[390,844]];
  const screenshots='docs/validation/ui/human-review-pilot/pilot-api-fix/screenshots';
  fs.mkdirSync(screenshots,{recursive:true});
  const viewports=[];
  for (const [width,height] of sizes) {
    await page.setViewportSize({width,height});
    await page.waitForTimeout(100);
    const state = await page.evaluate(() => ({
      width:innerWidth,height:innerHeight,
      rtl:getComputedStyle(document.documentElement).direction==='rtl',
      horizontal_overflow:Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)>document.documentElement.clientWidth,
      review_queue_active:document.querySelector('.nav-item[data-view="review"]')?.classList.contains('active'),
      pilot_mode_active:!document.querySelector('#pilotExitButton')?.hidden,
      phase_a_status:document.querySelector('#pilotStatus')?.innerText.includes('المرحلة أ'),
      position:document.querySelector('#pilotPosition')?.innerText,
      first_case_key:document.querySelector('#reviewQueueList [data-review-key]')?.dataset.reviewKey,
      visible_queue_count:document.querySelectorAll('#reviewQueueList [data-review-key]').length,
      phase_b_review_control_hidden:document.querySelector('#pilotPhaseReview')?.hidden===true,
      current_phase:reviewWorkbench.pilot?.current_phase||null,
      active_case_phases:[...new Set((reviewWorkbench.pilot?.cases||[]).map(x=>x.phase))],
      phase_b_case_references:(reviewWorkbench.pilot?.case_references||[]).filter(x=>x.phase==='B').length,
    }));
    state.passed=state.rtl&&!state.horizontal_overflow&&state.review_queue_active&&state.pilot_mode_active&&
      state.phase_a_status&&state.position==='الحالة 1 من 20 · المرحلة أ'&&state.first_case_key==='duplicate:32'&&
      state.visible_queue_count===20&&state.phase_b_review_control_hidden&&state.current_phase==='A'&&
      state.active_case_phases.every(x=>x==='A')&&state.phase_b_case_references===0;
    viewports.push(state);
    await page.screenshot({path:path.join(screenshots,`pilot-entry-${width}x${height}.png`),fullPage:true});
  }
  const report={status:viewports.every(v=>v.passed)&&errors.length===0?'PASSED':'FAILED',
    navigation:'Review Queue -> Pilot Mode -> Phase A -> Case 1 of 20',
    first_case_key:'duplicate:32',phase_b_inaccessible:true,phase_b_review_control_visible:false,
    api_write_requests_sent_to_server:0,api_write_requests_intercepted:blockedWrites,
    javascript_errors:errors,viewports};
  fs.writeFileSync('docs/validation/ui/human-review-pilot/pilot-api-fix/playwright-results.json',JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({status:report.status,navigation:report.navigation,all_viewports_passed:viewports.every(v=>v.passed),viewports:viewports.length,javascript_errors:errors,api_write_requests_sent_to_server:0,intercepted_write_count:blockedWrites.length}));
  await browser.close();
  if(report.status!=='PASSED')process.exitCode=1;
})().catch(error=>{console.error(error.stack||error);process.exit(1);});

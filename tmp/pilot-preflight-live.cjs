const fs=require('fs'),path=require('path'),{chromium}=require('playwright-core');
(async()=>{
 const creds=fs.readFileSync(path.join(process.cwd(),'Local Admin Credentials.txt'),'utf8'),email=creds.match(/^Email:\s*(.+)$/m)?.[1]?.trim(),password=creds.match(/^Password:\s*(.+)$/m)?.[1]?.trim();
 const browser=await chromium.launch({headless:true,executablePath:'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'}),page=await browser.newPage();
 await page.goto('http://127.0.0.1:8080',{waitUntil:'networkidle'});await page.locator('#userButton').click();await page.locator('#loginEmail').fill(email);await page.locator('#loginPassword').fill(password);await page.locator('#loginForm button[type=submit]').click();await page.waitForFunction(()=>document.querySelector('#loginDialog')?.open===false);
 const snapshot=await page.evaluate(async()=>{
  const [qr,sr,jr,pr]=await Promise.all([fetch('/api/admin/review-queue?status=OPEN&limit=1000&disposition=ALL'),fetch('/api/admin/system-status'),fetch('/api/admin/jobs'),fetch('/api/admin/review-workbench/pilot')]);
  const [rows,system,jobs,pilot]=await Promise.all([qr.json(),sr.json(),jr.json(),pr.json()]);
  const open=rows.filter(r=>r.status==='OPEN'),actionable=open.filter(r=>r.disposition!=='SOURCE_RECHECK_REQUIRED');
  const count=(key,fn)=>Object.fromEntries([...new Set(open.map(fn))].sort().map(k=>[k,open.filter(r=>fn(r)===k).length]));
  const byPriority=Object.fromEntries(['P1','P2','P3','P4'].map(k=>[k,open.filter(r=>r.priority===k).length]));
  const byType=count('domain',r=>r.domain||'UNKNOWN');
  const bySubtype=count('subtype',r=>r.field||r.reason_key||'UNSPECIFIED');
  const bySource=count('source',r=>r.source||'SOURCE_NOT_ATTACHED_TO_REVIEW');
  const active=jobs.filter(j=>['QUEUED','RUNNING','RETRYING'].includes(String(j.job_state||'').toUpperCase()));
  return {captured_at:new Date().toISOString(),read_only:true,open_reviews_total:open.length,human_review_required:actionable.length,source_recheck_required:open.length-actionable.length,open_by_priority:byPriority,open_by_type:byType,open_by_subtype:bySubtype,open_by_source:bySource,sync_jobs_total:system.sync_jobs,active_sync_jobs_observed:active.length,active_sync_jobs_observation_window:jobs.length,latest_jobs_returned:jobs.length,pilot_started:pilot.started,pilot_event_count:pilot.events.length,pilot_case_count:pilot.cases.length,pilot_phase_counts:pilot.phase_counts};
 });
 fs.writeFileSync('docs/validation/ui/human-review-pilot/pilot-preflight-snapshot.json',JSON.stringify(snapshot,null,2)+'\n');
 console.log(JSON.stringify(snapshot));await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});

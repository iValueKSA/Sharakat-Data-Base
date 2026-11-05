const {chromium}=require('./pilot-playwright/node_modules/playwright-core');
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--no-sandbox']});
 const p=await b.newPage(); const rs=[];
 p.on('response',async r=>{const ct=r.headers()['content-type']||'';const q=r.request();const x={status:r.status(),url:r.url(),method:q.method(),type:q.resourceType(),ct};if(/json/i.test(ct)){try{x.body=(await r.text()).slice(0,500000)}catch{}}rs.push(x)});
 const url='https://invest.rcjy.gov.sa/InvestmentPortal/InvestmentOpportunities';
 const resp=await p.goto(url,{waitUntil:'domcontentloaded',timeout:45000});await p.waitForTimeout(8000);
 const dom=await p.evaluate(()=>({title:document.title,text:(document.body?.innerText||'').slice(0,22000),links:[...document.querySelectorAll('a[href]')].map(a=>({t:(a.innerText||'').trim(),href:a.href})).filter(a=>a.t||/opportun|detail|city|search/i.test(a.href)).slice(0,300),forms:[...document.forms].map(f=>({action:f.action,method:f.method,fields:[...f.elements].map(e=>({name:e.name,id:e.id,type:e.type,value:e.value})).slice(0,80)}))}));
 require('fs').writeFileSync('tmp/rcjy_investment_portal_probe.json',JSON.stringify({status:resp.status(),url:p.url(),dom,responses:rs},null,2));
 console.log(JSON.stringify({status:resp.status(),url:p.url(),title:dom.title,text:dom.text.slice(0,5000),links:dom.links.slice(0,60),responses:rs.map(x=>({status:x.status,url:x.url,method:x.method,type:x.type,ct:x.ct,body:x.body?.slice(0,14000)}))},null,2)); await b.close();
})().catch(e=>{console.error(e);process.exit(1)});

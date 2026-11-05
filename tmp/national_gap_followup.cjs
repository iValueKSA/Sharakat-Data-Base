const {chromium}=require('./pilot-playwright/node_modules/playwright-core');
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--no-sandbox']});
 const out={};
 const cases=[
  ['ncp-root','https://investors.ncp.gov.sa/'],['ncp-home','https://investors.ncp.gov.sa/home'],
  ['rcjy-opps','https://www.rcjy.gov.sa/investment-opportunities'],['rcjy-investment','https://www.rcjy.gov.sa/en/web/guest/investmentrc'],
  ['tourism-app','https://tourism.sa/en/'],['rcu-en','https://eservices.rcu.gov.sa/en/opportunities']
 ];
 for(const [k,url] of cases){const p=await b.newPage({ignoreHTTPSErrors:true});const rs=[];p.on('response',async r=>{let e={s:r.status(),u:r.url(),t:r.request().resourceType(),ct:r.headers()['content-type']};if(/json/i.test(e.ct||'')){try{e.body=(await r.text()).slice(0,30000)}catch{}}rs.push(e)});let nav={};try{let r=await p.goto(url,{waitUntil:'domcontentloaded',timeout:50000});nav={s:r.status(),u:p.url()};await p.waitForTimeout(6500);const dom=await p.evaluate(()=>({title:document.title,text:(document.body?.innerText||'').slice(0,15000),links:[...document.querySelectorAll('a[href]')].map(a=>({t:(a.innerText||'').trim().slice(0,120),u:a.href})).filter(x=>x.t||/opportun|investment|project|map/i.test(x.u)).slice(0,250),scripts:[...document.scripts].map(s=>s.src).filter(Boolean)}));
   if(k.startsWith('ncp')){dom.quickApi=await p.evaluate(async()=>{let cfg=await(await fetch('/assets/config.prod.json')).json();let paths=['/swagger/v1/swagger.json','/swagger/index.html','/openapi.json','/api-docs','/api/v1','/api/v1/projects?pageNumber=1&pageSize=12','/api/v1/projects?PageNumber=1&PageSize=12','/api/v1/opportunities?pageNumber=1&pageSize=12','/api/v1/public/projects?pageNumber=1&pageSize=12'];let ans=[];for(let path of paths){try{let r=await fetch(cfg.apiBaseUrl.replace(/\/$/,'')+path.replace(/^\/api\/v1/,''));let t=await r.text();ans.push({path,s:r.status,ct:r.headers.get('content-type'),body:t.slice(0,1000)})}catch(e){ans.push({path,e:String(e)})}}return {base:cfg.apiBaseUrl,ans}})}
   if(k==='rcu-en'){dom.api=await p.evaluate(async()=>{let r=await fetch('/api/investment-opportunities/list?Page.Size=100&Page.Index=1');let t=await r.text();return{s:r.status,body:t.slice(0,50000)}})}
   out[k]={nav,dom,responses:rs};
  }catch(e){out[k]={nav,error:String(e),responses:rs}}await p.close()}
 await b.close();require('fs').writeFileSync('tmp/national_gap_followup.json',JSON.stringify(out,null,2));
 for(const [k,v] of Object.entries(out)){console.log('\n=='+k,JSON.stringify(v.nav));console.log((v.dom?.title||'')+'\n'+(v.dom?.text||'').slice(0,2500));console.log('LINKS '+JSON.stringify(v.dom?.links?.filter(x=>/opportun|investment|project|map|تفاصيل|فرص|منافس/i.test(x.t+' '+x.u)).slice(0,30)));if(v.dom?.quickApi)console.log('NCP_API '+JSON.stringify(v.dom.quickApi));if(v.dom?.api)console.log('RCU_API '+JSON.stringify(v.dom.api).slice(0,6000));console.log('RESP '+JSON.stringify(v.responses.filter(x=>['xhr','fetch'].includes(x.t)||/api|graphql|map/i.test(x.u)).map(x=>({s:x.s,t:x.t,u:x.u,body:x.body?.slice(0,500)})).slice(0,35)))}
})().catch(e=>{console.error(e);process.exit(1)});

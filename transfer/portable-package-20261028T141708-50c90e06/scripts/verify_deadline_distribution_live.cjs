const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const fs = require("fs");
const path = require("path");

const base = "http://localhost:8080";
const out = path.resolve("docs/validation/ui/deadline-card-full-reconciliation");
const viewports = [[1920,1080],[1440,900],[1366,768],[768,900],[390,844]];
const expectedLabels = ["خلال 7 أيام","8–14 يومًا","15–30 يومًا","أكثر من 30 يومًا","بدون موعد محدد"];
const expectedColors = ["#378aa4","#006e61","#c39853","#7953a9","#989899"];
const assert = (value, message) => { if (!value) throw new Error(message); };

(async () => {
  fs.mkdirSync(path.join(out,"screenshots"),{recursive:true});
  const browser = await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  const jsErrors = [], httpErrors = [], expectedAuth401 = [];
  page.on("pageerror",error=>jsErrors.push(error.message));
  page.on("response",response=>{if(response.status()===401&&new URL(response.url()).pathname==="/api/auth/me")expectedAuth401.push({status:401,url:response.url(),reason:"Visitor session check; dashboard is public."});else if(response.status()>=400)httpErrors.push({status:response.status(),url:response.url()});});
  const result = {started_at:new Date().toISOString(),base_url:base,viewports:[],screenshots:[],clickthrough:null,js_errors:jsErrors,http_errors:httpErrors,expected_auth_401:expectedAuth401};
  try {
    for (const [width,height] of viewports) {
      await page.setViewportSize({width,height});
      await page.goto(`${base}/?view=data-dashboard`,{waitUntil:"networkidle"});
      await page.locator("#rdDeadlineCard").waitFor({state:"visible",timeout:30000});
      await page.waitForFunction(()=>document.querySelectorAll("#rdDeadlineBuckets [data-deadline-bucket]").length===5);
      const state = await page.evaluate(()=>{
        const card=document.querySelector("#rdDeadlineCard"), buttons=[...document.querySelectorAll("#rdDeadlineBuckets [data-deadline-bucket]")];
        const labels=buttons.map(button=>button.querySelector("small")?.textContent?.trim()||"");
        const counts=buttons.map(button=>Number(button.querySelector("b")?.textContent?.replaceAll(",","")||0));
        const colors=buttons.map(button=>getComputedStyle(button).getPropertyValue("--rd-deadline-color").trim().toLowerCase());
        const total=Number(document.querySelector("#rdDeadlineTotal")?.textContent?.replaceAll(",","")||0);
        const cardRect=card.getBoundingClientRect();
        return {labels,counts,colors,total,activeLabel:document.querySelector("#rdActiveValue")?.textContent?.trim(),direction:document.documentElement.dir,scrollWidth:document.documentElement.scrollWidth,innerWidth,cardWidth:cardRect.width,cardHeight:cardRect.height,allButtonsVisible:buttons.every(button=>{const r=button.getBoundingClientRect();return r.width>0&&r.height>0&&r.left>=0&&r.right<=innerWidth+1;})};
      });
      const categoryOK=JSON.stringify(state.labels)===JSON.stringify(expectedLabels);
      const colorsOK=JSON.stringify(state.colors)===JSON.stringify(expectedColors);
      const activeTotal=Number(state.activeLabel?.replaceAll(",",""));
      const passed=categoryOK&&colorsOK&&state.counts.reduce((a,b)=>a+b,0)===state.total&&state.total===activeTotal&&state.direction==="rtl"&&state.scrollWidth<=width&&state.allButtonsVisible;
      assert(passed,`Viewport ${width}x${height} failed: ${JSON.stringify(state)}`);
      const screenshot=[1920,1366,390].includes(width)?path.join(out,"screenshots",`deadline-card-${width}x${height}.png`):null;
      if(screenshot){await page.locator("#rdDeadlineCard").screenshot({path:screenshot});result.screenshots.push(screenshot);}
      result.viewports.push({width,height,status:passed?"PASSED":"FAILED",...state,visible_category_labels:categoryOK,five_distinct_expected_colors:colorsOK,horizontal_overflow:state.scrollWidth>width});
    }
    await page.locator('#rdDeadlineBuckets [data-deadline-bucket="no_deadline"]').click();
    await page.waitForFunction(()=>new URLSearchParams(location.search).get("deadline_status")==="without_reliable_deadline");
    await page.waitForFunction(()=>document.querySelector("#view-opportunities")?.classList.contains("visible"),null,{timeout:15000});
    await page.waitForFunction(()=>document.querySelector("#tableCount")?.textContent?.includes("370")&&document.querySelector("#lifecycleFilter")?.value==="active",null,{timeout:30000});
    const click = await page.evaluate(()=>({url:location.href,viewVisible:document.querySelector("#view-opportunities")?.classList.contains("visible"),count:document.querySelector("#tableCount")?.textContent?.trim(),activeFilter:document.querySelector("#lifecycleFilter")?.value}));
    click.passed=click.url.includes("deadline_status=without_reliable_deadline")&&click.viewVisible&&click.count.includes("370")&&click.activeFilter==="active";
    assert(click.passed,`No deadline click-through failed: ${JSON.stringify(click)}`);
    result.clickthrough=click;
    result.status=jsErrors.length===0&&httpErrors.length===0?"PASSED":"FAILED";
    assert(result.status==="PASSED",`Browser errors: ${JSON.stringify({jsErrors,httpErrors})}`);
    fs.writeFileSync(path.join(out,"deadline-card-playwright.json"),JSON.stringify(result,null,2),"utf8");
    console.log(JSON.stringify({status:result.status,viewports:result.viewports.map(({width,height,status})=>({width,height,status})),clickthrough:result.clickthrough,js_errors:jsErrors.length,http_errors:httpErrors.length,screenshots:result.screenshots},null,2));
  } catch(error) {
    result.status="FAILED";result.failure=error.message;
    fs.writeFileSync(path.join(out,"deadline-card-playwright.json"),JSON.stringify(result,null,2),"utf8");
    throw error;
  } finally { await browser.close(); }
})();

const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const fs = require("fs");
const path = require("path");

const base = "http://localhost:8080";
const out = path.resolve("docs/validation/ui/deadline-card-single-row");
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
  page.on("response",response=>{if(response.status()===401&&new URL(response.url()).pathname==="/api/auth/me")expectedAuth401.push({status:401,url:response.url()});else if(response.status()>=400)httpErrors.push({status:response.status(),url:response.url()});});
  const result = {started_at:new Date().toISOString(),base_url:base,viewports:[],screenshots:[],js_errors:jsErrors,http_errors:httpErrors,expected_auth_401:expectedAuth401};
  try {
    for (const [width,height] of viewports) {
      await page.setViewportSize({width,height});
      await page.goto(`${base}/?view=data-dashboard`,{waitUntil:"networkidle"});
      await page.locator("#rdDeadlineCard").waitFor({state:"visible",timeout:30000});
      await page.waitForFunction(()=>document.querySelectorAll("#rdDeadlineBuckets [data-deadline-bucket]").length===5);
      const state=await page.evaluate(()=>{
        const card=document.querySelector("#rdDeadlineCard"),host=document.querySelector("#rdDeadlineBuckets"),buttons=[...host.querySelectorAll("[data-deadline-bucket]")];
        const rects=buttons.map(button=>button.getBoundingClientRect());
        const labelRects=buttons.map(button=>button.querySelector("small").getBoundingClientRect());
        const bars=buttons.map(button=>button.querySelector(".rd-deadline-bar").getBoundingClientRect());
        const template=getComputedStyle(host).gridTemplateColumns;
        const rowTops=[...new Set(rects.map(rect=>Math.round(rect.top)))];
        const widthValues=rects.map(rect=>Math.round(rect.width*10)/10);
        const hostRect=host.getBoundingClientRect(),cardRect=card.getBoundingClientRect();
        return {title:card.querySelector("small")?.textContent?.trim(),labels:buttons.map(button=>button.querySelector("small")?.textContent?.trim()),counts:buttons.map(button=>Number(button.querySelector("b")?.textContent?.replaceAll(",","")||0)),colors:buttons.map(button=>getComputedStyle(button).getPropertyValue("--rd-deadline-color").trim().toLowerCase()),cardTotal:Number(document.querySelector("#rdDeadlineTotal")?.textContent?.replaceAll(",","")||0),activeTotal:Number(document.querySelector("#rdActiveValue")?.textContent?.replaceAll(",","")||0),layoutMode:getComputedStyle(host).display,gridTemplateColumns:template,rowTops,columnWidths:widthValues,columnWidthSpread:Math.max(...widthValues)-Math.min(...widthValues),barBottoms:bars.map(rect=>Math.round(rect.bottom*10)/10),labelHeights:labelRects.map(rect=>Math.round(rect.height*10)/10),labelClipping:buttons.some(button=>{const label=button.querySelector("small");return label.scrollWidth>label.clientWidth+1||label.scrollHeight>label.clientHeight+2;}),allLabelsVisible:buttons.every(button=>{const rect=button.querySelector("small").getBoundingClientRect();return rect.width>0&&rect.height>0&&rect.left>=0&&rect.right<=innerWidth+1;}),cardHeight:Math.round(cardRect.height*10)/10,cardWidth:Math.round(cardRect.width*10)/10,rtl:document.documentElement.dir==="rtl",pageOverflow:document.documentElement.scrollWidth>innerWidth,hostWidth:Math.round(hostRect.width*10)/10};
      });
      const rowCount=state.rowTops.length;
      const expectedRows=state.counts.length===5&&state.labels.length===5;
      const passed=state.layoutMode==="grid"&&state.labels.join("|")===expectedLabels.join("|")&&state.colors.join("|")===expectedColors.join("|")&&rowCount===1&&state.columnWidthSpread<=1&&new Set(state.barBottoms).size===1&&state.allLabelsVisible&&!state.labelClipping&&!state.pageOverflow&&state.rtl&&state.cardTotal===state.activeTotal&&state.counts.reduce((sum,count)=>sum+count,0)===state.cardTotal;
      const screenshot=path.join(out,"screenshots",`deadline-card-${width}x${height}.png`);
      await page.locator("#rdDeadlineCard").screenshot({path:screenshot});result.screenshots.push(screenshot);
      result.viewports.push({width,height,status:passed?"PASSED":"FAILED",rowCount,...state,barBaselineAligned:new Set(state.barBottoms).size===1,equalColumns:state.columnWidthSpread<=1,labelsVisible:state.allLabelsVisible});
      assert(passed,`Viewport ${width}x${height} layout failed: ${JSON.stringify(state)}`);
    }
    result.status=jsErrors.length===0&&httpErrors.length===0?"PASSED":"FAILED";
    assert(result.status==="PASSED",`Browser errors: ${JSON.stringify({jsErrors,httpErrors})}`);
    fs.writeFileSync(path.join(out,"deadline-card-single-row-playwright.json"),JSON.stringify(result,null,2),"utf8");
    console.log(JSON.stringify({status:result.status,viewports:result.viewports.map(({width,height,status,rowCount,cardHeight,columnWidthSpread,barBaselineAligned,pageOverflow})=>({width,height,status,rowCount,cardHeight,columnWidthSpread,barBaselineAligned,pageOverflow})),js_errors:jsErrors.length,http_errors:httpErrors.length,screenshots:result.screenshots},null,2));
  } catch(error) {
    result.status="FAILED";result.failure=error.message;
    fs.writeFileSync(path.join(out,"deadline-card-single-row-playwright.json"),JSON.stringify(result,null,2),"utf8");
    throw error;
  } finally { await browser.close(); }
})();

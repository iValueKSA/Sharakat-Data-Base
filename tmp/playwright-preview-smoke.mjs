const { createRequire } = await import('node:module');
const require = createRequire(import.meta.url);
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');
const root = path.resolve('docs/validation/ui-redesign');
console.log('cwd',process.cwd());
await fs.mkdir(root,{recursive:true});
console.log('directory ready',root);
const browser = await chromium.launch({headless:true});
console.log('browser launched');
try {
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  await page.goto('http://localhost:8081/',{waitUntil:'domcontentloaded',timeout:15000});
  console.log('page loaded',await page.title());
  await page.screenshot({path:path.join(root,'01-overview-desktop-1440x900.png'),timeout:15000});
  console.log('screenshot saved');
} finally { await browser.close(); }

const { chromium } = require('C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs/promises');
const { execFileSync } = require('node:child_process');
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', args: ['--no-sandbox'] });
  try {
    const response = await browser.newPage().then(page => page.request.get('http://localhost:8080/api/export.xlsx'));
    const file = 'tmp/final-readiness-xlsx-inspection.xlsx';
    await fs.writeFile(file, await response.body());
    execFileSync('docker', ['cp', file, 'alahsa-local-api-1:/tmp/final-readiness-xlsx-inspection.xlsx'], { stdio: 'ignore' });
    const code = "import openpyxl,json;w=openpyxl.load_workbook('/tmp/final-readiness-xlsx-inspection.xlsx',read_only=True,data_only=True); out=[];\nfor s in w.worksheets:\n rows=list(s.iter_rows(values_only=True));out.append({'sheet':s.title,'max_row':s.max_row,'max_column':s.max_column,'headers':rows[0] if rows else [],'nonempty_rows':sum(1 for r in rows[1:] if any(v is not None for v in r)),'nonempty_col0':sum(1 for r in rows[1:] if r and r[0] is not None),'nonempty_rows_sample':[(i+2,r[:3]) for i,r in enumerate(rows[1:]) if any(v is not None for v in r)][-4:]})\nprint(json.dumps(out,ensure_ascii=False,default=str))";
    const output = execFileSync('docker', ['exec', 'alahsa-local-api-1', 'python', '-c', code], { encoding: 'utf8' });
    console.log(JSON.stringify({ status: response.status(), inspection: JSON.parse(output) }, null, 2));
    await fs.unlink(file);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });

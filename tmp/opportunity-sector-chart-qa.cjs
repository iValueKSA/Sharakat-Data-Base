const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const base = 'http://localhost:8080';
const output = 'docs/validation/ui/opportunities-table-sector-chart/screenshots';
const viewports = [
  { width: 1920, height: 1080, name: '1920x1080' },
  { width: 1440, height: 900, name: '1440x900' },
  { width: 1366, height: 768, name: '1366x768' },
  { width: 768, height: 900, name: '768x900' },
  { width: 390, height: 844, name: '390x844' },
];

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const failures = [];
  const summary = { validationTimestampUtc: new Date().toISOString(), viewports: [], table: {}, chart: {}, browserErrors: [] };
  try {
    for (const viewport of viewports) {
      const page = await browser.newPage({ viewport });
      page.on('pageerror', error => failures.push(`${viewport.name}: ${error.message}`));
      await page.goto(`${base}/?view=opportunities`, { waitUntil: 'networkidle' });
      await page.waitForFunction(() => document.querySelectorAll('#opportunityRows tr').length > 0);
      const report = await page.evaluate(async () => {
        const headers = [...document.querySelectorAll('#view-opportunities thead th')];
        const rows = [...document.querySelectorAll('#opportunityRows tr')];
        const api = await (await fetch('/api/opportunities?limit=50&offset=0')).json();
        const keys = headers.map(cell => cell.dataset.column);
        const rowChecks = rows.map((row, index) => {
          const cells = [...row.cells];
          const item = api.items[index];
          const text = key => cells[keys.indexOf(key)]?.innerText.trim();
          const expectedArea = item.area ? `${Number(item.area).toLocaleString('en-US')} م²` : '—';
          return {
            structure: cells.length === headers.length && cells.every((cell, i) => cell.dataset.column === keys[i]),
            opportunity: cells[keys.indexOf('opportunity')]?.querySelector('strong')?.textContent === item.title, owner: text('owner') === (item.owner || '—'),
            sector: text('sector') === (item.sector || 'غير مصنف'), activity: text('activity') === (item.activity || 'غير محدد'),
            sub_activity: text('sub_activity') === (item.sub_activity || '—'), asset_facility_type: text('asset_facility_type') === (item.asset_facility_type || 'غير محدد'),
            area: text('area') === expectedArea, deadline: text('deadline') === (item.deadline || '—'),
            status: text('status').length > 0, sources: text('sources').startsWith(String(item.source_count || 0)),
            action: Boolean(cells[keys.indexOf('action')]?.querySelector('button.row-action[aria-label="عرض تفاصيل الفرصة"]')),
            id: item.id,
          };
        });
        const wrapper = document.querySelector('#view-opportunities .table-wrap');
        return {
          headerCount: headers.length,
          rowCellCounts: rows.map(row => row.cells.length),
          keys,
          rtl: getComputedStyle(document.querySelector('#view-opportunities table')).direction === 'rtl',
          documentWidth: document.documentElement.scrollWidth,
          viewportWidth: document.documentElement.clientWidth,
          tableWrapperWidth: wrapper.clientWidth,
          tableScrollWidth: wrapper.scrollWidth,
          actionHeaderAccessible: headers.at(-1).innerText.trim() === 'التفاصيل',
          semanticallyAligned: rowChecks.every(check => Object.entries(check).filter(([key]) => key !== 'id').every(([, ok]) => ok)),
          rowFailures: rowChecks.filter(check => Object.entries(check).filter(([key]) => key !== 'id').some(([, ok]) => !ok)),
        };
      });
      assert.equal(report.headerCount, 11, `${viewport.name}: expected all 11 visible data/action columns`);
      assert.ok(report.rowCellCounts.every(count => count === report.headerCount), `${viewport.name}: row cell/header mismatch`);
      assert.equal(report.rtl, true, `${viewport.name}: table must remain RTL`);
      assert.ok(report.documentWidth <= report.viewportWidth, `${viewport.name}: page horizontal overflow`);
      assert.equal(report.actionHeaderAccessible, true, `${viewport.name}: details action header missing accessible name`);
      assert.equal(report.semanticallyAligned, true, `${viewport.name}: field values do not match their API columns: ${JSON.stringify(report.rowFailures.slice(0, 2))}`);
      if (viewport.name === '1920x1080') await page.screenshot({ path: `${output}/opportunities-alignment-1920x1080.png` });
      if (viewport.name === '768x900') await page.screenshot({ path: `${output}/opportunities-alignment-768x900.png` });
      summary.viewports.push({ name: viewport.name, pageHorizontalOverflow: report.documentWidth > report.viewportWidth, rtl: report.rtl,
        headerCount: report.headerCount, checkedRows: report.rowCellCounts.length, checkedCellsPerRow: [...new Set(report.rowCellCounts)], semanticAlignment: report.semanticallyAligned,
        internalTableScroll: report.tableScrollWidth > report.tableWrapperWidth });

      if (viewport.name === '1920x1080') {
        const search = page.locator('#searchInput');
        await search.fill('44826');
        await page.waitForFunction(() => document.querySelector('#tableCount').textContent.includes('من 1 فرصة'));
        assert.equal(await page.locator('#opportunityRows tr').count(), 1, 'reference search should return exactly one Master');
        assert.equal((await page.locator('#opportunityRows tr td[data-column="activity"]').innerText()).trim(), 'غير محدد');
        await page.locator('#resetFilters').click();
        await page.waitForFunction(() => document.querySelector('#tableCount').textContent.includes('من 291 فرصة'));
        await page.locator('#sectorFilter').selectOption('sector:industrial');
        await page.waitForFunction(() => document.querySelector('#tableCount').textContent.includes('من 59 فرصة'));
        await page.locator('#resetFilters').click();
        await page.waitForFunction(() => document.querySelector('#tableCount').textContent.includes('من 291 فرصة'));
        await page.locator('#nextPage').click();
        await page.waitForFunction(() => document.querySelector('#pageSummary').textContent.includes('صفحة 2'));
        await page.locator('#previousPage').click();
        await page.waitForFunction(() => document.querySelector('#pageSummary').textContent.includes('صفحة 1'));
        const action = page.locator('#opportunityRows tr:first-child button.row-action');
        await action.focus(); await page.keyboard.press('Enter');
        await page.waitForFunction(() => document.querySelector('#modal').getAttribute('aria-hidden') === 'false');
        const detailVisible = await page.locator('#modal').isVisible();
        assert.equal(detailVisible, true, 'keyboard activation of the separate details action must open details');
        await page.locator('#modalClose').click();
        summary.table = { search44826: '1 Master', sectorFilterIndustrial: '59 Masters', resetTotal: '291 Masters', pagination: 'passed', keyboardDetails: 'passed' };
        await page.close();
      } else {
        await page.close();
      }
    }

    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    page.on('pageerror', error => failures.push(`dashboard: ${error.message}`));
    await page.goto(`${base}/?view=data-dashboard`, { waitUntil: 'networkidle' });
    await page.waitForFunction(() => document.querySelectorAll('#rdSectorChart .rd-column').length > 0);
    const chart = await page.evaluate(async () => {
      const api = await (await fetch('/api/data-dashboard')).json();
      const sectors = api.by_sector;
      const sourceTotal = sectors.reduce((total, row) => total + Number(row.count), 0);
      const canonicalOther = sectors.find(row => row.canonical_id === 'sector:other')?.count || 0;
      const tailCount = sectors.slice(7).reduce((total, row) => total + Number(row.count), 0);
      const bars = [...document.querySelectorAll('#rdSectorChart .rd-column')];
      const barValues = bars.map(bar => Number(bar.querySelector('.rd-column-value')?.textContent || 0));
      const labels = bars.map(bar => [...bar.querySelectorAll('.rd-column-label tspan')].map(part => part.textContent).join(''));
      const grouped = document.querySelector('#rdSectorChart [data-dash-filter="sector_values"]');
      const tooltip = document.querySelector('#rdSectorChart .rd-tooltip');
      return { total: api.kpis.total, sourceTotal, canonicalOther, tailCount, barValues, labels,
        displayedOther: Number(grouped?.querySelector('.rd-column-value')?.textContent || 0),
        groupedMembers: JSON.parse(grouped?.dataset.dashValues || '[]'),
        noRemainderBar: !labels.some(label => label.includes('بقية القطاعات')),
        sum: barValues.reduce((total, count) => total + count, 0), tooltipPresent: Boolean(tooltip) };
    });
    assert.equal(chart.total, chart.sourceTotal, 'canonical sector API buckets should reconcile with eligible Masters');
    assert.equal(chart.displayedOther, chart.canonicalOther + chart.tailCount, 'displayed Other should equal canonical Other plus current tail');
    assert.equal(chart.sum, chart.total, 'displayed chart buckets should sum to eligible Masters');
    assert.equal(chart.noRemainderBar, true, 'the remainder must not remain a separate bar');
    assert.equal(chart.labels.includes('أخرى'), true, 'aggregated Other label should be visible');
    await page.screenshot({ path: `${output}/dashboard-sector-other-1920x1080.png` });
    await page.locator('#rdSectorChart [data-dash-filter="sector_values"]').click();
    await page.waitForFunction(() => document.querySelector('#tableCount').textContent.includes('فرصة'));
    const resultCount = await page.locator('#tableCount').innerText();
    const sectorValuesQuery = new URL(page.url()).searchParams.get('sector_values');
    const groupResponse = await page.evaluate(async () => {
      const query = new URLSearchParams(location.search);
      return (await fetch(`/api/opportunities?sector_values=${encodeURIComponent(query.get('sector_values'))}&limit=500`)).json();
    });
    assert.equal(groupResponse.total, chart.displayedOther, 'click-through Master count should equal displayed Other');
    assert.equal(sectorValuesQuery !== null, true, 'click-through should retain the explicit canonical group members');
    assert.match(resultCount, new RegExp(`من ${chart.displayedOther} فرصة`));
    await page.screenshot({ path: `${output}/dashboard-sector-other-drilldown-1920x1080.png` });
    await page.locator('#resetFilters').click();
    await page.waitForFunction(() => document.querySelector('#tableCount').textContent.includes('من 291 فرصة'));
    summary.chart = { canonicalOther: chart.canonicalOther, tailSectorGroup: chart.tailCount, displayedOther: chart.displayedOther,
      chartSum: chart.sum, snapshotEligibleMasters: chart.total, noRemainderBucket: chart.noRemainderBar,
      groupedMembers: chart.groupedMembers, otherClickResultCount: groupResponse.total, resetRestoresTotal: true };
    summary.browserErrors = failures;
    assert.deepEqual(failures, [], 'unexpected page JavaScript errors');
    fs.writeFileSync(`${output}/qa-summary.json`, JSON.stringify(summary, null, 2), 'utf8');
    await page.close();
    console.log(JSON.stringify(summary, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });

const fs = require("fs");
const path = require("path");
const { chromium } = require("C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");

(async () => {
  const outputDir = path.resolve("docs/validation/data/opportunity-type-taxonomy/screenshots");
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe" });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    await page.goto("http://localhost:8080/?view=opportunities", { waitUntil: "networkidle" });
    await page.waitForFunction(() => document.querySelectorAll("#typeFilter option").length > 1);
    await page.waitForFunction(() => document.querySelectorAll("#opportunityRows tr").length > 0);

    const initial = await page.evaluate(async () => {
      const [filtersResponse, dashboardResponse] = await Promise.all([
        fetch("/api/filters"), fetch("/api/data-dashboard"),
      ]);
      const filters = await filtersResponse.json();
      const dashboard = await dashboardResponse.json();
      const option = filters.types.map(label => ({
        label,
        id: filters.option_ids.types[label],
        count: filters.option_counts.types[label],
      }));
      const results = [];
      for (const item of option) {
        const query = new URLSearchParams({ opportunity_type: item.id, limit: "1" });
        const response = await fetch(`/api/opportunities?${query}`);
        const data = await response.json();
        results.push({ label: item.label, id: item.id, optionCount: item.count, queryCount: data.total });
      }
      const crossFilterCounts = {};
      const dimensions = [
        ["sector", "sectors"], ["activity", "activities"], ["sub_activity", "sub_activities"],
        ["status", "statuses"], ["owner", "owners"], ["location", "locations"],
      ];
      for (const [param, optionKey] of dimensions) {
        let matched = null;
        for (const label of filters[optionKey] || []) {
          const id = filters.option_ids?.[optionKey]?.[label] || label;
          const query = new URLSearchParams({ opportunity_type: "opportunity_type:temporary_rental", [param]: id, limit: "500" });
          const response = await fetch(`/api/opportunities?${query}`);
          const data = await response.json();
          if (!response.ok || data.items.some(row => row.type !== "تأجير مؤقت")) throw new Error(`Cross-filter changed Type semantics: ${param}`);
          if (data.total > 0) { matched = { label, count: data.total }; break; }
        }
        if (!matched) throw new Error(`No overlapping ${param} option could be verified with the canonical Type`);
        crossFilterCounts[param] = matched;
      }
      const source = filters.sources?.find(item => item.key);
      if (source) {
        const query = new URLSearchParams({ opportunity_type: "opportunity_type:temporary_rental", source: source.key, limit: "500" });
        const response = await fetch(`/api/opportunities?${query}`);
        const data = await response.json();
        if (!response.ok || data.items.some(row => row.type !== "تأجير مؤقت")) throw new Error("Source cross-filter changed Type semantics");
        crossFilterCounts.source = data.total;
      }
      const ncpList = await (await fetch("/api/opportunities?source=ncp&limit=1")).json();
      const ncpDetails = ncpList.items.length
        ? await (await fetch(`/api/opportunities/${ncpList.items[0].id}`)).json()
        : null;
      return {
        direction: document.documentElement.getAttribute("dir"),
        option,
        optionQueryCounts: results,
        crossFilterCounts,
        ncpDetails,
        dashboardByType: dashboard.by_type,
        total: dashboard.kpis.total,
        htmlScrollWidth: document.documentElement.scrollWidth,
        viewportWidth: innerWidth,
      };
    });

    if (initial.direction !== "rtl") throw new Error(`Expected RTL page, got ${initial.direction}`);
    if (initial.option.length !== 2 || !initial.option.some(item => item.label === "غير محدد") || !initial.option.some(item => item.label === "تأجير مؤقت")) throw new Error("Opportunity Type options do not match the approved canonical label list");
    const typeCounts = Object.fromEntries(initial.option.map(item => [item.id, item.count]));
    if (typeCounts["opportunity_type:missing"] !== 162 || typeCounts["opportunity_type:temporary_rental"] !== 129) throw new Error("Canonical type option IDs/counts do not reconcile");
    if (initial.optionQueryCounts.some(item => item.optionCount !== item.queryCount)) throw new Error("Opportunity Type option count differs from query result count");
    const dashboardTypes = Object.fromEntries(initial.dashboardByType.map(item => [item.canonical_id, item]));
    if (Object.keys(dashboardTypes).length !== 2 || dashboardTypes["opportunity_type:missing"]?.count !== 162 || dashboardTypes["opportunity_type:temporary_rental"]?.count !== 129 || dashboardTypes["opportunity_type:temporary_rental"]?.name !== "تأجير مؤقت") throw new Error("Dashboard Type aggregation does not match canonical filters/counts");
    if (initial.htmlScrollWidth > initial.viewportWidth) throw new Error("Page has horizontal overflow at 1920px");
    if (initial.ncpDetails) {
      const ncpBusinessDetail = JSON.stringify({ changes: initial.ncpDetails.changes, facts: initial.ncpDetails.source_facts, sources: initial.ncpDetails.sources });
      if (/\b(?:PPP_PROJECT|LEASE_OPPORTUNITY|COMMERCIAL_FACILITY_OPPORTUNITY|INVESTMENT_OPPORTUNITY|TemporaryRental)\b/.test(ncpBusinessDetail)) throw new Error("Technical enum leaked into NCP business details or legacy history");
    }

    await page.locator("#typeFilter").selectOption("opportunity_type:temporary_rental");
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("129"));
    const firstRow = await page.locator("#opportunityRows tr").first().innerText();
    await page.locator("#nextPage").click();
    await page.waitForFunction(previous => document.querySelector("#opportunityRows tr")?.innerText !== previous, firstRow);
    await page.locator("#previousPage").click();
    await page.waitForFunction(previous => document.querySelector("#opportunityRows tr")?.innerText === previous, firstRow);
    const searchableTitle = (await page.locator("#opportunityRows tr").first().innerText()).split("\n")[0].trim();
    await page.locator("#searchInput").fill(searchableTitle);
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent && !document.querySelector("#tableCount")?.textContent.includes("129"));
    await page.locator("#searchInput").fill("");
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("129"));
    await page.locator("#opportunityRows [data-detail]").first().click();
    await page.waitForFunction(() => document.querySelector("#modal")?.classList.contains("show"));
    const detailText = await page.locator("#modalBody").innerText();
    if (!detailText.includes("نوع الفرصة") || !detailText.includes("تأجير مؤقت")) throw new Error("Opportunity Details does not display the canonical type field");
    if (/\b(?:Investment|TemporaryRental|PPP_PROJECT|LEASE_OPPORTUNITY|opportunity_type)\b/.test(detailText)) throw new Error("Raw or technical Opportunity Type leaked into details/change history");
    await page.screenshot({ path: path.join(outputDir, "after-opportunity-type-detail.png") });

    const exportEvidence = await page.evaluate(async () => {
      const query = new URLSearchParams({ opportunity_type: "opportunity_type:temporary_rental" });
      const [csvResponse, xlsxResponse] = await Promise.all([
        fetch(`/api/export.csv?${query}`), fetch(`/api/export.xlsx?${query}`),
      ]);
      const csv = await csvResponse.text();
      const xlsx = new Uint8Array(await xlsxResponse.arrayBuffer());
      return {
        csvStatus: csvResponse.status,
        csvRows: csv.trim().split(/\r?\n/).length - 1,
        csvTypeLabel: csv.includes("تأجير مؤقت"),
        xlsxStatus: xlsxResponse.status,
        xlsxSignature: String.fromCharCode(...xlsx.slice(0, 2)),
        xlsxBytes: xlsx.byteLength,
      };
    });
    if (exportEvidence.csvStatus !== 200 || exportEvidence.csvRows !== 129 || !exportEvidence.csvTypeLabel) throw new Error("Filtered CSV does not contain the expected 129 canonical rows");
    if (exportEvidence.xlsxStatus !== 200 || exportEvidence.xlsxSignature !== "PK" || exportEvidence.xlsxBytes < 1000) throw new Error("Filtered XLSX response is invalid");

    await page.locator("#modalClose").click();
    await page.locator("#resetFilters").click();
    await page.waitForFunction(() => document.querySelector("#typeFilter")?.value === "" && !document.querySelector("#activeFilters")?.textContent.trim());
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("291"));
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(outputDir, "after-opportunity-type-resolution.png") });
    await page.goto("http://localhost:8080/?view=data-dashboard", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#rdTypeChart [data-dash-filter='opportunity_type']", { timeout: 15000 });
    const chartBar = page.locator("#rdTypeChart [data-dash-filter='opportunity_type'][data-dash-value='opportunity_type:temporary_rental']");
    const chartValue = await chartBar.getAttribute("data-dash-value");
    if (chartValue !== "opportunity_type:temporary_rental") throw new Error(`Dashboard Type chart uses unexpected filter identity: ${chartValue}`);
    await chartBar.click();
    await page.waitForFunction(() => document.querySelector("#typeFilter")?.value === "opportunity_type:temporary_rental");
    await page.waitForFunction(() => document.querySelector("#tableCount")?.textContent.includes("129"));
    const dashboardFilteredTotal = await page.evaluate(async () => {
      const response = await fetch("/api/data-dashboard?opportunity_type=opportunity_type%3Atemporary_rental");
      const data = await response.json();
      return data.kpis.total;
    });
    if (dashboardFilteredTotal !== 129) throw new Error("Dashboard chart drill-down did not return the canonical filtered Master count");
    const final = {
      ...initial,
      detailsHasCanonicalType: true,
      exports: exportEvidence,
      resetFiltersWorks: true,
      dashboardChartFilterId: chartValue,
      dashboardChartDrillDownCount: dashboardFilteredTotal,
      dashboardChartNavigatedToCanonicalFilter: true,
      screenshot: "after-opportunity-type-resolution.png",
    };
    fs.writeFileSync(path.join(outputDir, "after-opportunity-type-resolution.json"), JSON.stringify(final, null, 2), "utf8");
    console.log(JSON.stringify(final, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

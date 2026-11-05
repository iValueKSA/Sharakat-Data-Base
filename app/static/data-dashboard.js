(() => {
  const $ = (id) => document.getElementById(id);
  const root = $("view-data-dashboard");
  if (!root) return;

  const hero = root.querySelector(".rd-video-hero");
  const heroVideo = $("dataDashboardHeroVideo");
  const heroSource = heroVideo?.querySelector("source[data-src]");
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  if (hero && heroVideo && heroSource) {
    const showPoster = () => hero.classList.remove("is-playing");
    const updateHeroPlayback = () => {
      const dashboardActive = root.classList.contains("visible");
      if (!dashboardActive || reducedMotion?.matches || document.visibilityState === "hidden") {
        heroVideo.autoplay = false;
        heroVideo.pause();
        showPoster();
        return;
      }
      hero.classList.remove("is-failed");
      heroVideo.autoplay = true;
      if (!heroSource.getAttribute("src")) {
        heroSource.src = heroSource.dataset.src;
        heroVideo.load();
      }
      heroVideo.play().catch(() => showPoster());
    };
    heroVideo.addEventListener("playing", () => {
      if (!reducedMotion?.matches && root.classList.contains("visible")) hero.classList.add("is-playing");
    });
    heroVideo.addEventListener("error", () => {
      hero.classList.add("is-failed");
      showPoster();
    });
    if (reducedMotion?.addEventListener) reducedMotion.addEventListener("change", updateHeroPlayback);
    else reducedMotion?.addListener?.(updateHeroPlayback);
    document.addEventListener("visibilitychange", updateHeroPlayback);
    new MutationObserver(updateHeroPlayback).observe(root, { attributes: true, attributeFilter: ["class"] });
    updateHeroPlayback();
  }

  const colors = ["#006e61", "#378aa4", "#c39853", "#124e5c", "#9b7a5a", "#989899"];
  const sectorColors = {
    "sector:unspecified": "#989899",
    "sector:industrial": "#006e61",
    "sector:commercial": "#378aa4",
    "sector:other": "#d1cbbd",
    "sector:environment": "#9b7a5a",
    "sector:real_estate": "#c39853",
    "sector:financial_services": "#124e5c",
    "sector:logistics": "#536461",
    "sector:education": "#7b6b8d",
    "sector:healthcare": "#a66b56",
    "sector:tourism": "#8a6db1",
    "sector:agriculture": "#64a08d",
  };
  const formatters = window.AHDAFormatters;
  const fmt = new Intl.NumberFormat("en-US-u-nu-latn", { maximumFractionDigits: 1 });
  const latinDigits = formatters?.latinDigits || ((value) => String(value ?? "").replace(/[٠-٩۰-۹]/g, (digit) => String(digit.charCodeAt(0) >= 0x6f0 ? digit.charCodeAt(0) - 0x6f0 : digit.charCodeAt(0) - 0x660)));
  const esc = (value) => latinDigits(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const n = (value) => (formatters?.integer || ((number) => fmt.format(Number(number || 0))))(value);
  const pct = (value) => (formatters?.percent || ((number) => `${fmt.format(Number(number || 0))}%`))(value);
  const label = (kind, value) => {
    if (kind === "status" && value === "Unknown") return "غير معروفة";
    const normalizers = window.AHDADisplayLabels || {};
    const normalizer = normalizers[kind];
    const result = typeof normalizer === "function" ? normalizer(value) : (value || "غير محدد");
    if (typeof result === "string" && /^[A-Za-z][A-Za-z0-9 _-]*$/.test(result)) return "قيمة عرض غير معتمدة";
    return result || "غير محدد";
  };
  const filterValue = (row) => row.canonical_id || row.filter_value || row.name || "";
  const filterKey = { type: "opportunity_type", opportunity_type: "opportunity_type" };
  const sum = (rows, key = "count") => (rows || []).reduce((total, row) => total + Number(row[key] || 0), 0);
  const healthLabel = (value) => {
    const result = ({ HEALTHY: "سليم", WARNING: "تحذير", STALE: "متأخر", FAILED: "متعذر", UNKNOWN: "غير محدد" })[value] || value || "غير محدد";
    return /^[A-Za-z][A-Za-z0-9 _-]*$/.test(result) ? "حالة غير محددة" : result;
  };
  const healthClass = (value) => value === "HEALTHY" ? "is-healthy" : ["WARNING", "STALE"].includes(value) ? "is-warning" : ["FAILED", "ERROR"].includes(value) ? "is-danger" : "is-neutral";
  const STATUS_PALETTE = ["#378aa4", "#006e61", "#9b7a5a", "#989899", "#d1cbbd", "#ac1f25", "#c39853", "#124e5c", "#64a08d", "#536461", "#7b6b8d", "#a66b56"];
  const statusColor = (row, used = new Set()) => {
    const status = String(row.name || row.filter_value || "").trim().toUpperCase();
    const canonical = String(row.canonical_id || "").toLowerCase();
    if (/ANNOUNCED|PUBLISHED|منشورة/.test(status)) return "#006e61";
    if (/ACTIVE|OPEN|AVAILABLE|متاحة|نشطة|مفتوحة/.test(status)) return "#006e61";
    if (/EXPIRED|منتهية|منتهي/.test(status)) return "#9b7a5a";
    if (/REMOVED|أزيلت|محذوفة/.test(status)) return "#989899";
    if (/CANCEL|AWARDED|CLOSED|ملغاة|ملغية/.test(status)) return "#ac1f25";
    if (status === "UNKNOWN" || canonical === "status:unknown") return "#c39853";
    if (/غير محددة|MISSING/.test(status) || canonical === "status:missing") return "#d1cbbd";
    const color = STATUS_PALETTE.find((candidate) => !used.has(candidate)) || STATUS_PALETTE[used.size % STATUS_PALETTE.length];
    used.add(color);
    return color;
  };
  const statusColors = (rows) => {
    const used = new Set();
    return rows.map((row) => {
      const color = statusColor(row, used);
      used.add(color);
      return color;
    });
  };
  const escapeLabelLines = (value, max = 12) => {
    const words = String(value || "").trim().split(/\s+/).filter(Boolean);
    const lines = [];
    let line = "";
    for (const word of words) {
      const next = line ? `${line} ${word}` : word;
      if (Array.from(next).length > max && line) { lines.push(line); line = word; }
      else line = next;
    }
    if (line) lines.push(line);
    return lines.slice(0, 3);
  };
  const niceMax = (max) => {
    if (max <= 0) return 1;
    const magnitude = 10 ** Math.floor(Math.log10(max));
    const fraction = max / magnitude;
    const rounded = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
    return rounded * magnitude;
  };
  const attr = (row, dimension, denominator) => {
    const target = dimension === "source" ? row.key : filterValue(row);
    if (!target) return "";
    const rowLabel = label(dimension, row.name || row.key);
    const value = Number(row.count || 0);
    const share = dimension === "source" && Number.isFinite(Number(row.share_percent)) ? Number(row.share_percent) : denominator ? value * 100 / denominator : 0;
    return `role="button" tabindex="0" data-dash-filter="${esc(filterKey[dimension] || dimension)}" data-dash-value="${esc(target)}" aria-label="تصفية حسب ${esc(rowLabel)}: ${n(value)} فرصة" data-tip-label="${esc(rowLabel)}" data-tip-value="${esc(`${n(value)} فرصة`)}" data-tip-share="${esc(`${pct(share)} من النتائج${dimension === "source" ? "؛ قد يتكرر الربط بين المصادر" : ""}`)}"`;
  };
  function showEmpty(container, message) {
    container.innerHTML = `<div class="rd-empty"><span aria-hidden="true">—</span><p>${esc(message)}</p></div>`;
    container.setAttribute("aria-busy", "false");
  }
  function chartTooltipMarkup() { return '<div class="rd-tooltip" role="status" hidden></div>'; }
  function setBusy(id, busy) { const node = $(id); if (node) node.setAttribute("aria-busy", String(busy)); }

  function renderActiveRing(data) {
    const total = Number(data.kpis?.total || 0), active = Number(data.kpis?.active || 0);
    const share = total ? Math.min(100, active / total * 100) : 0;
    const radius = 28, circumference = 2 * Math.PI * radius;
    $("rdActiveRing").innerHTML = `<svg viewBox="0 0 76 76" role="img" aria-label="${pct(share)} من الفرص نشطة"><circle class="rd-ring-track" cx="38" cy="38" r="${radius}"/><circle class="rd-ring-progress" cx="38" cy="38" r="${radius}" stroke-dasharray="${circumference * share / 100} ${circumference}" transform="rotate(-90 38 38)"/><text x="38" y="41" text-anchor="middle">${pct(share)}</text></svg>`;
  }

  function topWithRemainder(rows, labelText) {
    const source = (rows || []).filter((row) => Number(row.count || 0) > 0).slice();
    if (labelText === "القطاعات") {
      if (source.length <= 7) return source;
      const priority = (row) => ["sector:tourism", "sector:agriculture"].includes(row.canonical_id);
      const pinned = source.filter(priority).map((row) => ({ ...row }));
      const rankable = source.filter((row) => !priority(row));
      const top = rankable.slice(0, 7).map((row) => ({ ...row }));
      const visibleIds = new Set([...top, ...pinned].map((row) => row.canonical_id));
      const tail = rankable.filter((row) => !visibleIds.has(row.canonical_id));
      const canonicalOther = (row) => row.canonical_id === "sector:other" || row.name === "أخرى";
      const visibleOther = top.find(canonicalOther);
      const memberRows = visibleOther ? [visibleOther, ...tail] : tail.slice();
      const tailCount = sum(tail);
      if (visibleOther && tail.length) {
        visibleOther.count = Number(visibleOther.count || 0) + tailCount;
        visibleOther.aggregate = true;
        visibleOther.member_values = [...new Set(memberRows.map((row) => row.canonical_id || row.filter_value || row.name))];
        visibleOther.tail_count = tailCount;
      } else if (tail.length) {
        top.push({ name: "أخرى", canonical_id: "sector:other", filter_value: "أخرى", count: sum(memberRows), aggregate: true,
          member_values: [...new Set(memberRows.map((row) => row.canonical_id || row.filter_value || row.name))], tail_count: tailCount });
      }
        return [...top, ...pinned];
    }
    if (source.length <= 8) return source;
    const top = source.slice(0, 7);
    const rest = source.slice(7);
    top.push({ name: `بقية ${labelText}`, count: sum(rest), aggregate: true });
      return [...top, ...pinned];
  }

  function renderColumns(containerId, input, dimension, caption) {
    const host = $(containerId), rows = topWithRemainder(input, caption);
    if (!rows.length) { showEmpty(host, "لا تتوفر بيانات ضمن المرشحات الحالية."); return; }
    const width = Math.max(360, Math.round(host.clientWidth || 640));
    const height = 286;
    const pad = { left: 44, right: 12, top: 14, bottom: 76 };
    const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
    const maximum = niceMax(Math.max(...rows.map((row) => Number(row.count || 0))));
    const band = plotW / rows.length, barW = Math.min(58, band * .68);
    const denominator = Number(window.lastDashboardData?.kpis?.total || 0);
    const grid = Array.from({ length: 5 }, (_, index) => {
      const value = maximum * index / 4, y = pad.top + plotH - plotH * index / 4;
      return `<line class="rd-gridline" x1="${pad.left}" x2="${width - pad.right}" y1="${y}" y2="${y}"/><text class="rd-axis-label" x="${pad.left - 8}" y="${y + 4}" text-anchor="end">${n(Math.round(value))}</text>`;
    }).join("");
    const bars = rows.map((row, index) => {
      const value = Number(row.count || 0), x = pad.left + band * index + (band - barW) / 2;
      const barH = Math.max(value ? 2 : 0, plotH * value / maximum), y = pad.top + plotH - barH;
      const display = label(dimension, row.name), lines = escapeLabelLines(display, Math.max(8, Math.min(14, Math.floor(band / 6.5))));
      const text = lines.map((part, line) => `<tspan x="${x + barW / 2}" dy="${line ? 14 : 0}">${esc(part)}</tspan>`).join("");
        const fill = row.aggregate ? "#d1cbbd" : dimension === "sector" ? sectorColors[row.canonical_id] || colors[index % colors.length] : row.canonical_id?.endsWith(":missing") ? "#989899" : dimension === "opportunity_type" ? "#378aa4" : colors[index % colors.length];
      const sectorGroup = dimension === "sector" && row.aggregate && row.member_values?.length;
      const attrs = sectorGroup
        ? `role="button" tabindex="0" data-dash-filter="sector_values" data-dash-values="${esc(JSON.stringify(row.member_values))}" aria-label="تصفية حسب ${esc(display)}: ${n(value)} فرصة" data-tip-label="${esc(display)}" data-tip-value="${esc(`${n(value)} فرصة`)}" data-tip-share="يشمل أخرى والقطاعات الأقل عددًا"`
        : row.aggregate ? `role="img" aria-label="${esc(display)}: ${n(value)} فرصة"` : attr(row, dimension, denominator);
      const tipAttrs = row.aggregate && !sectorGroup ? `data-tip-label="${esc(display)}" data-tip-value="${esc(`${n(value)} فرصة`)}" data-tip-share="مجموع بقية الفئات"` : "";
      return `<g class="rd-column" ${attrs} ${tipAttrs}><title>${esc(display)} · ${n(value)} فرصة</title><rect class="rd-column-hit" x="${pad.left + band * index}" y="${pad.top}" width="${band}" height="${plotH + 70}"/><rect class="rd-column-bar" x="${x}" y="${y}" width="${barW}" height="${barH}" rx="3" style="--rd-column-color:${fill}"/><text class="rd-column-value" x="${x + barW / 2}" y="${Math.max(pad.top + 11, y - 6)}" text-anchor="middle">${n(value)}</text><text class="rd-column-label" x="${x + barW / 2}" y="${height - 52}" text-anchor="middle" direction="rtl">${text}</text></g>`;
    }).join("");
    const aggregate = rows.find((row) => row.aggregate && dimension === "sector");
    const chartNote = aggregate
      ? `<p class="rd-chart-note">أُضيفت ${n(aggregate.tail_count)} فرصة من القطاعات الأقل عددًا إلى «أخرى»؛ ويشمل النقر كل القطاعات المجمعة.</p>`
      : rows.some((row) => row.aggregate) ? `<p class="rd-chart-note">أُجمعت ${n(input.length - 7)} فئات أقل عددًا في «فئات أقل عددًا»؛ أعدادها ضمن المجموع.</p>` : "";
    host.innerHTML = `<svg class="rd-chart-svg rd-columns-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(caption)}: ${n(sum(input))} فرصة">${grid}${bars}</svg>${chartNote}${chartTooltipMarkup()}`;
    setBusy(containerId, false);
  }

  function renderDonut(data) {
    const rows = (data.by_status || []).filter((row) => Number(row.count || 0) > 0);
    const chart = $("rdStatusDonut"), legend = $("rdStatusLegend"), total = sum(rows);
    if (!rows.length || !total) { showEmpty(chart, "لا تتوفر بيانات حالة ضمن المرشحات الحالية."); legend.innerHTML = ""; return; }
    const radius = 66, circumference = 2 * Math.PI * radius, colorsForStatus = statusColors(rows);
    let offset = 0;
    const arcs = rows.map((row, index) => {
      const value = Number(row.count || 0), length = circumference * value / total, start = offset, color = colorsForStatus[index];
      const statusAttrs = attr(row, "status", total).replace(/ data-tip-value="[^"]*"/, "").replace(/ data-tip-share="[^"]*"/, "");
      offset += length;
      return `<circle class="rd-donut-segment" cx="90" cy="90" r="${radius}" fill="none" stroke="${color}" stroke-width="18" stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-start}" transform="rotate(-90 90 90)" ${statusAttrs} data-tip-color="${color}" data-tip-value="${esc(`${n(value)} فرصة`)}" data-tip-share="${esc(`النسبة: ${pct(value * 100 / total)}`)}"><title>${esc(label("status", row.name))} · ${n(value)} فرصة (${pct(value * 100 / total)})</title></circle>`;
    }).join("");
    chart.innerHTML = `<svg class="rd-donut-svg" viewBox="0 0 180 180" role="img" aria-label="توزيع الحالات، ${n(total)} فرصة"><circle class="rd-donut-track" cx="90" cy="90" r="${radius}"/>${arcs}<text class="rd-donut-total" x="90" y="86" text-anchor="middle">${n(total)}</text><text class="rd-donut-caption" x="90" y="106" text-anchor="middle">فرصة</text></svg>${chartTooltipMarkup()}`;
    legend.innerHTML = rows.map((row, index) => `<button type="button" class="rd-legend-row" data-dash-filter="status" data-dash-value="${esc(filterValue(row))}" aria-label="تصفية حسب ${esc(label("status", row.name))}: ${n(row.count)} فرصة"><i style="--rd-legend-color:${colorsForStatus[index]}"></i><span>${esc(label("status", row.name))}</span><b>${n(row.count)}</b></button>`).join("");
    setBusy("rdStatusDonut", false);
  }

  function renderSparkMetrics(data) {
    const k = data.kpis || {}, total = Number(k.total || 0), active = Number(k.active || 0);
    $("rdHeroTotal").textContent = n(total); $("rdHeroActive").textContent = n(active);
    $("rdActiveValue").textContent = n(active); $("rdSourceValue").textContent = n(k.enabled_sources);
    renderActiveRing(data);
    const sources = data.sources || [], healthy = sources.filter((source) => source.health === "HEALTHY").length;
    $("rdSourceHealthy").textContent = `${n(healthy)} من ${n(sources.length)} مصادر سليمة تقنيًا`;
    $("rdSourceProgress").style.width = `${sources.length ? healthy / sources.length * 100 : 0}%`;
    $("rdDeadlineTotal").textContent = n(k.deadline_distribution_total ?? active);
    const buckets = data.deadline_buckets || [], maxBucket = Math.max(1, ...buckets.map((row) => Number(row.count || 0)));
    $("rdDeadlineBuckets").innerHTML = buckets.map((row) => {
      const category = String(row.label || "");
      const count = Number(row.count || 0);
      const tooltip = `${category}: ${n(count)} فرصة`;
      return `<button type="button" class="rd-deadline-bucket" data-deadline-key="${esc(row.key)}" data-deadline-bucket="${esc(row.key)}" title="${esc(tooltip)}" aria-label="${esc(tooltip)}" style="--rd-deadline-color:${esc(row.color || "#989899")};--rd-deadline-bar-height:${Math.max(4, count / maxBucket * 18)}px"><i class="rd-deadline-bar" aria-hidden="true"></i><b>${n(count)}</b><small>${esc(category)}</small></button>`;
    }).join("");
    $("rdMultiCount").textContent = `${n(k.multi_source)} · ${pct(k.multi_source_percent)}`;
  }

  function renderSourceMix(data) {
    const host = $("rdSourceMix"), rows = (data.by_source || []).filter((row) => row.count > 0).slice(0, 8), max = Math.max(1, ...rows.map((row) => Number(row.count || 0)));
    if (!rows.length) { showEmpty(host, "لا توجد مصادر مرتبطة بالنتائج الحالية."); return; }
    const sourceLogo = window.sourceLogoMarkup;
    host.innerHTML = rows.map((row) => {
      const logo = typeof sourceLogo === "function" ? sourceLogo(row.key, true) : `<span class="rd-source-initial">${esc((row.name || "م").slice(0, 1))}</span>`;
      return `<div class="rd-source-mix-row" ${attr(row, "source", data.kpis?.total)}><span class="rd-source-brand">${logo}</span><span class="rd-source-name">${esc(row.name)}</span><span class="rd-source-count">${n(row.count)}</span><i class="rd-source-mix-track"><b style="width:${Number(row.count) / max * 100}%"></b></i><span class="rd-sr-only">${pct(row.share_percent)} من إجمالي الفرص ضمن المصادر.</span></div>`;
    }).join("") + chartTooltipMarkup();
    setBusy("rdSourceMix", false);
  }

  function renderRank(containerId, rows, dimension, emptyMessage) {
    const host = $(containerId), data = rows || [], max = Math.max(1, ...data.map((row) => Number(row.count || 0)));
    if (!data.length) { showEmpty(host, emptyMessage); return; }
    host.innerHTML = data.slice(0, 10).map((row, index) => `<div class="rd-rank-row" ${attr(row, dimension, sum(data))}><span class="rd-rank-index">${n(index + 1)}</span><span class="rd-rank-label">${esc(label(dimension, row.name || row.key))}</span><i class="rd-rank-track"><b style="width:${Number(row.count) / max * 100}%"></b></i><strong>${n(row.count)}</strong></div>`).join("") + chartTooltipMarkup();
    setBusy(containerId, false);
  }

  function renderQuality(data) {
    const host = $("rdQuality"), rows = data.completeness || [];
    host.innerHTML = rows.map((row) => `<div class="rd-quality-item"><div><span>${esc(row.label)}</span><b>${pct(row.percent)}</b></div><i><b class="${Number(row.percent) < 70 ? "is-low" : ""}" style="width:${Math.max(0, Math.min(100, Number(row.percent || 0)))}%"></b></i><small>${n(row.count)} من ${n(row.total)} فرصة</small></div>`).join("") || '<div class="rd-empty"><p>لا تتوفر بيانات اكتمال الحقول.</p></div>';
    setBusy("rdQuality", false);
  }

  function renderSources(data) {
    const host = $("rdSourceList"), rows = data.sources || [];
    if (!rows.length) { showEmpty(host, "لا توجد مصادر مفعلة."); return; }
    const labels = window.AHDADisplayLabels || {}, date = formatters?.date || ((value) => value || "غير مسجل");
    host.innerHTML = rows.map((source) => `<div class="rd-source-health-row"><i class="rd-health-dot ${healthClass(source.health)}" aria-hidden="true"></i><b>${esc(source.name)}</b><span class="rd-health-status ${healthClass(source.health)}">${esc(healthLabel(source.health))}</span><small class="rd-source-meta"><span>آخر نجاح ${source.last_successful_sync ? esc(date(source.last_successful_sync)) : "غير مسجل"}</span><span class="rd-coverage-status">التغطية: ${esc(labels.coverage?.(source.coverage) || "تغطية غير محددة")}</span></small></div>`).join("");
  }

  function renderUpcoming(data) {
    const host = $("rdUpcomingList"), rows = data.deadlines || [];
    if (!rows.length) { showEmpty(host, "لا توجد مواعيد قادمة موثقة ضمن المرشحات الحالية."); return; }
    const date = formatters?.date || ((value) => value || "—");
    host.innerHTML = rows.slice(0, 4).map((item) => `<button type="button" class="rd-upcoming-item" data-detail="${esc(item.id)}"><span class="rd-countdown">${item.days_remaining === 0 ? "اليوم" : `بعد ${n(item.days_remaining)} يوم`}</span><span class="rd-upcoming-copy"><b>${esc(item.title)}</b><small>${esc(item.owner || "جهة غير محددة")} · ${esc(date(item.deadline))}</small></span></button>`).join("");
  }

  function renderRecent(data) {
    const host = $("rdRecentRows"), rows = data.recent_opportunities || [];
    const date = formatters?.date || ((value) => value || "—");
    host.innerHTML = rows.length ? rows.map((item) => {
      const color = statusColor({ name: item.status });
      return `<tr><td><button type="button" class="rd-opportunity-link" data-detail="${esc(item.id)}"><b>${esc(item.title)}</b><small>${esc(item.owner || "جهة غير محددة")}</small></button></td><td>${esc(label("sector", item.sector))}</td><td><span class="rd-status-badge" data-status-key="${esc(item.status)}" style="--rd-status-color:${color}"><i aria-hidden="true"></i>${esc(label("status", item.status))}</span></td><td><span dir="ltr">${esc(date(item.deadline))}</span></td></tr>`;
    }).join("") : '<tr><td colspan="4" class="rd-table-empty">لا توجد فرص ضمن المرشحات الحالية.</td></tr>';
    const examples = data.multi_source_examples || [];
    $("rdMultiExamples").innerHTML = examples.length ? examples.slice(0, 3).map((item) => `<button type="button" data-detail="${esc(item.id)}"><b>${esc(item.title)}</b><small>${esc(item.owner || "جهة غير محددة")}</small></button>`).join("") : '<small class="rd-no-examples">لا توجد فرص متعددة المصادر ضمن النتائج الحالية.</small>';
  }

  let map = null, boundary = null, clusterLayer = null, heatLayer = null, currentMapData = null, mapMode = "clusters", mapReady = false, mapLoading = null, resizeTimer = null;
  const mapCenter = [25.4, 49.6];
  function focusMappedExtent(points) {
    if (!map) return;
    const locations = (points || []).filter((point) => Number.isFinite(Number(point.latitude)) && Number.isFinite(Number(point.longitude)));
    if (!locations.length) {
      if (currentMapData?.map_scope === "NATIONAL") map.setView([24, 45], 5);
      else if (boundary) map.fitBounds(boundary.getBounds(), { padding: [16, 16], maxZoom: 8 });
      return;
    }
    const bounds = window.L.latLngBounds(locations.map((point) => [Number(point.latitude), Number(point.longitude)]));
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 10 });
  }
  function mapNotice(message) { const host = $("rdMapNotice"); host.textContent = message; host.hidden = !message; }
  function renderMapStats(counts, scope) {
    const items = [["ضمن النتائج", counts.total], ["نقاط موثقة", counts.exact_mapped], ["بدون إحداثيات", counts.missing_coordinates],
      ...(scope === "NATIONAL" ? [] : [["خارج الحد المحلي", counts.outside_boundary]]),
      ["غير مثبتة بالمصدر", counts.unverified_coordinates], ["غير ممثلة", counts.unmapped]];
    $("rdGeoStats").innerHTML = items.map(([title, value], index) => `<span class="${index === 1 ? "is-primary" : ""}"><small>${title}</small><b>${n(value)}</b></span>`).join("");
  }
  function renderMapHeading(data) {
    const national = data.map_scope === "NATIONAL";
    $("rdMapTitle").textContent = national ? "خريطة الفرص الوطنية" : "خريطة فرص الأحساء";
    $("rdMapDescription").textContent = national
      ? "الإحداثيات الموثقة من المصدر فقط؛ النطاقات العامة والمواقع غير المحددة لا تنشئ نقاطًا."
      : "الإحداثيات المطابقة لسجل المصدر والحد المحلي فقط.";
    $("rdMapAttribution").hidden = national;
    $("rdOpportunityMap").setAttribute("aria-label", national ? "خريطة تفاعلية للفرص الوطنية" : "خريطة تفاعلية للفرص في الأحساء");
  }
  const pointPopup = (point) => `<div class="rd-map-popup" dir="rtl"><b>${esc(point.title)}</b><span>${esc(point.location || "موقع منشور")}</span><span>${n(point.count)} فرصة · ${n(point.active_count)} نشطة</span><span>${esc(point.sector || "قطاع غير مصنف")}</span><button type="button" data-map-open="${esc(point.ids.join(","))}">عرض الفرص في القائمة</button></div>`;
  async function ensureMap(scope = "AL_AHSA") {
    if (map) return;
    if (mapLoading) return mapLoading;
    mapLoading = (async () => {
      if (!window.L) throw new Error("تعذر تحميل مكتبة الخريطة المحلية.");
      map = window.L.map("rdOpportunityMap", { zoomControl: false, scrollWheelZoom: false, preferCanvas: true }).setView(scope === "NATIONAL" ? [24, 45] : mapCenter, scope === "NATIONAL" ? 5 : 9);
      window.L.control.zoom({ position: "topright" }).addTo(map);
      const tiles = window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors' });
      tiles.on("tileerror", () => mapNotice("تعذر تحميل خريطة الأساس؛ ستبقى الحدود والنقاط المحلية متاحة.")); tiles.addTo(map);
      clusterLayer = window.L.markerClusterGroup({ showCoverageOnHover: false, spiderfyOnMaxZoom: true, maxClusterRadius: 46, iconCreateFunction: (cluster) => {
        const count = cluster.getAllChildMarkers().reduce((value, marker) => value + Number(marker.options.opportunityCount || 1), 0);
        return window.L.divIcon({ html: `<span class="rd-cluster-count">${n(count)}</span>`, className: "rd-cluster-icon", iconSize: window.L.point(42, 42) });
      } }).addTo(map);
      if (scope !== "NATIONAL") {
        const response = await fetch("/static/geo/alahsa-governorate.geojson", { cache: "force-cache" });
        if (!response.ok) throw new Error("تعذر تحميل الحد المحلي للمحافظة.");
        const geojson = await response.json();
        boundary = window.L.geoJSON(geojson, { interactive: false, style: { color: "#378aa4", weight: 2, opacity: .9, fillColor: "#378aa4", fillOpacity: .08, dashArray: "5 5" } }).addTo(map);
      }
      map.on("popupopen", (event) => {
        const button = event.popup.getElement()?.querySelector("[data-map-open]");
        if (button) button.addEventListener("click", () => window.goToOpportunities?.({ map_ids: button.dataset.mapOpen }));
      });
      mapReady = true; setTimeout(() => map?.invalidateSize({ pan: false }), 60);
    })().catch((error) => { mapNotice(error.message || "تعذر إعداد الخريطة المحلية."); throw error; }).finally(() => { mapLoading = null; });
    return mapLoading;
  }
  function updateMapMode() {
    if (!map || !clusterLayer || !heatLayer) return;
    if (mapMode === "heat") { clusterLayer.remove(); heatLayer.addTo(map); }
    else { heatLayer.remove(); clusterLayer.addTo(map); }
    root.querySelectorAll("[data-rd-map-mode]").forEach((button) => {
      const active = button.dataset.rdMapMode === mapMode;
      button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active));
    });
  }
  function drawMap(data) {
    if (!map || !clusterLayer) return;
    clusterLayer.clearLayers(); heatLayer?.remove();
    const values = [];
    for (const point of data.points || []) {
      const marker = window.L.marker([point.latitude, point.longitude], {
        title: `${point.location}: ${n(point.count)} فرص`, opportunityCount: point.count,
        icon: window.L.divIcon({ html: '<span class="rd-map-dot"></span>', className: "rd-marker-icon", iconSize: [20, 20], iconAnchor: [10, 10] }),
      });
      marker.bindPopup(pointPopup(point), { maxWidth: 250 }); clusterLayer.addLayer(marker);
      values.push([point.latitude, point.longitude, Math.max(1, Number(point.count || 1))]);
    }
    heatLayer = window.L.heatLayer(values, { radius: 30, blur: 23, maxZoom: 12, max: Math.max(1, ...values.map((point) => point[2])), gradient: { .25: "#c39853", .55: "#378aa4", .82: "#006e61", 1: "#124e5c" } });
    updateMapMode(); focusMappedExtent(data.points);
    setTimeout(() => map?.invalidateSize({ pan: false }), 60);
  }
  async function loadMap(filters) {
    const query = new URLSearchParams(filters || {});
    try {
      const response = await fetch(`/api/data-dashboard/geography?${query}`, { credentials: "same-origin" });
      if (!response.ok) throw new Error("تعذر تحميل بيانات الخريطة.");
      currentMapData = await response.json(); renderMapStats(currentMapData.counts, currentMapData.map_scope); renderMapHeading(currentMapData);
      await ensureMap(currentMapData.map_scope); drawMap(currentMapData); mapNotice("");
    } catch (error) { mapNotice(error.message || "تعذر تحميل بيانات الخريطة؛ أعد تحميل اللوحة."); }
  }

  function render(data, filters) {
    window.lastDashboardData = data;
    renderSparkMetrics(data);
    renderColumns("rdSectorChart", data.by_sector || [], "sector", "القطاعات");
    renderDonut(data);
    renderSourceMix(data);
    renderRank("rdOwnerRank", data.by_owner || [], "owner", "لا توجد جهات ضمن النتائج الحالية.");
    renderQuality(data); renderSources(data); renderUpcoming(data); renderRecent(data);
    root.classList.remove("is-refreshing"); root.setAttribute("aria-busy", "false");
    loadMap(filters || {});
  }

  document.addEventListener("ahda:data-dashboard:loading", () => {
    root.classList.add("is-refreshing"); root.setAttribute("aria-busy", "true");
    ["rdSectorChart", "rdStatusDonut", "rdSourceMix", "rdOwnerRank", "rdQuality"].forEach((id) => {
      const host = $(id); if (host && !host.children.length) host.innerHTML = '<div class="rd-skeleton" aria-hidden="true"><i></i><i></i><i></i></div>';
      setBusy(id, true);
    });
  });
  document.addEventListener("ahda:data-dashboard:error", () => {
    root.classList.remove("is-refreshing"); root.setAttribute("aria-busy", "false");
    ["rdSectorChart", "rdStatusDonut", "rdSourceMix", "rdOwnerRank", "rdQuality"].forEach((id) => {
      if (!$(id).children.length) showEmpty($(id), "تعذر تحميل هذا المؤشر. حاول إعادة التحميل.");
    });
  });
  document.addEventListener("ahda:data-dashboard", (event) => {
    const { data, filters } = event.detail || {};
    if (data) render(data, filters);
    if (data) loadNationalGeoSummary(filters || {});
  });
  async function loadNationalGeoSummary(filters) {
    const panel = $("nationalGeoSummary"), host = $("nationalGeoSummaryValues");
    if (!panel || !host) return;
    try {
      const catalogResponse = await fetch("/api/geography/catalog", { credentials: "same-origin" });
      const catalog = catalogResponse.ok ? await catalogResponse.json() : {};
      if (catalog.national_dashboard_enabled !== true) { panel.hidden = true; return; }
      const query = new URLSearchParams(filters);
      const response = await fetch(`/api/data-dashboard/geography-summary?${query}`, { credentials: "same-origin" });
      if (!response.ok) { panel.hidden = true; return; }
      const result = await response.json();
      const rows = [...(result.by_region || []), ...(result.by_governorate || [])];
      host.innerHTML = `<p>${n(result.unique_master_total)} فرصة رئيسية فريدة · ${n(result.mapped_unique_masters)} موثقة الإحداثيات · ${n(result.scope_counts?.NATIONWIDE)} بنطاق وطني · ${n(result.unspecified_unique_masters)} غير محددة الموقع</p><div class="national-geo-bars">${rows.map(item => `<button type="button" data-national-geo-filter="${item.region_id ? "governorate" : "region"}" data-national-geo-id="${esc(item.id)}"><b>${esc(item.name_ar)}</b><small>${n(item.unique_masters)} فرصة رئيسية</small></button>`).join("")}</div>`;
      panel.hidden = false;
    } catch { panel.hidden = true; }
  }
  $("nationalGeoSummaryValues")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-national-geo-filter]");
    if (button) window.goToOpportunities?.({ [`${button.dataset.nationalGeoFilter}_id`]: button.dataset.nationalGeoId });
  });
  root.addEventListener("click", (event) => {
    const mode = event.target.closest("[data-rd-map-mode]");
    if (mode) { mapMode = mode.dataset.rdMapMode; updateMapMode(); }
  });

  function tipFor(event) {
    const target = event.target.closest("[data-tip-label]");
    if (!target || !root.contains(target)) return;
    const host = target.closest(".rd-chart-area,.rd-source-rank,.rd-rank-list,.rd-donut");
    const tooltip = host?.querySelector(".rd-tooltip");
    if (!tooltip) return;
    const colorMark = target.dataset.tipColor ? `<i class="rd-tooltip-mark" style="--rd-tip-color:${target.dataset.tipColor}" aria-hidden="true"></i>` : "";
    tooltip.innerHTML = `<b>${colorMark}${esc(target.dataset.tipLabel)}</b><span>${esc(target.dataset.tipValue || "")}</span><small>${esc(target.dataset.tipShare || "")}</small>`;
    tooltip.hidden = false;
    const hostRect = host.getBoundingClientRect(), targetRect = target.getBoundingClientRect();
    const left = Math.max(8, Math.min(host.clientWidth - tooltip.offsetWidth - 8, targetRect.left - hostRect.left + targetRect.width / 2 - tooltip.offsetWidth / 2));
    const top = Math.max(8, targetRect.top - hostRect.top - 6);
    tooltip.style.left = `${left}px`; tooltip.style.top = `${top}px`;
    tooltip.classList.toggle("is-below", top < tooltip.offsetHeight + 12);
  }
  document.addEventListener("pointerover", tipFor);
  document.addEventListener("focusin", tipFor);
  const hideTip = (event) => {
    const target = event.target.closest("[data-tip-label]");
    if (target && !target.contains(event.relatedTarget)) {
      const tooltip = target.closest(".rd-chart-area,.rd-source-rank,.rd-rank-list,.rd-donut")?.querySelector(".rd-tooltip");
      if (tooltip) tooltip.hidden = true;
    }
  };
  document.addEventListener("pointerout", hideTip);
  document.addEventListener("focusout", hideTip);
  document.addEventListener("keydown", (event) => {
    const item = event.target.closest(".rd-column[role='button'],[data-dash-filter][role='button']");
    if (item && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); item.dispatchEvent(new MouseEvent("click", { bubbles: true })); }
  });
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (window.lastDashboardData) {
        renderColumns("rdSectorChart", window.lastDashboardData.by_sector || [], "sector", "القطاعات");
      }
      if (mapReady) map?.invalidateSize({ pan: false });
    }, 140);
  });
})();

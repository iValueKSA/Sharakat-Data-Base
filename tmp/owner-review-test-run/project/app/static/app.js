const state = { sources: [], items: [], view: "overview", user: null, filtersLoaded: false, opportunityPage: 0, searchTimer: null, dataDashboardLoaded: false, dataFilters: {}, filterOptionIds: {}, dashboardDate: null, lastDashboardData: null, sidebarReturnFocus: null };
const $ = id => document.getElementById(id);
const toLatinDigits = value => String(value ?? "").replace(/[٠-٩۰-۹]/g, digit => String(digit.charCodeAt(0) >= 0x6f0 ? digit.charCodeAt(0) - 0x6f0 : digit.charCodeAt(0) - 0x660));
const numberLatin = new Intl.NumberFormat("en-US-u-nu-latn", { maximumFractionDigits: 1 });
const integerLatin = new Intl.NumberFormat("en-US-u-nu-latn", { maximumFractionDigits: 0 });
const formatNumberLatin = value => numberLatin.format(Number(value || 0));
const formatIntegerLatin = value => integerLatin.format(Number(value || 0));
const formatPercentLatin = value => `${formatNumberLatin(value)}%`;
const formatDateLatin = value => {
  if (!value) return "—";
  const raw = toLatinDigits(value);
  const dateOnly = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (dateOnly) return `${dateOnly[1]}/${dateOnly[2]}/${dateOnly[3]}`;
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.valueOf())) return raw;
  const parts = new Intl.DateTimeFormat("en-US-u-ca-gregory-nu-latn", { timeZone: "Asia/Amman", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(parsed);
  const part = type => parts.find(item => item.type === type)?.value || "00";
  return `${part("year")}/${part("month")}/${part("day")}`;
};
const formatDateTimeLatin = value => {
  if (!value) return "—";
  const raw = toLatinDigits(value), parsed = new Date(raw);
  if (Number.isNaN(parsed.valueOf())) return raw;
  const time = new Intl.DateTimeFormat("ar-SA-u-ca-gregory-nu-latn", { timeZone: "Asia/Amman", hour: "numeric", minute: "2-digit", hour12: true }).format(parsed);
  return `${formatDateLatin(parsed)} · ${toLatinDigits(time)}`;
};
window.AHDAFormatters = Object.freeze({ number: formatNumberLatin, integer: formatIntegerLatin, percent: formatPercentLatin, date: formatDateLatin, dateTime: formatDateTimeLatin, latinDigits: toLatinDigits });
const safe = value => toLatinDigits(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const geographyStatusMarkup = item => item?.geography?.confirmed ? "" : `<small class="geo-status">${safe(item?.geography?.status_ar || "الموقع غير محدد")}</small>`;
const aggregatedOtherSectorValue = "__aggregated_other_sectors__";
const roleLabel = role => ({ admin: "مسؤول", analyst: "محلل", viewer: "مشاهد" }[role] || "زائر");
const coverageLabel = value => ({ COMPLETE_PUBLIC_SOURCE: "مكتمل عبر المصدر العام", COMPLETE_FOR_DEFINED_SCOPE: "مكتمل ضمن النطاق المحدد", PUBLIC_COVERAGE_LIMITED: "تغطية البيانات العامة محدودة", PRIVATE_API_REQUIRED: "تتطلب صلاحية خاصة", AUTHENTICATED_SOURCE_REQUIRED: "يتطلب تسجيل دخول", PARTIAL_OFFICIAL_COVERAGE: "تغطية رسمية جزئية" }[value] || value || "تغطية غير محددة");
const sectorNames = { INVESTMENT_OPPORTUNITY: "فرصة استثمارية", COMMERCIAL_FACILITY_OPPORTUNITY: "فرصة منشأة تجارية", LEASE_OPPORTUNITY: "فرصة تأجير", PPP_PROJECT: "مشروع شراكة", Environment: "البيئة", ENVIRONMENT: "البيئة", Tourism: "السياحة", TOURISM: "السياحة", Agriculture: "الزراعة", AGRICULTURE: "الزراعة", Healthcare: "الرعاية الصحية", HEALTHCARE: "الرعاية الصحية", Education: "التعليم", EDUCATION: "التعليم", Logistics: "الخدمات اللوجستية", LOGISTICS: "الخدمات اللوجستية", Industrial: "صناعي", INDUSTRIAL: "صناعي", Commercial: "تجاري", COMMERCIAL: "تجاري", Unclassified: "غير مصنف", UNCLASSIFIED: "غير مصنف" };
const sectorLabel = value => sectorNames[value] || value || "غير مصنف";
const opportunityTypeNames = { "غير محدد": "غير محدد", "أخرى": "أخرى" };
const opportunityTypeLabel = value => opportunityTypeNames[value] || "غير محدد";
function toast(message) { const el = $("toast"); el.textContent = message; el.classList.add("show"); clearTimeout(window.toastTimer); window.toastTimer = setTimeout(() => el.classList.remove("show"), 3600); }

// All logos represent the publishing platform identified by the source adapter key.
const SOURCE_LOGOS = {
  furas: { path: "/static/source-logos/furas.svg", alt: "شعار منصة فرص", fallback: "فرص", status: "OFFICIAL_LOGO" },
  "alahsa-opportunities": { path: null, alt: "منصة الفرص الاستثمارية بالأحساء", fallback: "أحساء", status: "OFFICIAL_SOURCE_LOGO_MISSING" },
  ahda: { path: "/static/source-logos/ahda.svg", alt: "شعار هيئة تطوير الأحساء", fallback: "هيئة", status: "OFFICIAL_LOGO" },
  "invest-saudi": { path: "/static/source-logos/invest-saudi.png", alt: "شعار استثمر في السعودية", fallback: "IS", status: "OFFICIAL_LOGO" },
  kfu: { path: "/static/source-logos/kfu.webp", alt: "شعار جامعة الملك فيصل", fallback: "KFU", status: "OFFICIAL_LOGO" },
  modon: { path: "/static/source-logos/modon.png", alt: "شعار الهيئة السعودية للمدن الصناعية ومناطق التقنية مدن", fallback: "مدن", status: "OFFICIAL_LOGO" },
  ncp: { path: "/static/source-logos/ncp.svg", alt: "شعار المركز الوطني للتخصيص", fallback: "NCP", status: "OFFICIAL_LOGO" },
  nhc: { path: null, alt: "NHC الاستثمار", fallback: "NHC", status: "OFFICIAL_SOURCE_LOGO_MISSING" },
  pif: { path: null, alt: "بوابة القطاع الخاص لصندوق الاستثمارات العامة", fallback: "PIF", status: "OFFICIAL_SOURCE_LOGO_MISSING" },
  mwan: { path: "/static/source-logos/mwan.png", alt: "شعار المركز الوطني لإدارة النفايات موان", fallback: "موان", status: "OFFICIAL_LOGO" },
};
function sourceLogoMarkup(key, compact = false) {
  const logo = SOURCE_LOGOS[key] || { path: null, alt: "مصدر رسمي", fallback: "مصدر", status: "OFFICIAL_SOURCE_LOGO_MISSING" };
  const label = safe(logo.alt), fallback = safe(logo.fallback);
  return `<span class="source-logo ${compact ? "source-logo-compact" : ""}" role="img" aria-label="${label}" title="${label}">${logo.path ? `<img src="${logo.path}" alt="${label}" loading="lazy" decoding="async" onerror="this.hidden=true;this.nextElementSibling.hidden=false">` : ""}<span class="source-logo-fallback" ${logo.path ? "hidden" : ""} aria-hidden="true">${fallback}</span></span>`;
}
const sourceOpportunityCache = new Map();
function renderSourceOpportunity(sourceKey, item) {
  const source = (item.sources || []).find(entry => entry.key === sourceKey);
  const sourceUrl = source?.url;
  return `<article class="source-opportunity-row">${sourceLogoMarkup(sourceKey, true)}<div class="source-opportunity-copy"><button class="source-opportunity-title" type="button" data-detail="${item.id}">${safe(item.title)}</button><small>${safe(item.reference || item.canonical_id || "")} · ${safe(item.owner || "جهة غير محددة")}</small></div>${sourceUrl ? `<a class="source-opportunity-link" href="${safe(sourceUrl)}" target="_blank" rel="noreferrer" aria-label="فتح الإعلان الأصلي: ${safe(item.title)}" title="فتح الإعلان الأصلي">↗</a>` : ""}</article>`;
}
async function loadSourceOpportunities(sourceKey, panel, reset = true) {
  const list = panel.querySelector(".source-opportunity-list"), more = panel.querySelector(".source-opportunity-more"), summary = panel.querySelector("summary");
  const cache = sourceOpportunityCache.get(sourceKey) || { items: [], total: null, offset: 0, loading: false };
  if (cache.loading) return;
  cache.loading = true; sourceOpportunityCache.set(sourceKey, cache);
  if (reset) { cache.items = []; cache.offset = 0; cache.total = null; list.innerHTML = '<div class="loading">جارٍ تحميل الفرص…</div>'; }
  more.hidden = true;
  try {
    const query = new URLSearchParams({ source: sourceKey, limit: "50", offset: String(cache.offset) });
    const result = await api(`/api/opportunities?${query}`);
    cache.total = Number(result.total || 0); cache.items.push(...(result.items || [])); cache.offset += (result.items || []).length;
    list.innerHTML = cache.items.length ? cache.items.map(item => renderSourceOpportunity(sourceKey, item)).join("") : '<div class="loading">لا توجد فرص أحساء موحدة مرتبطة بهذا المصدر حاليًا.</div>';
    bindDetailButtons();
    summary.querySelector(".source-opportunity-count").textContent = `${cache.total.toLocaleString("en-US-u-nu-latn")} فرصة`;
    more.hidden = cache.offset >= cache.total;
  } catch (error) {
    sourceOpportunityCache.delete(sourceKey);
    list.innerHTML = `<div class="loading" role="alert">تعذّر تحميل الفرص: ${safe(error.message)}</div>`;
  } finally { cache.loading = false; }
}

async function promptLogin() {
  const dialog = $("loginDialog");
  if (!dialog.open) dialog.showModal();
  return new Promise(resolve => {
    const finish = value => { dialog.removeEventListener("close", onClose); resolve(value); };
    const onClose = () => finish(false);
    dialog.addEventListener("close", onClose, { once: true });
    $("loginForm").onsubmit = async event => {
      event.preventDefault(); $("loginError").textContent = "";
      try {
        const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", body: JSON.stringify({ email: $("loginEmail").value, password: $("loginPassword").value }) });
        if (!response.ok) throw Error("تعذر تسجيل الدخول. تحقق من البريد وكلمة المرور.");
        state.user = (await response.json()).user; $("loginPassword").value = ""; dialog.close(); setUserLabel(); applyRoleVisibility(); finish(true);
      } catch (error) { $("loginError").textContent = error.message; }
    };
  });
}
async function api(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  let response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  if (response.status === 401 && !url.startsWith("/api/auth/")) {
    if (await promptLogin()) response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  }
  if (!response.ok) { let message = "تعذر إكمال الطلب"; try { message = (await response.json()).detail || message; } catch {} throw Error(message); }
  return response.status === 204 ? null : response.json();
}
function applyRoleVisibility() {
  const role = state.user?.role;
  if (!role) {
    document.querySelectorAll("[data-role]").forEach(element => { element.hidden = true; });
    document.querySelectorAll("[data-view='review'],[data-view='alerts'],[data-view='admin'],[data-view='activity']").forEach(element => { element.hidden = true; });
    if (["review", "alerts", "admin", "activity"].includes(state.view)) view("overview");
    return;
  }
  document.querySelectorAll("[data-role]").forEach(element => { element.hidden = !element.dataset.role.split(",").includes(role); });
  if (role === "viewer") document.querySelectorAll("[data-view='review'],[data-view='alerts'],[data-view='admin'],[data-view='activity']").forEach(element => { element.hidden = true; });
  if ((state.view === "admin" && role !== "admin") || (state.view === "alerts" && role !== "admin") || (state.view === "review" && !["admin", "analyst"].includes(role))) view("overview");
}
function setUserLabel() {
  $("userLabel").textContent = state.user ? `${state.user.display_name || state.user.email} · ${roleLabel(state.user.role)}` : "زائر";
  $("userButton").title = state.user ? "تسجيل الخروج" : "تسجيل الدخول";
}

const pageNames = { overview: "نظرة عامة", "data-dashboard": "لوحة عرض البيانات", opportunities: "الفرص الاستثمارية", sources: "المصادر الرسمية", activity: "سجل المزامنة", review: "مراجعة البيانات", alerts: "التنبيهات", admin: "الإدارة" };
function view(name) {
  const target = $("view-" + name); if (!target) return;
  const restricted = ({ review: ["admin", "analyst"], alerts: ["admin"], admin: ["admin"] })[name];
  if (restricted && (!state.user || !restricted.includes(state.user.role))) { toast(state.user ? "لا تملك صلاحية الوصول إلى هذه الصفحة" : "سجّل الدخول للوصول إلى هذه الصفحة"); return; }
  state.view = name;
  const current = new URLSearchParams(window.location.search); current.set("view", name); history.replaceState(null, "", `${window.location.pathname}?${current.toString()}`);
  document.querySelectorAll(".page-view").forEach(element => element.classList.remove("visible")); target.classList.add("visible"); window.scrollTo({ top: 0, behavior: "instant" });
  document.querySelectorAll(".nav-item").forEach(element => { const active = element.dataset.view === name; element.classList.toggle("active", active); if (active) element.setAttribute("aria-current", "page"); else element.removeAttribute("aria-current"); });
  $("pageCrumb").textContent = pageNames[name];
  closeMobileSidebar();
  if (name === "opportunities") loadOpportunities();
  if (name === "data-dashboard") loadDataDashboard();
  if (name === "sources") loadSources();
  if (name === "activity") loadJobs();
  if (name === "review") loadReview();
  if (name === "alerts") loadAlerts();
  if (name === "admin") loadAdmin();
}
document.querySelectorAll(".nav-item").forEach(button => button.addEventListener("click", () => view(button.dataset.view)));
document.querySelectorAll("[data-goto]").forEach(button => button.addEventListener("click", () => view(button.dataset.goto)));
$("sidebarToggle").addEventListener("click", () => openMobileSidebar());
$("sidebarBackdrop").addEventListener("click", () => closeMobileSidebar());
function openMobileSidebar() {
  if (window.matchMedia("(min-width: 921px)").matches) return;
  state.sidebarReturnFocus = document.activeElement;
  $("sidebar").classList.add("is-open"); $("sidebarBackdrop").hidden = false;
  $("sidebarToggle").setAttribute("aria-expanded", "true"); $("sidebarToggle").setAttribute("aria-label", "إغلاق قائمة التنقل");
  document.body.classList.add("sidebar-open");
  const firstNavItem = $("sidebar").querySelector(".nav-item:not([hidden])");
  window.setTimeout(() => { if (document.body.classList.contains("sidebar-open")) firstNavItem?.focus({ preventScroll: true }); }, 35);
}
function closeMobileSidebar() {
  const wasOpen = $("sidebar").classList.contains("is-open");
  $("sidebar").classList.remove("is-open"); $("sidebarBackdrop").hidden = true;
  $("sidebarToggle").setAttribute("aria-expanded", "false"); $("sidebarToggle").setAttribute("aria-label", "فتح قائمة التنقل");
  document.body.classList.remove("sidebar-open");
  if (wasOpen && state.sidebarReturnFocus?.isConnected) state.sidebarReturnFocus.focus();
}
document.addEventListener("keydown", event => { if (event.key === "Escape" && $("sidebar").classList.contains("is-open")) closeMobileSidebar(); });
$("brand")?.addEventListener("click", event => { event.preventDefault(); view("overview"); });
$("openSources").onclick = () => view("sources");
$("userButton").onclick = async () => {
  if (!state.user) { await promptLogin(); return; }
  if (!window.confirm("هل تريد تسجيل الخروج؟")) return;
  try { await api("/api/auth/logout", { method: "POST" }); state.user = null; setUserLabel(); applyRoleVisibility(); toast("تم تسجيل الخروج"); }
  catch (error) { toast(error.message); }
};

async function loadDashboard() {
  try {
    const dashboard = await api("/api/dashboard");
    $("metricTotal").textContent = Number(dashboard.unique_master_opportunities || dashboard.total || 0).toLocaleString("en-US-u-nu-latn");
    $("metricActive").textContent = Number(dashboard.active || 0).toLocaleString("en-US-u-nu-latn");
    $("metricNew").textContent = Number(dashboard.new_today || 0).toLocaleString("en-US-u-nu-latn");
    $("metricSources").textContent = Number(dashboard.enabled_sources || 0).toLocaleString("en-US-u-nu-latn");
    $("metricReview").textContent = (Number(dashboard.pending_duplicates || 0) + Number(dashboard.pending_location_reviews || 0)).toLocaleString("en-US-u-nu-latn");
    $("metricMasters").textContent = Number(dashboard.unique_master_opportunities || 0).toLocaleString("en-US-u-nu-latn");
    $("metricListings").textContent = Number(dashboard.source_listings_collected || 0).toLocaleString("en-US-u-nu-latn");
    $("metricMultiSource").textContent = Number(dashboard.multi_source_opportunities || 0).toLocaleString("en-US-u-nu-latn");
    $("navCount").textContent = Number(dashboard.total || 0).toLocaleString("en-US-u-nu-latn");
    $("reviewCount").textContent = (Number(dashboard.pending_duplicates || 0) + Number(dashboard.pending_location_reviews || 0)).toLocaleString("en-US-u-nu-latn");
    const result = await api("/api/opportunities?limit=300"); state.items = result.items || [];
    const today = new Date(), closingCutoff = new Date(today); closingCutoff.setDate(today.getDate() + 30);
    const closingSoon = state.items.filter(item => { const deadline = item.deadline ? new Date(item.deadline) : null; return deadline && !Number.isNaN(deadline.valueOf()) && deadline >= new Date(today.toDateString()) && deadline <= closingCutoff; });
    $("metricClosing").textContent = closingSoon.length.toLocaleString("en-US-u-nu-latn");
    renderLatest(); renderDeadlines(); renderSectors(dashboard.sectors || []);
    await loadSources(true); renderSourceChart();
  } catch (error) { toast(error.message); }
}
function renderLatest() {
  const items = (state.items || []).slice(0, 5); $("emptyLatest").style.display = items.length ? "none" : "flex";
  $("latestOpportunities").innerHTML = items.map(item => `<div class="latest-item" data-detail="${item.id}" tabindex="0" role="button"><div><b>${safe(item.title)}</b><small>${safe(item.owner || "جهة غير محددة")} · ${safe(sectorLabel(item.sector))}</small></div><span class="latest-area">${item.area ? Number(item.area).toLocaleString("en-US") + " م²" : "—"}</span></div>`).join("");
  bindDetailButtons();
}
function bindDetailButtons() { document.querySelectorAll("[data-detail]").forEach(element => { element.onclick = () => showDetail(element.dataset.detail); element.onkeydown = event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); showDetail(element.dataset.detail); } }; }); }
function renderDeadlines() {
  const container = $("upcomingDeadlines"), today = new Date();
  const items = (state.items || []).filter(item => item.deadline && !Number.isNaN(new Date(item.deadline).valueOf()) && new Date(item.deadline) >= new Date(today.toDateString())).sort((a, b) => new Date(a.deadline) - new Date(b.deadline)).slice(0, 4);
  container.innerHTML = items.length ? items.map(item => `<div class="deadline-item"><span class="deadline-date">${safe(formatDateLatin(item.deadline))}</span><span class="deadline-copy"><b>${safe(item.title)}</b><small>${safe(item.owner || "جهة غير محددة")}</small></span></div>`).join("") : '<div class="loading">لا توجد مواعيد قريبة منشورة.</div>';
}
function renderSectors(sectors) {
  const rows = sectors.filter(item => item.count).slice(0, 8), max = Math.max(1, ...rows.map(item => item.count));
  $("sectorChart").innerHTML = rows.length ? rows.map(item => `<div class="sector-item">${safe(sectorLabel(item.name))} <b>${Number(item.count).toLocaleString("en-US-u-nu-latn")}</b><div class="sector-line"><span style="width:${Math.max(6, item.count / max * 100)}%"></span></div></div>`).join("") : '<div class="loading">ستظهر بيانات التوزيع عند توفر فرص مصنفة.</div>';
}
function renderSourceChart() {
  const sources = [...state.sources].sort((a, b) => (b.record_count || 0) - (a.record_count || 0)).slice(0, 10);
  $("sourceChart").innerHTML = sources.length ? sources.map(source => `<div class="source-chart-item"><b>${safe(source.name)}</b><small>${safe(coverageLabel(source.coverage_status))}</small><strong>${Number(source.record_count || 0).toLocaleString("en-US-u-nu-latn")}</strong></div>`).join("") : '<div class="loading">لا توجد بيانات مصادر.</div>';
}

const dashFilterFields = [
  ["period", "dashPeriod", "الفترة"], ["status", "dashStatus", "الحالة"], ["sector", "dashSector", "القطاع"],
  ["activity", "dashActivity", "النشاط"], ["sub_activity", "dashSubActivity", "النشاط الفرعي"], ["subsector", "dashSubsector", "القطاع الفرعي"], ["source", "dashSource", "المصدر"], ["owner", "dashOwner", "الجهة"], ["location", "dashLocation", "الموقع"], ["opportunity_type", "dashType", "نوع الفرصة"], ["investment_model", "dashInvestmentModel", "نموذج الاستثمار"], ["asset_facility_type", "dashAssetFacilityType", "نوع الأصل أو الموقع"], ["lifecycle", "dashLifecycle", "نطاق الحالة"]
];
const dashNum = value => Number(value || 0).toLocaleString("en-US-u-nu-latn");
const optionId = (dimension, label) => state.filterOptionIds?.[dimension]?.[label] || label;
function restoreFilterValue(select, value, dimension) {
  if (!value) return;
  const values = [...select.options].map(option => option.value);
  if (values.includes(value)) { select.value = value; return; }
  const mapped = Object.entries(state.filterOptionIds?.[dimension] || {}).find(([label, id]) => label === value || id === value)?.[1];
  if (mapped && values.includes(mapped)) select.value = mapped;
}
function fillSelect(id, values, defaultLabel, labelFn = value => value, valueFn = value => value) {
  const select = $(id), current = select.value;
  select.innerHTML = `<option value="">${safe(defaultLabel)}</option>` + values.map(item => `<option value="${safe(valueFn(item))}">${safe(labelFn(item))}</option>`).join("");
  if ([...select.options].some(option => option.value === current)) select.value = current;
}
function readDashFilters() {
  return Object.fromEntries(dashFilterFields.map(([key, id]) => [key, $(id).value]).filter(([key, value]) => value && (key !== "period" || value !== "all")));
}
function updateDashUrl() {
  const params = new URLSearchParams(); params.set("view", "data-dashboard");
  for (const [key, value] of Object.entries(readDashFilters())) params.set(key, value);
  history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
}
function renderDataDashboard(data) {
  state.dashboardDate = data.as_of_date;
  state.lastDashboardData = data;
  $("navCount").textContent = dashNum(data.global_total);
  $("dataDashboardUpdated").textContent = data.latest_source_update ? `آخر مزامنة مصدر: ${date(data.latest_source_update)}` : "لا يوجد وقت مزامنة مسجل";
  $("topbarUpdateLabel").textContent = data.latest_source_update ? `آخر مزامنة · ${date(data.latest_source_update)}` : "لا يوجد وقت مزامنة مسجل";
  const activeFilters = readDashFilters();
  $("dashActiveCount").textContent = Object.keys(activeFilters).length ? `${dashNum(Object.keys(activeFilters).length)} مرشحات نشطة` : "كل الفرص";
  updateDashboardExportLinks();
  $("dataDashboardError").hidden = true;
  $("dashFilterChips").innerHTML = dashFilterFields.map(([key, id, label]) => { const value = $(id).value; if (!value || (key === "period" && value === "all")) return ""; const option = $(id).selectedOptions[0]?.textContent || value; return `<button class="filter-chip dash-chip" type="button" data-remove-dash-filter="${id}" aria-label="إزالة مرشح ${safe(label)}: ${safe(option)}">${safe(label)}: ${safe(option)} <span aria-hidden="true">×</span></button>`; }).join("");
  document.dispatchEvent(new CustomEvent("ahda:data-dashboard", { detail: { data, filters: activeFilters } }));
  bindDetailButtons();
}
function updateDashboardExportLinks() {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(readDashFilters())) query.set(key, value);
  for (const [id, format] of [["dashExportCsv", "csv"], ["dashExportXlsx", "xlsx"]]) $(id).href = `/api/export.${format}${query.size ? `?${query}` : ""}`;
}
async function loadDataDashboard() {
  $("dataDashboardError").hidden = true;
  $("view-data-dashboard").setAttribute("aria-busy", "true");
  if (!state.lastDashboardData) document.dispatchEvent(new CustomEvent("ahda:data-dashboard:loading"));
  try {
    if (!state.dataDashboardLoaded) {
      const filters = await api("/api/filters");
      state.filterOptionIds = filters.option_ids || {};
      fillSelect("dashSector", filters.sectors, "كل القطاعات", sectorLabel, label => optionId("sectors", label)); fillSelect("dashStatus", filters.statuses, "كل الحالات", statusLabel, label => optionId("statuses", label));
      fillSelect("dashActivity", filters.activities || [], "كل الأنشطة", value => value, label => optionId("activities", label)); fillSelect("dashSubActivity", filters.sub_activities || [], "كل الأنشطة الفرعية", value => value, label => optionId("sub_activities", label));
      fillSelect("dashSource", filters.sources, "كل المصادر", item => item.name, item => item.key);
      fillSelect("dashOwner", filters.owners, "كل الجهات", value => value, label => optionId("owners", label)); fillSelect("dashLocation", filters.locations, "كل المواقع", value => value, label => optionId("locations", label)); fillSelect("dashType", filters.types, "كل الأنواع", opportunityTypeLabel, label => optionId("types", label)); fillSelect("dashInvestmentModel", filters.investment_models || [], "كل نماذج الاستثمار", value => value, label => optionId("investment_models", label)); fillSelect("dashAssetFacilityType", filters.asset_facility_types || [], "كل أنواع الأصول والمواقع", value => value, label => optionId("asset_facility_types", label)); fillSelect("dashSubsector", filters.subsectors || [], "كل القطاعات الفرعية", value => value, label => optionId("subsectors", label));
      const params = new URLSearchParams(location.search);
      for (const [key, id] of dashFilterFields) if (params.has(key)) restoreFilterValue($(id), params.get(key), ({ sector: "sectors", activity: "activities", status: "statuses", owner: "owners", location: "locations", opportunity_type: "types", investment_model: "investment_models", asset_facility_type: "asset_facility_types", subsector: "subsectors", sub_activity: "sub_activities" })[key]);
      state.dataDashboardLoaded = true;
    }
    state.dataFilters = readDashFilters(); updateDashUrl();
    const query = new URLSearchParams(state.dataFilters);
    const data = await api(`/api/data-dashboard?${query}`); renderDataDashboard(data);
  } catch (error) { $("dataDashboardError").hidden = false; $("dataDashboardError").innerHTML = '<div><b>تعذر تحميل بيانات اللوحة.</b><span>تحقق من الاتصال ثم أعد المحاولة.</span></div><button class="button button-quiet" id="dashRetry" type="button">إعادة المحاولة</button>'; $("dashRetry").onclick = loadDataDashboard; if (!state.lastDashboardData) document.dispatchEvent(new CustomEvent("ahda:data-dashboard:error")); }
  finally { $("view-data-dashboard").setAttribute("aria-busy", "false"); }
}
function goToOpportunities(extra = {}) {
  const params = new URLSearchParams(); params.set("view", "opportunities");
  for (const [key, value] of Object.entries({ ...readDashFilters(), ...extra })) if (value) params.set(key, value);
  history.replaceState(null, "", `${location.pathname}?${params.toString()}`);
  state.opportunityFiltersInitialized = false; view("opportunities");
}
window.goToOpportunities = goToOpportunities;
document.querySelectorAll("#view-data-dashboard .rd-filter-grid select").forEach(select => select.addEventListener("change", loadDataDashboard));
$("dashReset").onclick = () => { for (const [, id] of dashFilterFields) $(id).value = id === "dashPeriod" ? "all" : ""; loadDataDashboard(); };
$("view-data-dashboard").addEventListener("click", event => {
  const kpi = event.target.closest("[data-kpi-action]");
  if (kpi) {
    const action = kpi.dataset.kpiAction;
    if (action === "sources") view("sources");
    else if (action === "active" || action === "historical") goToOpportunities({ lifecycle: action });
    else if (action === "deadlines" && state.dashboardDate) goToOpportunities({ lifecycle: "active", deadline_after: state.dashboardDate, deadline_before: (() => { const [year, month, day] = state.dashboardDate.split("-").map(Number); return new Date(Date.UTC(year, month - 1, day + 30)).toISOString().slice(0, 10); })() });
    else goToOpportunities();
  }
  const internalNav = event.target.closest("[data-goto]"); if (internalNav) view(internalNav.dataset.goto);
  const filterButton = event.target.closest("[data-dash-filter]");
  if (filterButton) {
    const key = filterButton.dataset.dashFilter, value = filterButton.dataset.dashValue;
    if (key === "sector_values") {
      try { const values = JSON.parse(filterButton.dataset.dashValues || "[]"); if (Array.isArray(values) && values.length) goToOpportunities({ sector: "", sector_values: JSON.stringify(values) }); }
      catch { toast("تعذر فتح مجموعة القطاعات."); }
    } else if (key && value) goToOpportunities({ [key]: value });
  }
  const periodPoint = event.target.closest("[data-analytics-period]");
  if (periodPoint) {
    const start = periodPoint.dataset.periodStart, end = periodPoint.dataset.periodEnd;
    if (start && end && periodPoint.dataset.periodKind === "deadline") goToOpportunities({ lifecycle: "active", deadline_after: start, deadline_before: end });
    else if (start && end && periodPoint.dataset.periodKind === "created") goToOpportunities({ created_after: start, created_before: end });
  }
  if (event.target.closest("[data-dash-goto]")) goToOpportunities();
  const chip = event.target.closest("[data-remove-dash-filter]"); if (chip) { $(chip.dataset.removeDashFilter).value = chip.dataset.removeDashFilter === "dashPeriod" ? "all" : ""; loadDataDashboard(); }
  const bucket = event.target.closest("[data-deadline-bucket]"); if (bucket) { const limits = { "7d": [0,7], "8_14d": [8,14], "15_30d": [15,30], over_30d: [31,null] }[bucket.dataset.deadlineBucket]; if (limits && state.dashboardDate) { const [from,to] = limits, addDays = days => { const [year,month,day] = state.dashboardDate.split("-").map(Number), value = new Date(Date.UTC(year,month-1,day+days)); return value.toISOString().slice(0,10); }; const extra = { lifecycle: "active", deadline_after: addDays(from) }; if (to !== null) extra.deadline_before = addDays(to); goToOpportunities(extra); } }
});

async function loadOpportunities() {
  try {
    if (!state.filtersLoaded) {
      const filters = await api("/api/filters");
      state.filterOptionIds = filters.option_ids || state.filterOptionIds;
      fillSelect("sectorFilter", filters.sectors, "كل القطاعات", sectorLabel, label => optionId("sectors", label)); fillSelect("activityFilter", filters.activities || [], "كل الأنشطة", value => value, label => optionId("activities", label)); fillSelect("subActivityFilter", filters.sub_activities || [], "كل الأنشطة الفرعية", value => value, label => optionId("sub_activities", label)); fillSelect("subsectorFilter", filters.subsectors || [], "كل القطاعات الفرعية", value => value, label => optionId("subsectors", label));
      fillSelect("statusFilter", filters.statuses, "كل الحالات", statusLabel, label => optionId("statuses", label));
      fillSelect("ownerFilter", filters.owners, "كل الجهات", value => value, label => optionId("owners", label)); fillSelect("sourceFilter", filters.sources, "كل المصادر", item => item.name, item => item.key); fillSelect("locationFilter", filters.locations, "كل المواقع", value => value, label => optionId("locations", label)); fillSelect("typeFilter", filters.types, "كل الأنواع", opportunityTypeLabel, label => optionId("types", label)); fillSelect("investmentModelFilter", filters.investment_models || [], "كل نماذج الاستثمار", value => value, label => optionId("investment_models", label)); fillSelect("assetFacilityTypeFilter", filters.asset_facility_types || [], "كل أنواع الأصول والمواقع", value => value, label => optionId("asset_facility_types", label)); state.filtersLoaded = true;
    }
    if (!state.opportunityFiltersInitialized) {
      const params = new URLSearchParams(location.search);
      for (const [key,id,dimension] of [["sector","sectorFilter","sectors"],["activity","activityFilter","activities"],["sub_activity","subActivityFilter","sub_activities"],["subsector","subsectorFilter","subsectors"],["status","statusFilter","statuses"],["owner","ownerFilter","owners"],["source","sourceFilter","sources"],["location","locationFilter","locations"],["opportunity_type","typeFilter","types"],["investment_model","investmentModelFilter","investment_models"],["asset_facility_type","assetFacilityTypeFilter","asset_facility_types"]]) if (params.has(key)) restoreFilterValue($(id), params.get(key), dimension);
      if (params.has("sector_values")) {
        const groupedSector = new Option("أخرى (تشمل بقية القطاعات)", aggregatedOtherSectorValue);
        $("sectorFilter").add(groupedSector); $("sectorFilter").value = aggregatedOtherSectorValue;
      }
      if (params.has("lifecycle")) $("lifecycleFilter").value = params.get("lifecycle");
      if (params.has("q")) $("searchInput").value = params.get("q");
      state.opportunityFiltersInitialized = true;
    }
    const pageSize = 50;
    const sectorValue = $("sectorFilter").value === aggregatedOtherSectorValue ? "" : $("sectorFilter").value;
    const query = new URLSearchParams({ q: $("searchInput").value, sector: sectorValue, activity: $("activityFilter").value, sub_activity: $("subActivityFilter").value, subsector: $("subsectorFilter").value, status: $("statusFilter").value, owner: $("ownerFilter").value, source: $("sourceFilter").value, location: $("locationFilter").value, opportunity_type: $("typeFilter").value, investment_model: $("investmentModelFilter").value, asset_facility_type: $("assetFacilityTypeFilter").value, lifecycle: $("lifecycleFilter").value, limit: String(pageSize), offset: String(state.opportunityPage * pageSize) });
    const urlParams = new URLSearchParams(location.search); for (const key of ["deadline_after","deadline_before","created_after","created_before","period","map_ids","sector_values"]) if (urlParams.has(key)) query.set(key,urlParams.get(key));
    const result = await api("/api/opportunities?" + query); state.items = result.items || [];
    const total = Number(result.total || 0), pageCount = Math.max(1, Math.ceil(total / pageSize));
    $("tableCount").textContent = total ? `عرض ${(state.opportunityPage * pageSize + 1).toLocaleString("en-US-u-nu-latn")}–${Math.min((state.opportunityPage + 1) * pageSize, total).toLocaleString("en-US-u-nu-latn")} من ${total.toLocaleString("en-US-u-nu-latn")} فرصة` : "لا توجد فرص مطابقة";
    $("previousPage").disabled = state.opportunityPage === 0;
    $("nextPage").disabled = state.opportunityPage >= pageCount - 1;
    $("pageSummary").textContent = `صفحة ${(state.opportunityPage + 1).toLocaleString("en-US-u-nu-latn")} من ${pageCount.toLocaleString("en-US-u-nu-latn")}`;
    $("emptyTable").classList.toggle("show", !state.items.length);
    const groupedSectorActive = urlParams.has("sector_values");
    $("opportunityRows").innerHTML = state.items.map(item => {
      const cell = (column, content) => `<td data-column="${column}">${content}</td>`;
      return `<tr>${cell("opportunity", `<strong>${safe(item.title)}</strong><small>${safe(item.reference || item.canonical_id)}</small>${geographyStatusMarkup(item)}`)}${cell("owner", safe(item.owner || "—"))}${cell("sector", safe(sectorLabel(item.sector)))}${cell("activity", safe(item.activity || "غير محدد"))}${cell("sub_activity", safe(item.sub_activity || "—"))}${cell("asset_facility_type", safe(item.asset_facility_type || "غير محدد"))}${cell("area", item.area ? Number(item.area).toLocaleString("en-US") + " م²" : "—")}${cell("deadline", safe(item.deadline || "—"))}${cell("status", `<span class="tag ${/منته|ملغ|تمت الترسية|أزيلت من المصدر|expired|cancel/i.test(item.status || "") ? "pending" : ""}">${safe(statusLabel(item.status))}</span>`)}${cell("sources", `<span class="source-pill">${Number(item.source_count || 0).toLocaleString("en-US-u-nu-latn")} مصادر</span>`)}${cell("action", `<button type="button" class="row-action" data-detail="${item.id}" aria-label="عرض تفاصيل الفرصة">↗</button>`)}</tr>`;
    }).join(""); bindDetailButtons();
    $("activeFilters").innerHTML = [$("searchInput").value && `بحث: ${safe($("searchInput").value)}`, groupedSectorActive ? "القطاع: أخرى (تشمل بقية القطاعات)" : $("sectorFilter").value && safe($("sectorFilter").selectedOptions[0]?.textContent), $("activityFilter").value && safe($("activityFilter").selectedOptions[0]?.textContent), $("subActivityFilter").value && safe($("subActivityFilter").selectedOptions[0]?.textContent), $("subsectorFilter").value && safe($("subsectorFilter").selectedOptions[0]?.textContent), $("statusFilter").value && safe($("statusFilter").selectedOptions[0]?.textContent), $("lifecycleFilter").value && safe($("lifecycleFilter").selectedOptions[0]?.textContent), $("ownerFilter").value && safe($("ownerFilter").selectedOptions[0]?.textContent), $("sourceFilter").value && safe($("sourceFilter").selectedOptions[0]?.textContent), $("locationFilter").value && safe($("locationFilter").selectedOptions[0]?.textContent), $("typeFilter").value && safe($("typeFilter").selectedOptions[0]?.textContent), $("investmentModelFilter").value && safe($("investmentModelFilter").selectedOptions[0]?.textContent), $("assetFacilityTypeFilter").value && safe($("assetFacilityTypeFilter").selectedOptions[0]?.textContent), urlParams.get("period") && `الفترة: ${safe(urlParams.get("period"))}`, urlParams.get("deadline_after") && `موعد من ${safe(urlParams.get("deadline_after"))}`, urlParams.get("deadline_before") && `موعد حتى ${safe(urlParams.get("deadline_before"))}`].filter(Boolean).map(value => `<span class="filter-chip">${value}</span>`).join("");
  } catch (error) { toast(error.message); }
}

document.querySelectorAll('a[href="/api/export.csv"], a[href="/api/export.xlsx"]').forEach(link => {
  if (link.id === "dashExportCsv" || link.id === "dashExportXlsx") return;
  link.addEventListener("click", () => {
    const query = new URLSearchParams();
    for (const [key, id] of [["sector", "sectorFilter"], ["activity", "activityFilter"], ["sub_activity", "subActivityFilter"], ["subsector", "subsectorFilter"], ["status", "statusFilter"], ["lifecycle", "lifecycleFilter"], ["owner", "ownerFilter"], ["source", "sourceFilter"], ["location", "locationFilter"], ["opportunity_type", "typeFilter"], ["investment_model", "investmentModelFilter"], ["asset_facility_type", "assetFacilityTypeFilter"]]) {
      const value = $(id)?.value;
      if (value) query.set(key, value);
    }
    const params = new URLSearchParams(location.search);
    for (const key of ["q", "period", "created_after", "created_before", "deadline_after", "deadline_before", "map_ids", "sector_values"]) if (key === "q" ? $("searchInput").value : params.get(key)) query.set(key, key === "q" ? $("searchInput").value : params.get(key));
    link.href = `${link.pathname}${query.size ? `?${query}` : ""}`;
  });
});

function healthClass(value) { const status = String(value || ""); return status === "HEALTHY" ? "healthy" : status.includes("WARNING") || ["PARSER_BROKEN", "RATE_LIMITED", "INCOMPLETE_COLLECTION_WARNING"].includes(status) ? "warning" : ["FAILED", "BLOCKED"].includes(status) ? "failed" : ""; }
function statusLabel(value) { return ({ HEALTHY: "سليم", RUNNING: "جارٍ التحديث", SUCCESS: "اكتملت المزامنة", COMPLETED: "اكتمل التشغيل", COMPLETED_WITH_WARNINGS: "اكتمل مع تنبيهات", WARNING: "يحتاج إلى متابعة", FAILED: "تعذّر الاتصال", SOURCE_FAILED: "تعذّر تحديث المصدر", SOURCE_WARNING: "تنبيه في المصدر", BLOCKED: "الوصول العام محظور", PARSER_WARNING: "تحذير في تحليل المصدر", PARSER_BROKEN: "تعذّر تحليل الصفحة", INCOMPLETE_COLLECTION_WARNING: "جمع غير مكتمل", INCOMPLETE: "جمع غير مكتمل", NEVER_SYNCED: "لم تتم المزامنة", DISABLED: "متوقف", QUEUED: "في قائمة الانتظار", SKIPPED_ALREADY_RUNNING: "تم تجاوز التشغيل لوجود مزامنة جارية", INFO: "معلومة", OPEN: "مفتوح", ACKNOWLEDGED: "تم الاطلاع", RESOLVED: "تمت المعالجة", HEALTHY_WITH_WARNINGS: "يعمل مع تنبيهات", RATE_LIMITED: "تأخر الرد من المصدر", ACCESS_BLOCKED: "الوصول العام محظور", UNKNOWN: "حالة غير معروفة", Unknown: "حالة غير معروفة", unknown: "حالة غير معروفة", Announced: "منشورة", ANNOUNCED: "منشورة", PUBLISHED: "منشورة", منشورة: "منشورة", AVAILABLE: "متاحة", متاحة: "متاحة", REMOVED: "أزيلت من المصدر", REMOVED_FROM_SOURCE: "أزيلت من المصدر", أزيلت_من_المصدر: "أزيلت من المصدر", EXPIRED: "منتهية", منتهية: "منتهية", CANCELLED: "ملغاة", ملغاة: "ملغاة", AWARDED: "تمت الترسية", تمت_الترسية: "تمت الترسية", "حالة غير معروفة": "حالة غير معروفة", "قيد مراجعة الحالة": "قيد مراجعة الحالة", "غير محددة": "غير محددة", ACTIVE: "نشطة", INACTIVE: "غير نشطة" })[value] || value || "غير محدد"; }
window.AHDADisplayLabels = Object.freeze({ sector: sectorLabel, opportunity_type: opportunityTypeLabel, status: value => { const mapped = statusLabel(value); return /^[A-Za-z][A-Za-z0-9 _-]*$/.test(mapped) ? "قيمة عرض غير معتمدة" : mapped; }, coverage: value => { const mapped = coverageLabel(value); return /^[A-Za-z][A-Za-z0-9 _-]*$/.test(mapped) ? "تغطية غير محددة" : mapped; } });
function sourceTypeLabel(value) { return ({ structured_opportunity_platform: "منصة فرص رسمية", local_opportunity_platform: "منصة فرص محلية", unstructured_opportunity_publisher: "ناشر فرص رسمية", national_opportunity_platform: "منصة وطنية", announcement_driven_local_source: "إعلانات محلية", industrial_spatial_opportunity_source: "مصدر صناعي ومكاني", ppp_privatisation_pipeline_source: "مشروعات الشراكة والتخصيص", real_estate_investment_and_partnership_source: "استثمار عقاري وشراكات", national_value_chain_investment_source: "منصة القطاع الخاص", waste_sector_investment_source: "فرص قطاع النفايات" })[value] || "مصدر رسمي"; }
function sourceCoverageNote(source) { const notes = { modon: "لا يعرض الكتالوج العام جردًا حيًا كاملًا للإتاحة الاستثمارية في الأحساء. النتائج العامة المحدودة لا تعني عدم توفر أصول.", ncp: "يرصد النطاق العام أرشيف الأخبار الإنجليزي ومقالاته المرتبطة. لا يشمل خط المستثمرين الأوسع، وتعذّر استكمال آخر صفحة من الأرشيف العربي.", nhc: "تعرض الصفحات العامة فئات الاستثمار ومسارات التأهيل والتقديم، ولا تعرض جردًا حاليًا مفصلًا للأحساء. الخدمات التي تتطلب تسجيل دخول خارج النطاق.", pif: "يعرض المسار العام صفحات المنظومات، لكن سجل الشركات والفرص لا يمكن استعراضه حاليًا بطريقة عامة حتمية. لم يُستدعَ أي واجه API خاصة.", mwan: "يشمل الرصد المشروعات الاستثمارية المنشورة صراحة. لم تُثبت الفرص العامة المنشورة ارتباطًا بمحافظة الأحساء.", furas: "يعرض المصدر الفرص المنشورة في القنوات الرسمية العامة ضمن صفحات الكتالوج المتاحة.", "alahsa-opportunities": "يعرض المصدر إعلانات الفرص المحلية المنشورة للأحساء.", ahda: "يشمل الرصد المحتوى العام المنشور ضمن نطاق المصدر المعتمد.", "invest-saudi": "يعتمد الرصد واجهة بيانات الفرص الرسمية المنشورة، وتُراجع المطابقة المكانية قبل القبول.", kfu: "يشمل الرصد إعلانات الاستثمار والتشغيل المنشورة من الجامعة." }; return notes[source.key] || source.coverage_notes || source.notes || "لا توجد ملاحظات منشورة."; }
async function loadSources(healthOnly = false) {
  try {
    state.sources = await api("/api/sources");
    $("sourceHealth").innerHTML = state.sources.slice(0, 6).map(source => `<div class="health-item"><span class="health-indicator ${healthClass(source.technical_health || source.status)}"></span><div class="health-main"><b>${safe(source.name)}</b><small>${safe(statusLabel(source.technical_health || source.status))} · ${safe(coverageLabel(source.coverage_status))}${source.last_success ? " · " + date(source.last_success) : " · لم تتم المزامنة"}</small></div><span class="health-count">${Number(source.record_count || 0).toLocaleString("en-US-u-nu-latn")}</span></div>`).join("");
    if (healthOnly) return;
    $("sourceCards").innerHTML = state.sources.map(source => `<article class="source-card"><div class="source-card-head">${sourceLogoMarkup(source.key)}<div class="source-title"><b>${safe(source.name)}</b><small>الجهة المشغلة: ${safe(source.source_operator || "غير محددة")} · ${safe(sourceTypeLabel(source.source_type))}</small></div><span class="source-state ${healthClass(source.technical_health || source.status)}">${safe(statusLabel(source.technical_health || source.status))}</span></div><details class="source-opportunities" data-source-opportunities="${safe(source.key)}"><summary><span>فرص الأحساء الموحدة المرتبطة بهذا المصدر</span><b class="source-opportunity-count">اضغط للعرض</b></summary><div class="source-opportunity-list"></div><button type="button" class="source-opportunity-more" hidden>عرض 50 فرصة أخرى</button></details><div class="source-meta"><span>نطاق التغطية<b>${safe(coverageLabel(source.coverage_status))}</b></span><span>آخر مزامنة ناجحة<b dir="ltr">${source.last_success ? date(source.last_success) : "—"}</b></span><span>المزامنة القادمة المتوقعة<b dir="ltr">${source.last_success ? date(new Date(new Date(source.last_success).getTime() + Number(source.interval || 0) * 60000)) : "—"}</b></span><span>التنبيهات المسجلة<b>${Number(source.errors || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>سجلات المصدر<b>${Number(source.record_count || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>فرص الأحساء النشطة<b>${Number(source.ahsa_records || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>فرص متعددة المصادر<b>${Number(source.multi_source_matches || 0).toLocaleString("en-US-u-nu-latn")}</b></span></div><div class="source-coverage"><b>حدود التغطية</b><p>${safe(sourceCoverageNote(source))}</p></div><details class="source-tech" data-role="admin"><summary>تفاصيل تقنية</summary><div class="source-meta"><span>المعلن / المكتمل<b>${source.source_total_reported ?? "—"} / ${source.unique_records ?? "—"} · ${source.collection_completeness_percent ?? "—"}%</b></span><span>الصفحات<b>${source.pages_successful ?? 0} / ${source.pages_requested ?? 0} · ${source.pagination_complete === true ? "مكتمل" : source.pagination_complete === false ? "ناقص" : "غير محدد"}</b></span><span>أخطاء المصدر<b>${Number(source.errors || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>طريقة الجمع<b>${safe(source.method || "غير محددة")}</b></span><span>مستلمة / محللة<b>${source.records_received ?? 0} / ${source.records_parsed ?? 0}</b></span><span>مقبولة / مرفوضة<b>${source.ahsa_records ?? 0} / ${source.rejected_records ?? 0}</b></span><span>مراجعات موقع<b>${source.location_review_count ?? 0}</b></span><span>جديدة / معدلة / دون تغيير<b>${source.new_records ?? 0} / ${source.updated_records ?? 0} / ${source.unchanged_records ?? 0}</b></span></div></details><div class="source-card-actions" data-role="admin,analyst"><button class="button button-quiet" data-sync="${safe(source.key)}">مزامنة الآن</button><button class="button button-quiet" data-interval="${safe(source.key)}" data-current-interval="${source.interval}">تعديل الجدول</button><button class="toggle ${source.enabled ? "on" : ""}" title="${source.enabled ? "المصدر مفعّل" : "المصدر متوقف"}" aria-label="تفعيل أو إيقاف المصدر" data-toggle="${safe(source.key)}" data-enabled="${source.enabled}"></button></div></article>`).join("");
    document.querySelectorAll("[data-source-opportunities]").forEach(panel => { panel.addEventListener("toggle", () => { if (panel.open && !sourceOpportunityCache.has(panel.dataset.sourceOpportunities)) loadSourceOpportunities(panel.dataset.sourceOpportunities, panel); }); panel.querySelector(".source-opportunity-more").onclick = () => loadSourceOpportunities(panel.dataset.sourceOpportunities, panel, false); });
    document.querySelectorAll("[data-sync]").forEach(button => button.onclick = () => syncOne(button.dataset.sync, button));
    document.querySelectorAll("[data-toggle]").forEach(button => button.onclick = () => toggleSource(button));
    document.querySelectorAll("[data-interval]").forEach(button => button.onclick = () => changeSourceInterval(button)); applyRoleVisibility();
  } catch (error) { toast(error.message); }
}

async function loadJobs() {
  try { const jobs = await api("/api/admin/jobs"); $("emptyJobs").classList.toggle("show", !jobs.length); const names = Object.fromEntries(state.sources.map(source => [source.id, source.name]));
    $("jobRows").innerHTML = jobs.map(job => `<tr><td>${safe(names[job.source_id] || "مصدر")}</td><td>${date(job.started_at)}</td><td><span class="tag ${job.status !== "SUCCESS" ? "pending" : ""}">${safe(statusLabel(job.status))}</span></td><td>${Number(job.pages_scanned || 0).toLocaleString("en-US-u-nu-latn")}</td><td>${Number(job.raw_count || 0).toLocaleString("en-US-u-nu-latn")}</td><td>${Number(job.ahsa_count || 0).toLocaleString("en-US-u-nu-latn")}</td><td>${Number(job.new_count || 0).toLocaleString("en-US-u-nu-latn")}</td><td>${Number(job.update_count || 0).toLocaleString("en-US-u-nu-latn")}</td></tr>`).join("");
  } catch (error) { toast(error.message); }
}

async function loadReview() {
  try {
    const [duplicates, merged, errors, raw, conflicts, taxonomy, locations, validation] = await Promise.all([api("/api/admin/duplicates"), api("/api/admin/duplicates/merged"), api("/api/admin/errors"), api("/api/admin/raw-records?limit=30"), api("/api/admin/conflicts?conflict_type=FIELD_VALUE_CONFLICT"), api("/api/admin/conflicts?conflict_type=TAXONOMY_CONFLICT"), api("/api/admin/location-reviews"), api("/api/admin/validation-report")]);
    const metricNames = { total_master_opportunities: "الفرص الموحدة", total_source_records: "سجلات المصادر", masters_with_multiple_sources: "فرص متعددة المصادر", duplicate_candidates_pending: "تكرارات معلقة", location_reviews_pending: "مراجعات الموقع", qualification_reviews_pending: "مراجعات التأهيل", opportunity_locations: "مواقع الفرص", missing_reference_number: "فرص بلا رقم مرجعي", missing_deadline: "فرص بلا موعد نهائي", missing_area: "فرص بلا مساحة منشورة", missing_owner: "فرص بلا جهة مالكة", low_location_confidence: "ثقة موقع منخفضة", low_data_quality: "جودة بيانات منخفضة", open_conflicts: "تعارضات مفتوحة", taxonomy_conflicts: "تعارضات التصنيف", field_conflicts: "تعارضات القيم", taxonomy_mappings: "قواعد التصنيف", discovered_content_items: "مواد مصدر مكتشفة", expired_opportunities: "فرص منتهية", possibly_removed_opportunities: "فرص ربما أزيلت", incomplete_sources: "مصادر جمعها غير مكتمل", limited_coverage_sources: "مصادر بتغطية محدودة", source_errors: "أخطاء المصادر" };
    $("validationMetrics").innerHTML = Object.entries(validation.metrics || {}).map(([key, value]) => `<div class="validation-metric"><span>${safe(metricNames[key] || key.replaceAll("_", " "))}</span><b>${Number(value || 0).toLocaleString("en-US-u-nu-latn")}</b></div>`).join("");
    const candidateIds = [...new Set(duplicates.flatMap(item => [item.left_id, item.right_id]))];
    const candidateRows = await Promise.all(candidateIds.map(async id => { try { return [id, await api(`/api/opportunities/${id}`)]; } catch { return [id, null]; } }));
    const candidateById = Object.fromEntries(candidateRows);
    const compareFields = [["العنوان", "title"], ["الجهة", "owner"], ["الرقم المرجعي", "reference"], ["المساحة", "area"], ["الموقع", "location"], ["تاريخ الإغلاق", "deadline"], ["المصدر", "sourceName"]];
    const displayValue = (record, key) => { const value = key === "sourceName" ? record?.sources?.map(source => source.name).filter(Boolean).join("، ") : record?.[key]; return value === null || value === undefined || value === "" ? "غير مسجل" : key === "area" ? `${Number(value).toLocaleString("en-US-u-nu-latn")} م²` : key === "deadline" ? date(value) : String(value); };
    const comparisonCell = (record, key) => { const value = displayValue(record, key); return `<span class="compare-value ${value === "غير مسجل" ? "is-missing" : ""}">${safe(value)}</span>`; };
    const pendingHTML = duplicates.map(item => {
      const evidence = item.explanation || {}, left = candidateById[item.left_id] || {title:item.left_title}, right = candidateById[item.right_id] || {title:item.right_title};
      const rows = compareFields.map(([label, key]) => { const a = displayValue(left, key), b = displayValue(right, key), same = a !== "غير مسجل" && b !== "غير مسجل" && a.trim().toLocaleLowerCase() === b.trim().toLocaleLowerCase(); return `<div class="compare-row ${same ? "is-same" : a === "غير مسجل" || b === "غير مسجل" ? "has-missing" : "is-different"}"><b>${label}</b>${comparisonCell(left, key)}${comparisonCell(right, key)}</div>`; }).join("");
      const positive = (evidence.positive_evidence || []).map(value => `<li>${safe(value)}</li>`).join(""), negative = (evidence.contradicting_evidence || []).map(value => `<li>${safe(value)}</li>`).join("");
      return `<article class="duplicate-case"><header class="duplicate-case-head"><div><b>مقارنة سجلي فرصة</b><small>رقم المراجعة ${Number(item.id).toLocaleString("en-US-u-nu-latn")}</small></div><span class="match-score">درجة التشابه ${Math.round(item.score * 100)}٪</span></header><div class="compare-head"><span>الحقل</span><b>السجل الأول</b><b>السجل الثاني</b></div><div class="compare-matrix">${rows}</div>${positive || negative ? `<details class="review-evidence"><summary>أدلة المطابقة والاختلاف</summary><ul>${positive}${negative}</ul></details>` : ""}<div class="review-actions"><button data-dup="${item.id}" data-action="merge">دمج السجلين</button><button data-dup="${item.id}" data-action="reject">ليسا مكررين</button></div></article>`;
    }).join("");
    const mergedHTML = merged.map(item => `<article class="review-line"><strong>دمج مسجل</strong>${safe(item.left_title)}<br>↔ ${safe(item.right_title)}<div class="review-actions"><button data-undo-dup="${item.id}">تراجع عن الدمج</button></div></article>`).join("");
    $("duplicateList").innerHTML = pendingHTML + mergedHTML || '<div class="loading">لا توجد حالات تكرار للمراجعة.</div>';
    $("locationReviewList").innerHTML = locations.length ? locations.map(item => `<article class="review-line location-case"><header class="review-case-head"><div><b>${safe(item.title)}</b><small>${safe(item.source)} · ${safe(item.sector || "تصنيف غير محدد")}</small></div><span class="match-score">ثقة الاستدلال ${Math.round(item.score * 100)}٪</span></header><dl class="location-facts"><div><dt>الموقع كما ورد</dt><dd>${safe(item.location || "غير محدد")}</dd></div><div><dt>الموقع المستنتج</dt><dd>الأحساء · قيد التأكيد</dd></div><div><dt>طريقة الاستدلال</dt><dd>${safe(item.reason || "مطابقة نصية")}</dd></div><div><dt>الدليل</dt><dd>${safe(item.evidence || "لا يوجد نص داعم")}</dd></div></dl>${item.url ? `<a class="source-action" href="${safe(item.url)}" target="_blank" rel="noreferrer">فتح المصدر الرسمي ↗</a>` : ""}<div class="review-actions"><button data-location="${item.id}" data-action="accept">تأكيد ارتباط الأحساء</button><button data-location="${item.id}" data-action="reject">رفض المطابقة المحلية</button></div></article>`).join("") : '<div class="loading">لا توجد حالات موقع معلقة.</div>';
    $("errorList").innerHTML = errors.length ? errors.map(item => `<article class="review-line"><strong>${safe(item.category)} · ${date(item.date)}</strong>${safe(item.message)}</article>`).join("") : '<div class="loading">لا توجد أخطاء مسجلة.</div>';
    const renderFieldConflicts = rows => rows.length ? rows.map(item => `<article class="review-line conflict-case"><header class="review-case-head"><div><b>${safe(item.title)}</b><small>الحقل: ${safe(item.field)} · ${date(item.date)}</small></div></header><div class="conflict-values"><div><span>القيمة الحالية</span><b>${safe(item.selected || "غير مسجل")}</b></div><div><span>القيمة في المصدر</span><b>${safe(item.conflicting || "غير مسجل")}</b></div></div><p class="provenance">المصدر: ${safe(item.source)}</p><div class="review-actions"><button data-conflict="${item.id}" data-action="keep">الإبقاء على الحالية</button><button data-conflict="${item.id}" data-action="use_source">اعتماد قيمة المصدر</button></div></article>`).join("") : '<div class="loading">لا توجد حالات معلقة.</div>';
    const renderTaxonomyConflicts = rows => rows.length ? rows.map(item => `<article class="review-line conflict-case"><header class="review-case-head"><div><b>${safe(item.title)}</b><small>${date(item.date)}</small></div></header><div class="conflict-values taxonomy-values"><div><span>التصنيف الحالي</span><b>${safe(item.selected || "غير مصنف")}</b></div><div><span>تصنيف المصدر</span><b>${safe(item.conflicting || "غير مصنف")}</b></div></div><p class="provenance">المصدر: ${safe(item.source)}</p><div class="review-actions"><button data-conflict="${item.id}" data-action="keep">الإبقاء على التصنيف الحالي</button><button data-conflict="${item.id}" data-action="use_source">اعتماد تصنيف المصدر</button></div></article>`).join("") : '<div class="loading">لا توجد حالات معلقة.</div>';
    $("conflictList").innerHTML = renderFieldConflicts(conflicts); $("taxonomyList").innerHTML = renderTaxonomyConflicts(taxonomy);
    $("rawList").innerHTML = raw.length ? raw.map(item => `<div class="raw-line"><span>${safe(item.source)} · ${safe(item.title)}</span><a href="${safe(item.url)}" target="_blank" rel="noreferrer">فتح المصدر ↗</a></div>`).join("") : '<div class="loading">لم تُجمع سجلات حتى الآن.</div>';
    document.querySelectorAll("[data-dup]").forEach(button => button.onclick = async () => { try { await api(`/api/admin/duplicates/${button.dataset.dup}/${button.dataset.action}`, { method: "POST" }); toast("تم حفظ قرار المراجعة"); loadReview(); } catch (error) { toast(error.message); } });
    document.querySelectorAll("[data-undo-dup]").forEach(button => button.onclick = async () => { try { await api(`/api/admin/duplicates/${button.dataset.undoDup}/undo`, { method: "POST" }); toast("تم التراجع عن الدمج"); loadReview(); } catch (error) { toast(error.message); } });
    document.querySelectorAll("[data-location]").forEach(button => button.onclick = async () => { try { await api(`/api/admin/location-reviews/${button.dataset.location}/${button.dataset.action}`, { method: "POST" }); toast("تم حفظ قرار الموقع"); loadReview(); } catch (error) { toast(error.message); } });
    document.querySelectorAll("[data-conflict]").forEach(button => button.onclick = async () => { try { await api(`/api/admin/conflicts/${button.dataset.conflict}/${button.dataset.action}`, { method: "POST" }); toast("تم حفظ قرار التعارض"); loadReview(); } catch (error) { toast(error.message); } });
  } catch (error) { toast(error.message); }
}

async function loadAlerts() {
  try {
    const status = $("alertStatus").value, alerts = await api(`/api/admin/alerts?status=${encodeURIComponent(status)}`);
    $("emptyAlerts").classList.toggle("show", !alerts.length); $("alertCount").textContent = alerts.length.toLocaleString("en-US-u-nu-latn");
    const sourceNames = Object.fromEntries(state.sources.map(source => [source.id, source.name]));
    const alertNames = { OPPORTUNITY_CREATED: "فرصة جديدة", OPPORTUNITY_UPDATED: "تحديث فرصة", SOURCE_FAILED: "تعذّر تحديث مصدر", SOURCE_WARNING: "تحذير في مصدر", BACKUP_SUCCEEDED: "اكتمل النسخ الاحتياطي", BACKUP_FAILED: "تعذّر النسخ الاحتياطي", SOURCE_RECOVERED: "عاد المصدر للعمل" };
    const severityNames = { INFO: "معلومة", WARNING: "تنبيه", HIGH: "أهمية عالية", CRITICAL: "حرج" };
    $("alertsList").innerHTML = alerts.map(alert => {
      const payload = alert.payload && typeof alert.payload === "object" ? alert.payload : {}, critical = ["CRITICAL", "HIGH"].includes(String(alert.severity).toUpperCase());
      const sourceName = sourceNames[alert.source_id] || (payload.primary_source ? String(payload.primary_source) : "النظام");
      let description = payload.title || "";
      if (alert.type === "SOURCE_FAILED" || alert.type === "SOURCE_WARNING") description = `${statusLabel(payload.status)}${payload.consecutive_failures ? ` · ${Number(payload.consecutive_failures).toLocaleString("en-US-u-nu-latn")} محاولات متتالية` : ""}`;
      else if (alert.type.startsWith("BACKUP_")) description = payload.size_bytes ? `حجم النسخة ${Math.round(Number(payload.size_bytes) / 1048576 * 10) / 10} ميغابايت` : "حالة النسخ الاحتياطي";
      const facts = [payload.owner, payload.sector, payload.location, payload.deadline && `آخر موعد ${payload.deadline}`].filter(Boolean).map(safe).join(" · ");
      const link = payload.official_url ? `<a href="${safe(payload.official_url)}" target="_blank" rel="noreferrer">فتح المصدر الأصلي ↗</a>` : "";
      return `<article class="alert-card ${critical ? "critical" : ""}"><span class="alert-mark" aria-hidden="true">◇</span><div class="alert-copy"><b>${safe(alertNames[alert.type] || statusLabel(alert.type))} · ${safe(severityNames[alert.severity] || alert.severity)}</b><p>${safe(sourceName)}${description ? ` · ${safe(description)}` : ""}</p>${facts ? `<small>${facts}</small>` : ""}${link}<small class="alert-time">${date(alert.created_at)}</small></div><div class="alert-actions">${alert.status === "OPEN" ? `<button data-alert="${alert.id}" data-action="acknowledge">تم الاطلاع</button>` : ""}${alert.status !== "RESOLVED" ? `<button data-alert="${alert.id}" data-action="resolve">تمت المعالجة</button>` : ""}</div></article>`;
    }).join("");
    document.querySelectorAll("[data-alert]").forEach(button => button.onclick = async () => { try { await api(`/api/admin/alerts/${button.dataset.alert}/${button.dataset.action}`, { method: "POST" }); loadAlerts(); } catch (error) { toast(error.message); } });
  } catch (error) { toast(error.message); }
}

async function loadAdmin() {
  try {
    const [system, schedules, users] = await Promise.all([api("/api/admin/system-status"), api("/api/admin/schedules"), api("/api/admin/users")]);
    const labels = { api: "واجهة المنصة", database: "قاعدة البيانات", redis: "قائمة المهام", workers: "العاملون", scheduler: "الجدولة", queue_depth: "مهام بالانتظار", database_size_bytes: "حجم قاعدة البيانات", raw_observations: "سجلات المصدر", sync_jobs: "عمليات المزامنة", attachments_size_bytes: "حجم المرفقات", pool: "اتصالات قاعدة البيانات", last_backup: "آخر نسخة احتياطية" };
    const serviceValue = (key, value) => {
      if (value === null || value === undefined) return "غير متاح";
      if (key === "last_backup" && typeof value === "object") return `${statusLabel(value.status)}${value.completed_at ? ` · ${date(value.completed_at)}` : ""}`;
      if (key === "pool") return "سليم";
      if (typeof value === "object") return Array.isArray(value) ? `${value.length.toLocaleString("en-US-u-nu-latn")} عناصر` : "متاح";
      if (typeof value === "boolean") return value ? "نعم" : "لا";
      if (typeof value === "string" && ["ok", "ready", "healthy", "connected"].includes(value.toLowerCase())) return "سليم";
      if (key.endsWith("_bytes") && Number.isFinite(Number(value))) return `${(Number(value) / 1048576).toFixed(1)} ميغابايت`;
      return String(value);
    };
    $("systemStatus").innerHTML = Object.entries(system).map(([key, value]) => `<div class="admin-metric"><span>${safe(labels[key] || key.replaceAll("_", " "))}</span><b>${safe(serviceValue(key, value))}</b>${value && typeof value === "object" || key === "pool" ? `<details class="admin-tech"><summary>تفاصيل تقنية</summary><pre dir="ltr">${safe(typeof value === "object" ? JSON.stringify(value, null, 2) : String(value))}</pre></details>` : ""}</div>`).join("");
    $("scheduleList").innerHTML = (schedules.sources || []).map(item => `<div class="schedule-row"><b>${safe(state.sources.find(source => source.key === item.source_key)?.name || item.source_key)}</b><span>${item.enabled ? "مفعّل" : "متوقف"}</span><span>كل ${Number(item.interval_minutes).toLocaleString("en-US-u-nu-latn")} دقيقة</span><span>آخر تشغيل: ${date(item.last_run)}</span><span>الحالة: ${safe(statusLabel(item.health))}</span></div>`).join("") || '<div class="loading">لا توجد جداول مصادر.</div>';
    $("userList").innerHTML = users.map(user => `<div class="user-row"><b>${safe(user.display_name)}</b><span>${safe(user.email)}</span><span>${roleLabel(user.role)} · ${user.is_active ? "نشط" : "معطّل"}</span>${user.is_active && user.id !== state.user?.id ? `<button class="button button-quiet" data-disable-user="${user.id}">تعطيل الحساب</button>` : "<small>الحساب الحالي</small>"}</div>`).join("") || '<div class="loading">لا يوجد مستخدمون.</div>';
    document.querySelectorAll("[data-disable-user]").forEach(button => button.onclick = async () => { if (!window.confirm("سيُعطّل هذا الحساب وتُنهى جلساته الحالية. هل تريد المتابعة؟")) return; try { await api(`/api/admin/users/${button.dataset.disableUser}/disable?confirm=true`, { method: "POST" }); toast("تم تعطيل الحساب"); loadAdmin(); } catch (error) { toast(error.message); } });
  } catch (error) { toast(error.message); }
}

async function syncOne(key, button) {
  if (button) { button.disabled = true; button.textContent = "جارٍ التحديث…"; }
  toast("بدأت مزامنة المصدر؛ قد تستغرق لحظات.");
  try { const result = await api(`/api/admin/sources/${encodeURIComponent(key)}/sync`, { method: "POST" }); if (result.status === "QUEUED") { toast("أُضيفت المزامنة إلى قائمة الانتظار"); if (state.view === "activity") await loadJobs(); return; } toast(`اكتملت المزامنة: ${result.ahsa_count ?? 0} فرصة أحسائية · ${result.new_count ?? 0} جديدة${result.error ? " · " + result.error : ""}`); await loadDashboard(); if (state.view === "sources") await loadSources(); if (state.view === "activity") await loadJobs(); }
  catch (error) { toast(error.message); }
  finally { if (button) { button.disabled = false; button.textContent = "مزامنة الآن"; } }
}
async function syncAll() { try { const sources = state.sources.filter(source => source.enabled); for (const source of sources) await syncOne(source.key); await loadDashboard(); } catch (error) { toast(error.message); } }
async function toggleSource(button) { const enabled = button.dataset.enabled !== "true"; if (!window.confirm(enabled ? "تأكيد تفعيل هذا المصدر؟" : "تأكيد إيقاف هذا المصدر؟")) return; try { await api(`/api/admin/sources/${button.dataset.toggle}?enabled=${enabled}&confirm=true`, { method: "PATCH" }); await loadSources(); toast(enabled ? "تم تفعيل المصدر" : "تم إيقاف المصدر"); } catch (error) { toast(error.message); } }
function date(value) { return formatDateTimeLatin(value); }
async function showDetail(id) {
  try {
    const item = await api(`/api/opportunities/${id}`);
  $("modalBody").innerHTML = `<div class="detail-head"><div class="eyebrow">${safe(item.canonical_id)}</div><h2 id="modalTitle">${safe(item.title)}</h2><p>الجهة المالكة: ${safe(item.owner || "غير محددة")} · الحالة الموحدة: ${safe(statusLabel(item.status))}</p></div><div class="detail-grid">${[["القطاع", item.sector], ["النشاط", item.activity], ["النشاط الفرعي", item.sub_activity], ["نوع الفرصة", item.type], ["نموذج الاستثمار", item.investment_model], ["نوع الأصل أو الموقع", item.asset_facility_type || "غير محدد"], ["الدولة", item.geography?.country], ["المنطقة", item.geography?.region], ["المحافظة", item.geography?.governorate], ["المدينة / الموقع", item.geography?.locality || (item.geography?.confirmed ? item.geography?.governorate : item.geography?.status_ar)], ["الحي", item.geography?.district], ["حالة الموقع الجغرافي", item.geography?.status_ar], ["سبب المراجعة", item.geography?.reason], ["وصف الموقع", item.location], ["المساحة", item.area ? Number(item.area).toLocaleString("en-US") + " م²" : null], ["القيمة الاستثمارية", item.investment_value], ["مدة العقد", item.duration ? item.duration + " سنة" : null], ["آخر موعد للتقديم", item.deadline], ["الرقم المرجعي", item.reference], ["مستوى ثقة الموقع", Math.round((item.confidence || 0) * 100) + "٪"], ["عدد المصادر", item.source_count]].map(([label, value]) => `<div class="detail-field"><small>${label}</small><b>${safe(value || "غير منشور")}</b></div>`).join("")}</div><div class="detail-sources"><h3>النشر حسب المصدر</h3>${(item.sources || []).map(source => `<article><a href="${safe(source.url)}" target="_blank" rel="noreferrer">${safe(source.publication_platform || source.name)} · فتح الإعلان الأصلي ↗</a><small class="source-location-evidence">جهة النشر: ${safe(source.publishing_entity || "غير محددة في سجل المصدر")} · مشغل المنصة: ${safe(source.source_operator || "غير محدد")}</small><small class="source-location-evidence">الحالة المعيارية: ${safe(statusLabel(source.canonical_status))} · النص الخام: ${safe(source.raw_status || "غير محدد")}</small>${source.status_review_flags?.length ? `<small class="source-location-evidence">تنبيه مراجعة: ${safe(source.status_review_flags.join("، "))}</small>` : ""}${source.raw_location ? `<small class="source-location-evidence">الموقع كما ورد: ${safe(source.raw_location)}</small>` : ""}</article>`).join("") || "—"}</div><div class="detail-changes"><h3>سجل التغييرات</h3>${item.changes?.length ? item.changes.map(change => `<p>${safe(change.field)}: ${safe(change.before || "—")} ← ${safe(change.after || "—")} · ${date(change.date)}</p>`).join("") : "<p>لا توجد تغييرات مسجلة.</p>"}</div>`;
    $("modal").classList.add("show"); $("modal").setAttribute("aria-hidden", "false"); $("modalClose").focus();
  } catch (error) { toast(error.message); }
}

$("modalClose").onclick = () => { $("modal").classList.remove("show"); $("modal").setAttribute("aria-hidden", "true"); };
$("modal").onclick = event => { if (event.target === $("modal")) $("modalClose").click(); };
document.addEventListener("keydown", event => {
  const modal = $("modal");
  if (!modal.classList.contains("show")) return;
  if (event.key === "Escape") { $("modalClose").click(); return; }
  if (event.key !== "Tab") return;
  const focusable = [...modal.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')].filter(element => element.getClientRects().length);
  if (!focusable.length) { event.preventDefault(); $("modalClose").focus(); return; }
  const first = focusable[0], last = focusable[focusable.length - 1];
  if (event.shiftKey && (document.activeElement === first || !modal.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && (document.activeElement === last || !modal.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
});
$("searchInput").oninput = () => { state.opportunityPage = 0; clearTimeout(state.searchTimer); state.searchTimer = setTimeout(() => { updateOpportunityUrl(); loadOpportunities(); }, 250); };
function updateOpportunityUrl() {
  const params = new URLSearchParams(); params.set("view", "opportunities");
  for (const [key,id] of [["sector","sectorFilter"],["activity","activityFilter"],["sub_activity","subActivityFilter"],["subsector","subsectorFilter"],["status","statusFilter"],["lifecycle","lifecycleFilter"],["owner","ownerFilter"],["source","sourceFilter"],["location","locationFilter"],["opportunity_type","typeFilter"],["investment_model","investmentModelFilter"],["asset_facility_type","assetFacilityTypeFilter"]]) {
    const value = $(id).value;
    if (key === "sector" && value === aggregatedOtherSectorValue) {
      const grouped = new URLSearchParams(location.search).get("sector_values"); if (grouped) params.set("sector_values", grouped);
    } else if (value) params.set(key,value);
  }
  for (const key of ["period","deadline_after","deadline_before","created_after","created_before","map_ids"]) { const value = new URLSearchParams(location.search).get(key); if (value) params.set(key,value); }
  const q = $("searchInput").value; if (q) params.set("q",q);
  history.replaceState(null,"",`${location.pathname}?${params.toString()}`);
}
["sectorFilter","activityFilter","subActivityFilter","subsectorFilter","statusFilter","lifecycleFilter","ownerFilter","sourceFilter","locationFilter","typeFilter","investmentModelFilter","assetFacilityTypeFilter"].forEach(id => $(id).addEventListener("change", () => { state.opportunityPage = 0; updateOpportunityUrl(); loadOpportunities(); }));
$("previousPage").onclick = () => { if (state.opportunityPage > 0) { state.opportunityPage--; loadOpportunities(); } };
$("nextPage").onclick = () => { state.opportunityPage++; loadOpportunities(); };
$("resetFilters").onclick = () => { $("searchInput").value = ""; for (const id of ["sectorFilter","activityFilter","subActivityFilter","subsectorFilter","statusFilter","lifecycleFilter","ownerFilter","sourceFilter","locationFilter","typeFilter","investmentModelFilter","assetFacilityTypeFilter"]) $(id).value = ""; state.opportunityPage = 0; state.opportunityFiltersInitialized = true; history.replaceState(null,"",`${location.pathname}?view=opportunities`); loadOpportunities(); };
$("alertStatus").onchange = loadAlerts; $("adminRefresh").onclick = loadAdmin;
document.querySelectorAll("[data-operation]").forEach(button => button.onclick = async () => { const action = button.dataset.operation; if (!window.confirm(action === "pause-schedules" ? "إيقاف جداول المزامنة لجميع المصادر؟" : "استئناف جداول المزامنة لجميع المصادر؟")) return; try { await api(`/api/admin/operations/${action}`, { method: "POST" }); toast("تم تحديث حالة الجداول"); loadAdmin(); } catch (error) { toast(error.message); } });
$("userCreateForm").onsubmit = async event => { event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget).entries()); try { await api("/api/admin/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); event.currentTarget.reset(); toast("تم إنشاء المستخدم"); loadAdmin(); } catch (error) { toast(error.message); } };
$("refreshBtn").onclick = () => { loadDashboard(); if (state.view === "data-dashboard") loadDataDashboard(); toast("تم تحديث لوحة المؤشرات"); };
["syncAll", "syncAll2", "syncAll3", "firstSync"].forEach(id => { if ($(id)) $(id).onclick = syncAll; });
$("alertStatus").value = "OPEN";
$("loginDialog").addEventListener("click", event => { if (event.target === $("loginDialog")) $("loginDialog").close(); });
async function changeSourceInterval(button) { const value = Number(window.prompt("الفاصل بالدقائق", button.dataset.currentInterval)); if (!Number.isInteger(value) || value < 15 || value > 10080) return; if (!window.confirm("تأكيد تحديث جدول هذا المصدر؟")) return; try { await api(`/api/admin/sources/${encodeURIComponent(button.dataset.interval)}?interval_minutes=${value}&confirm=true`, { method: "PATCH" }); toast("تم تحديث الجدول"); await loadSources(); } catch (error) { toast(error.message); } }
async function initialize() {
  try { const response = await fetch("/api/auth/me", { credentials: "same-origin" }); if (response.ok) state.user = (await response.json()).user; } catch {}
  setUserLabel(); applyRoleVisibility();
  ["syncAll", "syncAll2", "syncAll3", "firstSync"].forEach(id => { if ($(id)) $(id).onclick = syncAll; });
  const initialView = new URLSearchParams(location.search).get("view");
  if (initialView && $("view-" + initialView)) view(initialView);
  else if (!initialView) await loadDashboard();
}
initialize();


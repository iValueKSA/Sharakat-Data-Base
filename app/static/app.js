const state = { sources: [], items: [], view: "overview", user: null, filtersLoaded: false, opportunityPage: 0, searchTimer: null, dataDashboardLoaded: false, dataFilters: {}, filterOptionIds: {}, dashboardDate: null, lastDashboardData: null, sidebarReturnFocus: null, tableGeo: null, dashGeo: null, sortBy: "", sortOrder: "desc" };
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
  const dateOnly = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly) return `${dateOnly[1]}/${dateOnly[2]}/${dateOnly[3]}`;
  if (/^\d{4}-\d{2}-\d{2}T/.test(raw) && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)) return raw;
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.valueOf())) return raw;
  const parts = new Intl.DateTimeFormat("en-US-u-ca-gregory-nu-latn", { timeZone: "Asia/Riyadh", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(parsed);
  const part = type => parts.find(item => item.type === type)?.value || "00";
  return `${part("year")}/${part("month")}/${part("day")}`;
};
const saudiDateKey = (value = new Date()) => {
  const parts = new Intl.DateTimeFormat("en-CA-u-ca-gregory-nu-latn", { timeZone: "Asia/Riyadh", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(value);
  const part = type => parts.find(item => item.type === type)?.value || "00";
  return `${part("year")}-${part("month")}-${part("day")}`;
};
const businessDateKey = value => {
  if (!value) return null;
  const raw = toLatinDigits(value);
  const dateOnly = raw.match(/^(\d{4}-\d{2}-\d{2})$/);
  if (dateOnly) return dateOnly[1];
  if (/^\d{4}-\d{2}-\d{2}T/.test(raw) && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.valueOf()) ? null : saudiDateKey(parsed);
};
const addBusinessDays = (key, days) => {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
};
const formatDateTimeLatin = value => {
  if (!value) return "—";
  const raw = toLatinDigits(value), parsed = new Date(raw);
  if (Number.isNaN(parsed.valueOf())) return raw;
  const time = new Intl.DateTimeFormat("ar-SA-u-ca-gregory-nu-latn", { timeZone: "Asia/Amman", hour: "numeric", minute: "2-digit", hour12: true }).format(parsed);
  return `${formatDateLatin(parsed)} · ${toLatinDigits(time)}`;
};
window.AHDAFormatters = Object.freeze({ number: formatNumberLatin, integer: formatIntegerLatin, percent: formatPercentLatin, date: formatDateLatin, dateTime: formatDateTimeLatin, businessDateKey, latinDigits: toLatinDigits });
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
  "waha-development": { path: null, alt: "شركة واحة للتنمية والتطوير", fallback: "واحة", status: "OFFICIAL_SOURCE_LOGO_MISSING" },
  "rcjy-investment-opportunities": { path: null, alt: "فرص الهيئة الملكية للجبيل وينبع", fallback: "RCJY", status: "OFFICIAL_SOURCE_LOGO_MISSING" },
};
function sourceLogoMarkup(key, compact = false) {
  const logo = SOURCE_LOGOS[key] || { path: null, alt: "مصدر رسمي", fallback: "مصدر", status: "OFFICIAL_SOURCE_LOGO_MISSING" };
  const label = safe(logo.alt), fallback = safe(logo.fallback);
  return `<span class="source-logo ${compact ? "source-logo-compact" : ""}" role="img" aria-label="${label}" title="${label}">${logo.path ? `<img src="${logo.path}" alt="${label}" loading="lazy" decoding="async" onerror="this.hidden=true;this.nextElementSibling.hidden=false">` : ""}<span class="source-logo-fallback" ${logo.path ? "hidden" : ""} aria-hidden="true">${fallback}</span></span>`;
}
const sourceOpportunityCache = new Map();
function sourceAnnouncementMarkup(source) {
  if (source.url) {
    const note = source.link_health === "REDIRECTED_VALID" ? " (تم التحقق بعد إعادة التوجيه)"
      : source.link_health === "VALID" ? " (رابط متحقق)"
      : source.link_health === "UNVERIFIED" ? " (لم يُتحقق من الرابط بعد)" : "";
    return `<a href="${safe(source.url)}" target="_blank" rel="noreferrer">${safe(source.publication_platform || source.name)} · فتح الإعلان الأصلي ↗</a>${note ? `<small class="source-location-evidence">${safe(note)}</small>` : ""}`;
  }
  const message = source.link_health === "UNAVAILABLE_CONFIRMED"
    ? "الإعلان غير متاح حاليًا على المصدر"
    : source.link_health === "GENERIC_SOURCE_PAGE"
      ? "لا تتوفر صفحة تفاصيل للفرصة؛ لم تُعرض صفحة المصدر العامة كرابط للإعلان"
    : source.link_health === "TEMPORARILY_UNVERIFIABLE"
      ? "تعذر التحقق من رابط الإعلان حاليًا"
      : source.link_health === "INVALID"
        ? "رابط الإعلان الأصلي غير صالح"
      : "رابط الإعلان الأصلي غير متوفر";
  return `<span class="source-link-unavailable" role="status">${safe(source.publication_platform || source.name)} · ${message}</span>`;
}
function renderSourceOpportunity(sourceKey, item) {
  const source = (item.sources || []).find(entry => entry.key === sourceKey);
  const sourceUrl = source?.url;
  return `<article class="source-opportunity-row">${sourceLogoMarkup(sourceKey, true)}<div class="source-opportunity-copy"><button class="source-opportunity-title" type="button" data-detail="${item.id}">${safe(item.title)}</button><small>${safe(item.reference || "غير محدد" || "")} · ${safe(item.owner || "جهة غير محددة")}</small></div>${sourceUrl ? `<a class="source-opportunity-link" href="${safe(sourceUrl)}" target="_blank" rel="noreferrer" aria-label="فتح الإعلان الأصلي: ${safe(item.title)}" title="فتح الإعلان الأصلي">↗</a>` : ""}</article>`;
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
  if (role === "viewer") document.querySelectorAll("[data-view='alerts'],[data-view='admin'],[data-view='activity']").forEach(element => { element.hidden = true; });
  if ((state.view === "admin" && role !== "admin") || (state.view === "alerts" && role !== "admin") || (state.view === "review" && !["admin", "analyst", "viewer"].includes(role))) view("overview");
}
function setUserLabel() {
  $("userLabel").textContent = state.user ? `${state.user.display_name || state.user.email} · ${roleLabel(state.user.role)}` : "زائر";
  $("userButton").title = state.user ? "الحساب الشخصي" : "تسجيل الدخول";
  $("userButton").setAttribute("aria-label", state.user ? `الحساب الشخصي: ${state.user.display_name || state.user.email}` : "تسجيل الدخول");
  if (!state.user) closeAccountMenu();
}

const pageNames = { overview: "نظرة عامة", "data-dashboard": "لوحة عرض البيانات", opportunities: "الفرص الاستثمارية", sources: "المصادر الرسمية", activity: "سجل المزامنة", review: "مراجعة البيانات", alerts: "التنبيهات", admin: "الإدارة" };
function view(name) {
  const target = $("view-" + name); if (!target) return;
  const restricted = ({ review: ["admin", "analyst", "viewer"], alerts: ["admin"], admin: ["admin"] })[name];
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
  const menu = $("accountMenu"), opening = menu.hidden;
  menu.hidden = !opening; $("userButton").setAttribute("aria-expanded", String(opening));
  if (opening) $("openChangePassword").focus();
};
function closeAccountMenu() { $("accountMenu").hidden = true; $("userButton").setAttribute("aria-expanded", "false"); }
$("openChangePassword").onclick = () => {
  closeAccountMenu(); $("changePasswordError").textContent = ""; $("changePasswordSuccess").textContent = "";
  $("changePasswordForm").reset(); $("changePasswordDialog").showModal(); $("currentPassword").focus();
};
$("logoutButton").onclick = async () => {
  closeAccountMenu();
  try { await api("/api/auth/logout", { method: "POST" }); state.user = null; setUserLabel(); applyRoleVisibility(); toast("تم تسجيل الخروج"); }
  catch (error) { toast(error.message); }
};
document.addEventListener("click", event => {
  if (!event.target.closest(".account-menu-container")) closeAccountMenu();
});
document.addEventListener("keydown", event => { if (event.key === "Escape") closeAccountMenu(); });
$("cancelPasswordChange").onclick = () => $("changePasswordDialog").close();
$("changePasswordDialog").addEventListener("close", () => {
  $("changePasswordForm").reset(); $("changePasswordError").textContent = ""; $("changePasswordSuccess").textContent = "";
});
document.querySelectorAll(".password-visibility").forEach(button => button.addEventListener("click", () => {
  const input = $(button.dataset.passwordTarget), visible = input.type === "password";
  input.type = visible ? "text" : "password";
  button.textContent = visible ? "إخفاء" : "إظهار";
  button.setAttribute("aria-label", visible ? "إخفاء كلمة المرور" : "إظهار كلمة المرور");
}));
$("changePasswordForm").onsubmit = async event => {
  event.preventDefault();
  const form = event.currentTarget, submit = $("saveNewPassword"), error = $("changePasswordError"), success = $("changePasswordSuccess");
  error.textContent = ""; success.textContent = "";
  const current = $("currentPassword").value, next = $("newPassword").value, confirm = $("confirmNewPassword").value;
  if (next !== confirm) { error.textContent = "كلمتا المرور غير متطابقتين"; $("confirmNewPassword").focus(); return; }
  if (next.length < 12 || next.length > 256) { error.textContent = "كلمة المرور الجديدة لا تستوفي متطلبات الأمان"; $("newPassword").focus(); return; }
  if (next === current) { error.textContent = "اختر كلمة مرور جديدة تختلف عن الحالية"; $("newPassword").focus(); return; }
  submit.disabled = true; submit.setAttribute("aria-busy", "true"); submit.textContent = "جارٍ الحفظ…";
  try {
    const response = await fetch("/api/auth/change-password", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", body: JSON.stringify({ current_password: current, new_password: next, confirm_new_password: confirm }) });
    let data = {}; try { data = await response.json(); } catch {}
    if (!response.ok) throw Error(data.detail || "تعذر تغيير كلمة المرور");
    form.reset(); success.textContent = "تم تغيير كلمة المرور بنجاح";
    submit.disabled = true;
    window.setTimeout(() => { if ($("changePasswordDialog").open) $("changePasswordDialog").close(); }, 1100);
  } catch (err) { error.textContent = err.message; }
  finally { if (submit.isConnected) { submit.disabled = false; submit.removeAttribute("aria-busy"); submit.textContent = "حفظ كلمة المرور الجديدة"; } }
};

async function loadDashboard() {
  try {
    const dashboard = await api("/api/dashboard");
    $("metricTotal").textContent = Number(dashboard.unique_master_opportunities || dashboard.total || 0).toLocaleString("en-US-u-nu-latn");
    $("metricActive").textContent = Number(dashboard.active || 0).toLocaleString("en-US-u-nu-latn");
    $("metricNew").textContent = Number(dashboard.new_today || 0).toLocaleString("en-US-u-nu-latn");
    $("metricSources").textContent = Number(dashboard.enabled_sources || 0).toLocaleString("en-US-u-nu-latn");
    $("metricReview").textContent = Number(dashboard.pending_review_total ?? (Number(dashboard.pending_duplicates || 0) + Number(dashboard.pending_location_reviews || 0))).toLocaleString("en-US-u-nu-latn");
    $("metricMasters").textContent = Number(dashboard.unique_master_opportunities || 0).toLocaleString("en-US-u-nu-latn");
    $("metricListings").textContent = Number(dashboard.source_listings_collected || 0).toLocaleString("en-US-u-nu-latn");
    $("metricMultiSource").textContent = Number(dashboard.multi_source_opportunities || 0).toLocaleString("en-US-u-nu-latn");
    $("navCount").textContent = Number(dashboard.total || 0).toLocaleString("en-US-u-nu-latn");
    $("reviewCount").textContent = Number(dashboard.pending_review_total ?? (Number(dashboard.pending_duplicates || 0) + Number(dashboard.pending_location_reviews || 0))).toLocaleString("en-US-u-nu-latn");
    const result = await api("/api/opportunities?limit=300"); state.items = result.items || [];
    const today = saudiDateKey(), closingCutoff = addBusinessDays(today, 30);
    const closingSoon = state.items.filter(item => { const deadline = businessDateKey(item.deadline); return deadline && deadline >= today && deadline <= closingCutoff; });
    $("metricClosing").textContent = closingSoon.length.toLocaleString("en-US-u-nu-latn");
    renderLatest(); renderDeadlines(); renderSectors(dashboard.sectors || []);
    await loadSources(true); renderSourceChart();
  } catch (error) { toast(error.message); }
}
function renderLatest() {
  const items = (state.items || []).slice(0, 5); $("emptyLatest").style.display = items.length ? "none" : "flex";
  $("latestOpportunities").innerHTML = items.map(item => `<div class="latest-item" data-detail="${item.id}" tabindex="0" role="button"><div><b>${safe(item.title)}</b><small>${safe(item.owner || "جهة غير محددة")} · ${safe(sectorLabel(item.sector))}</small></div><span class="latest-area">${item.area !== null && item.area !== undefined ? Number(item.area).toLocaleString("en-US") + " " + (item.area_unit || "م²") : "—"}</span></div>`).join("");
  bindDetailButtons();
}
function bindDetailButtons() { document.querySelectorAll("[data-detail]").forEach(element => { element.onclick = () => showDetail(element.dataset.detail); element.onkeydown = event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); showDetail(element.dataset.detail); } }; }); }
function renderDeadlines() {
  const container = $("upcomingDeadlines"), today = saudiDateKey();
  const items = (state.items || []).filter(item => { const deadline = businessDateKey(item.deadline); return deadline && deadline >= today; }).sort((a, b) => businessDateKey(a.deadline).localeCompare(businessDateKey(b.deadline))).slice(0, 4);
  container.innerHTML = items.length ? items.map(item => `<div class="deadline-item"><span class="deadline-date">${safe(formatDateLatin(item.deadline))}</span><span class="deadline-copy"><b>${safe(item.title)}</b><small>${safe(item.owner || "جهة غير محددة")}</small></span></div>`).join("") : '<div class="loading">لا توجد مواعيد قريبة منشورة.</div>';
}
function renderSectors(sectors) {
  const populated = sectors.filter(item => item.count);
  const priority = new Set(["sector:tourism", "sector:agriculture"]);
  const rows = [...populated.filter(item => !priority.has(item.canonical_id)).slice(0, 8), ...populated.filter(item => priority.has(item.canonical_id))];
  const max = Math.max(1, ...rows.map(item => item.count));
  $("sectorChart").innerHTML = rows.length ? rows.map(item => `<div class="sector-item">${safe(sectorLabel(item.name))} <b>${Number(item.count).toLocaleString("en-US-u-nu-latn")}</b><div class="sector-line"><span style="width:${Math.max(6, item.count / max * 100)}%"></span></div></div>`).join("") : '<div class="loading">ستظهر بيانات التوزيع عند توفر فرص مصنفة.</div>';
}
function renderSourceChart() {
  const sources = [...state.sources].sort((a, b) => (b.record_count || 0) - (a.record_count || 0));
  $("sourceChart").innerHTML = sources.length ? sources.map(source => `<div class="source-chart-item"><b>${safe(source.name)}</b><small>${safe(coverageLabel(source.coverage_status))}</small><strong>${Number(source.record_count || 0).toLocaleString("en-US-u-nu-latn")}</strong></div>`).join("") : '<div class="loading">لا توجد بيانات مصادر.</div>';
}

const dashFilterFields = [
  ["q", "dashSearch", "البحث"], ["period", "dashPeriod", "الفترة"], ["status", "dashStatus", "الحالة"], ["sector", "dashSector", "القطاع"],
  ["activity", "dashActivity", "النشاط"], ["sub_activity", "dashSubActivity", "النشاط الفرعي"], ["subsector", "dashSubsector", "القطاع الفرعي"], ["source", "dashSource", "المصدر"], ["owner", "dashOwner", "الجهة"], ["location", "dashLocation", "المدينة"], ["opportunity_type", "dashType", "نوع الفرصة"], ["investment_model", "dashInvestmentModel", "نموذج الاستثمار"], ["asset_facility_type", "dashAssetFacilityType", "نوع الأصل أو الموقع"], ["lifecycle", "dashLifecycle", "نطاق الحالة"],
  ["region_id", "dashRegionFilter", "المنطقة"], ["governorate_id", "dashGovernorateFilter", "المحافظة"]
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
      fillSelect("dashOwner", filters.owners, "كل الجهات", value => value, label => optionId("owners", label)); fillSelect("dashLocation", filters.locations, "جميع المدن", value => value, label => optionId("locations", label)); fillSelect("dashType", filters.types, "كل الأنواع", opportunityTypeLabel, label => optionId("types", label)); fillSelect("dashInvestmentModel", filters.investment_models || [], "كل نماذج الاستثمار", value => value, label => optionId("investment_models", label)); fillSelect("dashAssetFacilityType", filters.asset_facility_types || [], "كل أنواع الأصول والمواقع", value => value, label => optionId("asset_facility_types", label)); fillSelect("dashSubsector", filters.subsectors || [], "كل القطاعات الفرعية", value => value, label => optionId("subsectors", label));
      if (window.NationalGeographyUI) state.dashGeo = await window.NationalGeographyUI.init("dash", () => loadDataDashboard());
      const params = new URLSearchParams(location.search);
      for (const [key, id] of dashFilterFields) if (params.has(key)) {
        if (key === "q") $(id).value = params.get(key);
        else restoreFilterValue($(id), params.get(key), ({ sector: "sectors", activity: "activities", status: "statuses", owner: "owners", location: "locations", opportunity_type: "types", investment_model: "investment_models", asset_facility_type: "asset_facility_types", subsector: "subsectors", sub_activity: "sub_activities" })[key]);
      }
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
document.querySelectorAll("#view-data-dashboard .rd-filter-grid select").forEach(select => { if (!["dashRegionFilter", "dashGovernorateFilter", "dashLocation"].includes(select.id)) select.addEventListener("change", loadDataDashboard); });
let dashSearchTimer;
$("dashSearch").addEventListener("input", () => { clearTimeout(dashSearchTimer); dashSearchTimer = setTimeout(loadDataDashboard, 250); });
$("dashReset").onclick = async () => { for (const [, id] of dashFilterFields) $(id).value = id === "dashPeriod" ? "all" : ""; await state.dashGeo?.reset(); loadDataDashboard(); };
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
  const bucket = event.target.closest("[data-deadline-bucket]"); if (bucket) { if (bucket.dataset.deadlineBucket === "no_deadline") goToOpportunities({ lifecycle: "active", deadline_status: "without_reliable_deadline" }); else { const limits = { "7d": [0,7], "8_14d": [8,14], "15_30d": [15,30], over_30d: [31,null] }[bucket.dataset.deadlineBucket]; if (limits && state.dashboardDate) { const [from,to] = limits, addDays = days => { const [year,month,day] = state.dashboardDate.split("-").map(Number), value = new Date(Date.UTC(year,month-1,day+days)); return value.toISOString().slice(0,10); }; const extra = { lifecycle: "active", deadline_after: addDays(from) }; if (to !== null) extra.deadline_before = addDays(to); goToOpportunities(extra); } } }
});

async function loadOpportunities() {
  try {
    if (!state.filtersLoaded) {
      const filters = await api("/api/filters");
      state.filterOptionIds = filters.option_ids || state.filterOptionIds;
      fillSelect("sectorFilter", filters.sectors, "كل القطاعات", sectorLabel, label => optionId("sectors", label)); fillSelect("activityFilter", filters.activities || [], "كل الأنشطة", value => value, label => optionId("activities", label)); fillSelect("subActivityFilter", filters.sub_activities || [], "كل الأنشطة الفرعية", value => value, label => optionId("sub_activities", label)); fillSelect("subsectorFilter", filters.subsectors || [], "كل القطاعات الفرعية", value => value, label => optionId("subsectors", label));
      fillSelect("statusFilter", filters.statuses, "كل الحالات", statusLabel, label => optionId("statuses", label));
      fillSelect("ownerFilter", filters.owners, "كل الجهات", value => value, label => optionId("owners", label)); fillSelect("sourceFilter", filters.sources, "كل المصادر", item => item.name, item => item.key); fillSelect("locationFilter", filters.locations, "جميع المدن", value => value, label => optionId("locations", label)); fillSelect("typeFilter", filters.types, "كل الأنواع", opportunityTypeLabel, label => optionId("types", label)); fillSelect("investmentModelFilter", filters.investment_models || [], "كل نماذج الاستثمار", value => value, label => optionId("investment_models", label)); fillSelect("assetFacilityTypeFilter", filters.asset_facility_types || [], "كل أنواع الأصول والمواقع", value => value, label => optionId("asset_facility_types", label)); state.filtersLoaded = true;
    }
    if (!state.tableGeo && window.NationalGeographyUI) state.tableGeo = await window.NationalGeographyUI.init("table", () => { state.opportunityPage = 0; updateOpportunityUrl(); loadOpportunities(); });
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
    const params = new URLSearchParams(location.search); state.sortBy = params.get("sort_by") || ""; state.sortOrder = params.get("sort_order") === "asc" ? "asc" : "desc";
    document.querySelectorAll("#view-opportunities [data-sort-key]").forEach(button=>{const active=button.dataset.sortKey===state.sortBy;button.textContent=button.dataset.sortLabel+(active?` ${state.sortOrder==="asc"?"↑":"↓"}`:"");button.closest("th")?.toggleAttribute("aria-sort",active);if(active)button.closest("th").setAttribute("aria-sort",state.sortOrder==="asc"?"ascending":"descending");});
    const query = new URLSearchParams({ q: $("searchInput").value, sector: sectorValue, activity: $("activityFilter").value, sub_activity: $("subActivityFilter").value, subsector: $("subsectorFilter").value, status: $("statusFilter").value, owner: $("ownerFilter").value, source: $("sourceFilter").value, location: $("locationFilter").value, opportunity_type: $("typeFilter").value, investment_model: $("investmentModelFilter").value, asset_facility_type: $("assetFacilityTypeFilter").value, lifecycle: $("lifecycleFilter").value, limit: String(pageSize), offset: String(state.opportunityPage * pageSize) });
    if (state.sortBy) { query.set("sort_by", state.sortBy); query.set("sort_order", state.sortOrder); }
    if (state.tableGeo?.enabled) for (const [key, value] of Object.entries(state.tableGeo.read())) if (value) query.set(key, value);
    const urlParams = new URLSearchParams(location.search); for (const key of ["deadline_after","deadline_before","deadline_status","created_after","created_before","period","map_ids","sector_values"]) if (urlParams.has(key)) query.set(key,urlParams.get(key));
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
    return `<tr>${cell("opportunity", `<strong>${safe(item.title)}</strong><small>${safe(item.reference || item.canonical_id)}</small>${geographyStatusMarkup(item)}`)}${cell("owner", safe(item.owner || "—"))}${cell("sector", safe(sectorLabel(item.sector)))}${cell("activity", safe(item.activity || "غير محدد"))}${cell("sub_activity", safe(item.sub_activity || "—"))}${cell("asset_facility_type", safe(item.asset_facility_type || "غير محدد"))}${cell("area", item.area ? Number(item.area).toLocaleString("en-US") + " م²" : "—")}${cell("deadline", safe(item.deadline || "غير محدد"))}${cell("status", `<span class="tag ${/منته|ملغ|تمت الترسية|أزيلت من المصدر|expired|cancel/i.test(item.status || "") ? "pending" : ""}">${safe(statusLabel(item.status))}</span>`)}${cell("sources", `<span class="source-pill">${Number(item.source_count || 0).toLocaleString("en-US-u-nu-latn")} مصادر</span>`)}${cell("action", `<button type="button" class="row-action" data-detail="${item.id}" aria-label="عرض تفاصيل الفرصة">↗</button>`)}</tr>`;
    }).join(""); bindDetailButtons();
    $("activeFilters").innerHTML = [$("searchInput").value && `بحث: ${safe($("searchInput").value)}`, state.tableGeo?.enabled && state.tableGeo.selectedLabel?.() && `المنطقة: ${safe(state.tableGeo.selectedLabel())}`, state.tableGeo?.enabled && state.tableGeo.selectedGovernorateLabel?.() && `المحافظة: ${safe(state.tableGeo.selectedGovernorateLabel())}`, groupedSectorActive ? "القطاع: أخرى (تشمل بقية القطاعات)" : $("sectorFilter").value && safe($("sectorFilter").selectedOptions[0]?.textContent), $("activityFilter").value && safe($("activityFilter").selectedOptions[0]?.textContent), $("subActivityFilter").value && safe($("subActivityFilter").selectedOptions[0]?.textContent), $("subsectorFilter").value && safe($("subsectorFilter").selectedOptions[0]?.textContent), $("statusFilter").value && safe($("statusFilter").selectedOptions[0]?.textContent), $("lifecycleFilter").value && safe($("lifecycleFilter").selectedOptions[0]?.textContent), $("ownerFilter").value && safe($("ownerFilter").selectedOptions[0]?.textContent), $("sourceFilter").value && safe($("sourceFilter").selectedOptions[0]?.textContent), $("locationFilter").value && safe($("locationFilter").selectedOptions[0]?.textContent), $("typeFilter").value && safe($("typeFilter").selectedOptions[0]?.textContent), $("investmentModelFilter").value && safe($("investmentModelFilter").selectedOptions[0]?.textContent), $("assetFacilityTypeFilter").value && safe($("assetFacilityTypeFilter").selectedOptions[0]?.textContent), urlParams.get("period") && `الفترة: ${safe(urlParams.get("period"))}`, urlParams.get("deadline_after") && `موعد من ${safe(urlParams.get("deadline_after"))}`, urlParams.get("deadline_before") && `موعد حتى ${safe(urlParams.get("deadline_before"))}`, urlParams.get("deadline_status") === "without_reliable_deadline" && "الموعد: بدون موعد محدد"].filter(Boolean).map(value => `<span class="filter-chip">${value}</span>`).join("");
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
    for (const key of ["q", "period", "created_after", "created_before", "deadline_after", "deadline_before", "deadline_status", "map_ids", "sector_values", "region_id", "governorate_id", "city_id", "geographic_scope"]) if (key === "q" ? $("searchInput").value : params.get(key)) query.set(key, key === "q" ? $("searchInput").value : params.get(key));
    link.href = `${link.pathname}${query.size ? `?${query}` : ""}`;
  });
});

function healthClass(value) { const status = String(value || ""); return status === "HEALTHY" ? "healthy" : status.includes("WARNING") || ["PARSER_BROKEN", "RATE_LIMITED", "INCOMPLETE_COLLECTION_WARNING"].includes(status) ? "warning" : ["FAILED", "BLOCKED"].includes(status) ? "failed" : ""; }
function statusLabel(value) { return ({ HEALTHY: "سليم", FRESH: "حديث", AGING: "بحاجة إلى تحديث", STALE: "متقادم", STATIC_OK: "مرجع ثابت ضمن موعد المراجعة", LIMITED_SOURCE_OK: "ضمن تحقق النطاق العام", MANUAL_REVIEW_DUE: "موعد المراجعة اليدوية", RUNNING: "جارٍ التحديث", SUCCESS: "اكتملت المزامنة", COMPLETED: "اكتمل التشغيل", COMPLETED_WITH_WARNINGS: "اكتمل مع تنبيهات", WARNING: "يحتاج إلى متابعة", FAILED: "تعذّر الاتصال", SOURCE_FAILED: "تعذّر تحديث المصدر", SOURCE_WARNING: "تنبيه في المصدر", BLOCKED: "الوصول العام محظور", PARSER_WARNING: "تحذير في تحليل المصدر", PARSER_BROKEN: "تعذّر تحليل الصفحة", INCOMPLETE_COLLECTION_WARNING: "جمع غير مكتمل", INCOMPLETE: "جمع غير مكتمل", NEVER_SYNCED: "لم تتم المزامنة", DISABLED: "متوقف", QUEUED: "في قائمة الانتظار", SKIPPED_ALREADY_RUNNING: "تم تجاوز التشغيل لوجود مزامنة جارية", INFO: "معلومة", OPEN: "مفتوح", ACKNOWLEDGED: "تم الاطلاع", RESOLVED: "تمت المعالجة", HEALTHY_WITH_WARNINGS: "يعمل مع تنبيهات", RATE_LIMITED: "تأخر الرد من المصدر", ACCESS_BLOCKED: "الوصول العام محظور", UNKNOWN: "حالة غير معروفة", Unknown: "حالة غير معروفة", unknown: "حالة غير معروفة", Announced: "متاحة", ANNOUNCED: "متاحة", PUBLISHED: "متاحة", منشورة: "متاحة", AVAILABLE: "متاحة", متاحة: "متاحة", REMOVED: "أزيلت من المصدر", REMOVED_FROM_SOURCE: "أزيلت من المصدر", أزيلت_من_المصدر: "أزيلت من المصدر", EXPIRED: "منتهية", منتهية: "منتهية", CANCELLED: "ملغاة", ملغاة: "ملغاة", AWARDED: "تمت الترسية", تمت_الترسية: "تمت الترسية", "حالة غير معروفة": "حالة غير معروفة", "قيد مراجعة الحالة": "قيد مراجعة الحالة", "غير محددة": "غير محددة", ACTIVE: "متاحة", INACTIVE: "غير نشطة" })[value] || value || "غير محدد"; }
window.AHDADisplayLabels = Object.freeze({ sector: sectorLabel, opportunity_type: opportunityTypeLabel, status: value => { const mapped = statusLabel(value); return /^[A-Za-z][A-Za-z0-9 _-]*$/.test(mapped) ? "قيمة عرض غير معتمدة" : mapped; }, coverage: value => { const mapped = coverageLabel(value); return /^[A-Za-z][A-Za-z0-9 _-]*$/.test(mapped) ? "تغطية غير محددة" : mapped; } });
function sourceTypeLabel(value) { return ({ structured_opportunity_platform: "منصة فرص رسمية", local_opportunity_platform: "منصة فرص محلية", unstructured_opportunity_publisher: "ناشر فرص رسمية", national_opportunity_platform: "منصة وطنية", announcement_driven_local_source: "إعلانات محلية", industrial_spatial_opportunity_source: "مصدر صناعي ومكاني", ppp_privatisation_pipeline_source: "مشروعات الشراكة والتخصيص", real_estate_investment_and_partnership_source: "استثمار عقاري وشراكات", national_value_chain_investment_source: "منصة القطاع الخاص", waste_sector_investment_source: "فرص قطاع النفايات", official_company_site_and_location_reference: "موقع شركة ومرجع مكاني" })[value] || "مصدر رسمي"; }
function sourceCoverageNote(source) { const notes = { modon: "لا يعرض الكتالوج العام جردًا حيًا كاملًا للإتاحة الاستثمارية في الأحساء. النتائج العامة المحدودة لا تعني عدم توفر أصول.", ncp: "يرصد النطاق العام أرشيف الأخبار الإنجليزي ومقالاته المرتبطة. لا يشمل خط المستثمرين الأوسع، وتعذّر استكمال آخر صفحة من الأرشيف العربي.", nhc: "تعرض الصفحات العامة فئات الاستثمار ومسارات التأهيل والتقديم، ولا تعرض جردًا حاليًا مفصلًا للأحساء. الخدمات التي تتطلب تسجيل دخول خارج النطاق.", pif: "يعرض المسار العام صفحات المنظومات، لكن سجل الشركات والفرص لا يمكن استعراضه حاليًا بطريقة عامة حتمية. لم يُستدعَ أي واجه API خاصة.", mwan: "يشمل الرصد المشروعات الاستثمارية المنشورة صراحة. لم تُثبت الفرص العامة المنشورة ارتباطًا بمحافظة الأحساء.", "waha-development": source.coverage_notes || "تعرض الصفحات العامة مجالات استثمار فقط، ولا تعرض فرصًا تفصيلية متاحة للجمهور." , furas: "يعرض المصدر الفرص المنشورة في القنوات الرسمية العامة ضمن صفحات الكتالوج المتاحة.", "alahsa-opportunities": "يعرض المصدر إعلانات الفرص المحلية المنشورة للأحساء.", ahda: "يشمل الرصد المحتوى العام المنشور ضمن نطاق المصدر المعتمد.", "invest-saudi": "يعتمد الرصد واجهة بيانات الفرص الرسمية المنشورة، وتُراجع المطابقة المكانية قبل القبول.", kfu: "يشمل الرصد إعلانات الاستثمار والتشغيل المنشورة من الجامعة." }; return notes[source.key] || source.coverage_notes || source.notes || "لا توجد ملاحظات منشورة."; }
async function loadSources(healthOnly = false) {
  try {
    const [sources, coverage] = await Promise.all([api("/api/sources"), api("/api/source-coverage")]);
    const coverageByKey = new Map((coverage.sources || []).map(item => [item.source_key, item]));
    state.sources = sources.map(source => {
      const summary = coverageByKey.get(source.key);
      if (!summary) return source;
      const successfulScan = summary.last_successful_scan || {};
      return { ...source, record_count: summary.current_source_record_count,
        historical_source_record_count: summary.historical_source_record_count,
        qualified_current_source_record_count: summary.qualified_current_source_record_count,
        pending_review_count: summary.pending_review_count,
        pending_absence_confirmation_count: summary.pending_absence_confirmation_count,
        ahsa_records: successfulScan.accepted_al_ahsa_count ?? source.ahsa_records };
    });
    $("sourceHealth").innerHTML = state.sources.map(source => `<div class="health-item"><span class="health-indicator ${healthClass(source.technical_health || source.status)}"></span><div class="health-main"><b>${safe(source.name)}</b><small>${safe(statusLabel(source.technical_health || source.status))} · ${safe(coverageLabel(source.coverage_status))}${source.last_success ? " · " + date(source.last_success) : " · لم تتم المزامنة"}</small></div><span class="health-count">${Number(source.record_count || 0).toLocaleString("en-US-u-nu-latn")}</span></div>`).join("");
    if (healthOnly) return;
    $("sourceCards").innerHTML = state.sources.map(source => `<article class="source-card"><div class="source-card-head">${sourceLogoMarkup(source.key)}<div class="source-title"><b>${safe(source.name)}</b><small>الجهة المشغلة: ${safe(source.source_operator || "غير محددة")} · ${safe(sourceTypeLabel(source.source_type))}</small></div><span class="source-state ${healthClass(source.technical_health || source.status)}">${safe(statusLabel(source.technical_health || source.status))}</span></div><details class="source-opportunities" data-source-opportunities="${safe(source.key)}"><summary><span>فرص الأحساء الموحدة المرتبطة بهذا المصدر</span><b class="source-opportunity-count">اضغط للعرض</b></summary><div class="source-opportunity-list"></div><button type="button" class="source-opportunity-more" hidden>عرض 50 فرصة أخرى</button></details><div class="source-meta"><span>نطاق التغطية<b>${safe(coverageLabel(source.coverage_status))}</b></span><span>حالة التفعيل<b>${source.enabled ? "مفعّل" : "غير مفعّل"}</b></span><span>آخر مزامنة ناجحة<b dir="ltr">${source.last_success ? date(source.last_success) : "—"}</b></span><span>المزامنة القادمة المتوقعة<b dir="ltr">${source.next_expected_check ? date(source.next_expected_check) : "—"}</b></span><span>التنبيهات المسجلة<b>${Number(source.errors || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>سجلات المصدر الحالية<b>${Number(source.record_count || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>السجلات التاريخية المحفوظة<b>${Number(source.historical_source_record_count || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>مرتبطة بفرص موحدة<b>${Number(source.qualified_current_source_record_count || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>مقبولة في آخر مسح ناجح<b>${Number(source.ahsa_records || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>مراجعات مفتوحة<b>${Number(source.pending_review_count || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>غياب بانتظار التأكيد<b>${Number(source.pending_absence_confirmation_count || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>فرص متعددة المصادر<b>${Number(source.multi_source_matches || 0).toLocaleString("en-US-u-nu-latn")}</b></span></div><div class="source-coverage"><b>حدود التغطية</b><p>${safe(sourceCoverageNote(source))}</p></div><details class="source-freshness" data-role="admin"><summary>حداثة المصدر والحالة التشغيلية</summary><div class="source-meta"><span>الصحة التقنية<b>${safe(statusLabel(source.technical_health || source.status))}</b></span><span>حالة التغطية<b>${safe(coverageLabel(source.coverage_status))}</b></span><span>حداثة الفحص<b>${safe(statusLabel(source.freshness_status || "UNKNOWN"))}${source.freshness_age_minutes != null ? ` · ${Number(source.freshness_age_minutes).toLocaleString("en-US-u-nu-latn")} دقيقة` : ""}</b></span><span>آخر محاولة<b dir="ltr">${source.last_attempt ? date(source.last_attempt) : "—"}</b></span><span>آخر نجاح<b dir="ltr">${source.last_success ? date(source.last_success) : "—"}</b></span><span>آخر مسح كامل<b dir="ltr">${source.last_complete_scan ? date(source.last_complete_scan) : source.last_scope_verification ? "تحقق نطاق عام · " + date(source.last_scope_verification) : "—"}</b></span><span>التحقق المتوقع التالي<b dir="ltr">${source.next_expected_check ? date(source.next_expected_check) : "—"}</b></span><span>نوع المصدر التشغيلي<b>${safe(source.operational_type || "غير محدد")}</b></span><span>حد التحذير / الفشل<b dir="ltr">${source.warning_threshold_minutes ?? "—"} / ${source.fail_threshold_minutes ?? "—"} دقيقة</b></span><span>الإخفاقات المتتالية<b>${Number(source.consecutive_failures || 0).toLocaleString("en-US-u-nu-latn")}</b></span></div><p>${safe(source.freshness_reason || "لا تتوفر أدلة حداثة كافية.")}</p></details><details class="source-tech" data-role="admin"><summary>تفاصيل تقنية</summary><div class="source-meta"><span>المعلن / المكتمل<b>${source.source_total_reported ?? "—"} / ${source.unique_records ?? "—"} · ${source.collection_completeness_percent ?? "—"}%</b></span><span>الصفحات<b>${source.pages_successful ?? 0} / ${source.pages_requested ?? 0} · ${source.pagination_complete === true ? "مكتمل" : source.pagination_complete === false ? "ناقص" : "غير محدد"}</b></span><span>أخطاء المصدر<b>${Number(source.errors || 0).toLocaleString("en-US-u-nu-latn")}</b></span><span>طريقة الجمع<b>${safe(source.method || "غير محددة")}</b></span><span>مستلمة / محللة<b>${source.records_received ?? 0} / ${source.records_parsed ?? 0}</b></span><span>مقبولة / مرفوضة<b>${source.ahsa_records ?? 0} / ${source.rejected_records ?? 0}</b></span><span>مراجعات موقع<b>${source.location_review_count ?? 0}</b></span><span>جديدة / معدلة / دون تغيير<b>${source.new_records ?? 0} / ${source.updated_records ?? 0} / ${source.unchanged_records ?? 0}</b></span></div></details>${source.sync_supported ? `<div class="source-card-actions" data-role="admin,analyst"><button class="button button-quiet" data-sync="${safe(source.key)}">مزامنة الآن</button><button class="button button-quiet" data-interval="${safe(source.key)}" data-current-interval="${source.interval}">تعديل الجدول</button><button class="toggle ${source.enabled ? "on" : ""}" title="${source.enabled ? "المصدر مفعّل" : "المصدر متوقف"}" aria-label="تفعيل أو إيقاف المصدر" data-toggle="${safe(source.key)}" data-enabled="${source.enabled}"></button></div>` : `<p class="source-coverage">${safe(source.enabled ? "لا يوجد محول مزامنة لهذا المصدر؛ تم منع تشغيله." : "سجل تغطية فقط؛ لا توجد فرص عامة مفصلة للجمع الآلي.")}</p>`}</article>`).join("");
    document.querySelectorAll("[data-source-opportunities]").forEach(panel => { panel.addEventListener("toggle", () => { if (panel.open && !sourceOpportunityCache.has(panel.dataset.sourceOpportunities)) loadSourceOpportunities(panel.dataset.sourceOpportunities, panel); }); panel.querySelector(".source-opportunity-more").onclick = () => loadSourceOpportunities(panel.dataset.sourceOpportunities, panel, false); });
    document.querySelectorAll("[data-sync]").forEach(button => button.onclick = () => syncOne(button.dataset.sync, button));
    document.querySelectorAll("[data-toggle]").forEach(button => button.onclick = () => toggleSource(button));
    document.querySelectorAll("[data-interval]").forEach(button => button.onclick = () => changeSourceInterval(button)); applyRoleVisibility();
  } catch (error) { toast(error.message); }
}

async function loadJobs() {
  try { const jobs = await api("/api/admin/jobs"); $("emptyJobs").classList.toggle("show", !jobs.length); const names = Object.fromEntries(state.sources.map(source => [source.id, source.name]));
    $("jobRows").innerHTML = jobs.map(job => { const elapsed = job.finished_at && job.started_at ? Math.max(0, Math.round((Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000)) : null; const elapsedText = job.job_state === "ABANDONED" ? "المدة غير متاحة" : elapsed === null ? "جارٍ" : elapsed < 60 ? `${elapsed} ث` : `${Math.floor(elapsed / 60)} د ${elapsed % 60} ث`; const stateLabel = job.job_state === "ABANDONED" ? "توقف بعد انقطاع العامل" : job.status === "RETRYING" ? "إعادة المحاولة" : statusLabel(job.status); const error = job.error ? String(job.error).slice(0, 180) : "—"; return `<tr><td>${safe(names[job.source_id] || "مصدر")}</td><td>${date(job.started_at)}</td><td>${job.finished_at ? `${date(job.finished_at)}<small>${safe(elapsedText)}</small>` : "—"}</td><td><span class="tag ${job.status !== "SUCCESS" ? "pending" : ""}" title="${safe(job.job_state || job.status)}">${safe(stateLabel)}</span></td><td>${Number(job.attempt_number || 1).toLocaleString("en-US-u-nu-latn")}</td><td>${Number(job.pages_scanned || 0).toLocaleString("en-US-u-nu-latn")}</td><td>${Number(job.raw_count || 0).toLocaleString("en-US-u-nu-latn")}</td><td>${Number(job.ahsa_count || 0).toLocaleString("en-US-u-nu-latn")}</td><td>${Number(job.new_count || 0).toLocaleString("en-US-u-nu-latn")}</td><td>${Number(job.update_count || 0).toLocaleString("en-US-u-nu-latn")}</td><td title="${safe(job.error || "")}">${safe(error)}</td></tr>`; }).join("");
  } catch (error) { toast(error.message); }
}

const reviewWorkbench = { queue: [], selected: null, detail: null, selectedAction: null, preview: null, dirty: false, filters: {}, batchSelection: new Set(), batchPreview: null, pilot: null, pilotMode: false, pilotMetrics: null, pendingPilotOutcome: null, pilotObserver: null };
function reviewDomainLabel(domain) { return ({ duplicate: "التكرار", location: "الموقع", qualification: "التأهيل", field_conflict: "تعارض القيم", taxonomy_conflict: "تعارض التصنيف" })[domain] || "مراجعة"; }
function reviewStateLabel(value) { return value === "SOURCE_RECHECK_REQUIRED" ? "يتطلب تحققًا من المصدر" : value === "HUMAN_REVIEW_REQUIRED" ? "قرار بشري مطلوب" : value || "غير محدد"; }
function reviewItemKey(item) { return `${item.domain}:${item.id}`; }
const pilotMetricsStorageKey = "ahsa-human-review-pilot-metrics-v1";
const pilotPendingStorageKey = "ahsa-human-review-pilot-pending-v1";
function pilotStoredMetrics() { try { return JSON.parse(localStorage.getItem(pilotMetricsStorageKey) || "{}"); } catch { return {}; } }
function savePilotStoredMetrics(value) { localStorage.setItem(pilotMetricsStorageKey, JSON.stringify(value)); }
function pilotCaseMetrics(key) { const all = pilotStoredMetrics(); return all[key] || { review_opened_at: new Date().toISOString(), source_cards_viewed_count: 0, _viewed_cards: [] }; }
function savePilotCaseMetrics(key, metrics) { const all = pilotStoredMetrics(); all[key] = metrics; savePilotStoredMetrics(all); reviewWorkbench.pilotMetrics = metrics; }
function pilotOutcomeCount(phase) { return (reviewWorkbench.pilot?.outcomes || []).filter(event => event.event_kind === "CASE_OUTCOME" && event.phase === phase).length; }
function renderPilotControls() {
  const state = reviewWorkbench.pilot, mode = reviewWorkbench.pilotMode;
  $("pilotStartButton").hidden = mode;
  $("pilotStartButton").textContent = state?.started ? `استئناف الطيار — المرحلة ${state.active_phase === "A" ? "أ" : "ب"}` : "بدء الطيار — المرحلة أ";
  $("pilotExitButton").hidden = !mode;
  const item = reviewWorkbench.queue.find(row => reviewItemKey(row) === reviewWorkbench.selected);
  const phase = state?.current_phase || state?.active_phase || "A", sequence = item?.pilot_phase_sequence;
  const phaseCount = Number(state?.current_phase_count || state?.phase_counts?.[phase] || 20);
  $("pilotPosition").hidden = !mode; $("pilotPosition").textContent = mode && sequence ? `الحالة ${formatIntegerLatin(sequence)} من ${formatIntegerLatin(phaseCount)} · المرحلة ${phase === "A" ? "أ" : "ب"}` : "";
  for (const id of ["pilotPreviousButton","pilotNextButton","pilotKeepOpenButton","pilotSourceRecheckButton"]) $(id).hidden = !mode;
  $("pilotPreviousButton").disabled = !item || reviewWorkbench.queue.findIndex(row => reviewItemKey(row) === reviewWorkbench.selected) <= 0;
  $("pilotNextButton").disabled = !item || reviewWorkbench.queue.findIndex(row => reviewItemKey(row) === reviewWorkbench.selected) >= reviewWorkbench.queue.length - 1;
  const completed = new Set(state?.completed_case_keys || []), alreadyRecorded = item && completed.has(reviewItemKey(item));
  const actionable=item?.status==="OPEN"&&item?.disposition!=="SOURCE_RECHECK_REQUIRED";
  $("pilotKeepOpenButton").disabled = !actionable || alreadyRecorded || Boolean(reviewWorkbench.dirty);
  $("pilotSourceRecheckButton").disabled = !actionable || alreadyRecorded || Boolean(reviewWorkbench.dirty);
  const phaseAComplete = pilotOutcomeCount("A") === Number(state?.phase_counts?.A || 20);
  $("pilotPhaseReview").hidden = !(mode && phase === "A" && phaseAComplete);
  $("pilotMarkPhaseAButton").disabled = $("pilotPhaseSummary").value.trim().length < 8;
  $("pilotStatus").textContent = !state?.started ? "لم يبدأ" : state.phase_a_reviewed ? "المرحلة ب" : "المرحلة أ";
  $("pilotProgress").textContent = state?.started ? `اكتمل ${formatIntegerLatin(pilotOutcomeCount("A"))}/20 من المرحلة أ و${formatIntegerLatin(pilotOutcomeCount("B"))}/20 من المرحلة ب. الغرض: معايرة سير العمل فقط.` : "العينة ثابتة ولم تبدأ. لا توجد قرارات أو نتائج طيار مسجلة.";
}
async function fetchPilotState() { reviewWorkbench.pilot = await api("/api/admin/review-workbench/pilot"); renderPilotControls(); }
function stampPilotMetric(name, value = new Date().toISOString()) { if (!reviewWorkbench.pilotMode || !reviewWorkbench.selected) return; const key = reviewWorkbench.selected, metrics = reviewWorkbench.pilotMetrics || pilotCaseMetrics(key); metrics[name] = value; savePilotCaseMetrics(key, metrics); }
function beginPilotFeedback(outcome, reason = null) {
  if (!reviewWorkbench.pilotMode || !reviewWorkbench.selected) return;
  reviewWorkbench.pendingPilotOutcome = { outcome, reason };
  localStorage.setItem(pilotPendingStorageKey,JSON.stringify({review_id_key:reviewWorkbench.selected,outcome,reason}));
  if (outcome === "SOURCE_RECHECK_REQUIRED") { $("pilotSourceReasonLabel").hidden = false; $("pilotSourceReason").hidden = false; $("pilotSourceReason").required = true; }
  else { $("pilotSourceReasonLabel").hidden = true; $("pilotSourceReason").hidden = true; $("pilotSourceReason").required = false; }
  $("pilotSourceReason").value=reason||"";
  $("pilotFeedbackPanel").hidden = false; $("pilotFeedbackPanel").scrollIntoView({ behavior: "smooth", block: "start" });
}
async function savePilotFeedback() {
  const pending = reviewWorkbench.pendingPilotOutcome, item = reviewWorkbench.queue.find(row => reviewItemKey(row) === reviewWorkbench.selected);
  if (!pending || !item || !reviewWorkbench.pilot) throw new Error("لا توجد نتيجة طيار معلقة لهذه الحالة.");
  const feedback = { evidence_sufficiency: $("pilotEvidenceFeedback").value, decision_clarity: $("pilotClarityFeedback").value,
    recommendation_helpfulness: $("pilotRecommendationFeedback").value, actions_appropriate: $("pilotActionsFeedback").value,
    missing_evidence_note: $("pilotMissingEvidenceNote").value.trim() };
  if (Object.entries(feedback).some(([key,value]) => key !== "missing_evidence_note" && !value)) throw new Error("أكمل إجابات ملاحظات الطيار الأربعة.");
  const reason = pending.outcome === "SOURCE_RECHECK_REQUIRED" ? $("pilotSourceReason").value.trim() : pending.reason;
  if (pending.outcome === "SOURCE_RECHECK_REQUIRED" && reason.length < 8) throw new Error("اكتب سببًا واضحًا للإحالة إلى تحقق المصدر.");
  const metrics = { ...(reviewWorkbench.pilotMetrics || pilotCaseMetrics(reviewWorkbench.selected)) };
  delete metrics._viewed_cards;
  const opened = Date.parse(metrics.review_opened_at), now = Date.now(); metrics.handling_time_seconds = Number.isFinite(opened) ? Math.max(0,(now-opened)/1000) : null;
  if (metrics.first_evidence_interaction_at) metrics.time_to_first_evidence_seconds = Math.max(0,(Date.parse(metrics.first_evidence_interaction_at)-opened)/1000);
  if (metrics.decision_preview_opened_at && metrics.decision_submitted_at) metrics.time_from_preview_to_submit_seconds = Math.max(0,(Date.parse(metrics.decision_submitted_at)-Date.parse(metrics.decision_preview_opened_at))/1000);
  metrics.recommendation_available = Boolean(reviewWorkbench.detail?.recommendation?.action);
  metrics.recommendation_confidence = reviewWorkbench.detail?.recommendation?.confidence || "NONE";
  const response = await api("/api/admin/review-workbench/pilot/events", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pilot_id: reviewWorkbench.pilot.pilot_id, event_kind: pending.outcome === "REOPENED_AFTER_DECISION" ? "CASE_REOPENED" : "CASE_OUTCOME", review_id_key: reviewWorkbench.selected,
      phase: item.pilot_phase, outcome: pending.outcome, reason, feedback, metrics }) });
  reviewWorkbench.pendingPilotOutcome = null; $("pilotFeedbackPanel").hidden = true; $("pilotSourceReason").value = "";
  localStorage.removeItem(pilotPendingStorageKey);
  for (const id of ["pilotEvidenceFeedback","pilotClarityFeedback","pilotRecommendationFeedback","pilotActionsFeedback","pilotMissingEvidenceNote"]) $(id).value = "";
  const all = pilotStoredMetrics(); delete all[reviewWorkbench.selected]; savePilotStoredMetrics(all); reviewWorkbench.pilotMetrics = null;
  await fetchPilotState();
  const completed=new Set(reviewWorkbench.pilot.completed_case_keys||[]), idx=reviewWorkbench.queue.findIndex(row=>reviewItemKey(row)===reviewWorkbench.selected);
  const next=reviewWorkbench.queue.slice(idx+1).find(row=>!completed.has(reviewItemKey(row)));
  if (next) { await loadReviewDetail(reviewItemKey(next)); } else { reviewWorkbench.selected=null; reviewWorkbench.detail=null; $("reviewDecisionPanel").innerHTML='<div class="review-empty-state">اكتملت حالات هذه المرحلة. راجع النتائج قبل الانتقال إلى المرحلة التالية.</div>'; $("reviewEvidencePanel").innerHTML='<div class="review-empty-state">لا توجد حالة نشطة للعرض.</div>'; renderReviewQueue(); renderPilotControls(); }
}
function initializePilotControls() {
  $("pilotStartButton").onclick=async()=>{try{await api("/api/admin/review-workbench/pilot/events",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({pilot_id:"AHSA-HUMAN-REVIEW-PILOT-2026-10",event_kind:"PILOT_STARTED"})});await fetchPilotState();reviewWorkbench.pilotMode=true;await loadReview(null);}catch(error){toast(error.message);}};
  $("pilotExitButton").onclick=async()=>{if(reviewWorkbench.pendingPilotOutcome){toast("أكمل ملاحظات الحالة الحالية قبل الخروج.");return;}if(reviewWorkbench.dirty&&!window.confirm("لديك تغيير غير محفوظ. هل تريد الخروج من وضع الطيار؟"))return;reviewWorkbench.pilotMode=false;reviewWorkbench.dirty=false;$("pilotFeedbackPanel").hidden=true;await loadReview(null);renderPilotControls();};
  $("pilotKeepOpenButton").onclick=()=>beginPilotFeedback("KEPT_OPEN");
  $("pilotSourceRecheckButton").onclick=()=>beginPilotFeedback("SOURCE_RECHECK_REQUIRED");
  $("pilotFeedbackSubmitButton").onclick=async()=>{try{await savePilotFeedback();}catch(error){toast(error.message);}};
  $("pilotPreviousButton").onclick=()=>moveReview(reviewWorkbench.queue.findIndex(item=>reviewItemKey(item)===reviewWorkbench.selected)-1);
  $("pilotNextButton").onclick=()=>moveReview(reviewWorkbench.queue.findIndex(item=>reviewItemKey(item)===reviewWorkbench.selected)+1);
  $("pilotPhaseSummary").oninput=()=>{$("pilotMarkPhaseAButton").disabled=$("pilotPhaseSummary").value.trim().length<8;};
  $("pilotMarkPhaseAButton").onclick=async()=>{try{await api("/api/admin/review-workbench/pilot/events",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({pilot_id:reviewWorkbench.pilot.pilot_id,event_kind:"PHASE_A_REVIEWED",reason:$("pilotPhaseSummary").value.trim()})});$("pilotPhaseSummary").value="";await fetchPilotState();await loadReview(null);}catch(error){toast(error.message);}};
  document.addEventListener("click",event=>{
    if(!reviewWorkbench.pilotMode||!reviewWorkbench.selected)return;
    const target=event.target, evidence=$("reviewEvidencePanel");
    if(evidence?.contains(target)){stampPilotMetric("first_evidence_interaction_at",reviewWorkbench.pilotMetrics?.first_evidence_interaction_at||new Date().toISOString());if(target.closest("a[href]"))stampPilotMetric("source_link_opened",true);const summary=target.closest("summary"),details=summary?.parentElement;if(details&&!details.open){stampPilotMetric("evidence_panel_expanded",true);if(details.classList.contains("review-history"))stampPilotMetric("observation_history_opened",true);if(details.closest(".review-source-card")&&/الخام|raw data/i.test(summary.textContent||""))stampPilotMetric("raw_data_opened",true);}}
    if(target.closest("#reviewPreviewButton")){stampPilotMetric("decision_preview_used",true);stampPilotMetric("decision_preview_opened_at");}
    if(target.closest("#reviewReopenPreviewButton"))stampPilotMetric("reopen_used",true);
  },true);
}
function renderReviewQueue() {
  const list = $("reviewQueueList"), queue = reviewWorkbench.queue;
  $("reviewQueueShown").textContent = formatIntegerLatin(queue.length);
  list.innerHTML = queue.length ? queue.map(item => `<article class="review-queue-row">${!reviewWorkbench.pilotMode && item.domain === "field_conflict" && item.status === "OPEN" && item.disposition !== "SOURCE_RECHECK_REQUIRED" ? `<label class="review-batch-select"><input type="checkbox" data-batch-review="${safe(reviewItemKey(item))}" ${reviewWorkbench.batchSelection.has(reviewItemKey(item)) ? "checked" : ""}>تحديد لدفعة</label>` : ""}<button type="button" class="review-queue-item ${reviewWorkbench.selected === reviewItemKey(item) ? "is-selected" : ""}" data-review-key="${safe(reviewItemKey(item))}"><span class="review-queue-top"><b>${safe(item.priority || "P4")}</b><small>${safe(reviewDomainLabel(item.domain))} · ${formatIntegerLatin(item.age_days || 0)} يوم</small></span><strong>${safe(item.title || "مراجعة بدون عنوان")}</strong><span class="review-queue-meta">${safe(item.source || "عدة مصادر")} · ${safe(reviewStateLabel(item.disposition))}${item.pilot_completed ? " · اكتملت في الطيار" : ""}</span><span class="review-queue-master">${(item.master_ids || []).map(id => `Master ${formatIntegerLatin(id)}`).join(" · ") || "لا يوجد Master مرتبط"}</span></button></article>`).join("") : '<div class="loading">لا توجد مراجعات بهذه المرشحات.</div>';
  list.querySelectorAll("[data-review-key]").forEach(button => button.onclick = () => { if (reviewWorkbench.dirty && !window.confirm("لديك قرار غير محفوظ. هل تريد تركه؟")) return; reviewWorkbench.dirty = false; loadReviewDetail(button.dataset.reviewKey); });
  list.querySelectorAll("[data-batch-review]").forEach(box => box.onchange = () => { if (box.checked) reviewWorkbench.batchSelection.add(box.dataset.batchReview); else reviewWorkbench.batchSelection.delete(box.dataset.batchReview); renderReviewQueue(); });
  const batchPanel = $("reviewBatchPanel"); batchPanel.hidden = reviewWorkbench.batchSelection.size < 2;
  $("reviewBatchPreviewButton").onclick = previewReviewBatch; $("reviewBatchCommitButton").onclick = commitReviewBatch;
  renderPilotControls();
}
async function previewReviewBatch() {
  try {
    const reason = $("reviewBatchReason").value; if (!reason) throw new Error("اختر سبب الدفعة أولًا");
    const items = await Promise.all([...reviewWorkbench.batchSelection].map(async key => { const [domain,id] = key.split(":"); const detail = await api(`/api/admin/review-workbench/${encodeURIComponent(domain)}/${id}`); return { domain, review_id: Number(id), version_token: detail.version_token, recommendation_version: detail.recommendation_version }; }));
    const result = await api("/api/admin/review-workbench/batch/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items, action: "keep", reason, override_reason: $("reviewBatchOverrideReason").value || null, batch_operation_id: crypto.randomUUID(), confirm: false }) });
    reviewWorkbench.batchPreview = result; const preview = $("reviewBatchPreview");
    preview.innerHTML = `<b>${result.eligible ? "الدفعة متجانسة وجاهزة للمعاينة" : "الدفعة غير مؤهلة"}</b><p>التوقيعات المتطابقة: ${formatIntegerLatin(result.signature_count || 0)} · الحالات المقبولة: ${formatIntegerLatin((result.items || []).length)}</p><p>${safe(result.eligibility_reason || result.impact || "")}</p>${(result.recommendation_snapshots || []).map(item => `<p>التوصية للمراجعة ${formatIntegerLatin(item.review_id)}: ${safe(item.label || item.action || "لا توجد توصية آلية موثوقة")} · ${safe(item.confidence || "NONE")} · ${safe(item.reason || "")}</p>`).join("")}${(result.items || []).length ? `<p>المراجعات: ${result.items.map(item => formatIntegerLatin(item.review_id)).join("، ")}</p>` : ""}${(result.excluded || []).length ? `<ul>${result.excluded.map(item => `<li>${formatIntegerLatin(item.review_id)}: ${safe(item.reason)}</li>`).join("")}</ul>` : ""}`;
    preview.hidden = false; $("reviewBatchCommitButton").hidden = !result.eligible;
  } catch (error) { toast(error.message); }
}
async function commitReviewBatch() {
  try {
    const preview = reviewWorkbench.batchPreview; if (!preview?.eligible) throw new Error("عاين دفعة متجانسة قبل التأكيد");
    if (!window.confirm(`تنفيذ قرار الإبقاء على القيمة لـ ${preview.items.length} مراجعة؟ ستُسجل مراجعة وتدقيق مستقل لكل حالة.`)) return;
    const response = await api("/api/admin/review-workbench/batch/commit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items: preview.items, action: "keep", reason: preview.reason, batch_operation_id: preview.batch_operation_id, batch_signature: preview.signature, override_reason: $("reviewBatchOverrideReason").value || null, confirm: true }) });
    toast(`تم حفظ الدفعة وتدقيق ${response.individual_audit_count} حالات.`); reviewWorkbench.batchSelection.clear(); reviewWorkbench.batchPreview = null; await loadReview(null);
  } catch (error) { toast(error.message); }
}
function valueText(value) { return value === null || value === undefined || value === "" ? "غير محدد" : safe(value); }
function duplicateValueText(value) {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length)) return "غير محدد";
  if (Array.isArray(value)) return safe(value.map(item => typeof item === "object" && item !== null ? JSON.stringify(item) : String(item)).join("، "));
  if (typeof value === "object") return safe(JSON.stringify(value));
  return safe(value);
}
function renderWorkbenchDetail(detail) {
  const decision = $("reviewDecisionPanel"), evidencePane = $("reviewEvidencePanel"), domainLabel = reviewDomainLabel(detail.domain);
  const title = detail.title || detail.masters?.[0]?.title || "مراجعة";
  const masters = (detail.masters || []).map(master => `<div class="review-master-context"><div><small>الفرصة الموحدة · ${formatIntegerLatin(master.id)}</small><b>${safe(master.title)}</b></div><span>${safe(statusLabel(master.status))}</span><dl><div><dt>الجهة المالكة</dt><dd>${valueText(master.owner)}</dd></div><div><dt>منصة النشر</dt><dd>${valueText(master.publication_platform)}</dd></div><div><dt>الناشرون</dt><dd>${valueText((detail.sources || []).filter(source => source.master_id === master.id).map(source => source.publisher).filter(Boolean).join("، "))}</dd></div><div><dt>القطاع</dt><dd>${valueText(master.sector)}</dd></div><div><dt>النشاط</dt><dd>${valueText(master.activity)}</dd></div><div><dt>المساحة</dt><dd>${master.area == null ? "غير محدد" : `${formatNumberLatin(master.area)} ${safe(master.area_unit || "وحدة غير محددة")}`}</dd></div><div><dt>القيمة الاستثمارية</dt><dd>${master.investment_value == null ? "غير محدد" : `${formatNumberLatin(master.investment_value)} ${safe(master.currency || "عملة غير محددة")}`}</dd></div><div><dt>المدة</dt><dd>${master.duration == null ? "غير محدد" : `${formatNumberLatin(master.duration)} ${safe(master.duration_unit || "وحدة غير محددة")}`}</dd></div><div><dt>الموقع</dt><dd>${valueText([master.city, master.district, master.location].filter(Boolean).join(" · "))}</dd></div><div><dt>الإحداثيات</dt><dd>${master.latitude == null || master.longitude == null ? "غير محددة" : `${formatNumberLatin(master.latitude)}, ${formatNumberLatin(master.longitude)}`}</dd></div></dl></div>`).join("");
  const comparison = detail.comparison || {}, values = [
    { label: "القيمة الحالية", value: comparison.current_value, origin: "القيمة المعيارية" },
    ...(comparison.competing_values || []).map(entry => ({ label: "القيمة الواردة", value: entry.value, origin: entry.source || "المصدر", source_record_id: entry.source_record_id, observed_at: entry.observed_at }))
  ];
  const compareHtml = values.length > 1 && detail.domain.includes("conflict") ? `<section class="review-comparison"><h3>مقارنة القيم <span class="review-evidence-state">${safe(({ AGREEMENT: "اتفاق", CONFLICT: "تعارض", MISSING_VALUE: "قيمة مفقودة", SINGLE_SOURCE: "مصدر واحد" })[comparison.assessment] || "مقارنة")}</span></h3><div class="review-value-grid">${values.map(value => `<article><small>${safe(value.label)}</small><b>${valueText(value.value)}</b><span>${safe(value.origin)}${value.source_record_id ? ` · سجل المصدر ${formatIntegerLatin(value.source_record_id)}` : ""}</span>${value.observed_at ? `<time>${safe(formatDateTimeLatin(value.observed_at))}</time>` : ""}</article>`).join("")}</div><p class="review-provenance">مصدر القيمة المعيارية: ${(comparison.canonical_provenance || []).map(p => `${safe(p.source || "مصدر غير محدد")} · ${safe(formatDateTimeLatin(p.captured_at))}`).join("، ") || "لا تتوفر إحالة توثيقية سابقة لهذا الحقل."}</p></section>` : "";
  const duplicateComparison = detail.domain === "duplicate" ? (detail.duplicate_comparison || {}) : null;
  const duplicateDifferent = duplicateComparison ? [...(duplicateComparison.different_fields || []), ...(duplicateComparison.missing_on_left || []), ...(duplicateComparison.missing_on_right || [])] : [];
  const duplicateCompareHtml = duplicateComparison ? `<section class="duplicate-difference-panel"><h3>الاختلافات بين الفرصتين</h3>${duplicateDifferent.length ? `<div class="duplicate-difference-list">${duplicateDifferent.map(row => `<article class="duplicate-difference-row"><b>${safe(row.label)}</b><span><small>الفرصة الأولى</small>${duplicateValueText(row.left)}</span><span><small>الفرصة الثانية</small>${duplicateValueText(row.right)}</span></article>`).join("")}</div>` : `<p class="duplicate-governance-blocker">لا تظهر فروق في الحقول المتاحة حاليًا. افحص الحقول المتطابقة وأدلة المصدر أدناه.</p>`}<aside class="duplicate-human-reason"><h4>لماذا تتطلب هذه الحالة مراجعة بشرية؟</h4><p>${safe(duplicateComparison.human_review_reason || duplicateComparison.blocking_reason || "دليل الهوية الحالي غير كافٍ للدمج الآلي.")}</p></aside><details class="duplicate-matches"><summary>عرض الحقول المتطابقة (${formatIntegerLatin((duplicateComparison.matched_fields || []).length)})</summary><ul>${(duplicateComparison.matched_fields || []).map(row => `<li><b>${safe(row.label)}:</b> ${duplicateValueText(row.left)}</li>`).join("") || "<li>لا توجد حقول متطابقة مسجلة.</li>"}</ul></details></section>` : "";
    const actionHtml = (detail.allowed_actions || []).map(action => `<button type="button" class="review-action-button ${reviewWorkbench.selectedAction === action.key ? "is-selected" : ""}" data-review-action="${safe(action.key)}">${safe(action.key === "merge" ? "نفس الفرصة — دمج" : action.label)}</button>`).join("");
  const unresolvedHtml = detail.domain === "duplicate" ? `<button type="button" class="review-action-button review-keep-open" data-review-keep-open>غير محسوم / إبقاء للمراجعة</button>` : "";
  const recommendation = detail.recommendation || {};
  if(reviewWorkbench.pilotMode){const metrics=reviewWorkbench.pilotMetrics||pilotCaseMetrics(reviewWorkbench.selected);metrics.recommendation_available=Boolean(recommendation.action);metrics.recommendation_confidence=recommendation.confidence||"NONE";savePilotCaseMetrics(reviewWorkbench.selected,metrics);}
  const reopenHtml = detail.reopen_allowed ? `<section class="review-reopen-panel"><h3>إعادة فتح المراجعة</h3><p class="review-muted">ستظهر بيانات القرار السابق وأدلته هنا بعد معاينة إعادة الفتح.</p><label for="reviewReopenReason">سبب إعادة الفتح</label><select id="reviewReopenReason"><option value="">اختر سببًا</option><option>ظهور دليل جديد</option><option>تغير بيانات المصدر</option><option>إعادة تقييم القرار السابق</option><option>تعارض جديد</option><option>سبب آخر</option></select><textarea id="reviewReopenNote" rows="2" maxlength="1800" placeholder="ملاحظة اختيارية"></textarea><button type="button" class="button button-quiet" id="reviewReopenPreviewButton">معاينة إعادة الفتح</button><div id="reviewReopenPreview" class="review-preview" hidden></div><button type="button" class="button button-dark" id="reviewReopenSubmit" hidden>تأكيد إعادة الفتح</button></section>` : "";
  decision.innerHTML = `<header class="review-detail-header"><div><span class="section-kicker">${safe(domainLabel)} · ${safe(reviewStateLabel(detail.disposition))}</span><h2>${safe(title)}</h2><p>رقم المراجعة ${formatIntegerLatin(detail.id)} · ${safe(detail.priority)} · ${formatIntegerLatin(detail.age_days || 0)} يوم · ${safe(statusLabel(detail.source_status || detail.status))}</p></div><span class="review-status-pill">${safe(reviewStateLabel(detail.disposition))}</span></header><section class="review-question"><small>ما هو القرار المطلوب؟</small><b>${safe(detail.reason_label || "راجع الأدلة واختر الإجراء المناسب.")}</b></section><div class="review-header-meta"><span>المجال <b>${safe(domainLabel)}</b></span><span>الحقل <b>${safe(detail.field || "—")}</b></span><span>المصادر المرتبطة <b>${formatIntegerLatin(detail.linked_source_count || 0)}</b></span><span>Master <b>${(detail.master_ids || []).map(formatIntegerLatin).join("، ") || "—"}</b></span></div>${masters}${duplicateCompareHtml}${compareHtml}<section class="review-recommendation"><div><span class="section-kicker">توصية النظام</span><b>${recommendation.action ? safe(recommendation.label || recommendation.action) : "لا توجد توصية آلية موثوقة"}</b></div><p>${safe(recommendation.reason || "لا توجد قاعدة حتمية موثوقة لهذه الحالة.")}</p>${recommendation.confidence ? `<small>الثقة: ${safe(recommendation.confidence)}</small>` : ""}${recommendation.rule ? `<small>القاعدة: ${safe(recommendation.rule)}</small>` : ""}${recommendation.supporting_evidence?.length ? `<small>أدلة مؤيدة: ${recommendation.supporting_evidence.map(row => `سجل ${formatIntegerLatin(row.source_record_id)}`).join("، ")}</small>` : ""}</section><section class="review-decision-form"><h3>القرار</h3><div class="review-action-list">${actionHtml}${unresolvedHtml}${!actionHtml && detail.domain !== "duplicate" ? '<p class="review-muted">لا يتوفر إجراء حسم لهذا الدور أو لهذه الحالة.</p>' : ""}</div><label for="reviewDecisionReason">سبب القرار <span>مطلوب</span></label><select id="reviewDecisionReason"><option value="">اختر سببًا</option><option>مصدر رسمي أكثر موثوقية</option><option>القيمة الحالية مدعومة من عدة مصادر</option><option>القيمة الأخرى تمثل منصة النشر وليست المالك</option><option>تعارض غير محسوم</option><option>تم التحقق يدويًا</option></select><label for="recommendationOverrideReason">سبب تجاوز التوصية <span>مطلوب عند مخالفتها</span></label><select id="recommendationOverrideReason"><option value="">اختر إذا خالفت التوصية</option><option>مصدر أحدث وأكثر موثوقية</option><option>السياق لا تدعمه التوصية</option><option>تحقق يدوي إضافي</option><option>تعارض في الأدلة</option><option>سبب آخر</option></select><label for="reviewDecisionNote">ملاحظة المحلل <small>اختيارية</small></label><textarea id="reviewDecisionNote" rows="2" maxlength="1800" placeholder="أضف توضيحًا عند الحاجة"></textarea><div id="reviewDecisionPreview" class="review-preview" hidden></div><div class="review-decision-controls"><button type="button" class="button button-quiet" id="reviewPreviewButton">معاينة أثر القرار</button><button type="button" class="button button-dark" id="reviewSubmitButton" disabled>تأكيد القرار</button></div></section>${reopenHtml}<footer class="review-next-controls"><button type="button" id="reviewPrevious">السابق</button><button type="button" id="reviewNext">التالي</button><button type="button" id="reviewBackToQueue">العودة للطابور</button></footer>`;
  const sourceCards = (detail.sources || []).map(source => `<article class="review-source-card" data-source-record-id="${formatIntegerLatin(source.source_record_id)}"><header><div><b>${safe(source.source)}</b><small>معرّف سجل المصدر ${safe(source.source_opportunity_id)} · ${formatDateTimeLatin(source.observed_at)}</small></div><span>${safe(statusLabel(source.source_state))}</span></header><p><b>العنوان الخام:</b> ${safe(source.raw_title || "غير محدد")}</p><p><b>القيمة الخام:</b> ${valueText(source.raw_field_value)} · <b>القيمة المعيارية:</b> ${valueText(source.normalized_value)}</p><small>المعرّف الداخلي ${formatIntegerLatin(source.source_record_id)} · النوع ${safe(source.mapping_rule || "دليل مباشر")}</small>${source.source_url ? `<p><a href="${safe(source.source_url)}" target="_blank" rel="noopener noreferrer">فتح المصدر الأصلي ↗</a></p>` : `<p class="review-muted">لا يتوفر رابط تفاصيل آمن لهذا السجل.</p>`}${(source.evidence_note || []).length ? `<small>ملاحظات الدليل: ${safe(source.evidence_note.join("، "))}</small>` : ""}<details><summary>عرض البيانات الخام</summary><pre>${safe(JSON.stringify(source.raw_payload || source.raw_excerpt || {}, null, 2))}</pre></details></article>`).join("");
  const historyHtml = (detail.history || []).length ? `<ol class="review-timeline">${detail.history.map(row => `<li><time>${safe(formatDateTimeLatin(row.observed_at))}</time><b>${valueText(row.value)}</b><small>${row.historical ? "قيمة من سجل تاريخي" : row.current ? "القيمة الحالية" : "تغيير مسجل"}</small></li>`).join("")}</ol>` : '<p class="review-muted">لا يوجد سجل ملاحظات سابق لهذا الحقل.</p>';
  const timelineRows = detail.timeline || [], knownTimeline = timelineRows.filter(row => !row.historical_unknown_time), unknownTimeline = timelineRows.filter(row => row.historical_unknown_time);
  const timelineItemHtml = row => `<li><time>${safe(formatDateTimeLatin(row.timestamp) || "وقت غير متوفر")}</time><b>${safe(row.label || row.event_type)}</b><small>${safe(row.actor || "غير متوفر")}${row.description ? ` · ${safe(row.description)}` : ""}</small>${row.previous_value || row.new_value ? `<small>${valueText(row.previous_value)} ← ${valueText(row.new_value)}</small>` : ""}</li>`;
  const auditHtml = timelineRows.length ? `<ol class="review-timeline">${knownTimeline.map(timelineItemHtml).join("")}</ol>${unknownTimeline.length ? `<section class="review-history-unknown"><b>سجل تاريخي بوقت غير متوفر</b><ol class="review-timeline">${unknownTimeline.map(timelineItemHtml).join("")}</ol></section>` : ""}` : '<p class="review-muted">لا توجد أحداث تاريخية مسجلة لهذه المراجعة.</p>';
  evidencePane.innerHTML = `<section><span class="section-kicker">الأدلة والمصدر</span><h2>الأدلة</h2>${sourceCards || '<p class="review-muted">لا توجد سجلات مصدر مرتبطة مباشرة.</p>'}</section><details class="review-history" open><summary>سجل ملاحظات الحقل</summary>${historyHtml}</details><details class="review-history"><summary>سجل المراجعة والتدقيق</summary>${auditHtml}</details>`;
  if(reviewWorkbench.pilotObserver){reviewWorkbench.pilotObserver.disconnect();reviewWorkbench.pilotObserver=null;}
  if(reviewWorkbench.pilotMode&&"IntersectionObserver" in window){reviewWorkbench.pilotObserver=new IntersectionObserver(entries=>{for(const entry of entries){if(!entry.isIntersecting)continue;const card=entry.target,metrics=reviewWorkbench.pilotMetrics||pilotCaseMetrics(reviewWorkbench.selected),seen=new Set(metrics._viewed_cards||[]),id=card.dataset.sourceRecordId||card.innerText.slice(0,80);if(!seen.has(id)){seen.add(id);metrics._viewed_cards=[...seen];metrics.source_cards_viewed_count=seen.size;savePilotCaseMetrics(reviewWorkbench.selected,metrics);}}},{threshold:0.2});evidencePane.querySelectorAll(".review-source-card").forEach(card=>reviewWorkbench.pilotObserver.observe(card));}
  if (detail.version_token) api(`/api/admin/review-workbench/${encodeURIComponent(detail.domain)}/${detail.id}/recommendation-shown?version_token=${encodeURIComponent(detail.version_token)}`, { method: "POST" }).catch(() => {});
  if (detail.reopen_allowed) { const resetReopenPreview = () => { $("reviewReopenPreview").hidden = true; $("reviewReopenSubmit").hidden = true; }; $("reviewReopenReason").onchange = resetReopenPreview; $("reviewReopenNote").oninput = resetReopenPreview; $("reviewReopenPreviewButton").onclick = async () => { try { if (!$("reviewReopenReason").value) throw new Error("اختر سبب إعادة الفتح قبل المعاينة"); const result = await api(`/api/admin/review-workbench/${encodeURIComponent(detail.domain)}/${detail.id}/reopen/preview?version_token=${encodeURIComponent(detail.version_token)}`, { method: "POST" }); detail.reopen_preview = result; $("reviewReopenPreview").innerHTML = `${result.historical_decision_incomplete ? `<strong>${safe(result.historical_notice || "قرار تاريخي — بعض بيانات التدقيق غير متوفرة")}</strong><br>` : ""}<b>الحالة الحالية:</b> ${safe(result.current_status)}<br><b>القرار الأصلي:</b> ${safe(result.original_decision || "غير متوفر في السجل التاريخي")}<br><b>المنفذ الأصلي:</b> ${safe(result.original_actor || "غير متوفر في السجل التاريخي")}<br><b>وقت القرار:</b> ${safe(formatDateTimeLatin(result.original_timestamp) || "غير متوفر في السجل التاريخي")}<br><b>سبب القرار:</b> ${safe(result.original_reason || "غير متوفر في السجل التاريخي")}<br><b>تغيرات الدليل:</b> ${result.current_evidence_changes?.length ? result.current_evidence_changes.map(change => `تغيرت بصمة سجل المصدر ${formatIntegerLatin(change.source_record_id)}`).join("، ") : result.evidence_change_comparison_available ? "لا توجد تغييرات موثقة منذ القرار السابق." : "لا تتوفر لقطة سابقة تسمح بمقارنة الدليل الحالي."}`; $("reviewReopenPreview").hidden = false; $("reviewReopenSubmit").hidden = false; } catch (error) { toast(error.message); } }; $("reviewReopenSubmit").onclick = async () => { try { const reason = $("reviewReopenReason").value; if (!reason) throw new Error("اختر سبب إعادة الفتح"); if (!window.confirm("إعادة فتح المراجعة مع الاحتفاظ بقرارها السابق في سجل التدقيق؟")) return; await api(`/api/admin/review-workbench/${encodeURIComponent(detail.domain)}/${detail.id}/reopen`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason, note: $("reviewReopenNote").value.trim(), version_token: detail.version_token }) }); $("reviewQueueStatus").value = "OPEN"; if(reviewWorkbench.pilotMode){stampPilotMetric("reopen_used",true);beginPilotFeedback("REOPENED_AFTER_DECISION");toast("أُعيد فتح المراجعة وسُجل السبب والتدقيق. أكمل الملاحظات لتوثيقها في الطيار.");}else{toast("أُعيد فتح المراجعة وسُجل السبب والتدقيق.");await loadReview(`${detail.domain}:${detail.id}`);} } catch (error) { toast(error.message); } }; }  const setDirty = () => { reviewWorkbench.dirty = true; reviewWorkbench.preview = null; $("reviewDecisionPreview").hidden = true; $("reviewSubmitButton").disabled = true; };
  $("reviewDecisionReason").onchange = setDirty; $("recommendationOverrideReason").onchange = setDirty; $("reviewDecisionNote").oninput = setDirty;
  document.querySelectorAll("[data-review-action]").forEach(button => button.onclick = () => { reviewWorkbench.selectedAction = button.dataset.reviewAction; document.querySelectorAll("[data-review-action]").forEach(actionButton => actionButton.classList.toggle("is-selected", actionButton === button)); setDirty(); });
  document.querySelectorAll("[data-review-keep-open]").forEach(button => button.onclick = () => { reviewWorkbench.selectedAction = null; reviewWorkbench.preview = null; reviewWorkbench.dirty = false; document.querySelectorAll("[data-review-action]").forEach(actionButton => actionButton.classList.remove("is-selected")); $("reviewDecisionPreview").hidden = true; $("reviewSubmitButton").disabled = true; toast("ستبقى الحالة مفتوحة للمراجعة؛ لم يُرسل أي تغيير."); });
  $("reviewPreviewButton").onclick = async () => {
    try { if (!reviewWorkbench.selectedAction) throw new Error("اختر إجراءً أولًا"); const response = await api(`/api/admin/review-workbench/${encodeURIComponent(detail.domain)}/${detail.id}/preview?action=${encodeURIComponent(reviewWorkbench.selectedAction)}&version_token=${encodeURIComponent(detail.version_token)}`, { method: "POST" }); reviewWorkbench.preview = response; const el = $("reviewDecisionPreview"); el.innerHTML = `<b>أثر القرار</b><ul>${(response.impacts || []).map(impact => `<li>${safe(impact.entity === "canonical_value" ? `القيمة المعيارية: ${valueText(impact.before)} ← ${valueText(impact.after)}` : impact.note || "ستتغير حالة المراجعة إلى محسومة.")}</li>`).join("")}</ul><small>سيُنشأ سجل تدقيق مرتبط بالحالة والقرار والدليل.</small>`; el.hidden = false; $("reviewSubmitButton").disabled = false; } catch (error) { toast(error.message); }
  };
  $("reviewSubmitButton").onclick = async () => {
    try { const reason = $("reviewDecisionReason").value, note = $("reviewDecisionNote").value.trim(), overrideReason = $("recommendationOverrideReason").value; if (!reason) throw new Error("اختر سبب القرار"); if (reviewWorkbench.detail?.recommendation?.action && reviewWorkbench.selectedAction !== reviewWorkbench.detail.recommendation.action && !overrideReason) throw new Error("سبب تجاوز التوصية مطلوب"); if (!reviewWorkbench.preview) throw new Error("عاين أثر القرار قبل التأكيد"); if (!window.confirm("هل تريد حفظ القرار الظاهر في المعاينة؟")) return; const fullNote = note ? `${reason} — ${note}` : reason; const url = detail.domain === "location" ? `/api/admin/location-reviews/${detail.id}/${reviewWorkbench.selectedAction}` : detail.domain === "qualification" ? `/api/admin/qualification-reviews/${detail.id}/${reviewWorkbench.selectedAction}` : detail.domain === "duplicate" ? `/api/admin/duplicates/${detail.id}/${reviewWorkbench.selectedAction}` : `/api/admin/conflicts/${detail.id}/${reviewWorkbench.selectedAction}`; await api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note: fullNote, version_token: detail.version_token, recommendation_version: detail.recommendation_version, recommendation_override_reason: overrideReason || null, analyst_note: note || null }) }); reviewWorkbench.dirty = false; if (reviewWorkbench.pilotMode) { const metrics=reviewWorkbench.pilotMetrics||pilotCaseMetrics(reviewWorkbench.selected), recommendation=detail.recommendation||{}; metrics.decision_submitted_at=new Date().toISOString(); metrics.recommendation_followed=recommendation.action ? reviewWorkbench.selectedAction===recommendation.action : null; metrics.recommendation_overridden=recommendation.action ? reviewWorkbench.selectedAction!==recommendation.action : false; metrics.override_reason=metrics.recommendation_overridden ? (overrideReason||null) : null; savePilotCaseMetrics(reviewWorkbench.selected,metrics); beginPilotFeedback("RESOLVED"); toast("سُجل القرار البشري. أكمل ملاحظات هذه الحالة لمتابعة الطيار."); } else { toast("تم حفظ القرار وتوثيقه. جارٍ فتح الحالة التالية."); const currentIndex = reviewWorkbench.queue.findIndex(item => reviewItemKey(item) === reviewWorkbench.selected); const preferred = reviewWorkbench.queue[currentIndex + 1] || reviewWorkbench.queue[currentIndex - 1]; await loadReview(preferred ? reviewItemKey(preferred) : null); } } catch (error) { toast(error.message); if (error.message.includes("تحديث هذه الحالة") || error.message.includes("تغيرت التوصية")) loadReviewDetail(reviewWorkbench.selected); }
  };
  const index = reviewWorkbench.queue.findIndex(item => reviewItemKey(item) === reviewWorkbench.selected);
  $("reviewPrevious").onclick = () => moveReview(index - 1); $("reviewNext").onclick = () => moveReview(index + 1); $("reviewBackToQueue").onclick = () => { if (!reviewWorkbench.dirty || window.confirm("لديك قرار غير محفوظ. هل تريد تركه؟")) { reviewWorkbench.dirty = false; $("reviewQueueList").scrollIntoView({ behavior: "smooth", block: "start" }); } };
}
async function loadReviewDetail(key) {
  const item = reviewWorkbench.queue.find(row => reviewItemKey(row) === key); if (!item) return;
  reviewWorkbench.selected = key; reviewWorkbench.selectedAction = null; reviewWorkbench.preview = null; reviewWorkbench.dirty = false; renderReviewQueue();
  if(reviewWorkbench.pilotMode){reviewWorkbench.pilotMetrics=pilotCaseMetrics(key);savePilotCaseMetrics(key,reviewWorkbench.pilotMetrics);$("pilotFeedbackPanel").hidden=true;}
  $("reviewDecisionPanel").innerHTML = '<div class="loading">جارٍ تحميل تفاصيل المراجعة والأدلة…</div>';
  if(item.pilot_unavailable){$("reviewDecisionPanel").innerHTML='<div class="review-empty-state">هذه الحالة من العينة الثابتة لكنها غير متاحة حاليًا. لم يتم استبدالها.</div>';return;}
  try { reviewWorkbench.detail = await api(`/api/admin/review-workbench/${encodeURIComponent(item.domain)}/${item.id}`); renderWorkbenchDetail(reviewWorkbench.detail); const pending=JSON.parse(localStorage.getItem(pilotPendingStorageKey)||"null"); if(reviewWorkbench.pilotMode&&pending?.review_id_key===key)beginPilotFeedback(pending.outcome,pending.reason); } catch (error) { $("reviewDecisionPanel").innerHTML = `<div class="review-empty-state">تعذر تحميل تفاصيل المراجعة: ${safe(error.message)}</div>`; }
}
function moveReview(index) { if (reviewWorkbench.dirty && !window.confirm("لديك قرار غير محفوظ. هل تريد الانتقال؟")) return; const item = reviewWorkbench.queue[index]; if (item) loadReviewDetail(reviewItemKey(item)); }
window.addEventListener("beforeunload", event => { if (reviewWorkbench.dirty) { event.preventDefault(); event.returnValue = ""; } });
window.addEventListener("keydown", event => { if (!$("view-review")?.classList.contains("active") || event.altKey || event.ctrlKey || event.metaKey) return; if (event.target.matches("input,textarea,select,button")) return; const index = reviewWorkbench.queue.findIndex(item => reviewItemKey(item) === reviewWorkbench.selected); if (event.key === "ArrowDown") { event.preventDefault(); moveReview(index + 1); } else if (event.key === "ArrowUp") { event.preventDefault(); moveReview(index - 1); } });
async function loadReview(selectedKey = reviewWorkbench.selected) {
  try {
    if (reviewWorkbench.dirty && !window.confirm("لديك قرار غير محفوظ. هل تريد تركه؟")) return;
    reviewWorkbench.dirty = false;
    if (reviewWorkbench.pilotMode) { reviewWorkbench.pilot=await api("/api/admin/review-workbench/pilot"); }
    const queueStatus = reviewWorkbench.pilotMode ? "ALL" : ($("reviewQueueStatus")?.value || "OPEN");
    if (queueStatus !== "OPEN") { reviewWorkbench.batchSelection.clear(); reviewWorkbench.batchPreview = null; }
    const params = new URLSearchParams({ status: queueStatus, domain: reviewWorkbench.pilotMode ? "all" : ($("reviewDomain")?.value || "all"), limit: "1000" });
    const priority = $("reviewPriority")?.value, source = $("reviewSource")?.value, disposition = $("reviewDisposition")?.value || "ACTIONABLE", minAge = $("reviewAgeMin")?.value, maxAge = $("reviewAgeMax")?.value, masterStatus = $("reviewMasterStatus")?.value, evidenceStatus = $("reviewEvidenceStatus")?.value;
    if (priority) params.set("priority", priority); if (source) params.set("source_filter", source); if (minAge) params.set("min_age", minAge); if (maxAge) params.set("max_age", maxAge); if (masterStatus) params.set("master_status", masterStatus); if (evidenceStatus) params.set("evidence_status", evidenceStatus); params.set("exclude_source_recheck", "true"); if (disposition === "SOURCE_RECHECK_REQUIRED") { params.delete("exclude_source_recheck"); params.set("disposition", disposition); } else if (disposition === "ALL") { params.delete("exclude_source_recheck"); params.set("disposition", "ALL"); }
    const [all, validation, operational] = await Promise.all([api("/api/admin/review-queue?status=OPEN&limit=1000"), api("/api/admin/validation-report"), api("/api/admin/review-workbench/metrics")]);
    const open = all.filter(item => item.status === "OPEN"), actionable = open.filter(item => item.disposition !== "SOURCE_RECHECK_REQUIRED"); let result = await api(`/api/admin/review-queue?${params}`);
    if(reviewWorkbench.pilotMode){const phase=reviewWorkbench.pilot?.current_phase||reviewWorkbench.pilot?.active_phase||"A",completed=new Set(reviewWorkbench.pilot?.completed_case_keys||[]);result=(reviewWorkbench.pilot?.cases||[]).filter(entry=>entry.phase===phase).map(entry=>entry.current?{...entry.current,pilot_sequence:entry.pilot_sequence,pilot_phase_sequence:entry.phase_sequence,pilot_phase:entry.phase,pilot_completed:completed.has(entry.review_id_key)}:{domain:entry.type,id:entry.review_id,title:`الحالة غير متاحة · ${entry.review_id_key}`,status:"UNAVAILABLE",disposition:"UNAVAILABLE",priority:"—",master_ids:[],pilot_sequence:entry.pilot_sequence,pilot_phase_sequence:entry.phase_sequence,pilot_phase:entry.phase,pilot_unavailable:true});}
    reviewWorkbench.queue = result; const completed=new Set(reviewWorkbench.pilot?.completed_case_keys||[]),chosen = result.find(item => reviewItemKey(item) === selectedKey) || result.find(item=>!completed.has(reviewItemKey(item))&&!item.pilot_unavailable) || (reviewWorkbench.pilotMode?undefined:result[0]);
    $("reviewOpenTotal").textContent = formatIntegerLatin(open.length); $("reviewCountOpen").textContent = formatIntegerLatin(open.length); $("reviewCountHuman").textContent = formatIntegerLatin(actionable.length); $("reviewCountRecheck").textContent = formatIntegerLatin(open.length - actionable.length);
    for (const level of ["P1", "P2", "P3", "P4"]) $(`reviewCount${level}`).textContent = formatIntegerLatin(actionable.filter(item => item.priority === level).length);
    const sourceSelect = $("reviewSource"), priorSource = sourceSelect.value, sourceOptions = [...new Map(open.filter(item => item.source).map(item => [item.source, item.source])).values()]; sourceSelect.innerHTML = '<option value="">كل المصادر</option>' + sourceOptions.map(value => `<option value="${safe(value)}">${safe(value)}</option>`).join(""); if (sourceOptions.includes(priorSource)) sourceSelect.value = priorSource;
    for(const id of ["reviewPriority","reviewDomain","reviewQueueStatus","reviewSource","reviewDisposition","reviewAgeMin","reviewAgeMax","reviewMasterStatus","reviewEvidenceStatus"])if($(id))$(id).disabled=reviewWorkbench.pilotMode;
    renderReviewQueue();
    if (chosen) await loadReviewDetail(reviewItemKey(chosen)); else { reviewWorkbench.selected = null; reviewWorkbench.detail = null; $("reviewDecisionPanel").innerHTML = reviewWorkbench.pilotMode?'<div class="review-empty-state">اكتملت حالات المرحلة الحالية أو لا تتوفر حالة متاحة. راجع النتائج قبل الانتقال.</div>':'<div class="review-empty-state">لا توجد حالات تطابق المرشحات.</div>'; $("reviewEvidencePanel").innerHTML = '<div class="review-empty-state">ستظهر الأدلة بعد اختيار حالة.</div>'; }
    const gates = validation.gates || validation.results || []; const metrics = Array.isArray(gates) ? gates : Object.entries(gates).map(([key,value]) => ({ key, ...value })); $("validationMetrics").innerHTML = metrics.slice(0, 12).map(item => `<div class="validation-metric"><span>${safe(item.gate_key || item.key || item.name || "فحص")}</span><b>${safe(item.status || "—")}</b></div>`).join("");
    $("reviewOperationalMetrics").innerHTML = [["المراجعات المحسومة خلال 30 يومًا",formatIntegerLatin(operational.resolved_last_30_days)], ["متوسط زمن المعالجة",operational.average_handling_seconds == null ? "غير متاح" : `${formatNumberLatin(operational.average_handling_seconds / 3600)} ساعة`], ["الوسيط الزمني للمعالجة",operational.median_handling_seconds == null ? "غير متاح" : `${formatNumberLatin(operational.median_handling_seconds / 3600)} ساعة`], ["معدل قبول التوصيات",operational.recommendation_acceptance_rate == null ? "لا توجد بيانات توصية" : formatPercentLatin(operational.recommendation_acceptance_rate * 100)], ["معدل تجاوز التوصية",operational.recommendation_override_rate == null ? "لا توجد بيانات توصية" : formatPercentLatin(operational.recommendation_override_rate * 100)], ["الرصيد حسب الأولوية",Object.entries(operational.backlog_by_priority || {}).map(([key,value]) => `${key}: ${formatIntegerLatin(value)}`).join(" · ")]].map(([label,value]) => `<div class="validation-metric"><span>${safe(label)}</span><b>${safe(value)}</b></div>`).join("");
    $("reviewPriority").onchange = () => loadReview(null); $("reviewSource").onchange = () => loadReview(null); $("reviewDisposition").onchange = () => loadReview(null); $("reviewAgeMin").onchange = () => loadReview(null); $("reviewAgeMax").onchange = () => loadReview(null); $("reviewDomain").onchange = () => loadReview(null); $("reviewMasterStatus").onchange = () => loadReview(null); $("reviewEvidenceStatus").onchange = () => loadReview(null); $("reviewQueueStatus").onchange = () => loadReview(null);
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
    const [system, schedules, users, dq] = await Promise.all([api("/api/admin/system-status"), api("/api/admin/schedules"), api("/api/admin/users"), api("/api/admin/data-quality/latest")]);
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
    const dqStatus = dq.status || (dq.counts?.fail ? "FAIL" : dq.counts?.warning ? "WARNING" : "PASS");
    const dqStatusLabel = ({ PASS: "سليم", WARNING: "تحذيرات", FAIL: "إخفاق", NOT_RUN: "لم يُشغّل" })[dqStatus] || dqStatus;
    $("dqRunMeta").textContent = dq.completed_at ? `آخر تشغيل: ${date(dq.completed_at)} · النطاق: ${safe(dq.scope || "—")}` : "لم يُسجّل فحص بعد.";
    $("dqStatusSummary").innerHTML = [["الحالة",dqStatusLabel],["ناجحة",dq.counts?.pass ?? 0],["تحذيرات",dq.counts?.warning ?? 0],["إخفاقات",dq.counts?.fail ?? 0]].map(([label,value]) => `<div class="admin-metric"><span>${safe(label)}</span><b>${safe(value)}</b></div>`).join("");
    const dqFailures = [...(dq.failed_gates || []), ...(dq.warning_gates || [])];
    $("dqFailureDetails").innerHTML = dqFailures.length ? `<details><summary>تفاصيل الحالات (${dqFailures.length.toLocaleString("en-US-u-nu-latn")})</summary>${dqFailures.map(gate => `<div class="dq-failure ${gate.status === "FAIL" ? "is-fail" : "is-warning"}"><b>${safe(gate.gate_key)}</b><span>${safe(gate.domain)} · ${safe(gate.status)}</span><small>${safe(gate.message || "")}</small>${gate.sample_ids?.length ? `<small>معرّفات: ${safe(gate.sample_ids.join("، "))}</small>` : ""}</div>`).join("")}</details>` : '<p class="dq-clear">لا توجد إخفاقات أو تحذيرات في آخر تشغيل.</p>';
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
  $("modalBody").innerHTML = `<div class="detail-head"><div class="eyebrow">${safe(item.canonical_id)}</div><h2 id="modalTitle">${safe(item.title)}</h2><p>الجهة المالكة: ${safe(item.owner || "غير محددة")} · الحالة الموحدة: ${safe(statusLabel(item.status))}</p></div><div class="detail-grid">${[["القطاع", item.sector], ["النشاط", item.activity], ["النشاط الفرعي", item.sub_activity], ["نوع الفرصة", item.type], ["نموذج الاستثمار", item.investment_model], ["نوع الأصل أو الموقع", item.asset_facility_type || "غير محدد"], ["الدولة", item.geography?.country], ["المنطقة", item.geography?.region], ["المحافظة", item.geography?.governorate], ["المدينة / الموقع", item.geography?.locality || (item.geography?.confirmed ? item.geography?.governorate : item.geography?.status_ar)], ["الحي", item.geography?.district], ["حالة الموقع الجغرافي", item.geography?.status_ar], ["سبب المراجعة", item.geography?.reason], ["وصف الموقع", item.location], ["المساحة", item.area !== null && item.area !== undefined ? Number(item.area).toLocaleString("en-US") + " " + (item.area_unit || "م²") : null], ["القيمة الاستثمارية", item.investment_value !== null && item.investment_value !== undefined ? Number(item.investment_value).toLocaleString("en-US") + (item.currency ? " " + item.currency : "") : null], ["مدة العقد", item.duration !== null && item.duration !== undefined ? item.duration + " " + (item.duration_unit === "year" ? "سنة" : item.duration_unit) : null], ["آخر موعد للتقديم", item.deadline || "غير محدد"], ["الرقم المرجعي", item.reference], ["مستوى ثقة الموقع", Math.round((item.confidence || 0) * 100) + "٪"], ["عدد المصادر", item.source_count]].map(([label, value]) => `<div class="detail-field"><small>${label}</small><b>${safe(value === null || value === undefined || value === "" ? "غير منشور" : value)}</b></div>`).join("")}</div><div class="detail-sources"><h3>النشر حسب المصدر</h3>${(item.sources || []).map(source => `<article>${sourceAnnouncementMarkup(source)}<small class="source-location-evidence">جهة النشر: ${safe(source.publishing_entity || "غير محددة في سجل المصدر")} · مشغل المنصة: ${safe(source.source_operator || "غير محدد")}</small>${source.source_external_id ? `<small class="source-location-evidence">معرّف المصدر التقني: ${safe(source.source_external_id)}</small>` : ""}<small class="source-location-evidence">الحالة المعيارية: ${safe(statusLabel(source.canonical_status))} · النص الخام: ${safe(source.raw_status || "غير محدد")}</small>${source.status_review_flags?.length ? `<small class="source-location-evidence">تنبيه مراجعة: ${safe(source.status_review_flags.join("، "))}</small>` : ""}${source.raw_location ? `<small class="source-location-evidence">الموقع كما ورد: ${safe(source.raw_location)}</small>` : ""}</article>`).join("") || "—"}</div><div class="detail-changes"><h3>سجل التغييرات</h3>${item.changes?.length ? item.changes.map(change => `<p>${safe(change.field)}: ${safe(change.before || "—")} ← ${safe(change.after || "—")} · ${date(change.date)}</p>`).join("") : "<p>لا توجد تغييرات مسجلة.</p>"}</div>`;
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
  if (state.tableGeo?.enabled) for (const [key, value] of Object.entries(state.tableGeo.read())) if (value) params.set(key, value);
  if (state.sortBy) { params.set("sort_by", state.sortBy); params.set("sort_order", state.sortOrder); }
  for (const key of ["period","deadline_after","deadline_before","deadline_status","created_after","created_before","map_ids"]) { const value = new URLSearchParams(location.search).get(key); if (value) params.set(key,value); }
  if (!state.tableGeo?.enabled) for (const key of ["region_id","governorate_id","city_id","geographic_scope"]) { const value = new URLSearchParams(location.search).get(key); if (value) params.set(key,value); }
  const q = $("searchInput").value; if (q) params.set("q",q);
  history.replaceState(null,"",`${location.pathname}?${params.toString()}`);
}
["sectorFilter","activityFilter","subActivityFilter","subsectorFilter","statusFilter","lifecycleFilter","ownerFilter","sourceFilter","locationFilter","typeFilter","investmentModelFilter","assetFacilityTypeFilter"].forEach(id => $(id).addEventListener("change", () => { state.opportunityPage = 0; updateOpportunityUrl(); loadOpportunities(); }));
document.querySelectorAll("#view-opportunities [data-sort-key]").forEach(button => button.addEventListener("click", () => {
  const key=button.dataset.sortKey;
  state.sortOrder=state.sortBy===key?(state.sortOrder==="asc"?"desc":"asc"):"asc";
  state.sortBy=key; state.opportunityPage=0; updateOpportunityUrl(); loadOpportunities();
  document.querySelectorAll("#view-opportunities th[data-column]").forEach(th=>th.removeAttribute("aria-sort"));
  button.closest("th")?.setAttribute("aria-sort",state.sortOrder==="asc"?"ascending":"descending");
  button.setAttribute("aria-label",`${button.dataset.sortLabel} · ${state.sortOrder==="asc"?"تصاعدي":"تنازلي"}`);
  button.textContent=`${button.dataset.sortLabel} ${state.sortOrder==="asc"?"↑":"↓"}`;
}));
$("previousPage").onclick = () => { if (state.opportunityPage > 0) { state.opportunityPage--; loadOpportunities(); } };
$("nextPage").onclick = () => { state.opportunityPage++; loadOpportunities(); };
$("resetFilters").onclick = async () => { $("searchInput").value = ""; for (const id of ["sectorFilter","activityFilter","subActivityFilter","subsectorFilter","statusFilter","lifecycleFilter","ownerFilter","sourceFilter","locationFilter","typeFilter","investmentModelFilter","assetFacilityTypeFilter"]) $(id).value = ""; if (state.tableGeo?.enabled) await state.tableGeo.reset(); state.sortBy="";state.sortOrder="desc";document.querySelectorAll("#view-opportunities [data-sort-key]").forEach(button=>button.textContent=button.dataset.sortLabel);document.querySelectorAll("#view-opportunities th[data-column]").forEach(th=>th.removeAttribute("aria-sort"));state.opportunityPage = 0; state.opportunityFiltersInitialized = true; history.replaceState(null,"",`${location.pathname}?view=opportunities`); loadOpportunities(); };
$("alertStatus").onchange = loadAlerts; $("adminRefresh").onclick = loadAdmin;
$("dqRunNow").onclick = async () => { const button=$("dqRunNow");button.disabled=true;button.textContent="جارٍ الفحص…";try{await api("/api/admin/data-quality/run?scope=full",{method:"POST"});toast("اكتمل فحص جودة البيانات");await loadAdmin();}catch(error){toast(error.message);}finally{button.disabled=false;button.textContent="تشغيل فحص كامل";} };
document.querySelectorAll("[data-operation]").forEach(button => button.onclick = async () => { const action = button.dataset.operation; if (!window.confirm(action === "pause-schedules" ? "إيقاف جداول المزامنة لجميع المصادر؟" : "استئناف جداول المزامنة لجميع المصادر؟")) return; try { await api(`/api/admin/operations/${action}`, { method: "POST" }); toast("تم تحديث حالة الجداول"); loadAdmin(); } catch (error) { toast(error.message); } });
$("userCreateForm").onsubmit = async event => { event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget).entries()); try { await api("/api/admin/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); event.currentTarget.reset(); toast("تم إنشاء المستخدم"); loadAdmin(); } catch (error) { toast(error.message); } };
$("refreshBtn").onclick = () => { loadDashboard(); if (state.view === "data-dashboard") loadDataDashboard(); toast("تم تحديث لوحة المؤشرات"); };
["syncAll", "syncAll2", "syncAll3", "firstSync"].forEach(id => { if ($(id)) $(id).onclick = syncAll; });
$("alertStatus").value = "OPEN";
$("loginDialog").addEventListener("click", event => { if (event.target === $("loginDialog")) $("loginDialog").close(); });
async function changeSourceInterval(button) { const value = Number(window.prompt("الفاصل بالدقائق", button.dataset.currentInterval)); if (!Number.isInteger(value) || value < 15 || value > 10080) return; if (!window.confirm("تأكيد تحديث جدول هذا المصدر؟")) return; try { await api(`/api/admin/sources/${encodeURIComponent(button.dataset.interval)}?interval_minutes=${value}&confirm=true`, { method: "PATCH" }); toast("تم تحديث الجدول"); await loadSources(); } catch (error) { toast(error.message); } }
async function initialize() {
  initializePilotControls();
  try { const response = await fetch("/api/auth/me", { credentials: "same-origin" }); if (response.ok) state.user = (await response.json()).user; } catch {}
  setUserLabel(); applyRoleVisibility();
  ["syncAll", "syncAll2", "syncAll3", "firstSync"].forEach(id => { if ($(id)) $(id).onclick = syncAll; });
  const initialView = new URLSearchParams(location.search).get("view");
  if (initialView && $("view-" + initialView)) view(initialView);
  else if (!initialView) await loadDashboard();
}
initialize();





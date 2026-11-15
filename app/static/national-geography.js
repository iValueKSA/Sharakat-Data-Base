/* Canonical Region -> Governorate selectors shared by the list and dashboard. */
(() => {
  const get = id => document.getElementById(id);
  const escape = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
  const placeKey = value => String(value || "").normalize("NFKC").replace(/[أإآٱ]/g, "ا").replace(/ى/g, "ي").replace(/\s+/g, " ").trim();
  const cleanName = value => {
    const cleaned = String(value || "").replace(/^إمارة\s+منطقة\s+/u, "").replace(/^منطقة\s+/u, "").replace(/^محافظة\s+/u, "").trim();
    return cleaned === "الشرقية" ? "المنطقة الشرقية" : cleaned;
  };
  const option = (value, label) => `<option value="${escape(value)}">${escape(label)}</option>`;
  async function json(url) {
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) throw new Error("تعذر تحميل خيارات المرجع الجغرافي.");
    return response.json();
  }
  async function init(prefix, onChange) {
    const panel = get(`${prefix}NationalGeoFilters`);
    const region = get(`${prefix}RegionFilter`), governorate = get(`${prefix}GovernorateFilter`);
    const city = get(prefix === "table" ? "locationFilter" : "dashLocation");
    if (!panel || !region || !governorate || !city) return { enabled: false };
    try {
      const catalog = await json("/api/geography/catalog");
      if (catalog.reference_ready !== true) { region.disabled = true; governorate.disabled = true; return { enabled: false }; }
      const options = await json("/api/geography/filter-options");
      const regions = [...(options.regions || [])].sort((a, b) => {
        const ai = Number(a.id), bi = Number(b.id);
        return Number.isFinite(ai) && Number.isFinite(bi) ? ai - bi : String(a.id).localeCompare(String(b.id));
      });
      const governorates = (options.governorates || []).filter(item => Number(item.unique_masters) > 0);
      const regionsById = new Map(regions.map(item => [String(item.id), item]));
      const governoratesByRegion = new Map();
      for (const item of governorates) {
        const parentId = String(item.parent_id || "");
        if (!governoratesByRegion.has(parentId)) governoratesByRegion.set(parentId, []);
        governoratesByRegion.get(parentId).push(item);
      }
      const ahsa = governorates.find(item => placeKey(cleanName(item.display_name_ar || item.name_ar)) === placeKey("الأحساء"));
      const cityOptions = [...city.options].slice(1).map(item => ({ id: item.value, label: item.textContent }));
      const params = new URLSearchParams(location.search);
      region.innerHTML = option("", "جميع المناطق") + regions.map(item => option(item.id, cleanName(item.display_name_ar || item.name_ar))).join("");
      const initialRegion = params.get("region_id") || "";
      const initialGovernorate = params.get("governorate_id") || "";
      if (regions.some(item => String(item.id) === initialRegion)) region.value = initialRegion;
      function updateGovernorates(selected = "") {
        const regionId = String(region.value || "");
        const choices = regionsById.has(regionId) ? (governoratesByRegion.get(regionId) || []) : [];
        governorate.innerHTML = option("", "جميع المحافظات") + choices.map(item => option(item.id, cleanName(item.display_name_ar || item.name_ar))).join("");
        const selectedIsValid = choices.some(item => String(item.id) === String(selected));
        governorate.value = selectedIsValid ? String(selected) : "";
        const unavailable = !regionId || !regionsById.has(regionId) || choices.length === 0;
        governorate.disabled = unavailable;
        governorate.setAttribute("aria-disabled", String(unavailable));
        return choices;
      }
      function updateCities(selected = "") {
        const available = ahsa && governorate.value === String(ahsa.id) ? cityOptions : [];
        city.innerHTML = option("", "جميع المدن") + available.map(item => option(item.id, item.label)).join("");
        city.disabled = available.length === 0;
        if (available.some(item => item.id === selected)) city.value = selected;
      }
      updateGovernorates(initialGovernorate);
      updateCities(params.get("location") || "");
      panel.hidden = false;
      region.addEventListener("change", () => {
        updateGovernorates();
        updateCities();
        onChange();
      });
      governorate.addEventListener("change", () => { updateCities(); onChange(); });
      city.addEventListener("change", onChange);
      return {
        enabled: true,
        read: () => ({ region_id: region.value, governorate_id: governorate.value }),
        selectedLabel: () => region.value ? (region.selectedOptions[0]?.textContent || "") : "",
        selectedGovernorateLabel: () => governorate.value ? (governorate.selectedOptions[0]?.textContent || "") : "",
        async reset() { region.value = ""; updateGovernorates(); updateCities(); }
      };
    } catch {
      region.disabled = true; governorate.disabled = true;
      return { enabled: false };
    }
  }
  window.NationalGeographyUI = { init };
})();
